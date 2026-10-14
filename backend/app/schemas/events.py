from typing import Literal

from pydantic import BaseModel, Field


class ClientPing(BaseModel):
    """会话客户端发送的连接存活检测。"""

    type: Literal["client.ping"]
    request_id: str | None = None


class UserMessageEvent(BaseModel):
    """用户插话事件；会保存为独立的用户 Turn，并触发下一位角色回复。"""

    type: Literal["user.message"]
    text: str = Field(min_length=1, max_length=4000)
    client_message_id: str


class SessionStartEvent(BaseModel):
    """启动 A/B 自动轮流对话。"""

    type: Literal["session.start"]
    client_message_id: str | None = None


class SessionStopEvent(BaseModel):
    """停止后续自动轮次。"""

    type: Literal["session.stop"]
    client_message_id: str | None = None


class ConnectionReady(BaseModel):
    """服务端确认 WebSocket 会话连接成功的首个事件。"""

    type: Literal["connection.ready"] = "connection.ready"
    session_id: str
    seq: int = 0


class EventAccepted(BaseModel):
    """确认客户端事件已通过协议校验并进入编排器。"""

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


ClientEvent = ClientPing | UserMessageEvent | SessionStartEvent | SessionStopEvent
