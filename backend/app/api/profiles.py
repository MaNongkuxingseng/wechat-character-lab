from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ImportedMessage, ProfileTrait, ProfileVersion, Role, Source
from app.profiles.service import approve_version, create_draft
from app.repositories.profiles import get_version, list_evidence, list_traits, list_versions
from app.schemas.profile import (
    EvidenceRead,
    ProfileVersionRead,
    ProfileVersionSummary,
    TraitRead,
    TraitReviewRequest,
)

router = APIRouter(prefix="/api/roles/{role_id}/profiles", tags=["profiles"])


@router.post("/analyze", response_model=ProfileVersionRead, status_code=201)
def analyze_role_profile(role_id: str, db: Session = Depends(get_db)) -> ProfileVersionRead:
    """基于已审核且映射到该角色的消息生成可解释统计草稿。"""
    _require_role(db, role_id)
    try:
        version = create_draft(db, role_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "insufficient_samples", "message": str(exc)},
        ) from exc
    return _version_read(db, version)


@router.get("", response_model=list[ProfileVersionSummary])
def get_role_profiles(role_id: str, db: Session = Depends(get_db)) -> list[ProfileVersionSummary]:
    """列出角色的草稿、当前画像和历史版本。"""
    _require_role(db, role_id)
    return [ProfileVersionSummary.model_validate(version) for version in list_versions(db, role_id)]


@router.get("/{version_id}", response_model=ProfileVersionRead)
def get_role_profile(
    role_id: str,
    version_id: str,
    db: Session = Depends(get_db),
) -> ProfileVersionRead:
    """读取画像版本及其证据摘录。"""
    version = _get_version_or_404(db, role_id, version_id)
    return _version_read(db, version)


@router.post("/{version_id}/traits/{trait_id}/review", response_model=TraitRead)
def review_profile_trait(
    role_id: str,
    version_id: str,
    trait_id: str,
    payload: TraitReviewRequest,
    db: Session = Depends(get_db),
) -> TraitRead:
    """审核或修订一项草稿特征；已发布版本不可原地修改。"""
    version = _get_version_or_404(db, role_id, version_id)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "profile_not_editable"})
    trait = db.scalar(
        select(ProfileTrait).where(
            ProfileTrait.id == trait_id,
            ProfileTrait.profile_version_id == version.id,
        )
    )
    if trait is None:
        raise HTTPException(status_code=404, detail={"code": "trait_not_found"})
    trait.review_status = payload.status
    trait.reviewer_note = payload.reviewer_note
    if payload.description is not None:
        trait.description = payload.description
    if payload.context is not None:
        trait.context = payload.context
    db.commit()
    db.refresh(trait)
    return _trait_read(db, version, trait)


@router.post("/{version_id}/publish", response_model=ProfileVersionRead)
def publish_profile(
    role_id: str,
    version_id: str,
    db: Session = Depends(get_db),
) -> ProfileVersionRead:
    """发布已逐项审核的画像版本，并将上一版标记为历史版本。"""
    version = _get_version_or_404(db, role_id, version_id)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "profile_not_draft"})
    try:
        approve_version(db, version)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "profile_review_incomplete", "message": str(exc)},
        ) from exc
    db.refresh(version)
    return _version_read(db, version)


def _require_role(db: Session, role_id: str) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "role_not_found"})
    return role


def _get_version_or_404(db: Session, role_id: str, version_id: str) -> ProfileVersion:
    _require_role(db, role_id)
    version = get_version(db, role_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail={"code": "profile_version_not_found"})
    return version


def _version_read(db: Session, version: ProfileVersion) -> ProfileVersionRead:
    return ProfileVersionRead(
        id=version.id,
        role_id=version.role_id,
        version=version.version,
        status=version.status,
        analyzer=version.analyzer,
        sample_count=version.sample_count,
        created_at=version.created_at,
        approved_at=version.approved_at,
        traits=[_trait_read(db, version, trait) for trait in list_traits(db, version.id)],
    )


def _trait_read(db: Session, version: ProfileVersion, trait: ProfileTrait) -> TraitRead:
    evidence_reads: list[EvidenceRead] = []
    for evidence in list_evidence(db, trait.id):
        message = db.scalar(
            select(ImportedMessage)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                ImportedMessage.id == evidence.message_id,
                ImportedMessage.speaker_role_id == version.role_id,
                Source.status == "approved",
            )
        )
        if message is None:
            continue
        evidence_reads.append(
            EvidenceRead(
                message_id=message.id,
                speaker_label=message.speaker_label,
                sent_at=message.sent_at,
                excerpt=message.text[:240],
                rationale=evidence.rationale,
            )
        )
    return TraitRead(
        id=trait.id,
        category=trait.category,
        key=trait.trait_key,
        description=trait.description,
        confidence=trait.confidence,
        confidence_source=trait.confidence_source,
        context=trait.context,
        review_status=trait.review_status,
        reviewer_note=trait.reviewer_note,
        evidence=evidence_reads,
    )
