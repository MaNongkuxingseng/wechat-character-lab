from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import (
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileCandidateSnapshot,
    Role,
)


def _seed_candidate_graph(test_session_factory):
    db = test_session_factory()
    db.add(
        Role(
            id="role_a",
            label="角色 A",
            profile="",
            style_profile={},
            voice_profile={},
            consent_status="preset",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    snapshot = ProfileCandidateSnapshot(
        id=str(uuid4()),
        source_dataset_id="synthetic-dataset",
        role_scope=["role_a"],
        analyzer_manifest=[{"name": "test", "version": "1"}],
        input_digest="a" * 64,
        analyzer_digest="b" * 64,
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.flush()
    candidate = ProfileCandidateItem(
        id=str(uuid4()),
        snapshot_id=snapshot.id,
        profile_item_id="item-1",
        subject_id="role_a",
        category="language_style",
        claim="合成测试候选",
        confidence=None,
        analyzer_name="test",
        analyzer_version="1",
        review_status="pending",
        candidate_fingerprint="c" * 64,
        updated_at=datetime.now(UTC),
    )
    db.add(candidate)
    db.commit()
    return db, snapshot, candidate


def test_candidate_metadata_registers_all_models(test_session_factory):
    engine = test_session_factory.kw["bind"]
    tables = set(inspect(engine).get_table_names())
    assert {
        "profile_candidate_snapshots",
        "profile_candidate_items",
        "profile_candidate_evidence",
        "profile_candidate_review_events",
    }.issubset(tables)


def test_candidate_confidence_can_be_unknown_and_source_id_is_not_imported_fk(
    test_session_factory,
):
    db, _, candidate = _seed_candidate_graph(test_session_factory)
    assert candidate.confidence is None
    evidence = ProfileCandidateEvidence(
        id=str(uuid4()),
        candidate_id=candidate.id,
        direction="supporting",
        source_dataset_id="synthetic-dataset",
        source_message_id="jsonl-message-1",
        rationale="合成证据",
        match_status="unmatched",
    )
    db.add(evidence)
    db.commit()
    assert evidence.imported_message_id is None
    engine = test_session_factory.kw["bind"]
    foreign_keys = inspect(engine).get_foreign_keys("profile_candidate_evidence")
    constrained_columns = {
        column for foreign_key in foreign_keys for column in foreign_key["constrained_columns"]
    }
    assert "source_message_id" not in constrained_columns
    assert "imported_message_id" in constrained_columns


def test_candidate_constraints_reject_invalid_status_and_cross_direction_duplicate(
    test_session_factory,
):
    db, snapshot, candidate = _seed_candidate_graph(test_session_factory)
    with pytest.raises(IntegrityError):
        snapshot.status = "published"
        db.commit()
    db.rollback()
    db.refresh(snapshot)
    assert snapshot.status == "draft"

    with pytest.raises(IntegrityError):
        db.add(
            ProfileCandidateItem(
                id=str(uuid4()),
                snapshot_id=snapshot.id,
                profile_item_id="item-2",
                subject_id="role_a",
                category="fact",
                claim="invalid",
                confidence=1.5,
                analyzer_name="test",
                analyzer_version="1",
                candidate_fingerprint="d" * 64,
                updated_at=datetime.now(UTC),
            )
        )
        db.commit()

    db.rollback()
    with pytest.raises(IntegrityError):
        candidate.review_status = "published"
        db.commit()

    db.rollback()
    db.refresh(candidate)
    assert candidate.review_status == "pending"

    db.rollback()
    with pytest.raises(IntegrityError):
        db.add(
            ProfileCandidateEvidence(
                id=str(uuid4()),
                candidate_id=candidate.id,
                direction="supporting",
                source_dataset_id="synthetic-dataset",
                source_message_id="unmatched-with-db-id",
                imported_message_id="not-a-proven-imported-message",
                rationale="unmatched evidence cannot carry formal ID",
                match_status="unmatched",
            )
        )
        db.commit()
    db.rollback()

    db.add(
        ProfileCandidateEvidence(
            id=str(uuid4()),
            candidate_id=candidate.id,
            direction="supporting",
            source_dataset_id="synthetic-dataset",
            source_message_id="same-message",
            rationale="first",
            match_status="unmatched",
        )
    )
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(
            ProfileCandidateEvidence(
                id=str(uuid4()),
                candidate_id=candidate.id,
                direction="counter",
                source_dataset_id="synthetic-dataset",
                source_message_id="same-message",
                rationale="cross direction must reject",
                match_status="unmatched",
            )
        )
        db.commit()
