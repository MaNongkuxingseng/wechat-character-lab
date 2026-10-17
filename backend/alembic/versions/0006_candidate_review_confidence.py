"""Record reviewer confidence revisions on candidate review events."""

import sqlalchemy as sa

from alembic import op

revision = "0006_candidate_review_confidence"
down_revision = "0005_profile_engine_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_candidate_items",
        sa.Column(
            "reviewer_confidence",
            sa.Float(),
            sa.CheckConstraint(
                "reviewer_confidence IS NULL OR "
                "(reviewer_confidence >= 0 AND reviewer_confidence <= 1)",
                name="ck_candidate_item_reviewer_confidence",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "profile_candidate_review_events",
        sa.Column(
            "reviewer_confidence_before",
            sa.Float(),
            sa.CheckConstraint(
                "reviewer_confidence_before IS NULL OR "
                "(reviewer_confidence_before >= 0 AND reviewer_confidence_before <= 1)",
                name="ck_candidate_review_event_reviewer_confidence_before",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "profile_candidate_review_events",
        sa.Column(
            "reviewer_confidence_after",
            sa.Float(),
            sa.CheckConstraint(
                "reviewer_confidence_after IS NULL OR "
                "(reviewer_confidence_after >= 0 AND reviewer_confidence_after <= 1)",
                name="ck_candidate_review_event_reviewer_confidence_after",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("profile_candidate_review_events", "reviewer_confidence_after")
    op.drop_column("profile_candidate_review_events", "reviewer_confidence_before")
    op.drop_column("profile_candidate_items", "reviewer_confidence")
