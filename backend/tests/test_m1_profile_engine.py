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
    ProfileTrait,
    Role,
    Source,
)
from app.profiles.admission import AdmissionError, admit_candidate_item
from app.profiles.candidate_persistence import (
    invalidate_imported_message_evidence,
)
from app.profiles.candidate_review import review_candidate_item
from app.profiles.consumer import build_role_context
from app.profiles.source_contract import analyze_and_persist_jsonl


def _row(message_id: str, content: str) -> dict[str, object]:
    flags = {"is_ai_generated": False, "is_system": False}
    security_sources = derive_security_flags(flags).source_map()
    return {
        "canonical_contract_version": "wechat-canonical-v1",
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
                    "canonical_contract_version": "wechat-canonical-v1",
                    "canonical_message_id": row["message_id"],
                    "canonical_timestamp": row["timestamp"],
                    "message_type": "text",
                    "content_status": "present",
                    "timestamp_status": "parsed_utc",
                    "is_ai_generated": False,
                    "is_system": False,
                    "security_flag_sources": row["security_flag_sources"],
                    "security_flag_inputs": row["security_flag_inputs"],
                },
            )
        )
    db.commit()
    return rows


def test_candidate_persistence_is_idempotent_and_keeps_unmatched_evidence(test_session_factory):
    db = test_session_factory()
    rows = _seed(db)
    missing_import = db.scalar(
        select(ImportedMessage).where(ImportedMessage.external_id == rows[0]["message_id"])
    )
    assert missing_import is not None
    db.delete(missing_import)
    db.commit()
    persisted = analyze_and_persist_jsonl(
        db,
        rows,
        sender_role_map={"synthetic-a": "role_a"},
        source_id="source-a",
    )
    retry = analyze_and_persist_jsonl(
        db,
        rows,
        sender_role_map={"synthetic-a": "role_a"},
        source_id="source-a",
    )
    assert persisted.persistence.created is True
    assert retry.persistence.created is False
    evidence = list(db.scalars(select(ProfileCandidateEvidence)))
    assert evidence
    assert any(item.match_status == "unmatched" for item in evidence)
    assert {item.source_message_id for item in evidence} <= {row["message_id"] for row in rows}


def test_review_admission_and_consumer_context_are_separate(test_session_factory):
    db = test_session_factory()
    rows = _seed(db)
    analyze_and_persist_jsonl(
        db,
        rows,
        sender_role_map={"synthetic-a": "role_a"},
        source_id="source-a",
    )
    item = db.scalar(
        select(ProfileCandidateItem).where(
            ProfileCandidateItem.category == "observable.message_length_median"
        )
    )
    assert item is not None
    review_candidate_item(
        db,
        item.id,
        to_status="accepted",
        reviewer_id="reviewer-a",
        note="审核人基于样本支撑度给出显式置信度",
        reviewer_confidence=0.8,
    )
    db.refresh(item)
    assert item.confidence is None
    assert item.reviewer_confidence == 0.8
    version = admit_candidate_item(db, item.id)
    assert version.status == "draft"
    assert version.source_candidate_item_id == item.id
    db.refresh(item)
    item.review_status = "accepted"
    version.status = "approved"
    trait = db.scalar(select(ProfileTrait).where(ProfileTrait.profile_version_id == version.id))
    assert trait is not None
    assert trait.confidence == 0.8
    assert trait.confidence_source == "reviewer_assessed"
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
    analyze_and_persist_jsonl(
        db,
        rows,
        sender_role_map={"synthetic-a": "role_a"},
        source_id="source-a",
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
