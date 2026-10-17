import asyncio
from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import Field, TypeAdapter, ValidationError

from app.core.orchestrator import ConversationOrchestrator, ProfileContextUnavailable
from app.core.state_machine import SessionState
from app.db import SessionLocal
from app.repositories.sessions import get_session
from app.schemas.events import (
    ClientEvent,
    ClientPing,
    ConnectionPong,
    ConnectionReady,
    EventAccepted,
    ProtocolError,
    SessionPauseEvent,
    SessionResumeEvent,
    SessionStartEvent,
    SessionStopEvent,
)

router = APIRouter(tags=["session-events"])
ClientEventAdapter = TypeAdapter(Annotated[ClientEvent, Field(discriminator="type")])


@router.websocket("/api/sessions/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: str) -> None:
    """驱动本地 Mock 对话；接收循环始终可取消后台生成（generation）。"""
    with SessionLocal() as db:
        exists = get_session(db, session_id) is not None
    if not exists:
        await websocket.close(code=4404, reason="session_not_found")
        return

    await websocket.accept()
    await websocket.send_json(ConnectionReady(session_id=session_id).model_dump())
    auto_task: asyncio.Task[None] | None = None

    async def cancel_auto_loop(reason: str) -> None:
        """先等待生成退出，再记录中断；保证不会写入迟到回复。"""
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
        with SessionLocal() as db:
            output = ConversationOrchestrator(db, session_id).record_event(
                "generation.cancelled", {"reason": reason}
            )
        await websocket.send_json(output)

    async def auto_loop(immediate: bool = False) -> None:
        """轮间保留等待窗口；暂停、插话、停止均可取消整个任务。"""
        try:
            while True:
                with SessionLocal() as db:
                    current = get_session(db, session_id)
                    if current is None or current.status != SessionState.RUNNING.value:
                        return
                    delay = float(current.settings.get("turn_delay_seconds", 4.0))
                if not immediate:
                    await asyncio.sleep(delay)
                immediate = False
                with SessionLocal() as db:
                    orchestrator = ConversationOrchestrator(db, session_id)
                    for output in await orchestrator.create_role_turn():
                        await websocket.send_json(output)
                    if orchestrator.session().status == SessionState.COMPLETED.value:
                        return
        except asyncio.CancelledError:
            raise
        except ProfileContextUnavailable as exc:
            with SessionLocal() as db:
                orchestrator = ConversationOrchestrator(db, session_id)
                if orchestrator.session().status == SessionState.RUNNING.value:
                    await websocket.send_json(orchestrator.set_state(SessionState.PAUSED))
            await websocket.send_json(
                ProtocolError(code="profile_unavailable", message=str(exc)).model_dump()
            )
        except Exception:
            # 不向客户端泄漏 Provider 内部异常或凭证，只报告可恢复状态。
            with SessionLocal() as db:
                orchestrator = ConversationOrchestrator(db, session_id)
                if orchestrator.session().status == SessionState.RUNNING.value:
                    await websocket.send_json(orchestrator.set_state(SessionState.ERROR))
            await websocket.send_json(
                ProtocolError(
                    code="generation_failed", message="角色生成失败，请新建会话。"
                ).model_dump()
            )

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
                await websocket.send_json(ConnectionPong(request_id=event.request_id).model_dump())
                continue

            with SessionLocal() as db:
                status = ConversationOrchestrator(db, session_id).session().status
            allowed = {SessionState.RUNNING.value, SessionState.PAUSED.value}
            if isinstance(event, SessionStartEvent):
                allowed = {SessionState.CREATED.value}
            elif isinstance(event, SessionPauseEvent):
                allowed = {SessionState.RUNNING.value}
            elif isinstance(event, SessionResumeEvent):
                allowed = {SessionState.PAUSED.value}
            elif isinstance(event, SessionStopEvent):
                allowed.add(SessionState.CREATED.value)
            if status not in allowed:
                await websocket.send_json(
                    ProtocolError(
                        code="invalid_session_state", message="当前会话状态不允许此操作。"
                    ).model_dump()
                )
                continue
            if event.type == "user.message" and not event.text.strip():
                await websocket.send_json(
                    ProtocolError(code="empty_message", message="插话不能为空。").model_dump()
                )
                continue

            # 取消操作在新事务之前完成，防止旧 ORM 快照覆盖新轮次计数。
            await cancel_auto_loop(event.type)
            with SessionLocal() as db:
                orchestrator = ConversationOrchestrator(db, session_id)
                if isinstance(event, SessionStartEvent):
                    outputs = [
                        orchestrator.set_state(SessionState.INITIALIZING),
                        orchestrator.set_state(SessionState.RUNNING),
                    ]
                elif isinstance(event, SessionPauseEvent):
                    outputs = [orchestrator.set_state(SessionState.PAUSED)]
                elif isinstance(event, SessionResumeEvent):
                    outputs = [orchestrator.set_state(SessionState.RUNNING)]
                elif isinstance(event, SessionStopEvent):
                    outputs = orchestrator.stop()
                else:
                    current = orchestrator.session()
                    if current.turn_count >= current.turn_limit:
                        outputs = [orchestrator.set_state(SessionState.COMPLETED)]
                        await websocket.send_json(
                            ProtocolError(
                                code="turn_limit", message="会话已达到轮次上限。"
                            ).model_dump()
                        )
                    else:
                        outputs = orchestrator.add_user_turn(event.text)
                await websocket.send_json(
                    EventAccepted(
                        client_message_id=event.client_message_id or event.type
                    ).model_dump()
                )
                for output in outputs:
                    await websocket.send_json(output)
                if orchestrator.session().status == SessionState.RUNNING.value:
                    auto_task = asyncio.create_task(auto_loop(isinstance(event, SessionStartEvent)))
    except WebSocketDisconnect:
        return
    finally:
        # 断线自动暂停（disconnect pause），保留已完成消息和恢复入口。
        if auto_task is not None and not auto_task.done():
            auto_task.cancel()
            try:
                await auto_task
            except asyncio.CancelledError:
                pass
        with SessionLocal() as db:
            orchestrator = ConversationOrchestrator(db, session_id)
            if orchestrator.session().status == SessionState.RUNNING.value:
                orchestrator.set_state(SessionState.PAUSED)
