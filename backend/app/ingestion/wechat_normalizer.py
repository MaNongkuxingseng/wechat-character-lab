"""将 wechatauto 单会话消息转换为可追溯的标准化 JSON 记录。

作者: valen MPF
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.ingestion.security_flags import derive_security_flags

TYPE_NAMES = {
    1: "text",
    3: "image",
    34: "voice",
    42: "contact",
    43: "video",
    47: "emoji",
    48: "location",
}
_SECURITY_PROVENANCE_FIELDS = (
    "type",
    "message_type",
    "type_code",
    "is_ai_generated",
    "is_system",
)
VALID_EPOCH_MIN = 946684800  # 2000-01-01 UTC
VALID_EPOCH_MAX = 4102444800  # 2100-01-01 UTC


def normalize_payload(
    payload: Any, *, source_file: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """标准化单会话 JSON，并返回记录与脱敏统计摘要。"""
    if not isinstance(payload, dict):
        raise ValueError("顶层 JSON 必须是对象")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("顶层必须包含 messages 数组")

    records: list[dict[str, Any]] = []
    bases: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    errors: list[dict[str, Any]] = []
    for row_number, message in enumerate(messages, start=1):
        try:
            record, base_id = _normalize_message(message, row_number, source_file)
        except ValueError as exc:
            errors.append({"row": row_number, "error": str(exc)})
            continue
        bases[base_id] += 1
        occurrence = bases[base_id]
        if occurrence > 1:
            record["message_id"] = f"{base_id}#{occurrence}"
            record["message_id_status"] = "collision_suffix"
            record["id_collision"] = True
        type_counts[record["message_type"]] += 1
        records.append(record)

    return records, {
        "input_messages": len(messages),
        "output_records": len(records),
        "error_count": len(errors),
        "errors": errors,
        "id_collision_count": sum(1 for record in records if record["id_collision"]),
        "message_type_counts": dict(sorted(type_counts.items())),
        "source_file": source_file,
    }


def _normalize_message(
    message: Any, row_number: int, source_file: str
) -> tuple[dict[str, Any], str]:
    if not isinstance(message, dict):
        raise ValueError("消息记录必须是对象")

    local_id = _optional_scalar(message.get("local_id"))
    server_id = _optional_scalar(message.get("server_id"))
    if local_id is not None or server_id is not None:
        base_id = f"wechat:{local_id or 'null'}:{server_id or 'null'}"
        id_status = "source_ids"
    else:
        canonical = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        base_id = f"wechat:hash:{digest}"
        id_status = "content_hash_fallback"

    type_code = _optional_int(message.get("type_code"))
    message_type = TYPE_NAMES.get(
        type_code, f"unknown:{type_code}" if type_code is not None else "unknown"
    )
    timestamp, timestamp_status = _timestamp(message.get("create_time"))
    sender = _optional_text(message.get("sender_name"))
    content_value = message.get("content")
    if isinstance(content_value, str):
        content = content_value
        content_status = "empty" if content == "" else "present"
    elif content_value is None:
        content = None
        content_status = "missing"
    else:
        content = None
        content_status = "not_text"

    raw_source_metadata = message.get("source_metadata")
    security_flags = derive_security_flags(message)
    record = {
        "message_id": base_id,
        "message_id_status": id_status,
        "id_collision": False,
        "source_local_id": local_id,
        "source_server_id": server_id,
        "timestamp": timestamp,
        "timestamp_raw": message.get("create_time"),
        "timestamp_status": timestamp_status,
        "sender": sender,
        "message_type": message_type,
        "source_type_code": type_code,
        "content": content,
        "content_status": content_status,
        "is_ai_generated": security_flags.is_ai_generated,
        "is_system": security_flags.is_system,
        "security_flag_sources": security_flags.source_map(),
        "security_flag_inputs": _security_flag_inputs(message, raw_source_metadata),
        "source_file": source_file,
        "source_message_ref": f"messages[{row_number}]",
        "source_metadata": {
            "type": message.get("type"),
            "md5": message.get("md5"),
            "sender_id": message.get("sender_id"),
            "sort_seq": message.get("sort_seq"),
        },
    }
    return record, base_id


def _security_flag_inputs(
    message: Mapping[str, Any], source_metadata: Any
) -> dict[str, dict[str, Any]]:
    """保留安全推导涉及的原始字段，区分顶层与嵌套来源。"""
    top_level = {
        field: message[field]
        for field in _SECURITY_PROVENANCE_FIELDS
        if field in message
    }
    nested = (
        {
            field: source_metadata[field]
            for field in _SECURITY_PROVENANCE_FIELDS
            if field in source_metadata
        }
        if isinstance(source_metadata, Mapping)
        else {}
    )
    return {"top_level": top_level, "source_metadata": nested}


def _timestamp(value: Any) -> tuple[str | None, str]:
    try:
        epoch = int(value)
    except (TypeError, ValueError, OverflowError):
        return None, "missing" if value is None else "invalid"
    if not VALID_EPOCH_MIN <= epoch < VALID_EPOCH_MAX:
        return None, "out_of_range"
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z"), "parsed_utc"


def _optional_scalar(value: Any) -> str | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int)):
        return value
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
