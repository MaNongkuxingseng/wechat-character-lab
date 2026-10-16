"""新增 JSONL 画像候选持久化层。"""

import sqlalchemy as sa

from alembic import op

revision = "0004_profile_candidate_persistence"
down_revision = "0003_voice_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_candidate_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_dataset_id", sa.String(length=255), nullable=False),
        sa.Column("role_scope", sa.JSON(), nullable=False),
        sa.Column("analyzer_manifest", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("analyzer_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_dataset_id",
            "input_digest",
            "analyzer_digest",
            name="uq_candidate_snapshot_input",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'under_review', 'accepted', 'rejected', 'expired')",
            name="ck_candidate_snapshot_status",
        ),
    )
    op.create_index(
        "ix_profile_candidate_snapshots_source_dataset_id",
        "profile_candidate_snapshots",
        ["source_dataset_id"],
    )

    op.create_table(
        "profile_candidate_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("profile_candidate_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_item_id", sa.String(length=128), nullable=False),
        sa.Column("subject_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analyzer_name", sa.String(length=64), nullable=False),
        sa.Column("analyzer_version", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("candidate_fingerprint", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id", "profile_item_id", name="uq_candidate_item_snapshot_item"
        ),
        sa.UniqueConstraint(
            "snapshot_id", "candidate_fingerprint", name="uq_candidate_item_fingerprint"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_candidate_item_confidence",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_item_review_status",
        ),
    )
    op.create_index(
        "ix_profile_candidate_items_snapshot_id", "profile_candidate_items", ["snapshot_id"]
    )
    op.create_index(
        "ix_profile_candidate_items_subject_id", "profile_candidate_items", ["subject_id"]
    )

    op.create_table(
        "profile_candidate_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("profile_candidate_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=255), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "imported_message_id",
            sa.String(length=36),
            sa.ForeignKey("imported_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("quote_digest", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.String(length=500), nullable=False),
        sa.Column("match_status", sa.String(length=16), nullable=False, server_default="unmatched"),
        sa.Column("invalid_reason", sa.String(length=120), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "candidate_id", "source_message_id", name="uq_candidate_evidence_source_message"
        ),
        sa.CheckConstraint(
            "direction IN ('supporting', 'counter')", name="ck_candidate_evidence_direction"
        ),
        sa.CheckConstraint(
            "match_status IN ('unmatched', 'matched', 'invalid')",
            name="ck_candidate_evidence_match_status",
        ),
        sa.CheckConstraint(
            "(match_status = 'matched' AND imported_message_id IS NOT NULL) OR "
            "(match_status != 'matched' AND imported_message_id IS NULL)",
            name="ck_candidate_evidence_matched_reference",
        ),
    )
    op.create_index(
        "ix_profile_candidate_evidence_candidate_id",
        "profile_candidate_evidence",
        ["candidate_id"],
    )
    op.create_index(
        "ix_profile_candidate_evidence_source_dataset_id",
        "profile_candidate_evidence",
        ["source_dataset_id"],
    )
    op.create_index(
        "ix_profile_candidate_evidence_imported_message_id",
        "profile_candidate_evidence",
        ["imported_message_id"],
    )

    op.create_table(
        "profile_candidate_review_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("profile_candidate_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("reviewer_id", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decision_reason_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "to_status IN ('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_review_event_to_status",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('pending', 'accepted', 'rejected', 'needs_review')",
            name="ck_candidate_review_event_from_status",
        ),
    )
    op.create_index(
        "ix_profile_candidate_review_events_candidate_id",
        "profile_candidate_review_events",
        ["candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_candidate_review_events_candidate_id",
        table_name="profile_candidate_review_events",
    )
    op.drop_table("profile_candidate_review_events")
    op.drop_index(
        "ix_profile_candidate_evidence_imported_message_id",
        table_name="profile_candidate_evidence",
    )
    op.drop_index(
        "ix_profile_candidate_evidence_source_dataset_id",
        table_name="profile_candidate_evidence",
    )
    op.drop_index(
        "ix_profile_candidate_evidence_candidate_id",
        table_name="profile_candidate_evidence",
    )
    op.drop_table("profile_candidate_evidence")
    op.drop_index(
        "ix_profile_candidate_items_subject_id", table_name="profile_candidate_items"
    )
    op.drop_index(
        "ix_profile_candidate_items_snapshot_id", table_name="profile_candidate_items"
    )
    op.drop_table("profile_candidate_items")
    op.drop_index(
        "ix_profile_candidate_snapshots_source_dataset_id",
        table_name="profile_candidate_snapshots",
    )
    op.drop_table("profile_candidate_snapshots")
