from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.api import events as events_api
from app.models import ConversationSession, Role


def seed_roles(factory: sessionmaker[Session]) -> None:
    """为 API 测试写入最小 A/B 角色配置。"""
    with factory.begin() as db:
        for role_id, label in (("role_a", "角色 A"), ("role_b", "角色 B")):
            db.add(
                Role(
                    id=role_id,
                    label=label,
                    profile="",
                    style_profile={},
                    voice_profile={"provider": "mock"},
                    consent_status="preset",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )


def test_health_and_roles(client, test_session_factory):
    seed_roles(test_session_factory)

    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/api/roles")

    assert response.status_code == 200
    assert [role["id"] for role in response.json()] == ["role_a", "role_b"]


def test_create_and_read_session(client, test_session_factory):
    seed_roles(test_session_factory)
    created = client.post("/api/sessions", json={"topic": "AI 与日常工作"})

    assert created.status_code == 201
    session_id = created.json()["id"]
    assert created.json()["status"] == "created"
    assert client.get(f"/api/sessions/{session_id}").json()["topic"] == "AI 与日常工作"


def test_session_rejects_unknown_role(client, test_session_factory):
    seed_roles(test_session_factory)

    response = client.post(
        "/api/sessions",
        json={"topic": "主题", "role_ids": ["role_a", "missing"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "role_not_found"


def test_role_update_persists_profile(client, test_session_factory):
    seed_roles(test_session_factory)

    response = client.put(
        "/api/roles/role_a",
        json={"label": "我的角色", "profile": "偏好简短、直接的表达"},
    )

    assert response.status_code == 200
    assert response.json()["label"] == "我的角色"
    assert response.json()["profile"] == "偏好简短、直接的表达"


def test_role_update_returns_not_found_for_unknown_role(client, test_session_factory):
    seed_roles(test_session_factory)

    response = client.put("/api/roles/missing", json={"label": "不存在"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "role_not_found"


def test_websocket_validates_and_acknowledges_events(client, test_session_factory, monkeypatch):
    seed_roles(test_session_factory)
    session_id = "test-session"
    with test_session_factory.begin() as db:
        db.add(
            ConversationSession(
                id=session_id,
                mode="topic",
                topic="主题",
                status="created",
                turn_limit=12,
                turn_count=0,
                settings={"role_ids": ["role_a", "role_b"]},
            )
        )
    monkeypatch.setattr(events_api, "SessionLocal", test_session_factory)

    with client.websocket_connect(f"/api/sessions/{session_id}/events") as websocket:
        assert websocket.receive_json()["type"] == "connection.ready"
        websocket.send_json({"type": "client.ping", "request_id": "ping-1"})
        assert websocket.receive_json()["type"] == "connection.pong"
        websocket.send_json({"type": "user.message", "client_message_id": "msg-1", "text": "你好"})
        assert websocket.receive_json()["type"] == "event.accepted"
        websocket.send_json({"type": "unsupported.event"})
        assert websocket.receive_json()["code"] == "invalid_event"


def test_websocket_runs_mock_turns_and_accepts_stop(client, test_session_factory, monkeypatch):
    seed_roles(test_session_factory)
    session_id = "running-session"
    with test_session_factory.begin() as db:
        db.add(
            ConversationSession(
                id=session_id,
                mode="topic",
                topic="本地测试",
                status="created",
                turn_limit=4,
                turn_count=0,
                settings={"role_ids": ["role_a", "role_b"]},
            )
        )
    monkeypatch.setattr(events_api, "SessionLocal", test_session_factory)

    with client.websocket_connect(f"/api/sessions/{session_id}/events") as websocket:
        assert websocket.receive_json()["type"] == "connection.ready"
        websocket.send_json({"type": "session.start", "client_message_id": "start-1"})
        assert websocket.receive_json()["type"] == "event.accepted"
        assert websocket.receive_json()["type"] == "session.state"
        assert websocket.receive_json()["type"] == "session.state"
        first_turn = websocket.receive_json()
        assert first_turn["type"] == "turn.created"
        assert first_turn["speaker_role_id"] == "role_a"
        assert websocket.receive_json()["type"] == "message.created"
        websocket.send_json({"type": "user.message", "client_message_id": "user-1", "text": "插话"})
        assert websocket.receive_json()["type"] == "event.accepted"
        assert websocket.receive_json()["type"] == "turn.created"
        assert websocket.receive_json()["type"] == "message.created"
        websocket.send_json({"type": "session.stop", "client_message_id": "stop-1"})
        stop_events = []
        while True:
            event = websocket.receive_json()
            stop_events.append(event)
            if event["type"] == "session.state" and event.get("status") == "completed":
                break
        stop_types = [event["type"] for event in stop_events]
        assert "event.accepted" in stop_types
        assert stop_types.count("session.state") >= 2
        with test_session_factory() as db:
            assert db.get(ConversationSession, session_id).status == "completed"


def test_voice_mock_endpoints_are_explicit(client):
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("sample.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["text"].startswith("Mock")

    response = client.post("/api/voice/synthesize", json={"text": "你好", "voice_id": "preset-a"})
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["audio_url"] is None


def test_voice_analysis_contract_reports_local_capabilities(client):
    capabilities = client.get("/api/voice/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["media_analysis"] == {
        "provider": "local",
        "available": True,
        "silk_decoder": False,
        "video_audio": True,
    }

    response = client.get("/api/voice/analyses")
    assert response.status_code == 200
    assert response.json() == {"items": []}
