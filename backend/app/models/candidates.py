"""JSONL 画像候选层的持久化模型（candidate persistence layer）。

候选层与正式 ProfileVersion/ProfileTrait/ProfileEvidence 分离。候选证据保留
JSONL 的 source_message_id；只有后续显式映射成功时，才填写 imported_message_id。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProfileCandidateSnapshot(Base):
    """一次 JSONL 分析输入和分析器清单对应的候选快照。"""

    __tablename__ = "profile_candidate_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_dataset_id",
            "input_digest",
            "analyzer_digest",
            name="uq_candidate_snapshot_input",
        ),
        CheckConstraint(
            "status IN ('draft', 'under_review', 'accepted', 'rejected', 'expired')",
            name="ck_candidate_snapshot_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_dataset_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role_scope: Mapped[list] = mapped_column(JSON, nullable=False)
    analyzer_manifest: Mapped[list] = mapped_column(JSON, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProfileCandidateItem(Base):
    """候选特征及其审核状态；不等同正式 ProfileTrait。"""

    __tablename__ = "profile_candidate_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "profile_item_id", name="uq_candidate_item_snapshot_item"),
        UniqueConstraint(
            "snapshot_id", "candidate_fingerprint", name="uq_candidate_item_fingerprint"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_candidate_item_confidence",
        ),
        CheckConstraint(
            "reviewer_confidence IS NULL OR "
            "(reviewer_confidence >= 0 AND reviewer_confidence <= 1)",
            name="ck_candidate_item_reviewer_confidence",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_item_review_status",
        ),
        CheckConstraint(
            "cognitive_state IN ('evidence_backed', 'model_inferred', 'unknown')",
            name="ck_candidate_item_cognitive_state",
        ),
        CheckConstraint(
            "conflict_status IN ('none', 'conflict', 'unresolved')",
            name="ck_candidate_item_conflict_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("profile_candidate_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cognitive_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    inference_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_status: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    analyzer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ProfileCandidateEvidence(Base):
    """候选特征的正向/反向证据和可选正式消息映射。"""

    __tablename__ = "profile_candidate_evidence"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "source_message_id", name="uq_candidate_evidence_source_message"
        ),
        CheckConstraint(
            "direction IN ('supporting', 'counter')", name="ck_candidate_evidence_direction"
        ),
        CheckConstraint(
            "match_status IN ('unmatched', 'matched', 'invalid')",
            name="ck_candidate_evidence_match_status",
        ),
        CheckConstraint(
            "(match_status = 'matched' AND imported_message_id IS NOT NULL) OR "
            "(match_status != 'matched' AND imported_message_id IS NULL)",
            name="ck_candidate_evidence_matched_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("profile_candidate_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    source_dataset_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("imported_messages.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    quote_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)
    match_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unmatched")
    invalid_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProfileCandidateUnmatchedEvidence(Base):
    """Rejected or unmatched analyzer evidence retained without chat text."""

    __tablename__ = "profile_candidate_unmatched_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("profile_candidate_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)


class ProfileCandidateReviewEvent(Base):
    """候选审核状态变更的不可变审计事件。"""

    __tablename__ = "profile_candidate_review_events"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_review_event_to_status",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_review_event_from_status",
        ),
        CheckConstraint(
            "reviewer_confidence_before IS NULL OR "
            "(reviewer_confidence_before >= 0 AND reviewer_confidence_before <= 1)",
            name="ck_candidate_review_event_reviewer_confidence_before",
        ),
        CheckConstraint(
            "reviewer_confidence_after IS NULL OR "
            "(reviewer_confidence_after >= 0 AND reviewer_confidence_after <= 1)",
            name="ck_candidate_review_event_reviewer_confidence_after",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("profile_candidate_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_confidence_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
