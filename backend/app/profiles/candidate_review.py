"""Candidate review state transitions and append-only review events."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ProfileCandidateItem, ProfileCandidateReviewEvent

VALID_STATUSES = {"pending", "accepted", "rejected", "needs_review"}
TRANSITIONS: Mapping[str, set[str]] = {
    "pending": {"accepted", "rejected", "needs_review"},
    "needs_review": {"pending", "accepted", "rejected"},
    "accepted": {"accepted"},
    "rejected": {"rejected"},
}


class ReviewConflictError(ValueError):
    """Raised when the candidate changed since the caller read it."""


def review_candidate_item(
    db: Session,
    candidate_id: str,
    *,
    to_status: str,
    reviewer_id: str | None = None,
    note: str | None = None,
    decision_reason_code: str | None = None,
    expected_from_status: str | None = None,
) -> ProfileCandidateItem:
    if to_status not in VALID_STATUSES:
        raise ValueError("invalid candidate review status")
    item = db.scalar(
        select(ProfileCandidateItem)
        .where(ProfileCandidateItem.id == candidate_id)
        .with_for_update()
    )
    if item is None:
        raise LookupError("candidate_not_found")
    if expected_from_status is not None and item.review_status != expected_from_status:
        raise ReviewConflictError("candidate_status_changed")
    if to_status not in TRANSITIONS[item.review_status]:
        raise ValueError(f"invalid candidate transition: {item.review_status} -> {to_status}")
    if to_status == item.review_status:
        return item

    event = ProfileCandidateReviewEvent(
        id=str(uuid4()),
        candidate_id=item.id,
        from_status=item.review_status,
        to_status=to_status,
        reviewer_id=reviewer_id,
        note=note,
        decision_reason_code=decision_reason_code,
        created_at=datetime.now(UTC),
    )
    try:
        result = db.execute(
            update(ProfileCandidateItem)
            .where(
                ProfileCandidateItem.id == item.id,
                ProfileCandidateItem.review_status == event.from_status,
            )
            .values(review_status=to_status, reviewer_note=note)
        )
        if result.rowcount != 1:
            raise ReviewConflictError("candidate_status_changed")
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(item)
    return item
