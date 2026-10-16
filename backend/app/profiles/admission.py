"""Explicit admission from reviewed candidates into the formal profile layer."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ImportedMessage,
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileEvidence,
    ProfileTrait,
    ProfileVersion,
    Source,
)


class AdmissionError(ValueError):
    """Candidate failed a formal profile admission rule."""


def admit_candidate_item(db: Session, candidate_id: str) -> ProfileVersion:
    item = db.scalar(
        select(ProfileCandidateItem)
        .where(ProfileCandidateItem.id == candidate_id)
        .with_for_update()
    )
    if item is None:
        raise LookupError("candidate_not_found")
    existing = db.scalar(
        select(ProfileVersion).where(ProfileVersion.source_candidate_item_id == item.id)
    )
    if existing is not None:
        return existing
    if item.review_status != "accepted":
        raise AdmissionError("candidate_must_be_accepted")
    if item.cognitive_state == "unknown":
        raise AdmissionError("unknown_cognitive_state")
    if item.confidence is None:
        raise AdmissionError("confidence_required_for_formal_profile")
    if item.conflict_status != "none":
        raise AdmissionError("conflicting_evidence_requires_review")
    if item.cognitive_state == "model_inferred" and not (item.inference_basis or "").strip():
        raise AdmissionError("inference_basis_required")

    evidence = list(
        db.scalars(
            select(ProfileCandidateEvidence)
            .where(ProfileCandidateEvidence.candidate_id == item.id)
            .order_by(ProfileCandidateEvidence.source_message_id)
        )
    )
    supporting = [row for row in evidence if row.direction == "supporting"]
    if any(row.direction == "counter" for row in evidence):
        raise AdmissionError("counter_evidence_not_supported_by_formal_model")
    valid_supporting = [row for row in supporting if row.match_status == "matched"]
    if not valid_supporting:
        raise AdmissionError("matched_supporting_evidence_required")
    for row in valid_supporting:
        message = db.scalar(
            select(ImportedMessage)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                ImportedMessage.id == row.imported_message_id,
                ImportedMessage.speaker_role_id == item.subject_id,
                Source.status == "approved",
            )
        )
        if message is None:
            raise AdmissionError("evidence_source_not_approved_or_role_mismatch")

    now = datetime.now(UTC)
    latest = db.scalar(
        select(func.max(ProfileVersion.version)).where(ProfileVersion.role_id == item.subject_id)
    )
    version = ProfileVersion(
        id=str(uuid4()),
        role_id=item.subject_id,
        version=(latest or 0) + 1,
        source_candidate_item_id=item.id,
        status="draft",
        analyzer=f"candidate:{item.analyzer_name}@{item.analyzer_version}",
        sample_count=len(valid_supporting),
        created_at=now,
    )
    db.add(version)
    db.flush()
    trait = ProfileTrait(
        id=str(uuid4()),
        profile_version_id=version.id,
        category=item.category,
        trait_key=item.profile_item_id,
        description=item.claim,
        confidence=item.confidence,
        cognitive_state=item.cognitive_state,
        inference_basis=item.inference_basis,
        conflict_status=item.conflict_status,
        context=None,
        review_status="pending",
        reviewer_note=item.reviewer_note,
        created_at=now,
    )
    db.add(trait)
    db.flush()
    for row in valid_supporting:
        db.add(
            ProfileEvidence(
                id=str(uuid4()),
                trait_id=trait.id,
                message_id=row.imported_message_id,
                rationale=row.rationale,
            )
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    return version
