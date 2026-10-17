"""Controlled source identity and canonical-message mapping for profile candidates.

作者：valen MPF

The JSONL message ID is an input-dataset identifier.  This module deliberately
keeps it separate from ``ImportedMessage.id`` and only creates a mapping after
checking an approved ``Source`` and the explicit role assignment.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.wechat_normalizer import CANONICAL_CONTRACT_VERSION
from app.models import ImportedMessage, Source
from app.profiles.candidate_persistence import (
    CandidatePersistenceResult,
    _persist_profile_result,
)
from app.profiles.jsonl_analyzer import ObservableAnalyzer, ProfileAnalyzer
from app.profiles.jsonl_service import JsonlProfileResult
from app.profiles.provider_runtime import resolve_provider_config
from app.profiles.semantic_analyzer import create_semantic_analyzer


class SourceContractError(ValueError):
    """Raised when a source cannot be used as a trusted candidate dataset."""


@dataclass(frozen=True)
class CanonicalDataset:
    """A reproducible, non-sensitive identity for canonical input records."""

    dataset_id: str
    input_digest: str
    role_scope: tuple[str, ...]
    messages: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class ControlledPersistenceResult:
    """Persistence result plus the identities calculated by this service."""

    persistence: CandidatePersistenceResult
    dataset_id: str
    input_digest: str
    analyzer_digest: str
    mapping_count: int
    mapping_issue_count: int
    analysis_status: str
    role_statuses: Mapping[str, str]
    sample_counts: Mapping[str, int]
    analyzer_statuses: tuple[Mapping[str, Any], ...]
    semantic_status: str


def build_canonical_dataset(
    messages: Sequence[Mapping[str, Any]],
    sender_role_map: Mapping[str, str],
    *,
    source_id: str | None = None,
) -> CanonicalDataset:
    """Validate the canonical contract and calculate a stable input identity.

    ``source_id`` must be supplied by a caller that has already selected an
    approved database Source.  Offline JSONL snapshots receive a digest-based
    identity and intentionally have no formal message mapping.
    """
    if not messages:
        raise SourceContractError("canonical_dataset_empty")
    if not sender_role_map or any(
        not isinstance(sender, str)
        or not sender.strip()
        or role_id not in {"role_a", "role_b"}
        for sender, role_id in sender_role_map.items()
    ):
        raise SourceContractError("explicit_sender_role_map_required")

    normalized: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for message in messages:
        if not isinstance(message, Mapping):
            raise SourceContractError("canonical_message_must_be_object")
        if message.get("canonical_contract_version") != CANONICAL_CONTRACT_VERSION:
            raise SourceContractError("canonical_contract_version_required")
        message_id = message.get("message_id")
        if not isinstance(message_id, str) or not message_id or message_id in seen_ids:
            raise SourceContractError("canonical_message_id_must_be_unique")
        sender = message.get("sender")
        if not isinstance(sender, str) or sender not in sender_role_map:
            raise SourceContractError("canonical_sender_not_explicitly_mapped")
        seen_ids.add(message_id)
        normalized.append(message)

    digest_payload = [
        _identity_record(
            message,
            sender_role_map.get(str(message.get("sender")))
            if message.get("sender") is not None
            else None,
        )
        for message in sorted(normalized, key=lambda item: str(item["message_id"]))
    ]
    encoded = json.dumps(
        {
            "contract": CANONICAL_CONTRACT_VERSION,
            "sender_role_map": dict(sorted(sender_role_map.items())),
            "messages": digest_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    input_digest = hashlib.sha256(encoded).hexdigest()
    dataset_id = source_id or f"jsonl:{input_digest}"
    return CanonicalDataset(
        dataset_id,
        input_digest,
        tuple(sorted(set(sender_role_map.values()))),
        tuple(normalized),
    )


def analyzer_digest(result: JsonlProfileResult) -> str:
    """Hash the analyzer names, versions, scope and output status actually used."""
    analyzers = [
        {
            "subject_id": item.get("subject_id"),
            "analyzer_name": item.get("analyzer_name"),
            "analyzer_version": item.get("analyzer_version"),
            "status": item.get("status"),
        }
        for item in result.analyzer_statuses
    ]
    payload = {
        "pipeline": CANONICAL_CONTRACT_VERSION,
        "analyzers": analyzers,
        "candidate_output_digests": sorted(
            hashlib.sha256(
                json.dumps(
                    item.candidate.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for item in result.candidates
        ),
        "analyzer_metadata": [
            item.get("metadata") for item in result.analyzer_statuses
        ],
        "observable_config": {
            "minimum_sample_count": ObservableAnalyzer.minimum_sample_count,
            "maximum_sample_count": ObservableAnalyzer.maximum_sample_count,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve_imported_message_mapping(
    db: Session,
    dataset: CanonicalDataset,
    sender_role_map: Mapping[str, str],
    *,
    source_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve canonical IDs to approved ImportedMessage IDs without guessing.

    The second mapping contains stable reasons for missing, ambiguous or
    role-inconsistent references.  It is retained as invalid candidate
    evidence rather than silently turning it into a valid match.
    """
    source = db.get(Source, source_id)
    if source is None:
        raise SourceContractError("source_not_found")
    if source.status != "approved":
        raise SourceContractError("source_not_approved")

    imported = list(
        db.scalars(select(ImportedMessage).where(ImportedMessage.source_id == source_id))
    )
    by_key: dict[str, list[ImportedMessage]] = defaultdict(list)
    for message in imported:
        by_key[message.external_id].append(message)
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        canonical_id = metadata.get("canonical_message_id")
        if isinstance(canonical_id, str) and canonical_id:
            by_key[canonical_id].append(message)

    mapping: dict[str, str] = {}
    issues: dict[str, str] = {}
    used_imported_ids: set[str] = set()
    for canonical in dataset.messages:
        source_message_id = str(canonical["message_id"])
        matches = {item.id: item for item in by_key.get(source_message_id, [])}
        if not matches:
            issues[source_message_id] = "missing_imported_message"
            continue
        if len(matches) != 1:
            issues[source_message_id] = "ambiguous_imported_message"
            continue
        imported_message = next(iter(matches.values()))
        expected_role = sender_role_map.get(str(canonical["sender"]))
        if expected_role is None or imported_message.speaker_role_id != expected_role:
            issues[source_message_id] = "role_mismatch"
            continue
        if imported_message.speaker_label != canonical.get("sender"):
            issues[source_message_id] = "sender_mismatch"
            continue
        metadata = (
            imported_message.metadata_json
            if isinstance(imported_message.metadata_json, dict)
            else {}
        )
        if metadata.get("canonical_contract_version") != CANONICAL_CONTRACT_VERSION:
            issues[source_message_id] = "canonical_source_metadata_missing"
            continue
        if metadata.get("message_type") != canonical.get("message_type"):
            issues[source_message_id] = "message_type_mismatch"
            continue
        if metadata.get("security_flag_inputs") != canonical.get("security_flag_inputs"):
            issues[source_message_id] = "security_provenance_mismatch"
            continue
        if metadata.get("security_flag_sources") != canonical.get("security_flag_sources"):
            issues[source_message_id] = "security_provenance_mismatch"
            continue
        if metadata.get("security_attestation") != canonical.get("security_attestation"):
            issues[source_message_id] = "security_attestation_mismatch"
            continue
        content = canonical.get("content")
        if canonical.get("content_status") == "present" and (
            not isinstance(content, str) or imported_message.text != content.strip()
        ):
            issues[source_message_id] = "content_mismatch"
            continue
        if imported_message.id in used_imported_ids:
            issues[source_message_id] = "duplicate_imported_mapping"
            continue
        if not _timestamps_agree(canonical, imported_message):
            issues[source_message_id] = "timestamp_mismatch"
            continue
        mapping[source_message_id] = imported_message.id
        used_imported_ids.add(imported_message.id)
    return mapping, issues


def _persist_analysis_result(
    db: Session,
    result: JsonlProfileResult,
    messages: Sequence[Mapping[str, Any]],
    *,
    sender_role_map: Mapping[str, str],
    source_id: str,
) -> ControlledPersistenceResult:
    """Persist only a result generated by the controlled Analyzer entrypoint."""
    if not source_id:
        raise SourceContractError("approved_source_required")
    source = db.get(Source, source_id)
    if source is None:
        raise SourceContractError("source_not_found")
    if source.status != "approved":
        raise SourceContractError("source_not_approved")
    dataset = build_canonical_dataset(messages, sender_role_map, source_id=source_id)
    _validate_result_binding(result, dataset, sender_role_map)
    mapping: dict[str, str] = {}
    mapping_issues: dict[str, str] = {}
    if source_id is not None:
        mapping, mapping_issues = resolve_imported_message_mapping(
            db, dataset, sender_role_map, source_id=source_id
        )
    persistence = _persist_profile_result(
        db,
        result,
        source_dataset_id=dataset.dataset_id,
        input_digest=dataset.input_digest,
        analyzer_digest=analyzer_digest(result),
        message_mapping=mapping,
        mapping_reasons=mapping_issues,
        trusted_source_id=source_id,
    )
    return ControlledPersistenceResult(
        persistence=persistence,
        dataset_id=dataset.dataset_id,
        input_digest=dataset.input_digest,
        analyzer_digest=analyzer_digest(result),
        mapping_count=len(mapping),
        mapping_issue_count=len(mapping_issues),
        analysis_status=result.status,
        role_statuses=dict(result.role_statuses),
        sample_counts=dict(result.sample_counts),
        analyzer_statuses=tuple(dict(item) for item in result.analyzer_statuses),
        semantic_status=result.semantic_status,
    )


def canonical_rows_from_approved_source(
    db: Session, source_id: str
) -> tuple[tuple[Mapping[str, Any], ...], dict[str, str]]:
    """Rebuild canonical records only from an approved, explicitly mapped source."""
    source = db.get(Source, source_id)
    if source is None:
        raise SourceContractError("source_not_found")
    if source.status != "approved":
        raise SourceContractError("source_not_approved")
    imported = list(
        db.scalars(
            select(ImportedMessage)
            .where(ImportedMessage.source_id == source_id)
            .order_by(ImportedMessage.external_id, ImportedMessage.id)
        )
    )
    if not imported:
        raise SourceContractError("source_has_no_imported_messages")

    sender_roles: dict[str, set[str]] = defaultdict(set)
    for item in imported:
        if item.speaker_role_id in {"role_a", "role_b"}:
            sender_roles[item.speaker_label].add(item.speaker_role_id)
    if any(len(roles) > 1 for roles in sender_roles.values()):
        raise SourceContractError("source_speaker_role_mapping_ambiguous")
    sender_role_map = {
        label: next(iter(roles)) for label, roles in sender_roles.items() if roles
    }
    if not sender_role_map:
        raise SourceContractError("source_has_no_explicit_role_mapping")

    records: list[Mapping[str, Any]] = []
    for item in imported:
        metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
        contract_version = metadata.get("canonical_contract_version")
        canonical_id = metadata.get("canonical_message_id")
        if not isinstance(canonical_id, str) or not canonical_id:
            canonical_id = item.external_id
        content_status = metadata.get("content_status")
        if contract_version != CANONICAL_CONTRACT_VERSION:
            content_status = "unknown"
        if content_status not in {"present", "empty", "missing", "not_text"}:
            content_status = "unknown"
        timestamp_status = metadata.get("timestamp_status")
        if timestamp_status not in {"parsed_utc", "missing", "invalid", "out_of_range"}:
            timestamp_status = "parsed_utc" if item.sent_at is not None else "missing"
        timestamp = metadata.get("canonical_timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            timestamp = _timestamp_text(item.sent_at)
        records.append(
            {
                "canonical_contract_version": contract_version,
                "message_id": canonical_id,
                "sender": (
                    item.speaker_label
                    if item.speaker_role_id in {"role_a", "role_b"}
                    else None
                ),
                "message_type": metadata.get("message_type", "unknown")
                if contract_version == CANONICAL_CONTRACT_VERSION
                else "unknown",
                "content": item.text if content_status == "present" else None,
                "content_status": content_status,
                "timestamp": timestamp,
                "timestamp_status": timestamp_status,
                "is_ai_generated": metadata.get("is_ai_generated"),
                "is_system": metadata.get("is_system"),
                "security_flag_sources": metadata.get("security_flag_sources"),
                "security_flag_inputs": metadata.get("security_flag_inputs"),
                "security_attestation": source.metadata_json.get("security_attestation"),
                "source_local_id": metadata.get("source_local_id"),
                "source_server_id": metadata.get("source_server_id"),
                "source_type_code": metadata.get("source_type_code", metadata.get("type_code")),
            }
        )
    return tuple(records), sender_role_map


def analyze_and_persist_approved_source(
    db: Session,
    source_id: str,
    *,
    semantic_analyzer: ProfileAnalyzer | None = None,
) -> ControlledPersistenceResult:
    """Analyze an approved source using local observables and configured semantics."""
    records, sender_role_map = canonical_rows_from_approved_source(db, source_id)
    return analyze_and_persist_jsonl(
        db,
        records,
        sender_role_map=sender_role_map,
        source_id=source_id,
        semantic_analyzer=semantic_analyzer,
    )


def analyze_and_persist_jsonl(
    db: Session,
    messages: Sequence[Mapping[str, Any]],
    *,
    sender_role_map: Mapping[str, str],
    source_id: str,
    semantic_analyzer: ProfileAnalyzer | None = None,
) -> ControlledPersistenceResult:
    """Analyze canonical JSONL; semantic transfer requires two explicit opt-ins."""
    from app.profiles.jsonl_service import analyze_normalized_messages

    source = db.get(Source, source_id)
    if source is None:
        raise SourceContractError("source_not_found")
    if source.status != "approved":
        raise SourceContractError("source_not_approved")
    transfer_authorized = bool((source.metadata_json or {}).get("semantic_llm_authorized", False))
    selected_semantic_analyzer = (
        semantic_analyzer
        if transfer_authorized and semantic_analyzer is not None
        else create_semantic_analyzer(
            approved_source=transfer_authorized,
            config=resolve_provider_config(db).semantic_config(),
        )
    )
    result = analyze_normalized_messages(
        messages,
        sender_role_map=sender_role_map,
        analyzers=(
            ObservableAnalyzer(),
            selected_semantic_analyzer,
        ),
    )
    return _persist_analysis_result(
        db,
        result,
        messages,
        sender_role_map=sender_role_map,
        source_id=source_id,
    )


def _identity_record(message: Mapping[str, Any], role_id: str | None) -> dict[str, Any]:
    content = message.get("content")
    content_digest = (
        hashlib.sha256(content.encode("utf-8")).hexdigest()
        if isinstance(content, str)
        else None
    )
    return {
        "message_id": message.get("message_id"),
        "role_id": role_id,
        "source_local_id": message.get("source_local_id"),
        "source_server_id": message.get("source_server_id"),
        "timestamp": message.get("timestamp"),
        "timestamp_status": message.get("timestamp_status"),
        "sender": message.get("sender"),
        "message_type": message.get("message_type"),
        "source_type_code": message.get("source_type_code"),
        "content_status": message.get("content_status"),
        "content_digest": content_digest,
        "is_ai_generated": message.get("is_ai_generated"),
        "is_system": message.get("is_system"),
        "security_flag_sources": message.get("security_flag_sources"),
        "security_flag_inputs": message.get("security_flag_inputs"),
        "security_attestation": message.get("security_attestation"),
        "canonical_contract_version": message.get("canonical_contract_version"),
    }


def _validate_result_binding(
    result: JsonlProfileResult,
    dataset: CanonicalDataset,
    sender_role_map: Mapping[str, str],
) -> None:
    """Reject candidate output that cannot be traced to this canonical input."""
    records = {str(item["message_id"]): item for item in dataset.messages}
    if set(result.role_statuses) != set(sender_role_map.values()):
        raise SourceContractError("analysis_role_scope_mismatch")
    for reviewed in result.candidates:
        candidate = reviewed.candidate
        if candidate.subject_id not in dataset.role_scope:
            raise SourceContractError("candidate_role_outside_dataset_scope")
        supporting = set(candidate.evidence_refs)
        counter = set(candidate.counter_evidence_refs)
        if not supporting and not counter:
            raise SourceContractError("candidate_evidence_required")
        if supporting & counter:
            raise SourceContractError("candidate_evidence_direction_conflict")
        for reference in supporting | counter:
            message = records.get(reference)
            if message is None:
                raise SourceContractError("candidate_evidence_not_in_dataset")
            sender = message.get("sender")
            if not isinstance(sender, str) or sender_role_map.get(sender) != candidate.subject_id:
                raise SourceContractError("candidate_evidence_role_mismatch")


def _timestamps_agree(canonical: Mapping[str, Any], imported: ImportedMessage) -> bool:
    if canonical.get("timestamp_status") != "parsed_utc":
        return True
    raw = canonical.get("timestamp")
    if not isinstance(raw, str) or imported.sent_at is None:
        return False
    try:
        expected = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    metadata = imported.metadata_json if isinstance(imported.metadata_json, dict) else {}
    stored = metadata.get("canonical_timestamp")
    if isinstance(stored, str):
        try:
            stored_datetime = datetime.fromisoformat(stored.replace("Z", "+00:00"))
        except ValueError:
            return False
        return (
            expected.tzinfo is not None
            and stored_datetime.tzinfo is not None
            and expected.astimezone(UTC) == stored_datetime.astimezone(UTC)
        )
    actual = imported.sent_at
    if expected.tzinfo is None:
        return False
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=UTC)
    return expected.astimezone(UTC) == actual.astimezone(UTC)


def _timestamp_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
