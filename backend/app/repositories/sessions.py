from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConversationSession


def get_session(db: Session, session_id: str) -> ConversationSession | None:
    """按主键读取会话。"""
    return db.scalar(select(ConversationSession).where(ConversationSession.id == session_id))
