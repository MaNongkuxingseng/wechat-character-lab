from typing import Protocol

from app.schemas.message import NormalizedMessage


class BridgeAdapter(Protocol):
    """WeChatBridge 接入契约；真实协议须以实际 API 文档为准。"""

    async def list_messages(self, source_id: str) -> list[NormalizedMessage]:
        """读取单一来源的标准化消息。"""
