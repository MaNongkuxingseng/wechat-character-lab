import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas.message import NormalizedMessage


class ArchiveParseError(ValueError):
    """归档不符合当前公开导入契约时抛出的可展示错误。"""


def parse_archive(path: Path) -> list[NormalizedMessage]:
    """解析通用 Inbox 归档；只读取 messages.json、messages.jsonl 或 messages.csv。"""
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ArchiveParseError("只支持 ZIP 归档文件")
    try:
        with zipfile.ZipFile(path) as archive:
            member = _find_message_member(archive.namelist())
            if member is None:
                raise ArchiveParseError(
                    "归档中未找到 messages.json、messages.jsonl、messages.ndjson 或 messages.csv"
                )
            raw = archive.read(member)
    except zipfile.BadZipFile as exc:
        raise ArchiveParseError("ZIP 归档损坏或无法读取") from exc

    if member.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    elif member.lower().endswith((".jsonl", ".ndjson")):
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    else:
        document = json.loads(raw.decode("utf-8"))
        rows = document.get("messages", []) if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ArchiveParseError("消息文件必须是数组，或包含 messages 数组字段")
    return [_normalize_row(row, index) for index, row in enumerate(rows, start=1)]


def _find_message_member(names: list[str]) -> str | None:
    allowed = {"messages.json", "messages.jsonl", "messages.ndjson", "messages.csv"}
    for name in names:
        if Path(name).name.lower() in allowed:
            return name
    return None


def _normalize_row(row: Any, index: int) -> NormalizedMessage:
    if not isinstance(row, dict):
        raise ArchiveParseError(f"第 {index} 条消息不是对象")
    external_id = _first_value(row, "external_id", "message_id", "id") or str(index)
    speaker = _first_value(row, "speaker_label", "speaker", "sender", "from")
    text = _first_value(row, "text", "content", "message")
    if not speaker or text is None:
        raise ArchiveParseError(f"第 {index} 条消息缺少 speaker 和 text 字段")
    sent_at_value = _first_value(row, "sent_at", "timestamp", "created_at")
    sent_at = _parse_datetime(sent_at_value) if sent_at_value else None
    return NormalizedMessage(
        external_id=str(external_id),
        speaker_label=str(speaker),
        text=str(text),
        sent_at=sent_at,
        metadata={"source_row": index},
    )


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)


def _parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveParseError(f"无法解析消息时间：{value}") from exc
