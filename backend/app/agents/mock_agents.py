from app.schemas.role import RoleProfile


class MockRoleAgent:
    """用于契约测试的角色 Agent；不调用模型或外部服务。"""

    async def respond(self, role: RoleProfile, context: str) -> str:
        del context
        return f"[{role.label} Mock 回复]"


class MockDirectorAgent:
    """用于契约测试的导演；仅返回控制计划。"""

    async def plan_next(
        self, topic: str, turn_count: int, role_ids: list[str]
    ) -> dict[str, object]:
        del topic
        return {
            "speaker_role_id": role_ids[turn_count % len(role_ids)],
            "intent": "mock_turn",
            "should_end": False,
        }
