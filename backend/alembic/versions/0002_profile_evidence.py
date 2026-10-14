"""新增带证据引用的角色画像版本与审核特征。"""

import sqlalchemy as sa

from alembic import op

revision = "0002_profile_evidence"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("role_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("analyzer", sa.String(length=64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("role_id", "version", name="uq_profile_role_version"),
    )
    op.create_index("ix_profile_versions_role_id", "profile_versions", ["role_id"])

    op.create_table(
        "profile_traits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "profile_version_id",
            sa.String(length=36),
            sa.ForeignKey("profile_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("trait_key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("context", sa.String(length=255), nullable=True),
        sa.Column("review_status", sa.String(length=24), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_profile_traits_profile_version_id", "profile_traits", ["profile_version_id"]
    )

    op.create_table(
        "profile_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "trait_id",
            sa.String(length=36),
            sa.ForeignKey("profile_traits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.String(length=36),
            sa.ForeignKey("imported_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rationale", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("trait_id", "message_id", name="uq_profile_evidence_trait_message"),
    )
    op.create_index("ix_profile_evidence_trait_id", "profile_evidence", ["trait_id"])
    op.create_index("ix_profile_evidence_message_id", "profile_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_evidence_message_id", table_name="profile_evidence")
    op.drop_index("ix_profile_evidence_trait_id", table_name="profile_evidence")
    op.drop_table("profile_evidence")
    op.drop_index("ix_profile_traits_profile_version_id", table_name="profile_traits")
    op.drop_table("profile_traits")
    op.drop_index("ix_profile_versions_role_id", table_name="profile_versions")
    op.drop_table("profile_versions")
