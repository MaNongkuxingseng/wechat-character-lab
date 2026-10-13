from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Role(Base):
    """可配置的模拟角色；角色差异通过数据配置驱动。"""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    profile: Mapped[str] = mapped_column(Text, nullable=False, default="")
    style_profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    voice_profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    consent_status: Mapped[str] = mapped_column(String(32), nullable=False, default="preset")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
