from typing import Literal

from pydantic import BaseModel, Field


class ClientPing(BaseModel):
    """会话客户端发送的连接存活检测。"""

    type: Literal["client.ping"]
    request_id: str | None = None


class UserMessageEvent(BaseModel):
    """用户文本事件契约；当前仅确认接收，尚未路由给 Agent。"""

    type: Literal["user.message"]
    text: str = Field(min_length=1, max_length=4000)
    client_message_id: str


class ConnectionReady(BaseModel):
    """服务端确认 WebSocket 会话连接成功的首个事件。"""

    type: Literal["connection.ready"] = "connection.ready"
    session_id: str
    seq: int = 0


class EventAccepted(BaseModel):
    """确认工程骨架中的事件已通过协议校验。"""

    type: Literal["event.accepted"] = "event.accepted"
    client_message_id: str
    seq: int = 0


class ConnectionPong(BaseModel):
    """服务端对客户端 ping 的响应。"""

    type: Literal["connection.pong"] = "connection.pong"
    request_id: str | None = None
    seq: int = 0


class ProtocolError(BaseModel):
    """返回给客户端的安全协议错误，不包含 Provider 或密钥细节。"""

    type: Literal["protocol.error"] = "protocol.error"
    code: str
    message: str
    seq: int = 0


ClientEvent = ClientPing | UserMessageEvent
