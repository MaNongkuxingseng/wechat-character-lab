from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileCandidateReviewEvent,
    ProfileCandidateSnapshot,
    ProfileCandidateUnmatchedEvidence,
)
from app.profiles.admission import AdmissionError, admit_candidate_item
from app.profiles.candidate_persistence import CandidatePersistenceError
from app.profiles.candidate_review import ReviewConflictError, review_candidate_item
from app.profiles.consumer import build_role_context
from app.profiles.source_contract import SourceContractError, analyze_and_persist_approved_source
from app.schemas.candidates import (
    CandidateAdmissionResponse,
    CandidateReviewRequest,
    CandidateReviewResponse,
    CandidateSourceAnalysisResponse,
)

router = APIRouter(prefix="/api/candidate", tags=["candidate-profiles"])


@router.post("/sources/{source_id}/analyze", response_model=CandidateSourceAnalysisResponse)
def analyze_approved_source(
    source_id: str, db: Session = Depends(get_db)
) -> CandidateSourceAnalysisResponse:
    """Analyze one explicitly approved source with local Observable analysis only."""
    try:
        result = analyze_and_persist_approved_source(db, source_id)
    except SourceContractError as exc:
        code = str(exc)
        status_code = 404 if code == "source_not_found" else 409
        raise HTTPException(status_code=status_code, detail={"code": code}) from exc
    except CandidatePersistenceError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    persisted = result.persistence
    return CandidateSourceAnalysisResponse(
        source_id=source_id,
        snapshot_id=persisted.snapshot_id,
        created=persisted.created,
        status=result.analysis_status,
        role_statuses=dict(result.role_statuses),
        sample_counts=dict(result.sample_counts),
        candidate_count=persisted.candidate_count,
        evidence_count=persisted.evidence_count,
        mapping_count=result.mapping_count,
        mapping_issue_count=result.mapping_issue_count,
        unmatched_count=persisted.unmatched_count,
    )


@router.get("/context/{role_id}")
def get_profile_context(
    role_id: str,
    topic: str | None = None,
    session_id: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return build_role_context(db, role_id, topic=topic, session_id=session_id).to_dict()


@router.get("/snapshots/{snapshot_id}")
def get_candidate_snapshot(snapshot_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    snapshot = db.get(ProfileCandidateSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "candidate_snapshot_not_found"})
    items = list(
        db.scalars(
            select(ProfileCandidateItem)
            .where(ProfileCandidateItem.snapshot_id == snapshot.id)
            .order_by(ProfileCandidateItem.profile_item_id)
        )
    )
    return {
        "id": snapshot.id,
        "source_dataset_id": snapshot.source_dataset_id,
        "role_scope": snapshot.role_scope,
        "status": snapshot.status,
        "items": [
            {
                "id": item.id,
                "profile_item_id": item.profile_item_id,
                "subject_id": item.subject_id,
                "category": item.category,
                "claim": item.claim,
                "cognitive_state": item.cognitive_state,
                "confidence": item.confidence,
                "reviewer_confidence": item.reviewer_confidence,
                "conflict_status": item.conflict_status,
                "review_status": item.review_status,
                "evidence": _evidence(db, item.id),
                "review_events": _review_events(db, item.id),
            }
            for item in items
        ],
        "unmatched_evidence": [
            {
                "signal_id": row.signal_id,
                "evidence_id": row.evidence_id,
                "kind": row.kind,
                "reason": row.reason,
            }
            for row in db.scalars(
                select(ProfileCandidateUnmatchedEvidence)
                .where(ProfileCandidateUnmatchedEvidence.snapshot_id == snapshot.id)
                .order_by(
                    ProfileCandidateUnmatchedEvidence.signal_id,
                    ProfileCandidateUnmatchedEvidence.evidence_id,
                    ProfileCandidateUnmatchedEvidence.reason,
                )
            )
        ],
    }


@router.post("/items/{candidate_id}/review", response_model=CandidateReviewResponse)
def review_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    db: Session = Depends(get_db),
) -> CandidateReviewResponse:
    try:
        item = review_candidate_item(
            db,
            candidate_id,
            to_status=payload.to_status,
            reviewer_id=payload.reviewer_id,
            note=payload.note,
            decision_reason_code=payload.decision_reason_code,
            expected_from_status=payload.expected_from_status,
            reviewer_confidence=payload.reviewer_confidence,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_candidate_transition", "message": str(exc)}
        ) from exc
    return CandidateReviewResponse(
        candidate_id=item.id,
        review_status=item.review_status,
        reviewer_note=item.reviewer_note,
        confidence=item.confidence,
        reviewer_confidence=item.reviewer_confidence,
    )


@router.post("/items/{candidate_id}/admit", response_model=CandidateAdmissionResponse)
def admit_candidate(candidate_id: str, db: Session = Depends(get_db)) -> CandidateAdmissionResponse:
    try:
        version = admit_candidate_item(db, candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc)}) from exc
    except AdmissionError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return CandidateAdmissionResponse(
        profile_version_id=version.id,
        role_id=version.role_id,
        version=version.version,
        status=version.status,
    )


def _evidence(db: Session, candidate_id: str) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "direction": row.direction,
            "source_dataset_id": row.source_dataset_id,
            "source_message_id": row.source_message_id,
            "imported_message_id": row.imported_message_id,
            "match_status": row.match_status,
            "invalid_reason": row.invalid_reason,
        }
        for row in db.scalars(
            select(ProfileCandidateEvidence)
            .where(ProfileCandidateEvidence.candidate_id == candidate_id)
            .order_by(
                ProfileCandidateEvidence.direction, ProfileCandidateEvidence.source_message_id
            )
        )
    ]


def _review_events(db: Session, candidate_id: str) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reviewer_confidence_before": row.reviewer_confidence_before,
            "reviewer_confidence_after": row.reviewer_confidence_after,
            "reviewer_id": row.reviewer_id,
            "note": row.note,
            "decision_reason_code": row.decision_reason_code,
            "created_at": row.created_at,
        }
        for row in db.scalars(
            select(ProfileCandidateReviewEvent)
            .where(ProfileCandidateReviewEvent.candidate_id == candidate_id)
            .order_by(ProfileCandidateReviewEvent.created_at, ProfileCandidateReviewEvent.id)
        )
    ]
