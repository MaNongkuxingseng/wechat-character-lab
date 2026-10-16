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
        assert websocket.receive_json()["code"] == "invalid_session_state"
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
        assert websocket.receive_json()["type"] == "generation.cancelled"
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


def test_pause_user_resume_preserves_role_rotation(client, test_session_factory, monkeypatch):
    """暂停期间可插话；resume 后 B 接续 A，结束后操作明确报错。"""
    from sqlalchemy import select

    from app.models import Turn

    seed_roles(test_session_factory)
    created = client.post(
        "/api/sessions", json={"topic": "pause 测试", "turn_limit": 4, "turn_delay_seconds": 0.5}
    ).json()
    session_id = created["id"]
    monkeypatch.setattr(events_api, "SessionLocal", test_session_factory)

    def until(ws, event_type, **expected):
        for _ in range(20):
            event = ws.receive_json()
            if event["type"] == event_type and all(event.get(k) == v for k, v in expected.items()):
                return event
        raise AssertionError("未收到预期事件")

    with client.websocket_connect(f"/api/sessions/{session_id}/events") as ws:
        until(ws, "connection.ready")
        ws.send_json({"type": "session.start"})
        assert until(ws, "message.created")["speaker_role_id"] == "role_a"
        ws.send_json({"type": "session.pause"})
        until(ws, "session.state", status="paused")
        ws.send_json({"type": "user.message", "client_message_id": "u1", "text": "先听我说"})
        assert until(ws, "message.created")["speaker_role_id"] is None
        with test_session_factory() as db:
            assert db.get(ConversationSession, session_id).status == "paused"
        ws.send_json({"type": "client.ping", "request_id": "paused-check"})
        until(ws, "connection.pong", request_id="paused-check")
        ws.send_json({"type": "session.resume"})
        until(ws, "session.state", status="running")
        response = until(ws, "message.created")
        assert response["speaker_role_id"] == "role_b"
        assert "先听我说" in response["text"]
        assert until(ws, "message.created")["speaker_role_id"] == "role_a"
        until(ws, "session.state", status="completed")
        ws.send_json({"type": "session.start"})
        until(ws, "protocol.error", code="invalid_session_state")
        ws.send_json({"type": "user.message", "client_message_id": "u2", "text": "太晚了"})
        until(ws, "protocol.error", code="invalid_session_state")
    with test_session_factory() as db:
        turns = list(
            db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.sequence))
        )
        assert [turn.speaker_role_id for turn in turns] == ["role_a", None, "role_b", "role_a"]


def test_pause_cancels_inflight_generation(client, test_session_factory, monkeypatch):
    """慢 Provider 被 pause 取消后，不能持久化迟到回复。"""
    import asyncio
    import threading

    from sqlalchemy import func, select

    from app.agents.mock_agents import MockRoleAgent
    from app.models import Turn

    entered = threading.Event()
    cancelled = threading.Event()

    async def slow_respond(self, role, context):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    seed_roles(test_session_factory)
    created = client.post("/api/sessions", json={"topic": "取消测试"}).json()
    monkeypatch.setattr(events_api, "SessionLocal", test_session_factory)
    monkeypatch.setattr(MockRoleAgent, "respond", slow_respond)
    with client.websocket_connect(f"/api/sessions/{created['id']}/events") as ws:
        ws.receive_json()
        ws.send_json({"type": "session.start"})
        for _ in range(3):
            ws.receive_json()
        assert entered.wait(2)
        ws.send_json({"type": "session.pause"})
        assert ws.receive_json()["type"] == "generation.cancelled"
        assert ws.receive_json()["type"] == "event.accepted"
        assert ws.receive_json()["status"] == "paused"
        assert cancelled.wait(2)
        with test_session_factory() as db:
            assert db.scalar(select(func.count(Turn.id))) == 0
