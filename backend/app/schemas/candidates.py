from typing import Literal

from pydantic import BaseModel, Field


class CandidateReviewRequest(BaseModel):
    to_status: Literal["pending", "accepted", "rejected", "needs_review"]
    reviewer_id: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    decision_reason_code: str | None = Field(default=None, max_length=64)
    expected_from_status: str | None = None


class CandidateReviewResponse(BaseModel):
    candidate_id: str
    review_status: str
    reviewer_note: str | None


class CandidateAdmissionResponse(BaseModel):
    profile_version_id: str
    role_id: str
    version: int
    status: str
