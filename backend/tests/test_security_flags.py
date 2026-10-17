import pytest

from app.ingestion.security_flags import derive_security_flags
from app.ingestion.wechat_normalizer import normalize_payload
from app.profiles.synthetic_adapter import adapt_synthetic_signals


def _raw_message(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "local_id": 1,
        "server_id": 2,
        "create_time": 1700000000,
        "sender_name": "A",
        "type_code": 1,
        "type": "文本",
        "content": "合成安全标记消息",
    }
    message.update(overrides)
    return message


def test_explicit_boolean_flags_are_preserved_with_auditable_sources():
    flags = derive_security_flags(
        {"is_ai_generated": True, "is_system": False, "message_type": "text"}
    )

    assert flags.is_ai_generated is True
    assert flags.is_system is False
    assert flags.source_map() == {
        "is_ai_generated": "explicit:message.is_ai_generated",
        "is_system": "explicit:message.is_system",
    }


def test_explicit_type_markers_only_confirm_their_own_property():
    system_flags = derive_security_flags({"message_type": "system"})
    ai_flags = derive_security_flags({"message_type": "assistant"})

    assert system_flags.is_system is True
    assert system_flags.is_ai_generated is None
    assert ai_flags.is_ai_generated is True
    assert ai_flags.is_system is None


def test_missing_or_unknown_sources_remain_unknown():
    flags = derive_security_flags({"message_type": "text", "sender": "A"})

    assert flags.is_ai_generated is None
    assert flags.is_system is None
    assert flags.source_map() == {
        "is_ai_generated": "unknown:no_reliable_source",
        "is_system": "unknown:no_reliable_source",
    }


@pytest.mark.parametrize("invalid_value", ["false", 0, [], {}])
def test_invalid_flag_types_are_not_coerced(invalid_value):
    flags = derive_security_flags(
        {
            "is_ai_generated": invalid_value,
            "is_system": invalid_value,
            "message_type": "text",
        }
    )

    assert flags.is_ai_generated is None
    assert flags.is_system is None
    assert flags.source_map() == {
        "is_ai_generated": "invalid_type:message.is_ai_generated",
        "is_system": "invalid_type:message.is_system",
    }


def test_conflicting_source_flags_remain_unknown():
    flags = derive_security_flags(
        {
            "is_ai_generated": False,
            "source_metadata": {"is_ai_generated": True},
            "is_system": False,
        }
    )

    assert flags.is_ai_generated is None
    assert flags.is_system is False
    assert flags.source_map() == {
        "is_ai_generated": "conflict:message.is_ai_generated+source_metadata.is_ai_generated",
        "is_system": "explicit:message.is_system",
    }


@pytest.mark.parametrize(
    ("message", "field", "expected_source"),
    [
        (
            {"is_system": False, "message_type": "system"},
            "is_system",
            "conflict:explicit:message.is_system+type:system@message.message_type",
        ),
        (
            {"is_ai_generated": False, "message_type": "assistant"},
            "is_ai_generated",
            "conflict:explicit:message.is_ai_generated+type:assistant@message.message_type",
        ),
        (
            {"is_ai_generated": True, "message_type": "system"},
            "is_ai_generated",
            "conflict:explicit:message.is_ai_generated+type:system@message.message_type",
        ),
        (
            {"is_system": True, "message_type": "ai"},
            "is_system",
            "conflict:explicit:message.is_system+type:ai@message.message_type",
        ),
    ],
)
def test_explicit_flags_conflicting_with_type_markers_remain_unknown(
    message, field, expected_source
):
    flags = derive_security_flags(message)

    assert getattr(flags, field) is None
    assert flags.source_map()[field] == expected_source


def test_contradictory_explicit_type_sources_are_unknown_for_both_flags():
    flags = derive_security_flags(
        {"message_type": "system", "source_metadata": {"type": "assistant"}}
    )

    assert flags.is_ai_generated is None
    assert flags.is_system is None
    assert flags.source_map() == {
        "is_ai_generated": "conflict:type_markers:assistant+system",
        "is_system": "conflict:type_markers:assistant+system",
    }


def test_agreeing_type_sources_are_deterministic_and_auditable():
    first = derive_security_flags(
        {
            "message_type": "assistant",
            "source_metadata": {"type": "ai"},
        }
    )
    second = derive_security_flags(
        {
            "source_metadata": {"type": "ai"},
            "message_type": "assistant",
        }
    )

    assert first == second
    assert first.is_ai_generated is True
    assert first.is_system is None
    assert first.source_map()["is_ai_generated"] == "type:ai@source_metadata.type"


def test_normalizer_emits_three_state_flags_and_preserves_sources():
    records, _ = normalize_payload({"messages": [_raw_message()]}, source_file="synthetic.json")
    unknown = records[0]
    assert unknown["is_ai_generated"] is None
    assert unknown["is_system"] is None
    assert unknown["security_flag_sources"] == {
        "is_ai_generated": "unknown:no_reliable_source",
        "is_system": "unknown:no_reliable_source",
    }
    assert unknown["security_flag_inputs"] == {
        "top_level": {"type": "文本", "type_code": 1},
        "source_metadata": {},
    }

    records, _ = normalize_payload(
        {
            "messages": [
                _raw_message(is_ai_generated=True, is_system=False),
                _raw_message(local_id=3, server_id=4, type="system", type_code=999),
            ]
        },
        source_file="synthetic.json",
    )
    assert records[0]["is_ai_generated"] is True
    assert records[0]["is_system"] is False
    assert records[1]["is_ai_generated"] is None
    assert records[1]["is_system"] is True


def test_normalizer_preserves_conflicting_type_sources_without_overwriting_them():
    records, _ = normalize_payload(
        {
            "messages": [
                _raw_message(
                    type="text",
                    source_metadata={"type": "system", "message_type": "system"},
                )
            ]
        },
        source_file="synthetic.json",
    )

    record = records[0]
    assert record["is_ai_generated"] is None
    assert record["is_system"] is True
    assert record["security_flag_sources"] == {
        "is_ai_generated": "unknown:opposite_type:system@source_metadata.message_type",
        "is_system": "type:system@source_metadata.message_type",
    }
    assert record["security_flag_inputs"] == {
        "top_level": {"type": "text", "type_code": 1},
        "source_metadata": {"type": "system", "message_type": "system"},
    }


def test_normalizer_keeps_top_level_and_nested_ai_type_conflict_auditable():
    records, _ = normalize_payload(
        {
            "messages": [
                _raw_message(
                    type="system",
                    message_type="system",
                    source_metadata={"type": "assistant"},
                )
            ]
        },
        source_file="synthetic.json",
    )

    record = records[0]
    assert record["is_ai_generated"] is None
    assert record["is_system"] is None
    assert record["security_flag_sources"] == {
        "is_ai_generated": "conflict:type_markers:assistant+system",
        "is_system": "conflict:type_markers:assistant+system",
    }
    assert record["security_flag_inputs"] == {
        "top_level": {"type": "system", "message_type": "system", "type_code": 1},
        "source_metadata": {"type": "assistant"},
    }


def test_unknown_flags_cannot_bypass_adapter_eligibility():
    records, _ = normalize_payload({"messages": [_raw_message()]}, source_file="synthetic.json")
    result = adapt_synthetic_signals(
        records,
        [
            {
                "signal_id": "unknown-security",
                "subject_id": "role_a",
                "category": "preference",
                "claim": "未知安全标记不可作为证据",
                "evidence_ids": [records[0]["message_id"]],
            }
        ],
        sender_role_map={"A": "role_a"},
    )

    assert result.candidates == ()
    assert any(item.reason == "invalid_security_flag" for item in result.unmatched_evidence)


def test_explicit_safe_flags_pass_but_confirmed_ai_or_system_flags_do_not():
    records, _ = normalize_payload(
        {"messages": [_raw_message(is_ai_generated=False, is_system=False)]},
        source_file="synthetic.json",
    )
    safe_result = adapt_synthetic_signals(
        records,
        [
            {
                "signal_id": "safe-message",
                "subject_id": "role_a",
                "category": "preference",
                "claim": "明确安全标记的消息可以验证",
                "evidence_ids": [records[0]["message_id"]],
            }
        ],
        sender_role_map={"A": "role_a"},
    )
    assert len(safe_result.candidates) == 1


def test_human_attestation_allows_unknown_flags_without_rewriting_them():
    records, _ = normalize_payload({"messages": [_raw_message()]}, source_file="synthetic.json")
    record = dict(records[0])
    record.update(
        {
            "is_ai_generated": None,
            "is_system": None,
            "security_flag_sources": {
                "is_ai_generated": "unknown:no_reliable_source",
                "is_system": "unknown:no_reliable_source",
            },
            "security_attestation": {
                "human_authored": True,
                "contains_ai_generated": False,
                "contains_system_messages": False,
                "reviewer_id": "synthetic-reviewer",
                "reason": "bounded test sample",
                "attested_at": "2026-10-18T00:00:00Z",
            },
        }
    )
    result = adapt_synthetic_signals(
        [record],
        [
            {
                "signal_id": "attested-unknown",
                "subject_id": "role_a",
                "category": "preference",
                "claim": "经人工声明的未知标记仍保留原始语义",
                "evidence_ids": [record["message_id"]],
            }
        ],
        sender_role_map={"A": "role_a"},
    )
    assert len(result.candidates) == 1
    assert record["is_ai_generated"] is None
    assert record["is_system"] is None

    flagged_records, _ = normalize_payload(
        {
            "messages": [
                _raw_message(local_id=3, server_id=4, is_ai_generated=True, is_system=False),
                _raw_message(local_id=5, server_id=6, type="system", type_code=999),
            ]
        },
        source_file="synthetic.json",
    )
    flagged_signals = [
        {
            "signal_id": "ai-message",
            "subject_id": "role_a",
            "category": "preference",
            "claim": "AI 消息不能作为普通证据",
            "evidence_ids": [flagged_records[0]["message_id"]],
        },
        {
            "signal_id": "system-message",
            "subject_id": "role_a",
            "category": "preference",
            "claim": "系统消息不能作为普通证据",
            "evidence_ids": [flagged_records[1]["message_id"]],
        },
    ]
    flagged_result = adapt_synthetic_signals(
        flagged_records, flagged_signals, sender_role_map={"A": "role_a"}
    )
    assert flagged_result.candidates == ()
    reasons_by_signal = {
        signal_id: {
            item.reason
            for item in flagged_result.unmatched_evidence
            if item.signal_id == signal_id
        }
        for signal_id in ("ai-message", "system-message")
    }
    assert "message_not_eligible" in reasons_by_signal["ai-message"]
    assert reasons_by_signal["system-message"] >= {
        "invalid_security_flag",
        "message_not_eligible",
    }
