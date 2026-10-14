from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionCreate(BaseModel):
    """创建会话框架时接收的配置。"""

    mode: Literal["daily", "topic"] = "topic"
    topic: str = Field(min_length=1, max_length=500)
    turn_limit: int = Field(default=12, ge=2, le=100)
    role_ids: list[str] = Field(
        default_factory=lambda: ["role_a", "role_b"], min_length=2, max_length=2
    )

    @field_validator("role_ids")
    @classmethod
    def role_ids_must_be_distinct(cls, value: list[str]) -> list[str]:
        """防止双角色会话误用相同的角色 ID。"""
        if len(set(value)) != 2:
            raise ValueError("role_ids 必须包含两个不同的角色 ID")
        return value


class SessionRead(BaseModel):
    """稳定的会话响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    topic: str
    status: str
    turn_limit: int
    turn_count: int
    created_at: datetime
