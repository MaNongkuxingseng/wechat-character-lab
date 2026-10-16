"""Add candidate cognition fields and enforce evidence deletion safety."""

import sqlalchemy as sa

from alembic import op

revision = "0005_profile_engine_contracts"
down_revision = "0004_profile_candidate_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profile_candidate_items", recreate="always") as batch:
        batch.add_column(
            sa.Column(
                "cognitive_state",
                sa.String(length=24),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.add_column(sa.Column("inference_basis", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "conflict_status", sa.String(length=24), nullable=False, server_default="none"
            )
        )
        batch.create_check_constraint(
            "ck_candidate_item_cognitive_state",
            "cognitive_state IN ('evidence_backed', 'model_inferred', 'unknown')",
        )
        batch.create_check_constraint(
            "ck_candidate_item_conflict_status",
            "conflict_status IN ('none', 'conflict', 'unresolved')",
        )
    with op.batch_alter_table("profile_traits", recreate="always") as batch:
        batch.add_column(
            sa.Column(
                "cognitive_state",
                sa.String(length=24),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.add_column(sa.Column("inference_basis", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "conflict_status", sa.String(length=24), nullable=False, server_default="none"
            )
        )
        batch.create_check_constraint(
            "ck_profile_trait_cognitive_state",
            "cognitive_state IN ('evidence_backed', 'model_inferred', 'unknown')",
        )
        batch.create_check_constraint(
            "ck_profile_trait_conflict_status",
            "conflict_status IN ('none', 'conflict', 'unresolved')",
        )
    with op.batch_alter_table("profile_versions", recreate="always") as batch:
        batch.add_column(sa.Column("source_candidate_item_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_profile_versions_source_candidate_item",
            "profile_candidate_items",
            ["source_candidate_item_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_profile_version_candidate_source", ["source_candidate_item_id"]
        )
    op.create_index(
        "ix_profile_versions_source_candidate_item_id",
        "profile_versions",
        ["source_candidate_item_id"],
    )
    op.create_table(
        "profile_candidate_unmatched_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("profile_candidate_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
    )
    op.create_index(
        "ix_profile_candidate_unmatched_evidence_snapshot_id",
        "profile_candidate_unmatched_evidence",
        ["snapshot_id"],
    )
    _rebuild_evidence_table(ondelete="RESTRICT")


def downgrade() -> None:
    _rebuild_evidence_table(ondelete="SET NULL")
    op.drop_index(
        "ix_profile_candidate_unmatched_evidence_snapshot_id",
        table_name="profile_candidate_unmatched_evidence",
    )
    op.drop_table("profile_candidate_unmatched_evidence")
    with op.batch_alter_table("profile_traits", recreate="always") as batch:
        batch.drop_constraint("ck_profile_trait_conflict_status", type_="check")
        batch.drop_constraint("ck_profile_trait_cognitive_state", type_="check")
        batch.drop_column("conflict_status")
        batch.drop_column("inference_basis")
        batch.drop_column("cognitive_state")
    op.drop_index("ix_profile_versions_source_candidate_item_id", table_name="profile_versions")
    with op.batch_alter_table("profile_versions", recreate="always") as batch:
        batch.drop_constraint("uq_profile_version_candidate_source", type_="unique")
        batch.drop_constraint("fk_profile_versions_source_candidate_item", type_="foreignkey")
        batch.drop_column("source_candidate_item_id")
    with op.batch_alter_table("profile_candidate_items", recreate="always") as batch:
        batch.drop_constraint("ck_candidate_item_conflict_status", type_="check")
        batch.drop_constraint("ck_candidate_item_cognitive_state", type_="check")
        batch.drop_column("conflict_status")
        batch.drop_column("inference_basis")
        batch.drop_column("cognitive_state")


def _rebuild_evidence_table(*, ondelete: str) -> None:
    """SQLite cannot alter an unnamed FK, so recreate this small candidate table."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        raise RuntimeError("candidate evidence migration currently supports SQLite only")

    op.create_table(
        "profile_candidate_evidence_new",
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
            sa.ForeignKey("imported_messages.id", ondelete=ondelete),
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
    op.execute(
        "INSERT INTO profile_candidate_evidence_new "
        "(id, candidate_id, direction, source_dataset_id, source_message_id, "
        "imported_message_id, quote_digest, rationale, match_status, invalid_reason, matched_at) "
        "SELECT id, candidate_id, direction, source_dataset_id, source_message_id, "
        "imported_message_id, quote_digest, rationale, match_status, invalid_reason, matched_at "
        "FROM profile_candidate_evidence"
    )
    op.drop_index(
        "ix_profile_candidate_evidence_imported_message_id", table_name="profile_candidate_evidence"
    )
    op.drop_index(
        "ix_profile_candidate_evidence_source_dataset_id", table_name="profile_candidate_evidence"
    )
    op.drop_index(
        "ix_profile_candidate_evidence_candidate_id", table_name="profile_candidate_evidence"
    )
    op.drop_table("profile_candidate_evidence")
    op.rename_table("profile_candidate_evidence_new", "profile_candidate_evidence")
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
