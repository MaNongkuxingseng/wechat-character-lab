"""P2-B 合成数据适配器回归测试；不读取 data/，不调用外部服务。"""

from __future__ import annotations

import logging

from app.profiles.synthetic_adapter import adapt_synthetic_signals

ROLE_MAP = {"self": "role_a", "friend": "role_b"}


def _messages() -> list[dict[str, object]]:
    return [
        {
            "message_id": "syn-001",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "我喜欢清淡的茶。",
            "timestamp": "2026-01-01T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-002",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "我不喜欢太甜的饮料。",
            "timestamp": "2026-01-02T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-003",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "这个方案我还在犹豫。",
            "timestamp": "2026-01-03T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-004",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "后来我又觉得甜点也可以。",
            "timestamp": "2026-02-01T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-005",
            "sender": "self",
            "message_type": "text",
            "content_status": "present",
            "content": "我可以帮你查资料。",
            "timestamp": "2026-01-04T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-006",
            "sender": "friend",
            "message_type": "image",
            "content_status": "missing",
            "content": None,
            "timestamp": "2026-01-05T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-007",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "系统生成的摘要。",
            "is_ai_generated": True,
            "timestamp": "2026-01-06T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-008",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "这条消息时间不合法。",
            "timestamp": "not-a-time",
            "timestamp_status": "invalid",
        },
        {
            "message_id": "syn-009",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "重复 ID 的第一条。",
            "timestamp": "2026-01-07T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
        {
            "message_id": "syn-009",
            "sender": "friend",
            "message_type": "text",
            "content_status": "present",
            "content": "重复 ID 的第二条。",
            "timestamp": "2026-01-08T10:00:00Z",
            "timestamp_status": "parsed_utc",
        },
    ]


def _signals() -> list[dict[str, object]]:
    return [
        {
            "signal_id": "positive",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "偏好清淡的茶",
            "evidence_ids": ["syn-001"],
            "confidence": 0.8,
        },
        {
            "signal_id": "negative",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "不喜欢太甜的饮料",
            "evidence_ids": ["syn-002"],
            "confidence": 0.7,
        },
        {
            "signal_id": "uncertain",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "对方案态度犹豫",
            "evidence_ids": ["syn-003"],
        },
        {
            "signal_id": "changed",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "对甜点的偏好发生变化",
            "evidence_ids": ["syn-004"],
            "counter_evidence_ids": ["syn-002"],
            "requires_temporal": True,
            "confidence": 0.6,
        },
        {
            "signal_id": "other-role",
            "subject_id": "role_a",
            "category": "behavior",
            "claim": "愿意协助查资料",
            "evidence_ids": ["syn-005"],
            "confidence": 0.5,
        },
        {
            "signal_id": "media",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "图片表达了偏好",
            "evidence_ids": ["syn-006"],
        },
        {
            "signal_id": "ai",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "系统摘要表达了偏好",
            "evidence_ids": ["syn-007"],
        },
        {
            "signal_id": "bad-time",
            "subject_id": "role_b",
            "category": "behavior",
            "claim": "无效时间不能证明时序变化",
            "evidence_ids": ["syn-008"],
            "requires_temporal": True,
        },
        {
            "signal_id": "duplicate",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "重复 ID 不应猜测证据",
            "evidence_ids": ["syn-009"],
        },
        {
            "signal_id": "missing",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "不存在的消息不能作为证据",
            "evidence_ids": ["syn-404"],
        },
        {
            "signal_id": "bad-quote",
            "subject_id": "role_b",
            "category": "preference",
            "claim": "引文不匹配时拒绝候选",
            "evidence_ids": ["syn-001"],
            "evidence_quotes": {"syn-001": "不存在的引文"},
        },
    ]


def test_adapter_preserves_ids_roles_and_positive_negative_evidence():
    result = adapt_synthetic_signals(
        _messages(), _signals(), sender_role_map=ROLE_MAP, updated_at="2026-02-02T00:00:00Z"
    )

    assert len(result.candidates) == 5
    claims = {candidate.claim for candidate in result.candidates}
    assert "偏好清淡的茶" in claims
    assert "不喜欢太甜的饮料" in claims
    changed = next(item for item in result.candidates if item.claim == "对甜点的偏好发生变化")
    assert changed.evidence_refs == ("syn-004",)
    assert changed.counter_evidence_refs == ("syn-002",)
    assert changed.observed_at == "2026-02-01T10:00:00Z"
    assert all(ref.startswith("syn-") for item in result.candidates for ref in item.evidence_refs)


def test_adapter_rejects_ambiguous_missing_media_ai_and_invalid_temporal_evidence():
    result = adapt_synthetic_signals(_messages(), _signals(), sender_role_map=ROLE_MAP)
    reasons = {(item.evidence_id, item.reason) for item in result.unmatched_evidence}

    assert ("syn-006", "message_not_eligible") in reasons
    assert ("syn-007", "message_not_eligible") in reasons
    assert ("syn-008", "invalid_timestamp") in reasons
    assert ("syn-009", "ambiguous_message_id") in reasons
    assert ("syn-404", "not_found") in reasons
    assert ("syn-001", "quote_mismatch") in reasons


def test_adapter_is_deterministic_and_missing_confidence_is_unknown():
    first = adapt_synthetic_signals(
        _messages(), _signals(), sender_role_map=ROLE_MAP, updated_at="fixed"
    ).to_dict()
    second = adapt_synthetic_signals(
        _messages(), _signals(), sender_role_map=ROLE_MAP, updated_at="fixed"
    ).to_dict()

    assert first == second
    uncertain = next(item for item in first["candidates"] if item["claim"] == "对方案态度犹豫")
    assert uncertain["confidence"] is None
    assert uncertain["evidence_refs"] == ["syn-003"]


def test_adapter_logs_only_counts_and_no_message_content(caplog):
    caplog.set_level(logging.INFO)
    adapt_synthetic_signals(_messages(), _signals(), sender_role_map=ROLE_MAP)
    output = " ".join(record.getMessage() for record in caplog.records)
    assert "synthetic profile adaptation complete" in output
    assert "我喜欢清淡的茶" not in output
    assert "syn-001" not in output
