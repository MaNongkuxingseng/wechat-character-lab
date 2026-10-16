"""消息安全标记的三态推导 / Three-state security flag enrichment.

本模块只使用消息自身携带的显式标记或明确的类型标记，不根据普通文本、昵称
或 Python truthiness 猜测安全属性。无法确认时保留 ``None``，由下游严格校验决定
该消息能否作为画像证据。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_FLAG_FIELDS = ("is_ai_generated", "is_system")
_TYPE_MARKERS = {
    "ai": "is_ai_generated",
    "assistant": "is_ai_generated",
    "system": "is_system",
}


@dataclass(frozen=True)
class SecurityFlags:
    """安全标记及其可审计来源；``None`` 表示 unknown。"""

    is_ai_generated: bool | None
    is_system: bool | None
    sources: tuple[tuple[str, str], ...]

    def source_map(self) -> dict[str, str]:
        """返回稳定、可 JSON 序列化的来源映射。"""
        return dict(self.sources)


def derive_security_flags(message: Mapping[str, Any]) -> SecurityFlags:
    """从显式字段和明确类型标记推导安全属性，不进行隐式类型转换。"""
    values: dict[str, bool | None] = {}
    sources: dict[str, str] = {}
    for field in _FLAG_FIELDS:
        explicit, explicit_source = _explicit_flag(message, field)
        marker, marker_source = _marker_flag(message, field)
        if explicit_source.startswith("invalid_type"):
            values[field] = None
            sources[field] = explicit_source
            continue
        if explicit_source.startswith("conflict"):
            values[field] = None
            sources[field] = explicit_source
            continue
        if marker_source.startswith("conflict"):
            values[field] = None
            sources[field] = marker_source
            continue
        if explicit is not None and marker_source.startswith("opposite_type:"):
            values[field] = None
            sources[field] = f"conflict:{explicit_source}+{marker_source.removeprefix('opposite_')}"
            continue
        if explicit is not None and marker is not None and explicit != marker:
            values[field] = None
            sources[field] = f"conflict:{explicit_source}+{marker_source}"
            continue
        if explicit is not None:
            values[field] = explicit
            sources[field] = explicit_source
        elif marker is not None:
            values[field] = marker
            sources[field] = marker_source
        else:
            values[field] = None
            sources[field] = (
                f"unknown:{marker_source}"
                if marker_source.startswith("opposite_type:")
                else "unknown:no_reliable_source"
            )

    return SecurityFlags(
        is_ai_generated=values["is_ai_generated"],
        is_system=values["is_system"],
        sources=tuple(sorted(sources.items())),
    )


def _explicit_flag(message: Mapping[str, Any], field: str) -> tuple[bool | None, str]:
    values: list[tuple[bool, str]] = []
    if field in message:
        value = message[field]
        if not isinstance(value, bool):
            return None, f"invalid_type:message.{field}"
        values.append((value, f"message.{field}"))

    metadata = message.get("source_metadata")
    if isinstance(metadata, Mapping) and field in metadata:
        value = metadata[field]
        if not isinstance(value, bool):
            return None, f"invalid_type:source_metadata.{field}"
        values.append((value, f"source_metadata.{field}"))
    if not values:
        return None, "missing"
    if len({value for value, _ in values}) > 1:
        sources = "+".join(sorted(source for _, source in values))
        return None, f"conflict:{sources}"
    sources = "+".join(sorted(source for _, source in values))
    return values[0][0], f"explicit:{sources}"


def _marker_flag(message: Mapping[str, Any], field: str) -> tuple[bool | None, str]:
    marker_values: list[tuple[str, str]] = []
    candidates = [
        ("message.message_type", message.get("message_type")),
        ("message.type", message.get("type")),
    ]
    metadata = message.get("source_metadata")
    if isinstance(metadata, Mapping):
        candidates.extend(
            (
                ("source_metadata.message_type", metadata.get("message_type")),
                ("source_metadata.type", metadata.get("type")),
            )
        )
    for source, candidate in candidates:
        if not isinstance(candidate, str):
            continue
        marker = candidate.strip().lower()
        if marker in _TYPE_MARKERS:
            marker_values.append((marker, source))

    marker_kinds = {kind for kind, _ in marker_values}
    marker_categories = {_TYPE_MARKERS[kind] for kind in marker_kinds}
    if len(marker_categories) > 1:
        markers = "+".join(sorted(marker_kinds))
        return None, f"conflict:type_markers:{markers}"

    matching = sorted(
        (kind, source)
        for kind, source in marker_values
        if _TYPE_MARKERS[kind] == field
    )
    if matching:
        kind, source = matching[0]
        return True, f"type:{kind}@{source}"

    if marker_values:
        kind, source = sorted(marker_values)[0]
        return None, f"opposite_type:{kind}@{source}"
    return None, "missing"
