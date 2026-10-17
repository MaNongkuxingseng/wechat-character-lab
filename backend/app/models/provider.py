from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProviderConfiguration(Base):
    """Single local provider configuration; the API key is DPAPI ciphertext only."""

    __tablename__ = "provider_configuration"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(nullable=False)
    semantic_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    allow_message_content: Mapped[bool] = mapped_column(nullable=False, default=False)
    dialogue_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    connection_test_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="not_tested"
    )
    connection_test_config_digest: Mapped[str | None] = mapped_column(String(64))
    semantic_test_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="not_tested"
    )
    semantic_test_config_digest: Mapped[str | None] = mapped_column(String(64))
    connection_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    semantic_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
