"""会话编排器（conversation orchestrator）。

编排器只负责轮次、状态和持久化，不生成角色台词，也不接触浏览器或音频设备。
角色回复由 ``RoleAgent`` 负责，轮次选择由 ``DirectorAgent`` 负责。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.mock_agents import MockDirectorAgent, MockRoleAgent
from app.models import ConversationSession, ProfileTrait, ProfileVersion, Role, SessionEvent, Turn
from app.schemas.role import RoleProfile
from app.schemas.session import SessionRead

from .state_machine import SessionState


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
        if session.status in {SessionState.COMPLETED.value, SessionState.STOPPING.value}:
            return []
        role_ids = list(session.settings.get("role_ids", ["role_a", "role_b"]))
        plan = await self.director.plan_next(session.topic, session.turn_count, role_ids)
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
        approved_traits = list(
            self.db.scalars(
                select(ProfileTrait)
                .join(ProfileVersion, ProfileVersion.id == ProfileTrait.profile_version_id)
                .where(
                    ProfileVersion.role_id == role_id,
                    ProfileVersion.status == "approved",
                    ProfileTrait.review_status == "accepted",
                )
                .order_by(ProfileTrait.created_at)
            )
        )
        context = self._context(
            session.topic,
            list(reversed(previous)),
            [trait.description for trait in approved_traits],
        )
        text = await self.role_agent.respond(role_profile, context)
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
        }
        return [
            self.record_event("turn.created", payload),
            self.record_event("message.created", payload),
        ]

    def add_user_turn(self, text: str) -> list[dict[str, object]]:
        """保存用户插话，并将其作为下一轮 Agent 的上下文。"""
        session = self.session()
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
        session.status = SessionState.RUNNING.value
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
        return [
            self.record_event("turn.created", payload),
            self.record_event("message.created", payload),
        ]

    def stop(self) -> list[dict[str, object]]:
        """停止后续自动轮次；已完成消息不会被删除。"""
        session = self.session()
        if session.status not in {SessionState.COMPLETED.value, SessionState.ERROR.value}:
            stopping = self.set_state(SessionState.STOPPING)
            completed = self.set_state(SessionState.COMPLETED)
            return [stopping, completed]
        return [self.record_event("session.state", {"status": session.status})]

    @staticmethod
    def _context(topic: str, turns: list[Turn], traits: list[str]) -> str:
        transcript = "\n".join(f"{turn.speaker_role_id or 'user'}: {turn.text}" for turn in turns)
        profile = "；".join(traits) or "暂无已审核画像特征"
        return f"主题：{topic}\n画像：{profile}\n最近对话：\n{transcript}".strip()


def session_read(session: ConversationSession) -> SessionRead:
    """将 ORM 会话转换为稳定的 REST 响应。"""
    return SessionRead.model_validate(session)
