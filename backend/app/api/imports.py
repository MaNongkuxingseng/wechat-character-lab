import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.ingestion.archive_parser import ArchiveParseError, parse_archive
from app.ingestion.inbox_watcher import InboxWatcher
from app.ingestion.normalizer import normalize_message
from app.models import ImportedMessage, Role, Source
from app.repositories.imports import count_messages, get_source, list_sources
from app.schemas.imports import (
    ImportApprovalRequest,
    ImportApprovalResponse,
    ImportScanResponse,
    ImportSourceRead,
)

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("/capabilities")
def import_capabilities() -> dict[str, object]:
    """报告导入适配器能力；真实 Bridge API 尚未接入。"""
    return {"inbox_enabled": True, "bridge_api_enabled": False, "bridge_api_status": "mock"}


@router.get("", response_model=list[ImportSourceRead])
def get_imports(db: Session = Depends(get_db)) -> list[ImportSourceRead]:
    """列出已发现的导入来源及审核状态。"""
    return [_source_read(source) for source in list_sources(db)]


@router.post("/inbox/scan", response_model=ImportScanResponse)
def scan_inbox(db: Session = Depends(get_db)) -> ImportScanResponse:
    """扫描 Inbox 并为新归档创建待审核来源，不自动写入消息或记忆。"""
    root = Path(__file__).resolve().parents[3]
    inbox_path = (root / get_settings().inbox_path).resolve()
    sources: list[ImportSourceRead] = []
    archives = InboxWatcher(inbox_path).discover_archives()
    for archive in archives:
        digest = _sha256(archive)
        existing = _find_source_by_digest(db, digest)
        if existing is not None:
            sources.append(_source_read(existing))
            continue
        metadata = {"sha256": digest, "relative_path": str(archive.relative_to(root))}
        try:
            count = len(parse_archive(archive))
            source = Source(
                id=str(uuid4()),
                kind="inbox_archive",
                name=archive.name,
                status="pending_review",
                metadata_json={**metadata, "message_count": count},
                imported_at=datetime.now(UTC),
            )
        except ArchiveParseError as exc:
            source = Source(
                id=str(uuid4()),
                kind="inbox_archive",
                name=archive.name,
                status="parse_error",
                metadata_json={**metadata, "error": str(exc), "message_count": 0},
                imported_at=datetime.now(UTC),
            )
        db.add(source)
        db.commit()
        db.refresh(source)
        sources.append(_source_read(source))
    return ImportScanResponse(discovered=len(archives), sources=sources)


@router.post("/{source_id}/approve", response_model=ImportApprovalResponse)
def approve_import(
    source_id: str,
    payload: ImportApprovalRequest | None = None,
    db: Session = Depends(get_db),
) -> ImportApprovalResponse:
    """审核并导入一个来源；解析失败或已审核来源不可重复导入。"""
    payload = payload or ImportApprovalRequest()
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "source_not_found"})
    if source.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail={"code": "source_not_approvable", "status": source.status},
        )
    root = Path(__file__).resolve().parents[3]
    inbox_path = (root / get_settings().inbox_path).resolve()
    try:
        path = (root / source.metadata_json["relative_path"]).resolve()
        path.relative_to(inbox_path)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_source_path"}) from exc
    try:
        if _sha256(path) != source.metadata_json.get("sha256"):
            raise ArchiveParseError("归档文件在扫描后已发生变化，请重新扫描")
        messages = [normalize_message(message) for message in parse_archive(path)]
    except (ArchiveParseError, OSError) as exc:
        source.status = "parse_error"
        source.metadata_json = {**source.metadata_json, "error": str(exc)}
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"code": "archive_parse_error", "message": str(exc)},
        ) from exc

    role_ids = {role.id for role in db.query(Role).all()}
    invalid_roles = sorted(set(payload.speaker_mapping.values()) - role_ids)
    if invalid_roles:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_role_mapping", "role_ids": invalid_roles},
        )

    external_ids = [message.external_id for message in messages]
    if len(set(external_ids)) != len(external_ids):
        raise HTTPException(
            status_code=422,
            detail={"code": "duplicate_message_id", "message": "同一归档内存在重复 external_id"},
        )

    for message in messages:
        db.add(
            ImportedMessage(
                id=str(uuid4()),
                source_id=source.id,
                external_id=message.external_id,
                speaker_label=message.speaker_label,
                speaker_role_id=payload.speaker_mapping.get(message.speaker_label),
                text=message.text,
                sent_at=message.sent_at,
                metadata_json=message.metadata,
            )
        )
    source.status = "approved"
    source.metadata_json = {**source.metadata_json, "message_count": len(messages)}
    db.commit()
    db.refresh(source)
    return ImportApprovalResponse(
        source=_source_read(source), imported_messages=count_messages(db, source.id)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_source_by_digest(db: Session, digest: str) -> Source | None:
    for source in db.query(Source).all():
        if source.metadata_json.get("sha256") == digest:
            return source
    return None


def _source_read(source: Source) -> ImportSourceRead:
    return ImportSourceRead(
        id=source.id,
        name=source.name,
        kind=source.kind,
        status=source.status,
        message_count=int(source.metadata_json.get("message_count", 0)),
        error=source.metadata_json.get("error"),
    )
