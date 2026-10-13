from app.schemas.message import NormalizedMessage


class MockBridgeAdapter:
    """WeChatBridge Mock；不连接服务，也不读取本机聊天数据。"""

    async def list_messages(self, source_id: str) -> list[NormalizedMessage]:
        del source_id
        return []
