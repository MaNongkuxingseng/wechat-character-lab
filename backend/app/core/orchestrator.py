"""会话编排器（conversation orchestrator）。

编排器只负责轮次、状态和持久化，不生成角色台词，也不接触浏览器或音频设备。
角色回复由 ``RoleAgent`` 负责，轮次选择由 ``DirectorAgent`` 负责。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.mock_agents import MockDirectorAgent, MockRoleAgent
from app.agents.real_agent import RealRoleAgent
from app.models import ConversationSession, Role, SessionEvent, Turn
from app.profiles.consumer import RoleProfileContext, build_role_context
from app.profiles.provider_runtime import provider_config_digest, resolve_provider_config
from app.providers.openai_compatible import (
    DialogueProviderError,
    LLMGeneration,
    OpenAICompatibleLLMProvider,
)
from app.schemas.role import RoleProfile
from app.schemas.session import SessionRead

from .state_machine import SessionState, can_transition


class ProfileContextUnavailable(ValueError):
    """Raised when a session snapshot can no longer be used safely."""


class ConversationOrchestrator:
    """单个 WebSocket 会话使用的同步数据库编排器。"""

    def __init__(self, db: Session, session_id: str) -> None:
        self.db = db
        self.session_id = session_id
        self.director = MockDirectorAgent()
        self.role_agent = MockRoleAgent()

    def session(self) -> ConversationSession:
        session = self.db.get(ConversationSession, self.session_id)
        if session is None:
            raise LookupError("session_not_found")
        return session

    def next_sequence(self) -> int:
        current = self.db.scalar(
            select(SessionEvent.sequence)
            .where(SessionEvent.session_id == self.session_id)
            .order_by(SessionEvent.sequence.desc())
            .limit(1)
        )
        return int(current or 0) + 1

    def record_event(self, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        """写入可重放事件，并返回带 seq 的客户端事件。"""
        event = SessionEvent(
            session_id=self.session_id,
            sequence=self.next_sequence(),
            type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        self.db.add(event)
        self.db.commit()
        return {"type": event_type, "seq": event.sequence, **payload}

    def set_state(self, state: SessionState) -> dict[str, object]:
        session = self.session()
        if not can_transition(session.status, state):
            raise ValueError(f"不允许的会话状态转换：{session.status} -> {state.value}")
        session.status = state.value
        if state is SessionState.RUNNING and session.started_at is None:
            session.started_at = datetime.now(UTC)
        if state in {SessionState.COMPLETED, SessionState.ERROR}:
            session.ended_at = datetime.now(UTC)
        self.db.commit()
        return self.record_event("session.state", {"status": state.value})

    async def create_role_turn(self) -> list[dict[str, object]]:
        """生成下一条 A/B 回复；达到轮次上限时只发结束状态。"""
        session = self.session()
        if session.status != SessionState.RUNNING.value:
            return []
        role_ids = list(session.settings.get("role_ids", ["role_a", "role_b"]))
        # 角色轮换（role rotation）只统计角色消息，用户插话不改变 A/B 顺序。
        role_turn_count = (
            self.db.scalar(
                select(func.count(Turn.id)).where(
                    Turn.session_id == self.session_id, Turn.speaker_role_id.is_not(None)
                )
            )
            or 0
        )
        plan = await self.director.plan_next(session.topic, role_turn_count, role_ids)
        if bool(plan.get("should_end")) or session.turn_count >= session.turn_limit:
            return [self.set_state(SessionState.COMPLETED)]

        role_id = str(plan["speaker_role_id"])
        role = self.db.get(Role, role_id)
        if role is None:
            return [self.set_state(SessionState.ERROR)]
        role_profile = RoleProfile.model_validate(role)
        previous = list(
            self.db.scalars(
                select(Turn)
                .where(Turn.session_id == self.session_id)
                .order_by(Turn.sequence.desc())
                .limit(6)
            )
        )
        profile_context = self._profile_context(session, role_id)
        reviewed_profile = "；".join(feature.claim for feature in profile_context.features)
        role_profile = role_profile.model_copy(
            update={
                "profile": reviewed_profile,
                "style_profile": {"summary": reviewed_profile},
            }
        )
        context = self._context(
            session.topic,
            list(reversed(previous)),
            [feature.claim for feature in profile_context.features],
            intent=str(plan.get("intent") or "respond"),
        )
        provider_mode = str(session.settings.get("provider", "mock"))
        generation: LLMGeneration | None = None
        try:
            if provider_mode == "llm":
                provider = self._dialogue_provider(session)
                generation = await RealRoleAgent(provider).respond(role_profile, context)
                text = generation.text
            else:
                text = await self.role_agent.respond(role_profile, context)
                if not isinstance(text, str):
                    raise TypeError("mock_agent_response_not_text")
        except DialogueProviderError as exc:
            self.record_event(
                "generation.failed",
                {
                    "speaker_role_id": role_id,
                    "provider": session.settings.get("provider_type", "unknown"),
                    "model": session.settings.get("model"),
                    "status": "failed",
                    "error_code": exc.code,
                    "profile_version_id": profile_context.profile_version_id,
                    "trait_ids": list(profile_context.usage.get("trait_ids", [])),
                },
            )
            raise
        sequence = session.turn_count + 1
        turn = Turn(
            id=str(uuid4()),
            session_id=self.session_id,
            sequence=sequence,
            speaker_role_id=role_id,
            status="completed",
            text=text,
            interrupted=False,
            created_at=datetime.now(UTC),
        )
        session.turn_count = sequence
        session.status = SessionState.RUNNING.value
        self.db.add(turn)
        self.db.commit()
        payload = {
            "turn_id": turn.id,
            "turn": sequence,
            "speaker_role_id": role_id,
            "speaker_label": role.label,
            "text": text,
            "interrupted": False,
            "profile_version_id": profile_context.profile_version_id,
            "trait_ids": list(profile_context.usage.get("trait_ids", [])),
            "provider": generation.provider if generation else "mock",
            "model": generation.model if generation else None,
            "generation_status": "success",
            "latency_ms": generation.latency_ms if generation else 0,
            "trace_id": generation.trace_id if generation else None,
            "prompt_tokens": generation.prompt_tokens if generation else None,
            "completion_tokens": generation.completion_tokens if generation else None,
            "total_tokens": generation.total_tokens if generation else None,
        }
        outputs = [
            self.record_event("turn.created", payload),
            self.record_event("message.created", payload),
        ]
        if session.turn_count >= session.turn_limit:
            outputs.append(self.set_state(SessionState.COMPLETED))
        return outputs

    def _dialogue_provider(
        self, session: ConversationSession
    ) -> OpenAICompatibleLLMProvider:
        config = resolve_provider_config(self.db)
        if not config.configured:
            raise DialogueProviderError("provider_misconfigured")
        if not config.dialogue_enabled:
            raise DialogueProviderError("dialogue_disabled")
        expected = session.settings.get("provider_config_digest")
        if not expected or expected != provider_config_digest(config):
            raise DialogueProviderError("provider_config_changed")
        if session.settings.get("provider_type") != config.provider_type:
            raise DialogueProviderError("provider_config_changed")
        if session.settings.get("model") != config.model:
            raise DialogueProviderError("provider_config_changed")
        if config.connection_test_status != "success":
            raise DialogueProviderError("provider_not_verified")
        return OpenAICompatibleLLMProvider(config)

    def _profile_context(
        self, session: ConversationSession, role_id: str
    ) -> RoleProfileContext:
        # Legacy fixture sessions without a snapshot remain Mock-only demos;
        # API-created sessions always carry snapshots and are gated below.
        if "profile_snapshots" not in session.settings:
            return RoleProfileContext(role_id, "mock", "legacy_mock", None, (), {})
        context = build_role_context(self.db, role_id, session_id=self.session_id)
        if context.readiness != "ready" or context.profile_version_id is None:
            raise ProfileContextUnavailable(
                f"profile_unavailable:{role_id}:{context.readiness}"
            )
        snapshots = session.settings.get("profile_snapshots", {})
        expected = snapshots.get(role_id)
        if expected:
            actual_trait_ids = list(context.usage.get("trait_ids", []))
            if (
                expected.get("profile_version_id") != context.profile_version_id
                or expected.get("trait_ids", []) != actual_trait_ids
                or expected.get("readiness") != context.readiness
            ):
                raise ProfileContextUnavailable(f"profile_snapshot_stale:{role_id}")
        return context

    def add_user_turn(self, text: str) -> list[dict[str, object]]:
        """保存用户插话，并将其作为下一轮 Agent 的上下文。"""
        session = self.session()
        if session.status not in {SessionState.RUNNING.value, SessionState.PAUSED.value}:
            raise ValueError("当前会话不可插话")
        if not text.strip():
            raise ValueError("插话不能为空")
        if session.turn_count >= session.turn_limit:
            raise ValueError("会话已达到轮次上限")
        sequence = session.turn_count + 1
        turn = Turn(
            id=str(uuid4()),
            session_id=self.session_id,
            sequence=sequence,
            speaker_role_id=None,
            status="completed",
            text=text.strip(),
            interrupted=False,
            created_at=datetime.now(UTC),
        )
        session.turn_count = sequence
        self.db.add(turn)
        self.db.commit()
        payload = {
            "turn_id": turn.id,
            "turn": sequence,
            "speaker_role_id": None,
            "speaker_label": "我（用户插话）",
            "text": text.strip(),
            "interrupted": False,
        }
        outputs = [
            self.record_event("turn.created", payload),
            self.record_event("message.created", payload),
        ]
        if session.turn_count >= session.turn_limit:
            outputs.append(self.set_state(SessionState.COMPLETED))
        return outputs

    def stop(self) -> list[dict[str, object]]:
        """停止后续自动轮次；已完成消息不会被删除。"""
        session = self.session()
        if session.status not in {SessionState.COMPLETED.value, SessionState.ERROR.value}:
            stopping = self.set_state(SessionState.STOPPING)
            completed = self.set_state(SessionState.COMPLETED)
            return [stopping, completed]
        return [self.record_event("session.state", {"status": session.status})]

    @staticmethod
    def _context(topic: str, turns: list[Turn], traits: list[str], *, intent: str) -> str:
        transcript = "\n".join(f"{turn.speaker_role_id or 'user'}: {turn.text}" for turn in turns)
        profile = "；".join(traits) or "暂无已审核画像特征"
        return (
            f"主题：{topic}\n导演意图：{intent}\n画像：{profile}\n最近对话：\n{transcript}"
        ).strip()


def session_read(session: ConversationSession) -> SessionRead:
    """将 ORM 会话转换为稳定的 REST 响应。"""
    return SessionRead.model_validate(session)
