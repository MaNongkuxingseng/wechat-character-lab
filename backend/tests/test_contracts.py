import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.mock_agents import MockDirectorAgent, MockRoleAgent
from app.ingestion.inbox_watcher import InboxWatcher
from app.ingestion.mock_bridge import MockBridgeAdapter
from app.ingestion.normalizer import normalize_message
from app.providers.asr_base import MockASRProvider
from app.providers.llm_base import MockLLMProvider
from app.providers.tts_base import MockTTSProvider
from app.schemas.message import NormalizedMessage
from app.schemas.role import RoleProfile
from app.schemas.session import SessionCreate


def test_session_schema_requires_two_distinct_roles():
    with pytest.raises(ValidationError):
        SessionCreate(topic="主题", role_ids=["role_a", "role_a"])


def test_mock_agents_keep_director_and_role_output_separate():
    role = RoleProfile(
        id="role_a",
        label="角色 A",
        profile="",
        style_profile={},
        voice_profile={},
        consent_status="preset",
    )

    assert "Mock 回复" in asyncio.run(MockRoleAgent().respond(role, "上下文"))
    plan = asyncio.run(MockDirectorAgent().plan_next("主题", 0, ["role_a", "role_b"]))
    assert plan["speaker_role_id"] == "role_a"
    assert "text" not in plan


def test_mock_providers_do_not_call_external_services():
    async def run() -> tuple[str, str, bytes, list[NormalizedMessage]]:
        return (
            await MockLLMProvider().generate("系统", "用户输入"),
            await MockASRProvider().transcribe(b"audio", "audio/wav"),
            await MockTTSProvider().synthesize("你好", "voice_a"),
            await MockBridgeAdapter().list_messages("source"),
        )

    llm_result, asr_result, tts_result, bridge_result = asyncio.run(run())
    assert llm_result.startswith("Mock 生成结果")
    assert asr_result.startswith("Mock")
    assert tts_result == b""
    assert bridge_result == []


def test_normalizer_trims_text_and_speaker():
    message = NormalizedMessage(external_id="m-1", speaker_label="  对方  ", text="  你好  ")

    normalized = normalize_message(message)

    assert normalized.speaker_label == "对方"
    assert normalized.text == "你好"
    assert message.text == "  你好  "


def test_inbox_watcher_discovers_only_zip_files(tmp_path: Path):
    (tmp_path / "b.ZIP").write_bytes(b"")
    (tmp_path / "a.zip").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "folder.zip").mkdir()

    found = InboxWatcher(tmp_path).discover_archives()

    assert [path.name for path in found] == ["a.zip", "b.ZIP"]
    assert InboxWatcher(tmp_path / "missing").discover_archives() == []
