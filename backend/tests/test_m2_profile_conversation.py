import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.orchestrator import ConversationOrchestrator, ProfileContextUnavailable
from app.core.state_machine import SessionState
from app.models import (
    ImportedMessage,
    ProfileEvidence,
    ProfileTrait,
    ProfileVersion,
    Role,
    SessionEvent,
    Source,
)


def _seed_roles_and_profiles(factory) -> None:
    now = datetime.now(UTC)
    with factory.begin() as db:
        db.add_all(
            [
                Role(
                    id=role_id,
                    label=role_id.upper(),
                    profile=f"unreviewed role profile {role_id}",
                    style_profile={"summary": f"unreviewed style {role_id}"},
                    voice_profile={"provider": "mock"},
                    consent_status="preset",
                    created_at=now,
                    updated_at=now,
                )
                for role_id in ("role_a", "role_b")
            ]
        )
    with factory.begin() as db:
        for role_id in ("role_a", "role_b"):
            source_id = f"m2-source-{role_id}"
            message_id = f"m2-message-{role_id}"
            version_id = f"m2-version-{role_id}"
            trait_id = f"m2-trait-{role_id}"
            db.add(
                Source(
                    id=source_id,
                    kind="synthetic",
                    name=source_id,
                    status="approved",
                    metadata_json={},
                )
            )
            db.flush()
            db.add(
                ImportedMessage(
                    id=message_id,
                    source_id=source_id,
                    external_id=message_id,
                    speaker_label=role_id,
                    speaker_role_id=role_id,
                    text=f"synthetic evidence {role_id}",
                    sent_at=now,
                    metadata_json={
                        "message_type": "text",
                        "is_ai_generated": False,
                        "is_system": False,
                    },
                )
            )
            db.add(
                ProfileVersion(
                    id=version_id,
                    role_id=role_id,
                    version=1,
                    status="approved",
                    analyzer="synthetic-test",
                    sample_count=1,
                    created_at=now,
                    approved_at=now,
                )
            )
            db.flush()
            db.add(
                ProfileTrait(
                    id=trait_id,
                    profile_version_id=version_id,
                    category="synthetic",
                    trait_key="stance",
                    description=f"{role_id} trait",
                    confidence=0.8,
                    cognitive_state="evidence_backed",
                    conflict_status="none",
                    review_status="accepted",
                    created_at=now,
                )
            )
            db.flush()
            db.add(
                ProfileEvidence(
                    id=f"m2-evidence-{role_id}",
                    trait_id=trait_id,
                    message_id=message_id,
                    rationale="synthetic evidence",
                )
            )


def test_session_creation_requires_published_profile(client, test_session_factory):
    now = datetime.now(UTC)
    with test_session_factory.begin() as db:
        db.add_all(
            [
                Role(
                    id=role_id,
                    label=role_id,
                    profile="",
                    style_profile={},
                    voice_profile={},
                    consent_status="preset",
                    created_at=now,
                    updated_at=now,
                )
                for role_id in ("role_a", "role_b")
            ]
        )
    response = client.post("/api/sessions", json={"topic": "synthetic"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_unavailable"


def test_orchestrator_uses_role_snapshot_and_records_context_usage(client, test_session_factory):
    _seed_roles_and_profiles(test_session_factory)
    created = client.post("/api/sessions", json={"topic": "synthetic", "turn_limit": 2}).json()
    session_id = created["id"]
    assert created["settings"]["provider"] == "mock"
    assert created["settings"]["profile_snapshots"]["role_a"]["trait_ids"] == ["m2-trait-role_a"]

    with test_session_factory() as db:
        orchestrator = ConversationOrchestrator(db, session_id)
        orchestrator.set_state(SessionState.INITIALIZING)
        orchestrator.set_state(SessionState.RUNNING)
        outputs = asyncio.run(orchestrator.create_role_turn())
        message = next(item for item in outputs if item["type"] == "message.created")
        assert message["speaker_role_id"] == "role_a"
        assert message["trait_ids"] == ["m2-trait-role_a"]
        assert "role_a trait" in message["text"]
        assert "unreviewed" not in message["text"]
        usage = list(
            db.scalars(select(SessionEvent).where(SessionEvent.type == "profile.context_used"))
        )
        assert len(usage) == 1
        assert usage[0].payload["trait_ids"] == ["m2-trait-role_a"]
        assert "synthetic evidence" not in str(usage[0].payload)


def test_source_revocation_blocks_next_role_generation(client, test_session_factory):
    _seed_roles_and_profiles(test_session_factory)
    created = client.post("/api/sessions", json={"topic": "synthetic", "turn_limit": 4}).json()
    session_id = created["id"]
    with test_session_factory() as db:
        orchestrator = ConversationOrchestrator(db, session_id)
        orchestrator.set_state(SessionState.INITIALIZING)
        orchestrator.set_state(SessionState.RUNNING)
        asyncio.run(orchestrator.create_role_turn())
        db.get(Source, "m2-source-role_b").status = "pending_review"
        db.commit()
        with pytest.raises(ProfileContextUnavailable, match="profile_unavailable:role_b"):
            asyncio.run(orchestrator.create_role_turn())
