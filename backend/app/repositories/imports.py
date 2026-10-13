from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportedMessage, Source


def get_source(db: Session, source_id: str) -> Source | None:
    """读取单个导入来源。"""
    return db.get(Source, source_id)


def list_sources(db: Session) -> list[Source]:
    """按导入时间倒序返回来源。"""
    return list(db.scalars(select(Source).order_by(Source.imported_at.desc())))


def count_messages(db: Session, source_id: str) -> int:
    """统计来源已审核写入的标准化消息数量。"""
    statement = select(ImportedMessage.id).where(ImportedMessage.source_id == source_id)
    return len(db.scalars(statement).all())
