import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.ingestion.security_flags import derive_security_flags
from app.models import ImportedMessage, ProfileVersion, Role, Source
from app.profiles.semantic_analyzer import (
    OUTPUT_SCHEMA_VERSION,
    OpenAICompatibleSemanticAnalyzer,
    SemanticProviderConfig,
)
from app.profiles.source_contract import (
    SourceContractError,
    build_canonical_dataset,
    canonical_rows_from_approved_source,
)


def _seed_approved_source(db, *, transfer_authorized: bool) -> None:
    now = datetime.now(UTC)
    for role_id, label in (("role_a", "Synthetic A"), ("role_b", "Synthetic B")):
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
    db.add(
        Source(
            id="synthetic-approved-source",
            kind="synthetic",
            name="Synthetic approved source",
            status="approved",
            metadata_json={"semantic_llm_authorized": transfer_authorized},
            imported_at=now,
        )
    )
    db.flush()
    for role, label in (("a", "Synthetic A"), ("b", "Synthetic B")):
        for index in range(1, 4):
            message_id = f"{role}-{index}"
            flags = {"is_ai_generated": False, "is_system": False}
            _add_imported_message(db, now, role, label, message_id, flags)
    unsafe_flags = {"is_ai_generated": True, "is_system": False}
    _add_imported_message(db, now, "a", "Synthetic A", "a-unsafe", unsafe_flags)
    db.commit()


def _add_imported_message(db, now, role, label, message_id, flags):
    timestamp = "2026-01-01T10:00:00Z"
    source_metadata = {}
    security_inputs = {"top_level": flags, "source_metadata": source_metadata}
    security_sources = derive_security_flags(
        {**flags, "source_metadata": source_metadata}
    ).source_map()
    content = (
        "I prefer to plan weekend activities and keep a flexible alternative. "
        f"This sample identifier is {message_id}."
    )
    if flags["is_ai_generated"]:
        content = "Synthetic AI-generated row must never be sent to the analyzer."
    metadata = {
        "canonical_contract_version": "wechat-canonical-v1",
        "canonical_message_id": message_id,
        "canonical_timestamp": timestamp,
        "timestamp_status": "parsed_utc",
        "message_type": "text",
        "content_status": "present",
        "is_ai_generated": flags["is_ai_generated"],
        "is_system": flags["is_system"],
        "security_flag_inputs": security_inputs,
        "security_flag_sources": security_sources,
    }
    db.add(
        ImportedMessage(
            id=f"database-{message_id}",
            source_id="synthetic-approved-source",
            external_id=message_id,
            speaker_label=label,
            speaker_role_id=f"role_{role}",
            text=content,
            sent_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            metadata_json=metadata,
        )
    )


def _completion_response(body: bytes) -> bytes:
    request = json.loads(body)
    messages = json.loads(request["messages"][1]["content"])
    evidence_ids = [item["message_id"] for item in messages[:2]]
    subject_id = "role_a" if evidence_ids[0].startswith("a-") else "role_b"
    payload = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "subject_id": subject_id,
        "traits": [
            {
                "category": "behavior_pattern",
                "claim": "倾向提前规划活动，并保留灵活的替代安排",
                "evidence_ids": evidence_ids,
                "counter_evidence_ids": [],
                "rationale": "多条样本呈现相似的计划和替代方案线索",
                "uncertainty": "当前样本范围有限，其他场景表现尚未知",
                "confidence": 0.84,
                "conflict_status": "none",
            }
        ],
    }
    result = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
    return json.dumps(result, ensure_ascii=False).encode("utf-8")


def _provider(transport, *, authorized=True):
    return OpenAICompatibleSemanticAnalyzer(
        SemanticProviderConfig(
            enabled=True,
            allow_message_content=True,
            endpoint="http://127.0.0.1:9999/v1/chat/completions",
            model="synthetic-only",
            api_key="not-a-real-secret",
            timeout_seconds=1,
        ),
        approved_source=authorized,
        transport=transport,
        sleeper=lambda _: None,
    )


def test_approved_synthetic_source_to_review_admission_publish(
    client, test_session_factory, monkeypatch
):
    db = test_session_factory()
    _seed_approved_source(db, transfer_authorized=True)
    sent_message_ids: list[list[str]] = []

    def transport(endpoint, body, headers, timeout):
        request = json.loads(body)
        records = json.loads(request["messages"][1]["content"])
        sent_message_ids.append([item["message_id"] for item in records])
        assert all(set(item) == {"message_id", "content"} for item in records)
        assert "a-unsafe" not in [item["message_id"] for item in records]
        assert "database-a-1" not in body.decode("utf-8")
        return _completion_response(body)

    monkeypatch.setattr(
        "app.profiles.source_contract.create_semantic_analyzer",
        lambda **kwargs: _provider(transport, authorized=kwargs["approved_source"]),
    )

    analyzed = client.post("/api/candidate/sources/synthetic-approved-source/analyze")
    assert analyzed.status_code == 200
    summary = analyzed.json()
    assert summary["semantic_status"] == "ready"
    assert summary["candidate_count"] >= 2
    assert {"a-unsafe"}.isdisjoint({item for ids in sent_message_ids for item in ids})

    snapshot = client.get(f"/api/candidate/snapshots/{summary['snapshot_id']}")
    assert snapshot.status_code == 200
    semantic = next(
        item for item in snapshot.json()["items"]
        if item["analyzer_name"] == "llm_semantic_openai_compatible"
        and item["subject_id"] == "role_a"
    )
    assert semantic["cognitive_state"] == "model_inferred"
    assert semantic["confidence"] == 0.84
    assert "Uncertainty:" in semantic["inference_basis"]
    assert {row["match_status"] for row in semantic["evidence"]} == {"matched"}
    assert all(row["direction"] == "supporting" for row in semantic["evidence"])

    reviewed = client.post(
        f"/api/candidate/items/{semantic['id']}/review",
        json={
            "to_status": "accepted",
            "expected_from_status": "pending",
            "reviewer_id": "synthetic-reviewer",
            "note": "Synthetic evidence review",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["confidence"] == 0.84
    assert db.scalar(select(ProfileVersion).where(ProfileVersion.role_id == "role_a")) is None

    admitted = client.post(f"/api/candidate/items/{semantic['id']}/admit")
    assert admitted.status_code == 200
    version_id = admitted.json()["profile_version_id"]
    draft = client.get(f"/api/roles/role_a/profiles/{version_id}").json()
    assert draft["status"] == "draft"
    trait = draft["traits"][0]
    assert trait["confidence_source"] == "analyzer_measurement"
    assert trait["evidence"]

    reviewed_trait = client.post(
        f"/api/roles/role_a/profiles/{version_id}/traits/{trait['id']}/review",
        json={"status": "accepted", "reviewer_note": "Synthetic formal review"},
    )
    assert reviewed_trait.status_code == 200
    published = client.post(f"/api/roles/role_a/profiles/{version_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "approved"
    context = client.get("/api/candidate/context/role_a")
    assert context.status_code == 200
    assert context.json()["readiness"] == "ready"


def test_source_without_transfer_authorization_never_calls_configured_provider(
    test_session_factory,
):
    from app.profiles.source_contract import analyze_and_persist_approved_source

    db = test_session_factory()
    _seed_approved_source(db, transfer_authorized=False)
    calls = {"count": 0}

    def transport(endpoint, body, headers, timeout):
        calls["count"] += 1
        return _completion_response(body)

    result = analyze_and_persist_approved_source(
        db,
        "synthetic-approved-source",
        semantic_analyzer=_provider(transport, authorized=False),
    )
    assert calls["count"] == 0
    assert result.semantic_status == "source_transfer_not_authorized"


def test_source_analysis_without_explicit_role_mapping_is_not_guessed(
    test_session_factory,
):
    db = test_session_factory()
    _seed_approved_source(db, transfer_authorized=True)
    message = db.scalar(select(ImportedMessage).where(ImportedMessage.external_id == "a-1"))
    message.speaker_role_id = None
    db.commit()
    records, role_map = canonical_rows_from_approved_source(db, "synthetic-approved-source")
    assert role_map == {"Synthetic A": "role_a", "Synthetic B": "role_b"}
    unmapped = next(item for item in records if item["message_id"] == "a-1")
    assert unmapped["sender"] is None
    try:
        build_canonical_dataset(records, role_map, source_id="synthetic-approved-source")
    except SourceContractError as exc:
        assert "canonical_sender_not_explicitly_mapped" in str(exc)
    else:
        raise AssertionError("unmapped message was assigned to a profile role")


def test_source_transfer_consent_requires_approved_source_and_can_be_revoked(
    client, test_session_factory
):
    db = test_session_factory()
    _seed_approved_source(db, transfer_authorized=False)
    authorized = client.post(
        "/api/imports/synthetic-approved-source/semantic-transfer-consent",
        json={"authorized": True, "reviewer_id": "synthetic-reviewer"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["semantic_llm_authorized"] is True
    db.refresh(db.get(Source, "synthetic-approved-source"))
    assert db.get(Source, "synthetic-approved-source").metadata_json[
        "semantic_llm_authorization"
    ]["reviewer_id"] == "synthetic-reviewer"

    revoked = client.post(
        "/api/imports/synthetic-approved-source/semantic-transfer-consent",
        json={"authorized": False, "reviewer_id": "synthetic-reviewer"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["semantic_llm_authorized"] is False
