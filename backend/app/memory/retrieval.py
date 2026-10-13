from typing import Protocol


class MemoryRetriever(Protocol):
    """记忆检索契约；调用方必须明确提供允许访问记忆的角色 ID。"""

    def retrieve(self, owner_role_id: str, query: str, limit: int = 8) -> list[str]:
        """只返回指定角色的私有记忆及显式共享记忆。"""
