"""创建角色、会话、导入素材和记忆的初始数据库结构。"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("profile", sa.Text(), nullable=False, server_default=""),
        sa.Column("style_profile", sa.JSON(), nullable=False),
        sa.Column("voice_profile", sa.JSON(), nullable=False),
        sa.Column("consent_status", sa.String(length=32), nullable=False, server_default="preset"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("turn_limit", sa.Integer(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "speaker_role_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=True
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("interrupted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_turn_session_sequence"),
    )
    op.create_table(
        "session_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_event_session_sequence"),
    )
    op.create_table(
        "imported_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("speaker_label", sa.String(length=255), nullable=False),
        sa.Column(
            "speaker_role_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=True
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_message_source_external"),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_role_id", sa.String(length=64), sa.ForeignKey("roles.id"), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_message_ids", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.String),
            sa.column("label", sa.String),
            sa.column("profile", sa.Text),
            sa.column("style_profile", sa.JSON),
            sa.column("voice_profile", sa.JSON),
            sa.column("consent_status", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "id": "role_a",
                "label": "角色 A",
                "profile": "",
                "style_profile": {"reply_length": "medium", "emoji_usage": "some"},
                "voice_profile": {"provider": "mock", "voice_id": "voice_a"},
                "consent_status": "preset",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "id": "role_b",
                "label": "角色 B",
                "profile": "",
                "style_profile": {"reply_length": "medium", "emoji_usage": "some"},
                "voice_profile": {"provider": "mock", "voice_id": "voice_b"},
                "consent_status": "preset",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        ],
    )


def downgrade() -> None:
    for table_name in (
        "memories",
        "imported_messages",
        "session_events",
        "turns",
        "sources",
        "sessions",
        "roles",
    ):
        op.drop_table(table_name)
