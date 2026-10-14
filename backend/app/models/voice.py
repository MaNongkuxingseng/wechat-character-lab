from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VoiceAnalysis(Base):
    """本地媒体解析摘要；不存储音频字节，只保留可追溯的分析结果。"""

    __tablename__ = "voice_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id"), nullable=True, index=True)
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("imported_messages.id"), nullable=True, index=True
    )
    source_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    media_format: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    derived_from_video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rms_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    silence_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
