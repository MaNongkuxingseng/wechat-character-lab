"""媒体分析业务服务和 SQLite 持久化。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VoiceAnalysis

from .analyzer import SUPPORTED_VIDEO_EXTENSIONS, MediaAnalysisResult, MediaAnalyzer

ROLE_LABELS = {"我": "role_a", "角色 A": "role_a", "彭娜": "role_b", "角色 B": "role_b"}


def project_data_root() -> Path:
    """返回项目本机 data 根目录。"""
    return Path(__file__).resolve().parents[3] / "data"


def analyze_voice_assets(
    db: Session,
    *,
    include_videos: bool = True,
    minimum_samples: int = 3,
) -> dict[str, object]:
    """分析 manifest 中的微信语音，并在角色样本不足时补扫视频音轨。"""
    data_root = project_data_root()
    analyzer = MediaAnalyzer(data_root)
    results: list[VoiceAnalysis] = []
    manifest = data_root / "audio" / "pengna_20261014" / "manifest.json"
    if manifest.is_file():
        for item in _read_manifest(manifest):
            relative = Path("audio") / "pengna_20261014" / str(item["file"])
            result = analyzer.analyze(data_root / relative, source_kind="wechat_voice")
            role_id = ROLE_LABELS.get(str(item.get("speaker_label")))
            result.metadata.update(
                {
                    "speaker_label": item.get("speaker_label"),
                    "sent_at_utc": item.get("sent_at_utc"),
                    "asset_manifest": analyzer.relative_path(manifest),
                }
            )
            results.append(_upsert(db, result, role_id=role_id))

    counts = _role_counts(results)
    raw_counts = _role_raw_counts(results)
    video_candidates: list[VoiceAnalysis] = []
    insufficient_samples = any(
        counts.get(role_id, 0) < minimum_samples for role_id in ("role_a", "role_b")
    )
    if include_videos and insufficient_samples:
        for video in _find_videos(data_root):
            result = analyzer.analyze_video_audio(video)
            result.metadata["candidate_for_role_ids"] = [
                role_id
                for role_id in ("role_a", "role_b")
                if counts.get(role_id, 0) < minimum_samples
            ]
            video_candidates.append(_upsert(db, result, role_id=None))
    db.commit()
    all_rows = list(
        db.scalars(select(VoiceAnalysis).order_by(VoiceAnalysis.created_at, VoiceAnalysis.id))
    )
    return {
        "minimum_samples": minimum_samples,
        "voice_assets": [_read(row) for row in results],
        "video_candidates": [_read(row) for row in video_candidates],
        "all_analyses": [_read(row) for row in all_rows],
        "role_counts": counts,
        "raw_role_counts": raw_counts,
        "video_tool_available": _video_tools_available(),
    }


def list_voice_analyses(db: Session, role_id: str | None = None) -> list[dict[str, object]]:
    """读取语音分析摘要，按角色隔离；不返回音频内容。"""
    statement = select(VoiceAnalysis).order_by(VoiceAnalysis.created_at, VoiceAnalysis.id)
    if role_id:
        statement = statement.where(VoiceAnalysis.role_id == role_id)
    return [_read(row) for row in db.scalars(statement)]


def _upsert(db: Session, result: MediaAnalysisResult, *, role_id: str | None) -> VoiceAnalysis:
    row = db.scalar(select(VoiceAnalysis).where(VoiceAnalysis.source_path == result.source_path))
    if row is None:
        row = VoiceAnalysis(id=str(uuid4()), source_path=result.source_path, sha256=result.sha256)
        db.add(row)
    row.role_id = role_id
    row.source_kind = result.source_kind
    row.media_format = result.media_format
    row.status = result.status
    row.derived_from_video = result.derived_from_video
    row.duration_ms = result.duration_ms
    row.sample_rate = result.sample_rate
    row.channels = result.channels
    row.rms_db = result.rms_db
    row.silence_ratio = result.silence_ratio
    row.sha256 = result.sha256
    row.metadata_json = result.metadata
    row.error = result.error
    now = datetime.now(UTC)
    row.analyzed_at = now
    if row.created_at is None:
        row.created_at = now
    return row


def _read(row: VoiceAnalysis) -> dict[str, object]:
    return {
        "id": row.id,
        "role_id": row.role_id,
        "source_path": row.source_path,
        "source_kind": row.source_kind,
        "media_format": row.media_format,
        "status": row.status,
        "derived_from_video": row.derived_from_video,
        "duration_ms": row.duration_ms,
        "sample_rate": row.sample_rate,
        "channels": row.channels,
        "rms_db": row.rms_db,
        "silence_ratio": row.silence_ratio,
        "transcript": row.transcript,
        "sha256": row.sha256,
        "metadata": row.metadata_json or {},
        "error": row.error,
        "analyzed_at": row.analyzed_at,
    }


def _read_manifest(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files = payload.get("files", []) if isinstance(payload, dict) else []
    return [item for item in files if isinstance(item, dict) and item.get("file")]


def _find_videos(data_root: Path) -> list[Path]:
    return sorted(
        path
        for path in data_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def _role_counts(rows: list[VoiceAnalysis]) -> dict[str, int]:
    counts = {"role_a": 0, "role_b": 0}
    for row in rows:
        if row.role_id in counts and row.status == "decoded":
            counts[row.role_id] += 1
    return counts


def _role_raw_counts(rows: list[VoiceAnalysis]) -> dict[str, int]:
    """统计已识别到的原始样本，即使尚未解码也不丢失覆盖信息。"""
    counts = {"role_a": 0, "role_b": 0}
    for row in rows:
        if row.role_id in counts and row.status not in {"missing", "unsupported_format"}:
            counts[row.role_id] += 1
    return counts


def _video_tools_available() -> bool:
    from app.voice.analyzer import _ffmpeg_tools

    ffprobe, ffmpeg = _ffmpeg_tools()
    if ffprobe and ffmpeg:
        return True
    try:
        import av  # noqa: F401
    except ImportError:
        return False
    return True
