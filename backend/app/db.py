from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(database_url: str | None = None):
    """创建 SQLAlchemy Engine；SQLite 按需启用跨线程连接参数。"""
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """创建请求级 SQLAlchemy Session，并在请求结束时关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
