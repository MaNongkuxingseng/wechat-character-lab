from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RoleProfile(BaseModel):
    """角色 API 返回的公开配置结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    profile: str
    style_profile: dict[str, object] = Field(default_factory=dict)
    voice_profile: dict[str, object] = Field(default_factory=dict)
    consent_status: str


class RoleUpdate(BaseModel):
    """角色资料更新请求；未提供的字段保持原值。"""

    label: str | None = Field(default=None, min_length=1, max_length=80)
    profile: str | None = Field(default=None, max_length=8000)
    style_profile: dict[str, object] | None = None
    voice_profile: dict[str, object] | None = None
    consent_status: Literal["preset", "authorized", "unverified"] | None = None
