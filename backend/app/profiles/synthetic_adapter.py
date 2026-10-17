"""合成画像适配器 / Synthetic profile adapter.

本模块只处理已经标准化的消息字典和上游分析器产生的候选信号。
它不读取文件、不调用网络 Provider，也不把候选结论直接写入画像数据库。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

LOGGER = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_TEXT_MESSAGE_TYPES = {"text"}
_EXCLUDED_MESSAGE_TYPES = {"ai", "assistant", "system"}


@dataclass(frozen=True)
class UnmatchedEvidence:
    """无法安全回指到唯一消息的证据引用。"""

    signal_id: str
    evidence_id: str
    reason: str
    kind: str = "evidence"


@dataclass(frozen=True)
class ProfileCandidate:
    """统一画像候选结构；confidence 为 None 时表示 unknown。"""

    profile_item_id: str
    subject_id: str
    category: str
    claim: str
    evidence_refs: tuple[str, ...]
    confidence: float | None
    counter_evidence_refs: tuple[str, ...]
    observed_at: str | None
    updated_at: str
    inference_basis: str | None = None
    conflict_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化且字段顺序稳定的字典。"""
        result = asdict(self)
        result["evidence_refs"] = list(self.evidence_refs)
        result["counter_evidence_refs"] = list(self.counter_evidence_refs)
        return result


@dataclass(frozen=True)
class AdaptationResult:
    """适配结果；被拒绝的候选只通过 unmatched_evidence 暴露原因。"""

    candidates: tuple[ProfileCandidate, ...]
    unmatched_evidence: tuple[UnmatchedEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        """返回 API/测试可使用的结构，不包含消息正文。"""
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "unmatched_evidence": [asdict(item) for item in self.unmatched_evidence],
        }


def adapt_synthetic_signals(
    messages: Sequence[Mapping[str, Any]],
    signals: Sequence[Mapping[str, Any]],
    *,
    sender_role_map: Mapping[str, str],
    updated_at: str = "unknown",
) -> AdaptationResult:
    """将合成候选信号适配为可追溯画像候选。

    ``messages`` 应来自标准化 JSONL 的单次会话；``signals`` 是规则分析器或
    测试 stub 的结构化输出。只有消息 ID 唯一、角色一致、消息类型可用且
    引用完整的信号才会进入 candidates。原始 message_id 永不改写。
    """
    message_index: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for message in messages:
        message_id = message.get("message_id")
        if isinstance(message_id, str) and message_id:
            message_index[message_id].append(message)

    candidates: list[ProfileCandidate] = []
    unmatched: list[UnmatchedEvidence] = []
    for index, signal in enumerate(signals, start=1):
        signal_id = _signal_id(signal, index)
        subject_id = signal.get("subject_id")
        category = signal.get("category")
        claim = signal.get("claim")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (subject_id, category, claim)
        ):
            unmatched.append(
                UnmatchedEvidence(signal_id, "", "invalid_signal", kind="signal")
            )
            continue

        signal_errors: list[UnmatchedEvidence] = []
        evidence_ids = _validated_reference_ids(
            signal, "evidence_ids", signal_id, signal_errors
        )
        counter_ids = _validated_reference_ids(
            signal, "counter_evidence_ids", signal_id, signal_errors, required=False
        )
        overlap = set(evidence_ids) & set(counter_ids)
        if overlap:
            signal_errors.append(
                UnmatchedEvidence(
                    signal_id,
                    min(overlap),
                    "duplicate_evidence_reference",
                    kind="evidence",
                )
            )
        evidence_quotes = _quote_map(signal.get("evidence_quotes"))
        counter_quotes = _quote_map(signal.get("counter_evidence_quotes"))
        evidence_messages = _resolve_evidence(
            signal_id,
            evidence_ids,
            message_index,
            subject_id,
            sender_role_map,
            signal_errors,
            expected_quotes=evidence_quotes,
        )
        counter_messages = _resolve_evidence(
            signal_id,
            counter_ids,
            message_index,
            subject_id,
            sender_role_map,
            signal_errors,
            kind="counter_evidence",
            expected_quotes=counter_quotes,
        )
        if _requires_temporal(signal):
            for evidence_id, message in [*evidence_messages, *counter_messages]:
                if _timestamp(message) is None:
                    signal_errors.append(
                        UnmatchedEvidence(
                            signal_id, evidence_id, "invalid_timestamp", kind="temporal"
                        )
                    )

        if signal_errors:
            unmatched.extend(signal_errors)
            continue

        resolved_ids = tuple(message["message_id"] for _, message in evidence_messages)
        resolved_counter_ids = tuple(message["message_id"] for _, message in counter_messages)
        profile_item_id = _profile_item_id(
            str(subject_id),
            str(category),
            str(claim),
            resolved_ids,
            resolved_counter_ids,
        )
        timestamps = [
            timestamp
            for _, message in [*evidence_messages, *counter_messages]
            if (timestamp := _timestamp(message))
        ]
        candidates.append(
            ProfileCandidate(
                profile_item_id=profile_item_id,
                subject_id=str(subject_id),
                category=str(category),
                claim=_normalize_claim(str(claim)),
                evidence_refs=resolved_ids,
                confidence=_confidence(signal.get("confidence")),
                counter_evidence_refs=resolved_counter_ids,
                observed_at=max(timestamps) if timestamps else None,
                updated_at=updated_at,
                inference_basis=(
                    signal.get("inference_basis")
                    if isinstance(signal.get("inference_basis"), str)
                    else None
                ),
                conflict_status=(
                    signal.get("conflict_status")
                    if signal.get("conflict_status") in {"none", "conflict", "unresolved"}
                    else ("conflict" if resolved_counter_ids else "none")
                ),
            )
        )

    candidates.sort(key=lambda item: item.profile_item_id)
    unmatched.sort(key=lambda item: (item.signal_id, item.kind, item.evidence_id, item.reason))
    LOGGER.info(
        "synthetic profile adaptation complete: candidates=%d unmatched=%d",
        len(candidates),
        len(unmatched),
    )
    return AdaptationResult(tuple(candidates), tuple(unmatched))


def _resolve_evidence(
    signal_id: str,
    evidence_ids: tuple[str, ...],
    message_index: Mapping[str, list[Mapping[str, Any]]],
    subject_id: str,
    sender_role_map: Mapping[str, str],
    errors: list[UnmatchedEvidence],
    *,
    kind: str = "evidence",
    expected_quotes: Mapping[str, str] | None = None,
) -> list[tuple[str, Mapping[str, Any]]]:
    resolved: list[tuple[str, Mapping[str, Any]]] = []
    for evidence_id in evidence_ids:
        matches = message_index.get(evidence_id, [])
        if not matches:
            errors.append(UnmatchedEvidence(signal_id, evidence_id, "not_found", kind=kind))
            continue
        if len(matches) != 1:
            errors.append(
                UnmatchedEvidence(signal_id, evidence_id, "ambiguous_message_id", kind=kind)
            )
            continue
        message = matches[0]
        if not _is_eligible_text(message, errors, signal_id, evidence_id, kind):
            errors.append(
                UnmatchedEvidence(signal_id, evidence_id, "message_not_eligible", kind=kind)
            )
            continue
        expected_quote = (expected_quotes or {}).get(evidence_id)
        if expected_quote is not None and expected_quote not in str(message["content"]):
            errors.append(UnmatchedEvidence(signal_id, evidence_id, "quote_mismatch", kind=kind))
            continue
        sender = message.get("sender")
        if not isinstance(sender, str) or sender_role_map.get(sender) != subject_id:
            errors.append(UnmatchedEvidence(signal_id, evidence_id, "role_mismatch", kind=kind))
            continue
        resolved.append((evidence_id, message))
    return resolved


def _is_eligible_text(
    message: Mapping[str, Any],
    errors: list[UnmatchedEvidence],
    signal_id: str,
    evidence_id: str,
    kind: str,
) -> bool:
    for field in ("is_ai_generated", "is_system"):
        if field not in message:
            errors.append(
                UnmatchedEvidence(signal_id, evidence_id, "security_flag_missing", kind=kind)
            )
            return False
        value = message[field]
        if value is None and _attested_unknown_security(message, field):
            continue
        if not isinstance(value, bool):
            errors.append(
                UnmatchedEvidence(signal_id, evidence_id, "invalid_security_flag", kind=kind)
            )
            return False

    metadata = message.get("source_metadata")
    if isinstance(metadata, Mapping):
        for field in ("is_ai_generated", "is_system"):
            if field in metadata and not isinstance(metadata[field], bool):
                errors.append(
                    UnmatchedEvidence(signal_id, evidence_id, "invalid_security_flag", kind=kind)
                )
                return False
            if metadata.get(field) is True:
                return False

    message_type = message.get("message_type")
    if not isinstance(message_type, str):
        return False
    message_type = message_type.lower()
    if message_type not in _TEXT_MESSAGE_TYPES or message_type in _EXCLUDED_MESSAGE_TYPES:
        return False
    if message.get("content_status") != "present" or not isinstance(message.get("content"), str):
        return False
    if message["is_ai_generated"] or message["is_system"]:
        return False
    return True


def _attested_unknown_security(message: Mapping[str, Any], field: str) -> bool:
    """Allow an explicit human attestation without rewriting unknown flags.

    Source-level attestation can authorize bounded transfer while the normalized
    message keeps ``None`` for fields that the source cannot prove. Confirmed
    unsafe or conflicting provenance never passes this helper.
    """
    attestation = message.get("security_attestation")
    if not isinstance(attestation, Mapping) or not (
        attestation.get("human_authored") is True
        and attestation.get("contains_ai_generated") is False
        and attestation.get("contains_system_messages") is False
        and isinstance(attestation.get("reviewer_id"), str)
        and bool(attestation["reviewer_id"].strip())
        and isinstance(attestation.get("reason"), str)
        and bool(attestation["reason"].strip())
        and isinstance(attestation.get("attested_at"), str)
        and bool(attestation["attested_at"].strip())
    ):
        return False
    sources = message.get("security_flag_sources")
    inputs = message.get("security_flag_inputs")
    if not isinstance(sources, Mapping) or not isinstance(inputs, Mapping):
        return False
    if not isinstance(inputs.get("top_level"), Mapping) or not isinstance(
        inputs.get("source_metadata"), Mapping
    ):
        return False
    source = sources.get(field)
    return isinstance(source, str) and source.startswith("unknown:")


def _timestamp(message: Mapping[str, Any]) -> str | None:
    if message.get("timestamp_status") != "parsed_utc":
        return None
    raw = message.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return raw


def _requires_temporal(signal: Mapping[str, Any]) -> bool:
    return signal.get("requires_temporal") is True


def _validated_reference_ids(
    signal: Mapping[str, Any],
    field: str,
    signal_id: str,
    errors: list[UnmatchedEvidence],
    *,
    required: bool = True,
) -> tuple[str, ...]:
    """严格解析证据 ID，拒绝缺失、空值、非法类型和重复引用。"""
    if field not in signal:
        if required:
            errors.append(UnmatchedEvidence(signal_id, "", "evidence_field_missing"))
        return ()
    value = signal[field]
    if not required and isinstance(value, (list, tuple)) and not value:
        return ()
    if not isinstance(value, (list, tuple)) or not value:
        errors.append(UnmatchedEvidence(signal_id, "", "evidence_field_empty_or_invalid"))
        return ()
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(UnmatchedEvidence(signal_id, "", "invalid_evidence_reference"))
        return ()
    refs = tuple(item.strip() for item in value)
    if len(set(refs)) != len(refs):
        errors.append(UnmatchedEvidence(signal_id, refs[0], "duplicate_evidence_reference"))
        return ()
    return refs


def _quote_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: quote
        for key, quote in value.items()
        if isinstance(key, str) and isinstance(quote, str)
    }


def _signal_id(signal: Mapping[str, Any], index: int) -> str:
    value = signal.get("signal_id")
    return value if isinstance(value, str) and value else f"signal-{index:04d}"


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if 0 <= float(value) <= 1:
        return float(value)
    return None


def _normalize_claim(claim: str) -> str:
    return _WHITESPACE_RE.sub(" ", claim).strip()


def _profile_item_id(
    subject_id: str,
    category: str,
    claim: str,
    evidence_refs: tuple[str, ...],
    counter_refs: tuple[str, ...],
) -> str:
    payload = {
        "subject_id": subject_id,
        "category": category,
        "claim": _normalize_claim(claim),
        "evidence_refs": list(evidence_refs),
        "counter_evidence_refs": list(counter_refs),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "pi_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
