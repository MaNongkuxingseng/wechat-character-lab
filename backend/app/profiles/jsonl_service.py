"""规范化 JSONL 特征生成、候选审核与角色配置预览服务。"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

from app.ingestion.security_flags import derive_security_flags
from app.profiles.jsonl_analyzer import (
    AnalyzerOutput,
    DisabledLLMSemanticAnalyzer,
    FakeSemanticAnalyzer,
    ObservableAnalyzer,
    ProfileAnalyzer,
)
from app.profiles.synthetic_adapter import (
    ProfileCandidate,
    UnmatchedEvidence,
    adapt_synthetic_signals,
)

LOGGER = logging.getLogger(__name__)
_REVIEW_STATES = {"pending", "accepted", "rejected", "needs_review"}


@dataclass(frozen=True)
class ReviewedCandidate:
    """候选快照中的审核包装；不改变 adapter 的稳定候选结构。"""

    candidate: ProfileCandidate
    analyzer_name: str
    analyzer_version: str
    review_status: str = "pending"
    reviewer_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "analyzer_name": self.analyzer_name,
            "analyzer_version": self.analyzer_version,
            "review_status": self.review_status,
            "reviewer_note": self.reviewer_note,
        }


@dataclass(frozen=True)
class JsonlProfileResult:
    """一次 JSONL 分析快照，不会写入已发布画像或数据库。"""

    snapshot_id: str
    status: str
    sample_counts: Mapping[str, int]
    analyzer_statuses: tuple[Mapping[str, Any], ...]
    candidates: tuple[ReviewedCandidate, ...]
    unmatched_evidence: tuple[UnmatchedEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "sample_counts": dict(sorted(self.sample_counts.items())),
            "analyzer_statuses": [dict(item) for item in self.analyzer_statuses],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "unmatched_evidence": [asdict(item) for item in self.unmatched_evidence],
        }


def analyze_normalized_messages(
    messages: Iterable[Mapping[str, Any]],
    *,
    sender_role_map: Mapping[str, str],
    analyzers: Sequence[ProfileAnalyzer] | None = None,
) -> JsonlProfileResult:
    """分析内存中的规范化消息；不读取文件、不写库、不进行网络调用。"""
    _validate_role_map(sender_role_map)
    analyzer_list = tuple(
        analyzers
        if analyzers is not None
        else (ObservableAnalyzer(), FakeSemanticAnalyzer(), DisabledLLMSemanticAnalyzer())
    )
    raw_messages = tuple(messages)
    safe_messages, rejected = _eligible_messages(raw_messages, sender_role_map)

    signals: list[Mapping[str, Any]] = []
    analyzer_statuses: list[Mapping[str, Any]] = []
    signal_analyzers: dict[tuple[str, str, str], tuple[str, str]] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for message in safe_messages:
        grouped[sender_role_map[str(message["sender"])]].append(message)

    for subject_id in sorted(set(sender_role_map.values())):
        role_messages = tuple(
            sorted(grouped.get(subject_id, ()), key=lambda item: str(item["message_id"]))
        )
        for analyzer in analyzer_list:
            output = analyzer.analyze(subject_id, role_messages)
            _validate_analyzer_output(output)
            analyzer_statuses.append(
                {
                    "subject_id": subject_id,
                    "analyzer_name": output.analyzer_name,
                    "analyzer_version": output.analyzer_version,
                    "status": output.status,
                    "sample_count": output.sample_count,
                }
            )
            for signal in output.signals:
                signals.append(signal)
                key = (
                    str(signal.get("subject_id", "")),
                    str(signal.get("category", "")),
                    str(signal.get("claim", "")),
                )
                signal_analyzers[key] = (output.analyzer_name, output.analyzer_version)

    adapted = adapt_synthetic_signals(
        safe_messages,
        signals,
        sender_role_map=sender_role_map,
        updated_at="candidate_snapshot",
    )
    candidates = tuple(
        ReviewedCandidate(
            candidate=item,
            analyzer_name=signal_analyzers.get(
                (item.subject_id, item.category, item.claim), ("unknown", "unknown")
            )[0],
            analyzer_version=signal_analyzers.get(
                (item.subject_id, item.category, item.claim), ("unknown", "unknown")
            )[1],
        )
        for item in adapted.candidates
    )
    all_unmatched = tuple(sorted((*rejected, *adapted.unmatched_evidence), key=_unmatched_key))
    sample_counts = {
        subject_id: len(grouped.get(subject_id, ()))
        for subject_id in sorted(set(sender_role_map.values()))
    }
    statuses = tuple(analyzer_statuses)
    ready = any(item["status"] == "ready" for item in statuses)
    status = "ready" if ready else "insufficient_samples"
    snapshot_id = _snapshot_id(raw_messages, sender_role_map, statuses, candidates)
    LOGGER.info(
        "JSONL profile analysis complete: messages=%d eligible=%d candidates=%d rejected=%d",
        len(raw_messages),
        len(safe_messages),
        len(candidates),
        len(all_unmatched),
    )
    return JsonlProfileResult(
        snapshot_id, status, sample_counts, statuses, candidates, all_unmatched
    )


def review_candidate(
    result: JsonlProfileResult,
    profile_item_id: str,
    *,
    status: str,
    reviewer_note: str | None = None,
) -> JsonlProfileResult:
    """返回审核后的新快照；候选只能按 ID 精确命中，不能直接发布。"""
    if status not in _REVIEW_STATES:
        raise ValueError("unsupported review status")
    matches = [
        item for item in result.candidates if item.candidate.profile_item_id == profile_item_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate not found or ambiguous")
    updated = tuple(
        replace(item, review_status=status, reviewer_note=reviewer_note)
        if item.candidate.profile_item_id == profile_item_id
        else item
        for item in result.candidates
    )
    return replace(result, candidates=updated)


def build_role_config_preview(
    result: JsonlProfileResult,
    *,
    subject_id: str,
    previous_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """仅将已接受候选写入预览结构，绝不修改 Role 或已发布画像。"""
    accepted = [
        item
        for item in result.candidates
        if item.candidate.subject_id == subject_id and item.review_status == "accepted"
    ]
    traits = [
        {
            "category": item.candidate.category,
            "description": item.candidate.claim,
            "evidence_ids": list(item.candidate.evidence_refs),
            "counter_evidence_ids": list(item.candidate.counter_evidence_refs),
            "confidence": item.candidate.confidence,
            "analyzer": f"{item.analyzer_name}@{item.analyzer_version}",
        }
        for item in accepted
    ]
    preview = {
        "role_id": subject_id,
        "source_snapshot_id": result.snapshot_id,
        "profile_traits": traits,
    }
    previous = dict(previous_config or {})
    return {
        "preview": preview,
        "previous": previous,
        "changes": _config_diff(previous, preview),
        "publishable": False,
        "reason": "JSONL 候选尚未持久化并经过现有发布流程审核。",
    }


def _eligible_messages(
    messages: Sequence[Mapping[str, Any]], sender_role_map: Mapping[str, str]
) -> tuple[tuple[Mapping[str, Any], ...], tuple[UnmatchedEvidence, ...]]:
    ids = [
        message.get("message_id") if isinstance(message, Mapping) else None
        for message in messages
    ]
    counts = Counter(item for item in ids if isinstance(item, str) and item)
    eligible: list[Mapping[str, Any]] = []
    rejected: list[UnmatchedEvidence] = []
    for index, message in enumerate(messages, start=1):
        message_id = message.get("message_id") if isinstance(message, Mapping) else None
        evidence_id = message_id if isinstance(message_id, str) else f"row-{index}"
        reason = _message_rejection(message, message_id, counts, sender_role_map)
        if reason is None:
            eligible.append(message)
        else:
            rejected.append(UnmatchedEvidence(f"input-{index:04d}", evidence_id, reason, "message"))
    return tuple(eligible), tuple(rejected)


def _message_rejection(
    message: Any,
    message_id: Any,
    counts: Mapping[str, int],
    sender_role_map: Mapping[str, str],
) -> str | None:
    if not isinstance(message, Mapping):
        return "invalid_message"
    if not isinstance(message_id, str) or not message_id.strip():
        return "invalid_message_id"
    if message_id != message_id.strip():
        return "invalid_message_id"
    if counts.get(message_id) != 1:
        return "duplicate_message_id"
    sender = message.get("sender")
    if not isinstance(sender, str) or sender not in sender_role_map:
        return "unmapped_sender"
    flag_reason = _validate_security_provenance(message)
    if flag_reason:
        return flag_reason
    if message.get("message_type") != "text":
        return "non_text_message"
    if message.get("content_status") != "present":
        return "content_not_present"
    if not isinstance(message.get("content"), str) or not message["content"].strip():
        return "empty_or_invalid_content"
    return None


def _validate_security_provenance(message: Mapping[str, Any]) -> str | None:
    """重算安全标记并与规范化审计记录比对，拒绝 unknown/conflict/伪造来源。"""
    if message.get("is_ai_generated") is not False or message.get("is_system") is not False:
        return "unsafe_security_flags"
    provenance = message.get("security_flag_sources")
    inputs = message.get("security_flag_inputs")
    if not isinstance(provenance, Mapping) or not isinstance(inputs, Mapping):
        return "security_provenance_missing"
    top_level = inputs.get("top_level")
    source_metadata = inputs.get("source_metadata")
    if not isinstance(top_level, Mapping) or not isinstance(source_metadata, Mapping):
        return "security_provenance_incomplete"
    source_message: dict[str, Any] = dict(top_level)
    source_message["source_metadata"] = dict(source_metadata)
    derived = derive_security_flags(source_message)
    if derived.is_ai_generated is not False or derived.is_system is not False:
        return "security_provenance_not_explicitly_safe"
    observed = {
        field: provenance.get(field)
        for field in ("is_ai_generated", "is_system")
    }
    if observed != derived.source_map():
        return "security_provenance_mismatch"
    return None


def _validate_role_map(sender_role_map: Mapping[str, str]) -> None:
    """拒绝隐式昵称推断和无效角色值。"""
    if not isinstance(sender_role_map, Mapping) or not sender_role_map:
        raise ValueError("sender_role_map must be a non-empty explicit mapping")
    if any(
        not isinstance(sender, str)
        or not sender.strip()
        or not isinstance(role_id, str)
        or role_id not in {"role_a", "role_b"}
        for sender, role_id in sender_role_map.items()
    ):
        raise ValueError("sender_role_map must map explicit sender labels to role_a or role_b")


def _validate_analyzer_output(output: Any) -> None:
    """拒绝不符合版本化 AnalyzerOutput 契约的 Provider 响应。"""
    if not isinstance(output, AnalyzerOutput):
        raise TypeError("analyzer output must be AnalyzerOutput")
    if (
        not isinstance(output.analyzer_name, str)
        or not output.analyzer_name.strip()
        or not isinstance(output.analyzer_version, str)
        or not output.analyzer_version.strip()
        or output.status not in {"ready", "insufficient_samples", "provider_disabled"}
        or isinstance(output.sample_count, bool)
        or not isinstance(output.sample_count, int)
        or output.sample_count < 0
        or not isinstance(output.signals, (tuple, list))
        or any(not isinstance(item, Mapping) for item in output.signals)
    ):
        raise ValueError("invalid analyzer output contract")


def _snapshot_id(
    messages: Sequence[Mapping[str, Any]],
    sender_role_map: Mapping[str, str],
    statuses: Sequence[Mapping[str, Any]],
    candidates: Sequence[ReviewedCandidate],
) -> str:
    """候选快照 ID 只标识本次输入/分析结果，不是跨版本特征 ID。"""
    payload = {
        "messages": [
            {"message_id": item.get("message_id"), "content": item.get("content")}
            for item in messages
            if isinstance(item, Mapping)
        ],
        "sender_role_map": dict(sorted(sender_role_map.items())),
        "analyzers": [dict(item) for item in statuses],
        "candidate_ids": sorted(item.candidate.profile_item_id for item in candidates),
    }
    payload["messages"] = sorted(
        payload["messages"], key=lambda item: (str(item["message_id"]), str(item["content"]))
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "snapshot_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _config_diff(previous: Mapping[str, Any], preview: Mapping[str, Any]) -> dict[str, Any]:
    old_traits = previous.get("profile_traits", [])
    new_traits = preview.get("profile_traits", [])
    old = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in old_traits}
    new = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in new_traits}
    return {
        "added": [json.loads(item) for item in sorted(new - old)],
        "removed": [json.loads(item) for item in sorted(old - new)],
    }


def _unmatched_key(item: UnmatchedEvidence) -> tuple[str, str, str, str]:
    return item.signal_id, item.kind, item.evidence_id, item.reason


def parse_normalized_jsonl(text: str) -> tuple[Mapping[str, Any], ...]:
    """解析已规范化 JSONL 字符串；不访问文件系统或修补非法记录。"""
    if not isinstance(text, str):
        raise TypeError("JSONL input must be text")
    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"JSONL record at line {line_number} must be an object")
        records.append(value)
    return tuple(records)
