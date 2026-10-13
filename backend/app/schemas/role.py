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
