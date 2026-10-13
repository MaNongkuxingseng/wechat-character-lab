from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Source(Base):
    """导入归档或未来 Bridge API 来源，并记录审核状态。"""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImportedMessage(Base):
    """标准化后的导入消息，使用来源内稳定键进行去重。"""

    __tablename__ = "imported_messages"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_message_source_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    speaker_label: Mapped[str] = mapped_column(String(255), nullable=False)
    speaker_role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
