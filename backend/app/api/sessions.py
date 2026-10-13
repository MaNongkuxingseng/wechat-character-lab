from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ConversationSession
from app.repositories.roles import get_roles_by_ids
from app.repositories.sessions import get_session
from app.schemas.session import SessionCreate, SessionRead

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> ConversationSession:
    """创建会话记录；当前不会启动对话或调用 Agent。"""
    roles = get_roles_by_ids(db, payload.role_ids)
    if len(roles) != len(payload.role_ids):
        found = {role.id for role in roles}
        missing = [role_id for role_id in payload.role_ids if role_id not in found]
        raise HTTPException(status_code=404, detail={"code": "role_not_found", "role_ids": missing})

    session = ConversationSession(
        id=str(uuid4()),
        mode=payload.mode,
        topic=payload.topic.strip(),
        status="created",
        turn_limit=payload.turn_limit,
        turn_count=0,
        settings={"role_ids": payload.role_ids},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionRead)
def read_session(session_id: str, db: Session = Depends(get_db)) -> ConversationSession:
    """读取会话状态与配置摘要。"""
    session = get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "session_not_found"})
    return session
