from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import Field, TypeAdapter, ValidationError

from app.db import SessionLocal
from app.repositories.sessions import get_session
from app.schemas.events import (
    ClientPing,
    ConnectionPong,
    ConnectionReady,
    EventAccepted,
    ProtocolError,
    UserMessageEvent,
)

router = APIRouter(tags=["session-events"])
ClientEventAdapter = TypeAdapter(
    Annotated[ClientPing | UserMessageEvent, Field(discriminator="type")]
)


@router.websocket("/api/sessions/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: str) -> None:
    """建立会话事件连接；当前验证协议并确认消息，不触发 Agent。"""
    with SessionLocal() as db:
        exists = get_session(db, session_id) is not None
    if not exists:
        await websocket.close(code=4404, reason="session_not_found")
        return

    await websocket.accept()
    await websocket.send_json(ConnectionReady(session_id=session_id).model_dump())
    try:
        while True:
            raw_event = await websocket.receive_json()
            try:
                event = ClientEventAdapter.validate_python(raw_event)
            except ValidationError:
                await websocket.send_json(
                    ProtocolError(code="invalid_event", message="事件格式不符合协议").model_dump()
                )
                continue

            if isinstance(event, ClientPing):
                response = ConnectionPong(request_id=event.request_id)
            else:
                response = EventAccepted(client_message_id=event.client_message_id)
            await websocket.send_json(response.model_dump())
    except WebSocketDisconnect:
        return
