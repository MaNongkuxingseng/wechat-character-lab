import asyncio
from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import Field, TypeAdapter, ValidationError

from app.core.orchestrator import ConversationOrchestrator
from app.core.state_machine import SessionState
from app.db import SessionLocal
from app.repositories.sessions import get_session
from app.schemas.events import (
    ClientPing,
    ConnectionPong,
    ConnectionReady,
    EventAccepted,
    ProtocolError,
    SessionStartEvent,
    SessionStopEvent,
    UserMessageEvent,
)

router = APIRouter(tags=["session-events"])
ClientEventAdapter = TypeAdapter(
    Annotated[
        ClientPing | UserMessageEvent | SessionStartEvent | SessionStopEvent,
        Field(discriminator="type"),
    ]
)


@router.websocket("/api/sessions/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: str) -> None:
    """建立会话事件连接，并驱动本地 Mock A/B 对话编排。"""
    with SessionLocal() as db:
        exists = get_session(db, session_id) is not None
    if not exists:
        await websocket.close(code=4404, reason="session_not_found")
        return

    await websocket.accept()
    await websocket.send_json(ConnectionReady(session_id=session_id).model_dump())
    auto_task: asyncio.Task[None] | None = None
    generation_lock = asyncio.Lock()

    async def cancel_auto_loop() -> None:
        """等待后台轮次真正退出，避免停止后仍向客户端发送迟到事件。"""
        nonlocal auto_task
        if auto_task is None or auto_task.done():
            auto_task = None
            return
        auto_task.cancel()
        try:
            await auto_task
        except asyncio.CancelledError:
            pass
        auto_task = None

    async def auto_loop() -> None:
        """持续推进 A/B 轮次；取消任务即可停止迟到输出。"""
        while True:
            await asyncio.sleep(0.45)
            async with generation_lock:
                with SessionLocal() as db:
                    orchestrator = ConversationOrchestrator(db, session_id)
                    current = orchestrator.session()
                    if current.status != SessionState.RUNNING.value:
                        return
                    outputs = await orchestrator.create_role_turn()
                    for output in outputs:
                        await websocket.send_json(output)
                    if orchestrator.session().status == SessionState.COMPLETED.value:
                        return

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
                await websocket.send_json(response.model_dump())
                continue

            with SessionLocal() as db:
                orchestrator = ConversationOrchestrator(db, session_id)
                if isinstance(event, SessionStartEvent):
                    accepted = EventAccepted(
                        client_message_id=event.client_message_id or "session-start"
                    )
                    await websocket.send_json(accepted.model_dump())
                    await websocket.send_json(orchestrator.set_state(SessionState.INITIALIZING))
                    await websocket.send_json(orchestrator.set_state(SessionState.RUNNING))
                    async with generation_lock:
                        for output in await orchestrator.create_role_turn():
                            await websocket.send_json(output)
                    if auto_task is None or auto_task.done():
                        auto_task = asyncio.create_task(auto_loop())
                    continue
                if isinstance(event, SessionStopEvent):
                    accepted = EventAccepted(
                        client_message_id=event.client_message_id or "session-stop"
                    )
                    await websocket.send_json(accepted.model_dump())
                    await cancel_auto_loop()
                    for output in orchestrator.stop():
                        await websocket.send_json(output)
                    continue

                response = EventAccepted(client_message_id=event.client_message_id)
                await websocket.send_json(response.model_dump())
                was_running = orchestrator.session().status == SessionState.RUNNING.value
                if was_running:
                    async with generation_lock:
                        user_outputs = orchestrator.add_user_turn(event.text)
                        for output in user_outputs:
                            await websocket.send_json(output)
                        current_session = orchestrator.session()
                        if current_session.turn_count < current_session.turn_limit:
                            for output in await orchestrator.create_role_turn():
                                await websocket.send_json(output)
    except WebSocketDisconnect:
        await cancel_auto_loop()
        return
