"""P3-C canonical JSONL/ZIP source and candidate lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.convert_wechatauto_export import convert
from sqlalchemy import select

from app.ingestion.archive_parser import parse_archive
from app.ingestion.wechat_normalizer import normalize_payload
from app.models import ImportedMessage, ProfileCandidateEvidence, Role, Source
from app.profiles.source_contract import (
    SourceContractError,
    analyze_and_persist_approved_source,
    analyze_and_persist_jsonl,
    build_canonical_dataset,
    resolve_imported_message_mapping,
)

ROLE_MAP = {"A": "role_a", "B": "role_b"}


def _payload() -> dict[str, object]:
    messages = []
    for index in range(6):
        sender = "A" if index < 3 else "B"
        messages.append(
            {
                "local_id": index + 1,
                "server_id": index + 101,
                "sort_seq": index + 1,
                "create_time": 1700000000 + index,
                "sender_name": sender,
                "type_code": 1,
                "type": "text",
                "content": f"{sender} 合成消息 {index}？",
                "is_ai_generated": False,
                "is_system": False,
            }
        )
    return {"chats": [{"username": "synthetic"}], "nick_name": "A", "messages": messages}


def _canonical_and_zip(tmp_path: Path):
    source = tmp_path / "synthetic.json"
    destination = tmp_path / "synthetic.zip"
    import json

    source.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
    canonical, summary = normalize_payload(_payload(), source_file=source.name)
    assert summary["error_count"] == 0
    convert(source, destination)
    return canonical, parse_archive(destination)


def _seed_roles_and_source(db, parsed, source_id: str = "source-p3c") -> None:
    now = datetime.now(UTC)
    for role_id, label in (("role_a", "A"), ("role_b", "B")):
        db.add(
            Role(
                id=role_id,
                label=label,
                profile="",
                style_profile={},
                voice_profile={},
                consent_status="preset",
                created_at=now,
                updated_at=now,
            )
        )
    db.add(Source(id=source_id, kind="synthetic", name=source_id, status="approved"))
    db.flush()
    for index, row in enumerate(parsed, start=1):
        db.add(
            ImportedMessage(
                id=f"db-{index}",
                source_id=source_id,
                external_id=row.external_id,
                speaker_label=row.speaker_label,
                speaker_role_id=ROLE_MAP[row.speaker_label],
                text=row.text,
                sent_at=row.sent_at,
                metadata_json=row.metadata,
            )
        )
    db.commit()


def test_jsonl_and_zip_paths_preserve_equivalent_canonical_identity(tmp_path: Path):
    canonical, parsed = _canonical_and_zip(tmp_path)
    canonical_ids = [row["message_id"] for row in canonical]
    imported_ids = [row.metadata["canonical_message_id"] for row in parsed]
    assert canonical_ids == imported_ids
    assert [row["sender"] for row in canonical] == [row.speaker_label for row in parsed]
    assert all(
        row["message_type"] == item.metadata["message_type"]
        for row, item in zip(canonical, parsed, strict=True)
    )
    assert all(
        row["security_flag_sources"] == item.metadata["security_flag_sources"]
        for row, item in zip(canonical, parsed, strict=True)
    )
    assert all(
        row["security_flag_inputs"] == item.metadata["security_flag_inputs"]
        for row, item in zip(canonical, parsed, strict=True)
    )


def test_controlled_source_persistence_maps_ids_and_is_idempotent(test_session_factory, tmp_path):
    canonical, parsed = _canonical_and_zip(tmp_path)
    db = test_session_factory()
    _seed_roles_and_source(db, parsed)
    persisted = analyze_and_persist_jsonl(
        db, canonical, sender_role_map=ROLE_MAP, source_id="source-p3c"
    )
    retry = analyze_and_persist_jsonl(
        db, canonical, sender_role_map=ROLE_MAP, source_id="source-p3c"
    )
    assert persisted.persistence.created is True
    assert persisted.mapping_count == 6
    assert persisted.mapping_issue_count == 0
    assert retry.persistence.created is False
    assert db.scalar(
        select(ProfileCandidateEvidence).where(ProfileCandidateEvidence.match_status == "matched")
    ) is not None
    assert all(
        row.source_dataset_id == "source-p3c"
        for row in db.scalars(select(ProfileCandidateEvidence))
    )


def test_controlled_mapping_retains_invalid_role_mismatch(test_session_factory, tmp_path):
    canonical, parsed = _canonical_and_zip(tmp_path)
    db = test_session_factory()
    _seed_roles_and_source(db, parsed, source_id="source-p3c-invalid")
    db.scalar(
        select(ImportedMessage).where(ImportedMessage.external_id == parsed[0].external_id)
    ).speaker_role_id = "role_b"
    db.commit()
    reversed_map = {"A": "role_b", "B": "role_a"}
    dataset = build_canonical_dataset(
        canonical, reversed_map, source_id="source-p3c-invalid"
    )
    _, issues = resolve_imported_message_mapping(
        db, dataset, reversed_map, source_id="source-p3c-invalid"
    )
    assert set(issues.values()) == {"role_mismatch"}


def test_approved_source_entry_uses_persisted_explicit_roles(test_session_factory, tmp_path):
    _, parsed = _canonical_and_zip(tmp_path)
    db = test_session_factory()
    _seed_roles_and_source(db, parsed, source_id="source-p3c-entry")
    result = analyze_and_persist_approved_source(db, "source-p3c-entry")
    assert result.mapping_count == 6
    assert result.analysis_status == "ready"


def test_unapproved_source_is_rejected_before_candidate_persistence(test_session_factory, tmp_path):
    canonical, _ = _canonical_and_zip(tmp_path)
    db = test_session_factory()
    db.add(Source(id="source-pending", kind="synthetic", name="pending", status="pending_review"))
    db.commit()
    with pytest.raises(SourceContractError, match="source_not_approved"):
        analyze_and_persist_jsonl(
            db, canonical, sender_role_map=ROLE_MAP, source_id="source-pending"
        )


def test_candidate_review_admission_publish_and_context_api(client, test_session_factory, tmp_path):
    _, parsed = _canonical_and_zip(tmp_path)
    db = test_session_factory()
    _seed_roles_and_source(db, parsed, source_id="source-api")

    analyzed = client.post("/api/candidate/sources/source-api/analyze")
    assert analyzed.status_code == 200
    summary = analyzed.json()
    assert summary["created"] is True
    assert summary["status"] == "ready"
    assert summary["role_statuses"] == {"role_a": "ready", "role_b": "ready"}
    assert summary["mapping_count"] == 6

    snapshot = client.get(f"/api/candidate/snapshots/{summary['snapshot_id']}")
    assert snapshot.status_code == 200
    candidate = next(
        item
        for item in snapshot.json()["items"]
        if item["subject_id"] == "role_a"
        and item["category"] == "observable.message_length_median"
    )
    assert candidate["confidence"] is None
    reviewed = client.post(
        f"/api/candidate/items/{candidate['id']}/review",
        json={
            "to_status": "accepted",
            "expected_from_status": "pending",
            "reviewer_id": "synthetic-reviewer",
            "note": "合成测试审核：明确给出人工置信度",
            "reviewer_confidence": 0.75,
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["confidence"] is None
    assert reviewed.json()["reviewer_confidence"] == 0.75

    snapshot = client.get(f"/api/candidate/snapshots/{summary['snapshot_id']}").json()
    item = next(row for row in snapshot["items"] if row["id"] == candidate["id"])
    assert item["confidence"] is None
    assert item["reviewer_confidence"] == 0.75
    assert item["review_events"][-1]["reviewer_confidence_before"] is None
    assert item["review_events"][-1]["reviewer_confidence_after"] == 0.75

    admitted = client.post(f"/api/candidate/items/{candidate['id']}/admit")
    assert admitted.status_code == 200
    profile = client.get(
        f"/api/roles/role_a/profiles/{admitted.json()['profile_version_id']}"
    )
    assert profile.status_code == 200
    trait = profile.json()["traits"][0]
    assert trait["confidence_source"] == "reviewer_assessed"
    reviewed_trait = client.post(
        f"/api/roles/role_a/profiles/{admitted.json()['profile_version_id']}"
        f"/traits/{trait['id']}/review",
        json={"status": "accepted", "reviewer_note": "合成测试正式审核"},
    )
    assert reviewed_trait.status_code == 200
    published = client.post(
        f"/api/roles/role_a/profiles/{admitted.json()['profile_version_id']}/publish"
    )
    assert published.status_code == 200
    assert published.json()["status"] == "approved"

    context = client.get("/api/candidate/context/role_a?topic=observable")
    assert context.status_code == 200
    assert context.json()["readiness"] == "ready"
    assert context.json()["features"][0]["trait_id"] == trait["id"]
