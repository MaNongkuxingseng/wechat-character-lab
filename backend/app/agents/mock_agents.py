from app.schemas.role import RoleProfile


class MockRoleAgent:
    """本地可运行的角色 Agent；不调用模型或外部服务。"""

    async def respond(self, role: RoleProfile, context: str) -> str:
        style = role.style_profile.get("summary") or role.profile or "保持自己的表达习惯"
        profile_line = next(
            (line for line in context.splitlines() if line.startswith("画像：")), ""
        )
        if profile_line and profile_line != "画像：暂无已审核画像特征":
            style = profile_line.removeprefix("画像：")
        topic = context.splitlines()[0].removeprefix("主题：") if context else "当前主题"
        return f"[{role.label} Mock 回复] 关于“{topic}”，我会按“{style}”来回应。"


class MockDirectorAgent:
    """本地导演替身；只返回控制计划，不生成台词。"""

    async def plan_next(
        self, topic: str, turn_count: int, role_ids: list[str]
    ) -> dict[str, object]:
        del topic
        return {
            "speaker_role_id": role_ids[turn_count % len(role_ids)],
            "intent": "mock_turn",
            "should_end": False,
        }
