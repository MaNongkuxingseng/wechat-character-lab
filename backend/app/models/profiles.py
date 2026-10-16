from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProfileVersion(Base):
    """一个角色画像的草稿或已发布版本。"""

    __tablename__ = "profile_versions"
    __table_args__ = (
        UniqueConstraint("role_id", "version", name="uq_profile_role_version"),
        UniqueConstraint("source_candidate_item_id", name="uq_profile_version_candidate_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_candidate_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("profile_candidate_items.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    analyzer: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProfileTrait(Base):
    """一项带置信度和审核状态的画像观察或判断。"""

    __tablename__ = "profile_traits"
    __table_args__ = (
        CheckConstraint(
            "cognitive_state IN ('evidence_backed', 'model_inferred', 'unknown')",
            name="ck_profile_trait_cognitive_state",
        ),
        CheckConstraint(
            "conflict_status IN ('none', 'conflict', 'unresolved')",
            name="ck_profile_trait_conflict_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_version_id: Mapped[str] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    trait_key: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    cognitive_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    inference_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_status: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProfileEvidence(Base):
    """画像特征与一条原始消息之间的可追溯引用。"""

    __tablename__ = "profile_evidence"
    __table_args__ = (
        UniqueConstraint("trait_id", "message_id", name="uq_profile_evidence_trait_message"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trait_id: Mapped[str] = mapped_column(
        ForeignKey("profile_traits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("imported_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)
