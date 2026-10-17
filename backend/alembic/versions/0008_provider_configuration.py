"""Persist local provider configuration with an OS-protected secret blob."""

import sqlalchemy as sa

from alembic import op

revision = "0008_provider_configuration"
down_revision = "0007_profile_confidence_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_configuration",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("semantic_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "allow_message_content", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("dialogue_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "connection_test_status",
            sa.String(length=40),
            nullable=False,
            server_default="not_tested",
        ),
        sa.Column("connection_test_config_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "semantic_test_status",
            sa.String(length=40),
            nullable=False,
            server_default="not_tested",
        ),
        sa.Column("semantic_test_config_digest", sa.String(length=64), nullable=True),
        sa.Column("connection_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("semantic_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "config_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_configuration")
