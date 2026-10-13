from typing import Protocol

from app.schemas.role import RoleProfile


class RoleAgent(Protocol):
    """角色 Agent 契约；实现只接收组装好的上下文，不自行访问存储。"""

    async def respond(self, role: RoleProfile, context: str) -> str:
        """根据角色配置和已授权上下文生成一条回复。"""


class DirectorAgent(Protocol):
    """导演 Agent 契约；只规划对话控制信息，不生成角色台词。"""

    async def plan_next(
        self, topic: str, turn_count: int, role_ids: list[str]
    ) -> dict[str, object]:
        """返回下一位发言角色及本轮控制计划。"""
