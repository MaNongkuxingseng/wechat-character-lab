"""将 wechatauto-replica 的单会话 JSON 转为项目 Inbox ZIP。

用法示例：
    python scripts/convert_wechatauto_export.py raw.json normalized.zip

原始 JSON 保持不变；输出包只包含标准化后的 messages.json，不包含账号级导出元数据。
"""

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ingestion.wechat_normalizer import (
    CANONICAL_CONTRACT_VERSION,
    normalize_payload,
)


def convert(source: Path, destination: Path) -> dict[str, Any]:
    """转换单一会话，并在写出前检查完整性和唯一键。"""
    payload = _read_json(source)
    chats = payload.get("chats")
    messages = payload.get("messages")
    if not isinstance(chats, list) or len(chats) != 1:
        raise ValueError("原始导出必须且只能包含一个会话")
    if not isinstance(messages, list) or not messages:
        raise ValueError("原始导出没有消息记录")

    canonical_messages, canonical_summary = normalize_payload(
        payload, source_file=source.name
    )
    if canonical_summary["error_count"] or len(canonical_messages) != len(messages):
        raise ValueError("原始导出无法完整转换为 canonical 消息记录")

    rows: list[dict[str, Any]] = []
    external_ids: set[str] = set()
    speaker_counts: Counter[str] = Counter()
    message_type_counts: Counter[str] = Counter()
    timestamps: list[datetime] = []

    for index, (message, canonical) in enumerate(zip(messages, canonical_messages), start=1):
        if not isinstance(message, dict):
            raise TypeError(f"第 {index} 条记录不是对象")
        try:
            sent_at = datetime.fromtimestamp(
                int(message["create_time"]), tz=timezone.utc  # noqa: UP017
            )
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise ValueError(f"第 {index} 条记录的时间戳无效") from exc

        speaker = canonical["sender"]
        text = message.get("content")
        if not speaker or not isinstance(text, str):
            raise ValueError(f"第 {index} 条记录缺少发言人或文本内容")

        kind = canonical["message_type"]
        content_was_empty = not text.strip()
        if content_was_empty:
            # 保留空正文语义；画像安全门禁会排除它，不用占位符伪装文本。
            text = ""

        # 多分片数据库的 local_id 可能重复，加入行序号确保来源内 ID 唯一。
        legacy_external_id = "wechat:{sort_seq}:{local_id}:{server_id}:{index}".format(
            sort_seq=message.get("sort_seq"),
            local_id=message.get("local_id"),
            server_id=message.get("server_id"),
            index=index,
        )
        external_id = legacy_external_id
        if external_id in external_ids:
            raise ValueError(f"第 {index} 条记录产生重复 external_id")
        external_ids.add(external_id)

        rows.append(
            {
                "external_id": external_id,
                "speaker_label": speaker,
                "text": text,
                "sent_at": sent_at.isoformat().replace("+00:00", "Z"),
                "message_type": kind,
                "type_code": canonical["source_type_code"],
                "sender_id": message.get("sender_id"),
                "server_id": message.get("server_id"),
                "local_id": message.get("local_id"),
                "sort_seq": message.get("sort_seq"),
                "content_was_empty": content_was_empty,
                "metadata": {
                    "canonical_contract_version": CANONICAL_CONTRACT_VERSION,
                    "canonical_message_id": canonical["message_id"],
                    "canonical_message_id_status": canonical["message_id_status"],
                    "source_message_ref": canonical["source_message_ref"],
                    "source_local_id": canonical["source_local_id"],
                    "source_server_id": canonical["source_server_id"],
                    "source_type_code": canonical["source_type_code"],
                    "message_type": canonical["message_type"],
                    "content_status": canonical["content_status"],
                    "timestamp_status": canonical["timestamp_status"],
                    "is_ai_generated": canonical["is_ai_generated"],
                    "is_system": canonical["is_system"],
                    "security_flag_sources": canonical["security_flag_sources"],
                    "security_flag_inputs": canonical["security_flag_inputs"],
                },
            }
        )
        speaker_counts[speaker] += 1
        message_type_counts[str(kind)] += 1
        timestamps.append(sent_at)

    if len(speaker_counts) != 2:
        raise ValueError("当前转换器要求单聊恰有两种发言人标签")

    encoded = json.dumps(
        {"messages": rows}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        archive.writestr("messages.json", encoded)

    # 写出后重新打开归档，确认消息数量与 ZIP CRC 均有效。
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("输出 ZIP 校验失败")
        imported = json.loads(archive.read("messages.json"))
        if len(imported.get("messages", [])) != len(messages):
            raise ValueError("输出消息数与原始导出不一致")

    return {
        "messages": len(rows),
        "speaker_counts": list(speaker_counts.values()),
        "message_type_counts": dict(message_type_counts),
        "start_utc": min(timestamps).isoformat(),
        "end_utc": max(timestamps).isoformat(),
        "raw_sha256": _sha256(source),
        "import_zip_sha256": _sha256(destination),
        "raw_bytes": source.stat().st_size,
        "zip_bytes": destination.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(source: Path) -> Any:
    """Read UTF-8 JSON with or without a BOM."""
    return json.loads(source.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description="转换或标准化 wechatauto 单会话导出文件")
    parser.add_argument("source", type=Path, help="wechatauto 导出的原始 JSON")
    parser.add_argument("destination", type=Path, help="输出 ZIP 或 JSONL 路径")
    parser.add_argument("--format", choices=("zip", "jsonl"), default="zip")
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit(f"拒绝覆盖已有输出文件：{args.destination}")
    if args.format == "jsonl":
        payload = _read_json(args.source)
        source_file = (
            args.source.relative_to(ROOT).as_posix()
            if args.source.is_relative_to(ROOT)
            else args.source.name
        )
        records, summary = normalize_payload(payload, source_file=source_file)
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with args.destination.open("w", encoding="utf-8", newline="\n") as output:
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(json.dumps(summary, ensure_ascii=True))
        return
    print(json.dumps(convert(args.source, args.destination), ensure_ascii=True))


if __name__ == "__main__":
    main()
