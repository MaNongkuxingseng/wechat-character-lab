from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.ingestion.security_flags import derive_security_flags
from app.models import (
    ImportedMessage,
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileCandidateSnapshot,
    ProfileCandidateUnmatchedEvidence,
    ProfileTrait,
    Role,
    Source,
)
from app.profiles.admission import AdmissionError, admit_candidate_item
from app.profiles.candidate_persistence import (
    invalidate_imported_message_evidence,
    persist_profile_result,
)
from app.profiles.candidate_review import review_candidate_item
from app.profiles.consumer import build_role_context
from app.profiles.jsonl_service import UnmatchedEvidence, analyze_normalized_messages


def _row(message_id: str, content: str) -> dict[str, object]:
    flags = {"is_ai_generated": False, "is_system": False}
    security_sources = derive_security_flags(flags).source_map()
    return {
        "message_id": message_id,
        "sender": "synthetic-a",
        "message_type": "text",
        "content": content,
        "content_status": "present",
        "timestamp": "2026-01-01T10:00:00Z",
        "timestamp_status": "parsed_utc",
        **flags,
        "security_flag_sources": security_sources,
        "security_flag_inputs": {"top_level": flags, "source_metadata": {}},
    }


def _seed(db):
    now = datetime.now(UTC)
    db.add(
        Role(
            id="role_a",
            label="A",
            profile="",
            style_profile={},
            voice_profile={},
            consent_status="preset",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        Source(
            id="source-a", kind="synthetic", name="synthetic", status="approved", metadata_json={}
        )
    )
    rows = [_row(f"m-{index}", f"合成消息 {index}?") for index in range(3)]
    db.flush()
    for row in rows:
        db.add(
            ImportedMessage(
                id=f"db-{row['message_id']}",
                source_id="source-a",
                external_id=str(row["message_id"]),
                speaker_label="synthetic-a",
                speaker_role_id="role_a",
                text=str(row["content"]),
                sent_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                metadata_json={
                    "message_type": "text",
                    "is_ai_generated": False,
                    "is_system": False,
                },
            )
        )
    db.commit()
    return rows


def test_candidate_persistence_is_idempotent_and_keeps_unmatched_evidence(test_session_factory):
    db = test_session_factory()
    rows = _seed(db)
    result = analyze_normalized_messages(rows, sender_role_map={"synthetic-a": "role_a"})
    result = replace(
        result,
        unmatched_evidence=(UnmatchedEvidence("signal-1", "missing-message", "not_found"),),
    )
    persisted = persist_profile_result(
        db,
        result,
        source_dataset_id="synthetic-dataset",
        input_digest="a" * 64,
        analyzer_digest="b" * 64,
        message_mapping={"m-m-0": "db-m-0"},
    )
    retry = persist_profile_result(
        db,
        result,
        source_dataset_id="synthetic-dataset",
        input_digest="a" * 64,
        analyzer_digest="b" * 64,
        message_mapping={},
    )
    assert persisted.created is True
    assert retry.created is False
    evidence = list(db.scalars(select(ProfileCandidateEvidence)))
    assert evidence
    assert any(item.match_status == "unmatched" for item in evidence)
    assert {item.source_message_id for item in evidence} <= {row["message_id"] for row in rows}
    assert list(db.scalars(select(ProfileCandidateUnmatchedEvidence)))


def test_review_admission_and_consumer_context_are_separate(test_session_factory):
    db = test_session_factory()
    rows = _seed(db)
    result = analyze_normalized_messages(rows, sender_role_map={"synthetic-a": "role_a"})
    persist_profile_result(
        db,
        result,
        source_dataset_id="dataset-2",
        input_digest="c" * 64,
        analyzer_digest="d" * 64,
        message_mapping={row["message_id"]: f"db-{row['message_id']}" for row in rows},
    )
    item = db.scalar(
        select(ProfileCandidateItem).where(
            ProfileCandidateItem.category == "observable.message_length_median"
        )
    )
    assert item is not None
    review_candidate_item(db, item.id, to_status="accepted", reviewer_id="reviewer-a")
    item.confidence = 0.8
    db.commit()
    version = admit_candidate_item(db, item.id)
    assert version.status == "draft"
    assert version.source_candidate_item_id == item.id
    db.refresh(item)
    item.review_status = "accepted"
    version.status = "approved"
    trait = db.scalar(select(ProfileTrait).where(ProfileTrait.profile_version_id == version.id))
    assert trait is not None
    trait.review_status = "accepted"
    db.commit()
    context = build_role_context(db, "role_a", topic="observable")
    assert context.readiness == "ready"
    assert context.features
    assert context.usage["trait_ids"]
    db.get(Source, "source-a").status = "pending_review"
    db.commit()
    assert build_role_context(db, "role_a").readiness == "partial"


def test_matched_evidence_requires_explicit_invalidation_before_message_delete(
    test_session_factory,
):
    db = test_session_factory()
    rows = _seed(db)
    result = analyze_normalized_messages(rows, sender_role_map={"synthetic-a": "role_a"})
    persist_profile_result(
        db,
        result,
        source_dataset_id="dataset-3",
        input_digest="e" * 64,
        analyzer_digest="f" * 64,
        message_mapping={row["message_id"]: f"db-{row['message_id']}" for row in rows},
    )
    evidence = db.scalar(
        select(ProfileCandidateEvidence).where(ProfileCandidateEvidence.match_status == "matched")
    )
    assert evidence is not None
    imported_id = evidence.imported_message_id
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM imported_messages WHERE id=:id"), {"id": imported_id})
        db.commit()
    db.rollback()
    assert invalidate_imported_message_evidence(db, imported_id) >= 1
    db.commit()
    db.execute(text("DELETE FROM imported_messages WHERE id=:id"), {"id": imported_id})
    db.commit()
    db.refresh(evidence)
    assert evidence.match_status == "invalid"
    assert evidence.imported_message_id is None


def test_unknown_candidate_cannot_enter_formal_profile(test_session_factory):
    db = test_session_factory()
    now = datetime.now(UTC)
    db.add(
        Role(
            id="role_a",
            label="A",
            profile="",
            style_profile={},
            voice_profile={},
            consent_status="preset",
            created_at=now,
            updated_at=now,
        )
    )
    snapshot = ProfileCandidateSnapshot(
        id="snapshot-unknown",
        source_dataset_id="unknown-dataset",
        role_scope=["role_a"],
        analyzer_manifest=[],
        input_digest="1" * 64,
        analyzer_digest="2" * 64,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(snapshot)
    db.flush()
    item = ProfileCandidateItem(
        id="candidate-unknown",
        snapshot_id=snapshot.id,
        profile_item_id="pi-unknown",
        subject_id="role_a",
        category="semantic.test",
        claim="unknown",
        confidence=None,
        cognitive_state="unknown",
        conflict_status="none",
        analyzer_name="fake",
        analyzer_version="1",
        review_status="accepted",
        candidate_fingerprint="3" * 64,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    with pytest.raises(AdmissionError, match="unknown_cognitive_state"):
        admit_candidate_item(db, item.id)
