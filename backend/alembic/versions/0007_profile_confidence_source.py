"""Record whether formal-profile confidence is a measurement or reviewer score."""

import sqlalchemy as sa

from alembic import op

revision = "0007_profile_confidence_source"
down_revision = "0006_candidate_review_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_traits",
        sa.Column(
            "confidence_source",
            sa.String(length=32),
            sa.CheckConstraint(
                "confidence_source IN ('analyzer_measurement', 'reviewer_assessed')",
                name="ck_profile_trait_confidence_source",
            ),
            nullable=False,
            server_default="analyzer_measurement",
        ),
    )


def downgrade() -> None:
    op.drop_column("profile_traits", "confidence_source")
