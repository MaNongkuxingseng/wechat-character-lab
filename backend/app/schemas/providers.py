from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProviderConfigUpdate(BaseModel):
    provider_type: Literal["deepseek", "openai", "openai_compatible"] = "deepseek"
    endpoint: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    clear_api_key: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=120)
    semantic_enabled: bool = False
    allow_message_content: bool = False
    dialogue_enabled: bool = False


class ProviderConfigRead(BaseModel):
    configured: bool
    provider_type: str
    endpoint: str | None
    model: str | None
    api_key_configured: bool
    timeout_seconds: int
    semantic_enabled: bool
    allow_message_content: bool
    dialogue_enabled: bool
    env_overrides: list[str]
    connection_test_status: str
    semantic_test_status: str
    connection_tested_at: datetime | None
    semantic_tested_at: datetime | None
    config_updated_at: datetime | None


class ProviderTestResult(BaseModel):
    status: str
    provider_type: str
    model: str | None = None
    http_status: int | None = None
    detail_code: str | None = None
    available_models: list[str] = Field(default_factory=list)
    protocol_version: str | None = None
    signal_count: int | None = None
    api_key_configured: bool
    tested_at: datetime


class ProviderStatusRead(BaseModel):
    configured: bool
    connection_test_status: str
    semantic_test_status: str
    semantic_available: bool
    message_content_transfer_ready: bool
    dialogue_agent_implemented: bool = False
    dialogue_available: bool = False
    effective_config: ProviderConfigRead
