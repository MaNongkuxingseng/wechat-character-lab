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

TOPIC_EXPRESSIONS = {
    "reconciliation": ("复合", "恢复关系", "重新在一起", "和好", "修复关系"),
}


def _matches_topic_expression(response: str, topic_key: str) -> bool:
    """测试关键词覆盖，不将关键词命中解释为完整语义理解。"""
    return any(expression in response for expression in TOPIC_EXPRESSIONS[topic_key])


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

    topic = "请求复合"
    response = asyncio.run(
        MockRoleAgent().respond(
            role,
            f"主题：{topic}\n导演意图：open\n画像：消息长度中位数 10 字；问句比例 4%\n最近对话：",
        )
    )
    assert response
    assert "复合" not in response
    assert _matches_topic_expression(response, "reconciliation")
    assert "消息长度中位数" not in response
    assert "Mock" in response
    plan = asyncio.run(MockDirectorAgent().plan_next("主题", 0, ["role_a", "role_b"]))
    assert plan["speaker_role_id"] == "role_a"
    assert plan["intent"] == "open"
    assert "text" not in plan


def test_topic_expression_check_rejects_an_off_topic_reply():
    off_topic_response = "明天一起讨论天气和菜单。"

    assert not _matches_topic_expression(off_topic_response, "reconciliation")


def test_mock_role_agent_responds_to_user_context_and_role_difference():
    context = (
        "主题：请求复合\n导演意图：clarify\n画像：暂无已审核画像特征\n"
        "最近对话：\nuser: 我希望这次能把边界说清楚"
    )
    role_a = RoleProfile(
        id="role_a",
        label="角色 A",
        profile="",
        style_profile={},
        voice_profile={},
        consent_status="preset",
    )
    role_b = role_a.model_copy(update={"id": "role_b", "label": "角色 B"})

    response_a = asyncio.run(MockRoleAgent().respond(role_a, context))
    response_b = asyncio.run(MockRoleAgent().respond(role_b, context))

    assert "边界说清楚" in response_a
    assert "边界说清楚" in response_b
    assert response_a != response_b


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


def test_voice_asset_schema_is_local_only():
    """语音资产契约只描述本地清单，不携带音频字节。"""
    from app.api.voice import voice_assets

    payload = voice_assets()

    assert set(payload) == {"available", "format", "count", "bytes_total", "files"}
    assert payload["format"] == "SILK"
    assert all("data" not in item for item in payload["files"])


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
