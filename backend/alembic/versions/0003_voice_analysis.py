"""新增本地媒体解析摘要表。"""

import sqlalchemy as sa

from alembic import op

revision = "0003_voice_analysis"
down_revision = "0002_profile_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_analyses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("role_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=True),
        sa.Column(
            "source_message_id",
            sa.String(length=36),
            sa.ForeignKey("imported_messages.id"),
            nullable=True,
        ),
        sa.Column("source_path", sa.Text(), nullable=False, unique=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("media_format", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("derived_from_video", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("rms_db", sa.Float(), nullable=True),
        sa.Column("silence_ratio", sa.Float(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_analyses_role_id", "voice_analyses", ["role_id"])
    op.create_index("ix_voice_analyses_source_message_id", "voice_analyses", ["source_message_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_analyses_source_message_id", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_role_id", table_name="voice_analyses")
    op.drop_table("voice_analyses")
