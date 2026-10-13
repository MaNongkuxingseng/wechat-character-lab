from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Memory(Base):
    """经审核的人物事实或共同经历，可设为角色私有或显式共享。"""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
