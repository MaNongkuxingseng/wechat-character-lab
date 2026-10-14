from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportedMessage, ProfileEvidence, ProfileTrait, ProfileVersion, Source
from app.profiles.analyzer import ObservableTextAnalyzer

ANALYZER = ObservableTextAnalyzer()


def create_draft(db: Session, role_id: str) -> ProfileVersion:
    """仅用已审核且映射给目标角色的消息创建新的独立草稿版本。"""
    messages = list(
        db.scalars(
            select(ImportedMessage)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                Source.status == "approved",
                ImportedMessage.speaker_role_id == role_id,
            )
            .order_by(ImportedMessage.sent_at, ImportedMessage.id)
            .limit(ANALYZER.maximum_sample_count)
        )
    )
    drafts = ANALYZER.analyze(messages)
    latest_version = db.scalar(
        select(func.max(ProfileVersion.version)).where(ProfileVersion.role_id == role_id)
    )
    version = ProfileVersion(
        id=str(uuid4()),
        role_id=role_id,
        version=(latest_version or 0) + 1,
        status="draft",
        analyzer=ANALYZER.name,
        sample_count=min(len(messages), ANALYZER.maximum_sample_count),
        created_at=datetime.now(UTC),
    )
    db.add(version)
    db.flush()

    for draft in drafts:
        trait = ProfileTrait(
            id=str(uuid4()),
            profile_version_id=version.id,
            category=draft.category,
            trait_key=draft.key,
            description=draft.description,
            confidence=draft.confidence,
            context=None,
            review_status="pending",
        )
        db.add(trait)
        db.flush()
        for message_id in draft.message_ids:
            db.add(
                ProfileEvidence(
                    id=str(uuid4()),
                    trait_id=trait.id,
                    message_id=message_id,
                    rationale=draft.rationale,
                )
            )
    db.commit()
    db.refresh(version)
    return version


def approve_version(db: Session, version: ProfileVersion) -> None:
    """发布已逐项处理且至少有一条接受特征的画像版本。"""
    traits = list(
        db.scalars(select(ProfileTrait).where(ProfileTrait.profile_version_id == version.id))
    )
    if not traits or any(trait.review_status == "pending" for trait in traits):
        raise ValueError("发布前必须逐项审核所有画像特征")
    if not any(trait.review_status == "accepted" for trait in traits):
        raise ValueError("至少接受一项画像特征后才能发布")
    for trait in traits:
        if trait.review_status != "accepted":
            continue
        valid_evidence = db.scalar(
            select(ProfileEvidence.id)
            .join(ImportedMessage, ImportedMessage.id == ProfileEvidence.message_id)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                ProfileEvidence.trait_id == trait.id,
                ImportedMessage.speaker_role_id == version.role_id,
                Source.status == "approved",
            )
            .limit(1)
        )
        if valid_evidence is None:
            raise ValueError("每项接受的特征都必须保留至少一条有效来源证据")
    current_versions = list(
        db.scalars(
            select(ProfileVersion).where(
                ProfileVersion.role_id == version.role_id,
                ProfileVersion.status == "approved",
            )
        )
    )
    for current in current_versions:
        current.status = "superseded"
    version.status = "approved"
    version.approved_at = datetime.now(UTC)
    db.commit()
