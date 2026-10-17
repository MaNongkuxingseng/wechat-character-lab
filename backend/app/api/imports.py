import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
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
    ImportPreviewMessage,
    ImportPreviewRead,
    ImportScanResponse,
    ImportSourceRead,
    ImportSourceSummary,
    SemanticTransferConsentRequest,
)

router = APIRouter(prefix="/api/imports", tags=["imports"])
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
PREVIEW_LIMIT = 10


@router.get("/capabilities", response_model=ImportSourceSummary)
def import_capabilities() -> ImportSourceSummary:
    """报告导入适配器能力；真实 Bridge API 尚未接入。"""
    return ImportSourceSummary(upload_max_bytes=MAX_UPLOAD_SIZE)


@router.get("", response_model=list[ImportSourceRead])
def get_imports(db: Session = Depends(get_db)) -> list[ImportSourceRead]:
    """列出已发现的导入来源及审核状态。"""
    return [_source_read(source) for source in list_sources(db)]


@router.post("/upload", response_model=ImportSourceRead, status_code=201)
async def upload_archive(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImportSourceRead:
    """接收一个 ZIP 导出包并登记为待人工审核来源。"""
    original_name = _safe_filename(file.filename or "chat-export.zip")
    if not original_name.lower().endswith(".zip"):
        raise HTTPException(status_code=415, detail={"code": "zip_required"})
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail={"code": "empty_archive"})
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail={"code": "upload_too_large", "limit_mb": 50})

    root = Path(__file__).resolve().parents[3]
    inbox_path = (root / get_settings().inbox_path).resolve()
    digest = hashlib.sha256(content).hexdigest()
    existing = _find_source_by_digest(db, digest)
    if existing is not None:
        return _source_read(existing)
    inbox_path.mkdir(parents=True, exist_ok=True)
    path = inbox_path / f"{uuid4()}-{original_name}"
    path.write_bytes(content)
    return _register_archive(db, root, path)


@router.post("/inbox/scan", response_model=ImportScanResponse)
def scan_inbox(db: Session = Depends(get_db)) -> ImportScanResponse:
    """扫描 Inbox 并为新归档创建待审核来源，不自动写入消息或记忆。"""
    root = Path(__file__).resolve().parents[3]
    inbox_path = (root / get_settings().inbox_path).resolve()
    sources: list[ImportSourceRead] = []
    archives = InboxWatcher(inbox_path).discover_archives()
    for archive in archives:
        sources.append(_register_archive(db, root, archive))
    return ImportScanResponse(discovered=len(archives), sources=sources)


@router.get("/{source_id}/preview", response_model=ImportPreviewRead)
def preview_import(source_id: str, db: Session = Depends(get_db)) -> ImportPreviewRead:
    """返回发言人计数和最多十条摘录，供用户确认来源与映射。"""
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "source_not_found"})
    if source.status == "approved":
        messages = list(
            db.scalars(
                select(ImportedMessage)
                .where(ImportedMessage.source_id == source.id)
                .order_by(ImportedMessage.sent_at, ImportedMessage.id)
                .limit(PREVIEW_LIMIT)
            )
        )
        counts = dict(
            db.execute(
                select(ImportedMessage.speaker_label, func.count())
                .where(ImportedMessage.source_id == source.id)
                .group_by(ImportedMessage.speaker_label)
            ).all()
        )
    elif source.status == "pending_review":
        try:
            path = _source_path(source)
            if _sha256(path) != source.metadata_json.get("sha256"):
                raise HTTPException(status_code=409, detail={"code": "archive_changed"})
        except (KeyError, OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_source_path"}) from exc
        try:
            messages = parse_archive(path)
        except (ArchiveParseError, OSError) as exc:
            raise HTTPException(status_code=422, detail={"code": "archive_parse_error"}) from exc
        counts = {}
        for message in messages:
            counts[message.speaker_label] = counts.get(message.speaker_label, 0) + 1
        messages = messages[:PREVIEW_LIMIT]
    else:
        messages = []
        counts = {}
    return ImportPreviewRead(
        source=_source_read(source),
        speakers=counts,
        samples=[
            ImportPreviewMessage(
                speaker_label=message.speaker_label,
                text=message.text[:240],
                sent_at=message.sent_at,
            )
            for message in messages
        ],
    )


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
    try:
        path = _source_path(source)
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

    attestation: dict[str, object] | None = None
    if payload.trusted_human_attestation:
        reviewer_id = (payload.attestation_reviewer_id or "").strip()
        reason = (payload.attestation_reason or "").strip()
        if not reviewer_id or not reason:
            raise HTTPException(
                status_code=422,
                detail={"code": "security_attestation_requires_reviewer_and_reason"},
            )
        attestation = {
            "human_authored": True,
            "contains_ai_generated": False,
            "contains_system_messages": False,
            "reviewer_id": reviewer_id,
            "reason": reason,
            "attested_at": datetime.now(UTC).isoformat(),
        }
    for message in messages:
        message_metadata = dict(message.metadata)
        if attestation is not None:
            message_metadata["security_attestation"] = attestation
        db.add(
            ImportedMessage(
                id=str(uuid4()),
                source_id=source.id,
                external_id=message.external_id,
                speaker_label=message.speaker_label,
                speaker_role_id=payload.speaker_mapping.get(message.speaker_label),
                text=message.text,
                sent_at=message.sent_at,
                metadata_json=message_metadata,
            )
        )
    source.status = "approved"
    source.metadata_json = {
        **source.metadata_json,
        "message_count": len(messages),
        "semantic_llm_authorized": payload.semantic_llm_authorized,
    }
    if attestation is not None:
        source.metadata_json["security_attestation"] = attestation
    else:
        source.metadata_json.pop("security_attestation", None)
    db.commit()
    db.refresh(source)
    return ImportApprovalResponse(
        source=_source_read(source), imported_messages=count_messages(db, source.id)
    )


@router.post("/{source_id}/semantic-transfer-consent", response_model=ImportSourceRead)
def update_semantic_transfer_consent(
    source_id: str,
    payload: SemanticTransferConsentRequest,
    db: Session = Depends(get_db),
) -> ImportSourceRead:
    """Record an explicit per-source opt-in/out; this endpoint never calls a provider."""
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "source_not_found"})
    if source.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "source_not_approved"})
    metadata = dict(source.metadata_json or {})
    metadata["semantic_llm_authorized"] = payload.authorized
    metadata["semantic_llm_authorization"] = {
        "authorized": payload.authorized,
        "reviewer_id": payload.reviewer_id.strip(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    source.metadata_json = metadata
    db.commit()
    db.refresh(source)
    return _source_read(source)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(filename: str) -> str:
    """只保留基础文件名字符，不接受客户端提供的路径片段。"""
    basename = Path(filename.replace("\\", "/")).name
    safe_name = re.sub(r"[^\w.() -]", "_", basename, flags=re.UNICODE).strip(" .")
    return (safe_name or "chat-export.zip")[:180]


def _source_path(source: Source) -> Path:
    """解析来源路径并确保仍位于配置的 Inbox 根目录内。"""
    root = Path(__file__).resolve().parents[3]
    inbox_path = (root / get_settings().inbox_path).resolve()
    path = (root / source.metadata_json["relative_path"]).resolve()
    path.relative_to(inbox_path)
    return path


def _register_archive(db: Session, root: Path, archive: Path) -> ImportSourceRead:
    """按内容摘要登记归档；重复文件返回既有来源，解析失败保留错误来源。"""
    digest = _sha256(archive)
    existing = _find_source_by_digest(db, digest)
    if existing is not None:
        return _source_read(existing)
    metadata = {"sha256": digest, "relative_path": str(archive.relative_to(root))}
    try:
        count = len(parse_archive(archive))
        status = "pending_review"
        metadata["message_count"] = count
    except ArchiveParseError as exc:
        status = "parse_error"
        metadata.update({"error": str(exc), "message_count": 0})
    source = Source(
        id=str(uuid4()),
        kind="inbox_archive",
        name=archive.name,
        status=status,
        metadata_json=metadata,
        imported_at=datetime.now(UTC),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_read(source)


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
        semantic_llm_authorized=bool(source.metadata_json.get("semantic_llm_authorized", False)),
        security_attestation=source.metadata_json.get("security_attestation"),
    )
