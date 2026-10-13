from datetime import datetime

from pydantic import BaseModel, Field


class NormalizedMessage(BaseModel):
    """与来源适配器无关的标准化消息结构。"""

    external_id: str = Field(min_length=1, max_length=255)
    speaker_label: str = Field(min_length=1, max_length=255)
    text: str
    sent_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
