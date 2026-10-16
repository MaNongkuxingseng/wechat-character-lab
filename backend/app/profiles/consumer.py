"""Read-only profile context service for future conversation agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ImportedMessage,
    ProfileEvidence,
    ProfileTrait,
    ProfileVersion,
    SessionEvent,
    Source,
)


@dataclass(frozen=True)
class ProfileFeatureContext:
    trait_id: str
    category: str
    claim: str
    cognitive_state: str
    confidence: float | None
    evidence_refs: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class RoleProfileContext:
    role_id: str
    status: str
    readiness: str
    profile_version_id: str | None
    features: tuple[ProfileFeatureContext, ...]
    usage: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "role_id": self.role_id,
            "status": self.status,
            "readiness": self.readiness,
            "profile_version_id": self.profile_version_id,
            "features": [asdict(item) for item in self.features],
            "usage": self.usage,
        }


def build_role_context(
    db: Session,
    role_id: str,
    *,
    topic: str | None = None,
    session_id: str | None = None,
) -> RoleProfileContext:
    version = db.scalar(
        select(ProfileVersion)
        .where(ProfileVersion.role_id == role_id, ProfileVersion.status == "approved")
        .order_by(ProfileVersion.version.desc())
    )
    if version is None:
        return RoleProfileContext(
            role_id, "insufficient_samples", "insufficient_samples", None, (), {}
        )
    traits = list(
        db.scalars(
            select(ProfileTrait)
            .where(
                ProfileTrait.profile_version_id == version.id,
                ProfileTrait.review_status == "accepted",
            )
            .order_by(ProfileTrait.created_at, ProfileTrait.id)
        )
    )
    if topic:
        needle = topic.strip().lower()
        traits = [
            trait
            for trait in traits
            if needle in trait.description.lower()
            or needle in trait.category.lower()
            or needle in trait.trait_key.lower()
        ]
    feature_rows: list[ProfileFeatureContext] = []
    for trait in traits:
        evidence_refs = tuple(
            {"message_id": item.message_id, "rationale": item.rationale}
            for item in db.scalars(
                select(ProfileEvidence)
                .join(ImportedMessage, ImportedMessage.id == ProfileEvidence.message_id)
                .join(Source, Source.id == ImportedMessage.source_id)
                .where(
                    ProfileEvidence.trait_id == trait.id,
                    ImportedMessage.speaker_role_id == role_id,
                    Source.status == "approved",
                )
                .order_by(ProfileEvidence.message_id)
            )
        )
        if evidence_refs:
            feature_rows.append(
                ProfileFeatureContext(
                    trait_id=trait.id,
                    category=trait.category,
                    claim=trait.description,
                    cognitive_state=trait.cognitive_state,
                    confidence=trait.confidence,
                    evidence_refs=evidence_refs,
                )
            )
    features = tuple(feature_rows)
    readiness = "ready" if features else "partial"
    usage = {
        "profile_version_id": version.id,
        "trait_ids": [item.trait_id for item in features],
        "retrieval_basis": "topic" if topic else "role",
    }
    context = RoleProfileContext(role_id, "approved", readiness, version.id, features, usage)
    if session_id is not None:
        record_context_usage(db, session_id, context)
    return context


def record_context_usage(db: Session, session_id: str, context: RoleProfileContext) -> None:
    """Record only IDs and retrieval metadata, never profile text or message content."""
    sequence = db.scalar(
        select(SessionEvent.sequence)
        .where(SessionEvent.session_id == session_id)
        .order_by(SessionEvent.sequence.desc())
        .limit(1)
    )
    db.add(
        SessionEvent(
            session_id=session_id,
            sequence=int(sequence or 0) + 1,
            type="profile.context_used",
            payload={"role_id": context.role_id, **context.usage},
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
