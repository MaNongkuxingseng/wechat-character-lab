"""Run the P3-F synthetic profile and real-dialogue acceptance flow.

Author: valen MPF

This script is intentionally limited to an explicitly supplied isolated SQLite
database. It creates only fixed synthetic messages and never reads Inbox data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.sessions import create_session
from app.core.orchestrator import ConversationOrchestrator
from app.core.state_machine import SessionState
from app.db import make_engine
from app.ingestion.security_flags import derive_security_flags
from app.models import (
    ImportedMessage,
    ProfileCandidateEvidence,
    ProfileCandidateItem,
    ProfileTrait,
    Role,
    Source,
)
from app.profiles.admission import admit_candidate_item
from app.profiles.candidate_review import review_candidate_item
from app.profiles.service import approve_version
from app.profiles.source_contract import analyze_and_persist_approved_source
from app.schemas.session import SessionCreate

SOURCE_ID = "p3f-synthetic-provider-acceptance"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, help="Absolute isolated SQLite .db path")
    parser.add_argument("--output", required=True, help="Absolute JSON summary path")
    return parser.parse_args()


def _require_isolated_paths(database: str, output: str) -> tuple[Path, Path]:
    database_path = Path(database).resolve()
    output_path = Path(output).resolve()
    if database_path.suffix != ".db" or not database_path.is_file():
        raise ValueError("isolated_database_required")
    if output_path.suffix != ".json" or output_path.parent != database_path.parent:
        raise ValueError("output_must_share_isolated_directory")
    if "data" in {part.lower() for part in database_path.parts}:
        raise ValueError("repository_data_database_forbidden")
    return database_path, output_path


def _metadata(message_id: str, sent_at: datetime) -> dict[str, object]:
    flags = {"is_ai_generated": False, "is_system": False}
    inputs = {"top_level": flags, "source_metadata": {}}
    sources = derive_security_flags({**flags, "source_metadata": {}}).source_map()
    return {
        "canonical_contract_version": "wechat-canonical-v1",
        "canonical_message_id": message_id,
        "canonical_timestamp": sent_at.isoformat().replace("+00:00", "Z"),
        "timestamp_status": "parsed_utc",
        "message_type": "text",
        "content_status": "present",
        **flags,
        "security_flag_inputs": inputs,
        "security_flag_sources": sources,
    }


def _seed_synthetic_source(db) -> None:
    if db.get(Source, SOURCE_ID) is not None:
        raise ValueError("synthetic_source_already_exists")
    now = datetime.now(UTC)
    for role_id, label in (("role_a", "Synthetic A"), ("role_b", "Synthetic B")):
        role = db.get(Role, role_id)
        if role is None:
            db.add(
                Role(
                    id=role_id,
                    label=label,
                    profile="",
                    style_profile={},
                    voice_profile={},
                    consent_status="preset",
                    created_at=now,
                    updated_at=now,
                )
            )
    db.add(
        Source(
            id=SOURCE_ID,
            kind="synthetic",
            name="P3-F synthetic Provider acceptance",
            status="approved",
            metadata_json={"semantic_llm_authorized": True, "message_count": 8},
            imported_at=now,
        )
    )
    db.flush()
    samples = {
        "role_a": (
            "I prefer discussing difficult relationship decisions calmly and directly.",
            "Before rebuilding trust, I want clear boundaries and observable actions.",
            "I usually summarize an agreement and propose one practical next step.",
            "When emotions rise, I pause briefly and then return to the specific issue.",
        ),
        "role_b": (
            "I ask clarifying questions before agreeing to repair a relationship.",
            "I value consistent follow-through more than broad promises.",
            "I express uncertainty openly when the available evidence is limited.",
            "I prefer a gradual trial period with explicit check-ins and boundaries.",
        ),
    }
    for role_index, (role_id, texts) in enumerate(samples.items()):
        label = "Synthetic A" if role_id == "role_a" else "Synthetic B"
        for index, text in enumerate(texts, start=1):
            sent_at = now + timedelta(minutes=role_index * 10 + index)
            message_id = f"{role_id}-{index}"
            db.add(
                ImportedMessage(
                    id=f"p3f-db-{message_id}",
                    source_id=SOURCE_ID,
                    external_id=message_id,
                    speaker_label=label,
                    speaker_role_id=role_id,
                    text=text,
                    sent_at=sent_at,
                    metadata_json=_metadata(message_id, sent_at),
                )
            )
    db.commit()


def _review_and_publish(db, snapshot_id: str) -> dict[str, dict[str, object]]:
    items = list(
        db.scalars(
            select(ProfileCandidateItem)
            .where(
                ProfileCandidateItem.snapshot_id == snapshot_id,
                ProfileCandidateItem.analyzer_name == "llm_semantic_openai_compatible",
            )
            .order_by(ProfileCandidateItem.subject_id, ProfileCandidateItem.profile_item_id)
        )
    )
    published: dict[str, dict[str, object]] = {}
    for role_id in ("role_a", "role_b"):
        eligible = []
        for item in items:
            if item.subject_id != role_id or item.conflict_status != "none":
                continue
            evidence = list(
                db.scalars(
                    select(ProfileCandidateEvidence).where(
                        ProfileCandidateEvidence.candidate_id == item.id
                    )
                )
            )
            if evidence and all(
                row.direction == "supporting" and row.match_status == "matched"
                for row in evidence
            ):
                eligible.append(item)
        if not eligible:
            raise ValueError(f"no_eligible_semantic_candidate:{role_id}")
        selected = eligible[0]
        review_candidate_item(
            db,
            selected.id,
            to_status="accepted",
            expected_from_status="pending",
            reviewer_id="p3f-synthetic-acceptance",
            note="Synthetic acceptance: evidence mapping and role isolation verified.",
            decision_reason_code="synthetic_acceptance",
        )
        version = admit_candidate_item(db, selected.id)
        trait = db.scalar(
            select(ProfileTrait).where(ProfileTrait.profile_version_id == version.id)
        )
        if trait is None:
            raise ValueError(f"formal_trait_missing:{role_id}")
        trait.review_status = "accepted"
        trait.reviewer_note = "Synthetic formal profile acceptance."
        db.commit()
        approve_version(db, version)
        db.refresh(version)
        published[role_id] = {
            "candidate_id": selected.id,
            "profile_version_id": version.id,
            "trait_id": trait.id,
            "status": version.status,
        }
    return published


async def _run_dialogue(db) -> dict[str, object]:
    session = create_session(
        SessionCreate(
            topic="reconciliation",
            role_ids=["role_a", "role_b"],
            provider_mode="llm",
            turn_limit=4,
            turn_delay_seconds=0.5,
        ),
        db,
    )
    orchestrator = ConversationOrchestrator(db, session.id)
    orchestrator.set_state(SessionState.INITIALIZING)
    orchestrator.set_state(SessionState.RUNNING)
    turns: list[dict[str, object]] = []
    for _ in range(4):
        outputs = await orchestrator.create_role_turn()
        message = next(item for item in outputs if item["type"] == "message.created")
        turns.append(
            {
                "turn": message["turn"],
                "speaker_role_id": message["speaker_role_id"],
                "provider": message["provider"],
                "model": message["model"],
                "generation_status": message["generation_status"],
                "latency_ms": message["latency_ms"],
                "trace_id": message["trace_id"],
                "profile_version_id": message["profile_version_id"],
                "trait_ids": message["trait_ids"],
            }
        )
    return {"session_id": session.id, "status": session.status, "turns": turns}


def main() -> None:
    args = _args()
    database, output = _require_isolated_paths(args.database, args.output)
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        _seed_synthetic_source(db)
        analysis = analyze_and_persist_approved_source(db, SOURCE_ID)
        if analysis.semantic_status != "ready":
            raise RuntimeError(f"semantic_analysis_failed:{analysis.semantic_status}")
        published = _review_and_publish(db, analysis.persistence.snapshot_id)
        dialogue = asyncio.run(_run_dialogue(db))
        summary = {
            "source_id": SOURCE_ID,
            "synthetic_only": True,
            "semantic_status": analysis.semantic_status,
            "candidate_count": analysis.persistence.candidate_count,
            "mapping_count": analysis.mapping_count,
            "mapping_issue_count": analysis.mapping_issue_count,
            "unmatched_count": analysis.persistence.unmatched_count,
            "published": published,
            "dialogue": dialogue,
        }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
