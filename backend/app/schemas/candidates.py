import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CandidateReviewRequest(BaseModel):
    to_status: Literal["pending", "accepted", "rejected", "needs_review"]
    reviewer_id: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    decision_reason_code: str | None = Field(default=None, max_length=64)
    expected_from_status: str | None = None
    reviewer_confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("reviewer_confidence", mode="before")
    @classmethod
    def validate_reviewer_confidence(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("reviewer_confidence must be a numeric JSON value")
        if not math.isfinite(float(value)):
            raise ValueError("reviewer_confidence must be finite")
        return float(value)


class CandidateReviewResponse(BaseModel):
    candidate_id: str
    review_status: str
    reviewer_note: str | None
    confidence: float | None
    reviewer_confidence: float | None


class CandidateAdmissionResponse(BaseModel):
    profile_version_id: str
    role_id: str
    version: int
    status: str


class CandidateSourceAnalysisResponse(BaseModel):
    source_id: str
    snapshot_id: str
    created: bool
    status: str
    semantic_status: str
    analyzer_statuses: list[dict[str, object]]
    role_statuses: dict[str, str]
    sample_counts: dict[str, int]
    candidate_count: int
    evidence_count: int
    mapping_count: int
    mapping_issue_count: int
    unmatched_count: int
