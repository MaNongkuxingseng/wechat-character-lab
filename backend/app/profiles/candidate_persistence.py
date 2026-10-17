"""Transactional persistence for JSONL profile candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ImportedMessage,
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileCandidateSnapshot,
    ProfileCandidateUnmatchedEvidence,
    Role,
    Source,
)
from app.profiles.jsonl_service import JsonlProfileResult, ReviewedCandidate


@dataclass(frozen=True)
class CandidatePersistenceResult:
    snapshot_id: str
    created: bool
    candidate_count: int
    evidence_count: int
    unmatched_count: int


class CandidatePersistenceError(ValueError):
    """Raised when a candidate cannot be persisted without losing provenance."""


def _persist_profile_result(
    db: Session,
    result: JsonlProfileResult,
    *,
    source_dataset_id: str,
    input_digest: str,
    analyzer_digest: str,
    message_mapping: Mapping[str, str | None],
    mapping_reasons: Mapping[str, str] | None = None,
    trusted_source_id: str | None = None,
) -> CandidatePersistenceResult:
    """Persist one JSONL result atomically and return an idempotent snapshot result.

    ``message_mapping`` is deliberately explicit: JSONL source IDs are never used as
    ``ImportedMessage.id`` values. Missing mappings remain candidate evidence with an
    ``unmatched`` status; mappings to a missing or wrong-role message are ``invalid``.
    """
    if trusted_source_id is not None and source_dataset_id != trusted_source_id:
        raise CandidatePersistenceError("source_dataset_identity_mismatch")
    if trusted_source_id is not None:
        source = db.get(Source, trusted_source_id)
        if source is None or source.status != "approved":
            raise CandidatePersistenceError("source_not_approved")
    role_scope = sorted({item.candidate.subject_id for item in result.candidates})
    role_scope = sorted(set(result.role_statuses) | set(role_scope))
    scoped_input_digest = hashlib.sha256(
        json.dumps(
            {"input_digest": input_digest, "role_scope": role_scope},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(ProfileCandidateSnapshot).where(
            ProfileCandidateSnapshot.source_dataset_id == source_dataset_id,
            ProfileCandidateSnapshot.input_digest == scoped_input_digest,
            ProfileCandidateSnapshot.analyzer_digest == analyzer_digest,
        )
    )
    if existing is not None:
        return CandidatePersistenceResult(
            existing.id,
            False,
            len(
                list(
                    db.scalars(
                        select(ProfileCandidateItem).where(
                            ProfileCandidateItem.snapshot_id == existing.id
                        )
                    )
                )
            ),
            0,
            len(
                list(
                    db.scalars(
                        select(ProfileCandidateUnmatchedEvidence).where(
                            ProfileCandidateUnmatchedEvidence.snapshot_id == existing.id
                        )
                    )
                )
            ),
        )

    now = datetime.now(UTC)
    snapshot = ProfileCandidateSnapshot(
        id=str(uuid4()),
        source_dataset_id=source_dataset_id,
        role_scope=role_scope,
        analyzer_manifest=[dict(item) for item in result.analyzer_statuses],
        input_digest=scoped_input_digest,
        analyzer_digest=analyzer_digest,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(snapshot)
        db.flush()
        evidence_count = 0
        for reviewed in result.candidates:
            candidate = reviewed.candidate
            if db.get(Role, candidate.subject_id) is None:
                raise CandidatePersistenceError(f"role_not_found:{candidate.subject_id}")
            cognitive_state, inference_basis = _cognitive_state(reviewed)
            conflict_status = "conflict" if candidate.counter_evidence_refs else "none"
            item = ProfileCandidateItem(
                id=str(uuid4()),
                snapshot_id=snapshot.id,
                profile_item_id=candidate.profile_item_id,
                subject_id=candidate.subject_id,
                category=candidate.category,
                claim=candidate.claim,
                confidence=candidate.confidence,
                cognitive_state=cognitive_state,
                inference_basis=inference_basis,
                conflict_status=conflict_status,
                observed_at=_parse_datetime(candidate.observed_at),
                updated_at=now,
                analyzer_name=reviewed.analyzer_name,
                analyzer_version=reviewed.analyzer_version,
                review_status=reviewed.review_status,
                reviewer_note=reviewed.reviewer_note,
                candidate_fingerprint=hashlib.sha256(
                    candidate.profile_item_id.encode("utf-8")
                ).hexdigest(),
            )
            db.add(item)
            db.flush()
            for direction, refs in (
                ("supporting", candidate.evidence_refs),
                ("counter", candidate.counter_evidence_refs),
            ):
                for source_message_id in refs:
                    db.add(
                        _build_evidence(
                            db,
                            item,
                            direction=direction,
                            source_dataset_id=source_dataset_id,
                            source_message_id=source_message_id,
                             imported_id=message_mapping.get(source_message_id),
                             mapping_reason=(mapping_reasons or {}).get(source_message_id),
                             trusted_source_id=trusted_source_id,
                        )
                    )
                    evidence_count += 1
        unmatched_count = 0
        for item in result.unmatched_evidence:
            db.add(
                ProfileCandidateUnmatchedEvidence(
                    id=str(uuid4()),
                    snapshot_id=snapshot.id,
                    signal_id=item.signal_id[:128],
                    evidence_id=item.evidence_id[:255],
                    kind=item.kind[:32],
                    reason=item.reason[:120],
                )
            )
            unmatched_count += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return CandidatePersistenceResult(
        snapshot.id, True, len(result.candidates), evidence_count, unmatched_count
    )


def invalidate_imported_message_evidence(db: Session, imported_message_id: str) -> int:
    """Invalidate candidate mappings before a caller deletes a formal message."""
    rows = list(
        db.scalars(
            select(ProfileCandidateEvidence).where(
                ProfileCandidateEvidence.imported_message_id == imported_message_id,
                ProfileCandidateEvidence.match_status == "matched",
            )
        )
    )
    for evidence in rows:
        evidence.imported_message_id = None
        evidence.match_status = "invalid"
        evidence.invalid_reason = "imported_message_deleted"
        evidence.matched_at = None
    db.flush()
    return len(rows)


def _build_evidence(
    db: Session,
    item: ProfileCandidateItem,
    *,
    direction: str,
    source_dataset_id: str,
    source_message_id: str,
    imported_id: str | None,
    mapping_reason: str | None = None,
    trusted_source_id: str | None = None,
) -> ProfileCandidateEvidence:
    if not imported_id:
        if mapping_reason:
            if mapping_reason == "missing_imported_message":
                return ProfileCandidateEvidence(
                    id=str(uuid4()),
                    candidate_id=item.id,
                    direction=direction,
                    source_dataset_id=source_dataset_id,
                    source_message_id=source_message_id,
                    rationale="canonical source message has no imported database mapping",
                    match_status="unmatched",
                    invalid_reason=mapping_reason,
                )
            return ProfileCandidateEvidence(
                id=str(uuid4()),
                candidate_id=item.id,
                direction=direction,
                source_dataset_id=source_dataset_id,
                source_message_id=source_message_id,
                rationale="controlled source mapping did not produce a valid formal reference",
                match_status="invalid",
                invalid_reason=mapping_reason,
            )
        return ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=item.id,
            direction=direction,
            source_dataset_id=source_dataset_id,
            source_message_id=source_message_id,
            rationale="source message mapping was not supplied",
            match_status="unmatched",
            invalid_reason="missing_imported_mapping",
        )
    message = db.get(ImportedMessage, imported_id)
    if message is None:
        return ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=item.id,
            direction=direction,
            source_dataset_id=source_dataset_id,
            source_message_id=source_message_id,
            imported_message_id=None,
            rationale="mapped formal message does not exist",
            match_status="invalid",
            invalid_reason="imported_message_not_found",
        )
    if trusted_source_id is not None and message.source_id != trusted_source_id:
        return ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=item.id,
            direction=direction,
            source_dataset_id=source_dataset_id,
            source_message_id=source_message_id,
            rationale="mapped formal message belongs to another source",
            match_status="invalid",
            invalid_reason="source_mismatch",
        )
    if trusted_source_id is not None:
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        if metadata.get("canonical_message_id") != source_message_id:
            return ProfileCandidateEvidence(
                id=str(uuid4()),
                candidate_id=item.id,
                direction=direction,
                source_dataset_id=source_dataset_id,
                source_message_id=source_message_id,
                rationale="mapped formal message does not declare the same canonical source ID",
                match_status="invalid",
                invalid_reason="canonical_source_id_mismatch",
            )
    if message.speaker_role_id != item.subject_id:
        return ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=item.id,
            direction=direction,
            source_dataset_id=source_dataset_id,
            source_message_id=source_message_id,
            rationale="mapped formal message belongs to another role",
            match_status="invalid",
            invalid_reason="role_mismatch",
        )
    source_status = db.scalar(select(Source.status).where(Source.id == message.source_id))
    if source_status != "approved":
        return ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=item.id,
            direction=direction,
            source_dataset_id=source_dataset_id,
            source_message_id=source_message_id,
            rationale="mapped formal message source is not approved",
            match_status="invalid",
            invalid_reason="source_not_approved",
        )
    return ProfileCandidateEvidence(
        id=str(uuid4()),
        candidate_id=item.id,
        direction=direction,
        source_dataset_id=source_dataset_id,
        source_message_id=source_message_id,
        imported_message_id=imported_id,
        rationale="explicit source message mapping",
        match_status="matched",
        matched_at=datetime.now(UTC),
    )


def _cognitive_state(reviewed: ReviewedCandidate) -> tuple[str, str | None]:
    if reviewed.candidate.category.startswith("observable."):
        return "evidence_backed", "deterministic observable analyzer output"
    return "model_inferred", "semantic analyzer output requires human review"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or value == "unknown":
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidatePersistenceError("observed_at must include timezone")
    return parsed


# Kept for existing offline callers.  Production source lifecycles must use
# ``source_contract.persist_canonical_profile_result`` with a trusted Source.
persist_profile_result = _persist_profile_result
