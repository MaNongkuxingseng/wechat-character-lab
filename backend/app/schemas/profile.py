from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRead(BaseModel):
    """画像证据只返回目标角色有权查看的消息引用与必要摘录。"""

    message_id: str
    speaker_label: str
    sent_at: datetime | None
    excerpt: str
    rationale: str


class TraitRead(BaseModel):
    """可审核画像特征及其证据。"""

    id: str
    category: str
    key: str
    description: str
    confidence: float = Field(
        ge=0,
        le=1,
        description="当前统计分析器的样本支撑度，不代表人格判断为真的概率。",
    )
    context: str | None
    review_status: Literal["pending", "accepted", "rejected"]
    reviewer_note: str | None
    evidence: list[EvidenceRead]


class ProfileVersionRead(BaseModel):
    """画像版本详情；analyzer 标明生成方式，不暗示真实 LLM 已接入。"""

    id: str
    role_id: str
    version: int
    status: Literal["draft", "approved", "superseded"]
    analyzer: str
    sample_count: int
    created_at: datetime
    approved_at: datetime | None
    traits: list[TraitRead]


class ProfileVersionSummary(BaseModel):
    """用于画像版本列表的摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    role_id: str
    version: int
    status: Literal["draft", "approved", "superseded"]
    analyzer: str
    sample_count: int
    created_at: datetime
    approved_at: datetime | None


class TraitReviewRequest(BaseModel):
    """画像特征审核操作；可在接受前修订描述和适用场景。"""

    status: Literal["accepted", "rejected"]
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    context: str | None = Field(default=None, max_length=255)
    reviewer_note: str | None = Field(default=None, max_length=2000)
