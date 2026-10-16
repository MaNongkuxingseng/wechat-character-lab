"""P2-B 合成数据适配器回归测试；不读取 data/，不调用外部服务。"""

from __future__ import annotations

import logging

from app.profiles.synthetic_adapter import adapt_synthetic_signals

ROLE_MAP = {"self": "role_a", "friend": "role_b"}


def _messages() -> list[dict[str, object]]:
    messages = [
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
    return [
        {"is_ai_generated": False, "is_system": False, **message}
        for message in messages
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


def _basic_signal(**overrides: object) -> dict[str, object]:
    signal: dict[str, object] = {
        "signal_id": "invalid-input",
        "subject_id": "role_b",
        "category": "preference",
        "claim": "invalid input must be rejected",
    }
    signal.update(overrides)
    return signal


def _message_copy(message_id: str) -> dict[str, object]:
    return next(message.copy() for message in _messages() if message["message_id"] == message_id)


def test_adapter_rejects_missing_empty_invalid_partial_and_duplicate_evidence():
    cases = [
        (_basic_signal(), "evidence_field_missing"),
        (_basic_signal(evidence_ids=[]), "evidence_field_empty_or_invalid"),
        (_basic_signal(evidence_ids="syn-001"), "evidence_field_empty_or_invalid"),
        (_basic_signal(evidence_ids=["syn-001", 7]), "invalid_evidence_reference"),
        (_basic_signal(evidence_ids=["syn-001", "syn-001"]), "duplicate_evidence_reference"),
    ]

    for signal, expected_reason in cases:
        result = adapt_synthetic_signals(_messages(), [signal], sender_role_map=ROLE_MAP)
        assert result.candidates == ()
        assert any(item.reason == expected_reason for item in result.unmatched_evidence)


def test_adapter_requires_strict_temporal_status_and_timezone_for_both_polarities():
    missing_status = _message_copy("syn-003")
    missing_status.pop("timestamp_status")
    naive_timestamp = _message_copy("syn-004")
    naive_timestamp["timestamp"] = "2026-02-01T10:00:00"
    invalid_counter = _message_copy("syn-002")
    invalid_counter["timestamp_status"] = "invalid"

    cases = (
        ("syn-003", missing_status, _basic_signal(evidence_ids=["syn-003"])),
        ("syn-004", naive_timestamp, _basic_signal(evidence_ids=["syn-004"])),
        (
            "syn-002",
            invalid_counter,
            _basic_signal(
                evidence_ids=["syn-004"],
                counter_evidence_ids=["syn-002"],
            ),
        ),
    )
    for message_id, replacement, signal in cases:
        signal = {**signal, "requires_temporal": True}
        messages = [message for message in _messages() if message["message_id"] != message_id]
        messages.append(replacement)
        result = adapt_synthetic_signals(messages, [signal], sender_role_map=ROLE_MAP)
        assert result.candidates == ()
        assert any(item.reason == "invalid_timestamp" for item in result.unmatched_evidence)


def test_adapter_rejects_missing_and_non_boolean_security_flags():
    missing = _message_copy("syn-001")
    missing.pop("is_system")
    string_flag = _message_copy("syn-001")
    string_flag["is_ai_generated"] = "true"
    numeric_flag = _message_copy("syn-001")
    numeric_flag["is_system"] = 0
    metadata_flag = _message_copy("syn-001")
    metadata_flag["source_metadata"] = {"is_system": "false"}

    for message, expected_reason in (
        (missing, "security_flag_missing"),
        (string_flag, "invalid_security_flag"),
        (numeric_flag, "invalid_security_flag"),
        (metadata_flag, "invalid_security_flag"),
    ):
        result = adapt_synthetic_signals(
            [message],
            [_basic_signal(evidence_ids=["syn-001"])],
            sender_role_map=ROLE_MAP,
        )
        assert result.candidates == ()
        assert any(item.reason == expected_reason for item in result.unmatched_evidence)


def test_synthetic_end_to_end_keeps_auditable_candidates_and_rejections():
    """验证合成消息到候选/拒绝清单的完整可审计链路。"""
    messages = _messages()
    base_signals = _signals()
    extra_signals = [
        _basic_signal(
            signal_id="unmapped-role",
            subject_id="role_unknown",
            evidence_ids=["syn-001"],
        ),
        _basic_signal(
            signal_id="cross-polarity-duplicate",
            evidence_ids=["syn-001"],
            counter_evidence_ids=["syn-001"],
        ),
    ]
    signals = [*base_signals, *extra_signals]

    result = adapt_synthetic_signals(
        messages,
        signals,
        sender_role_map=ROLE_MAP,
        updated_at="2026-02-02T00:00:00Z",
    )
    unique_messages = {
        message["message_id"]: message
        for message in messages
        if sum(item["message_id"] == message["message_id"] for item in messages) == 1
    }

    assert result.candidates
    assert all(candidate.evidence_refs for candidate in result.candidates)
    for candidate in result.candidates:
        assert all(ref in unique_messages for ref in candidate.evidence_refs)
        assert all(ref in unique_messages for ref in candidate.counter_evidence_refs)
        assert all(
            ROLE_MAP[unique_messages[ref]["sender"]] == candidate.subject_id
            for ref in (*candidate.evidence_refs, *candidate.counter_evidence_refs)
        )

    rejection_pairs = {
        (item.signal_id, item.reason) for item in result.unmatched_evidence
    }
    assert ("unmapped-role", "role_mismatch") in rejection_pairs
    assert ("cross-polarity-duplicate", "duplicate_evidence_reference") in rejection_pairs
    assert {item.signal_id for item in result.unmatched_evidence} >= {
        "media",
        "ai",
        "bad-time",
        "duplicate",
        "missing",
        "bad-quote",
    }

    reordered_messages = list(reversed(messages))
    reordered_signals = [dict(reversed(list(signal.items()))) for signal in signals]
    repeated = adapt_synthetic_signals(
        reordered_messages,
        reordered_signals,
        sender_role_map=dict(reversed(list(ROLE_MAP.items()))),
        updated_at="2026-02-02T00:00:00Z",
    )
    assert result.to_dict() == repeated.to_dict()
