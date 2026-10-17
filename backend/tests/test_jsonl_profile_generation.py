"""仅使用人工合成规范化记录验证 JSONL 画像候选闭环。"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from app.ingestion.security_flags import derive_security_flags
from app.profiles.jsonl_analyzer import (
    AnalyzerOutput,
    DisabledLLMSemanticAnalyzer,
    FakeSemanticAnalyzer,
    LLMProviderConfig,
    ObservableAnalyzer,
)
from app.profiles.jsonl_service import (
    analyze_normalized_messages,
    build_role_config_preview,
    parse_normalized_jsonl,
    review_candidate,
)

ROLE_MAP = {"合成发言者甲": "role_a", "合成发言者乙": "role_b"}


def message(
    message_id: str,
    sender: str = "合成发言者甲",
    content: str = "合成文本内容",
    **overrides: Any,
) -> dict[str, Any]:
    flag_inputs = {
        "top_level": {"is_ai_generated": False, "is_system": False},
        "source_metadata": {},
    }
    flags = derive_security_flags(
        {
            **flag_inputs["top_level"],
            "source_metadata": flag_inputs["source_metadata"],
        }
    )
    record = {
        "message_id": message_id,
        "sender": sender,
        "message_type": "text",
        "content": content,
        "content_status": "present",
        "timestamp": "2026-01-01T10:00:00Z",
        "timestamp_status": "parsed_utc",
        "is_ai_generated": False,
        "is_system": False,
        "security_flag_sources": flags.source_map(),
        "security_flag_inputs": flag_inputs,
    }
    record.update(overrides)
    return record


def synthetic_messages() -> list[dict[str, Any]]:
    """构造角色分离、反向偏好和可观察语言行为样本。"""
    return [
        message("syn-a-1", content="我喜欢清淡的合成菜。"),
        message("syn-a-2", content="不太想吃辣的合成菜。"),
        message("syn-a-3", content="哈哈，可以呀？"),
        message("syn-b-1", "合成发言者乙", "我更偏好辣味的合成菜。"),
        message("syn-b-2", "合成发言者乙", "嗯嗯！"),
        message("syn-b-3", "合成发言者乙", "今天先这样。"),
    ]


def test_jsonl_observable_and_fake_semantic_generate_reviewable_candidates(caplog):
    caplog.set_level(logging.INFO)
    rows = synthetic_messages()
    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert result.status == "ready"
    assert result.role_statuses == {"role_a": "ready", "role_b": "ready"}
    assert result.sample_counts == {"role_a": 3, "role_b": 3}
    assert result.candidates
    assert all(item.review_status == "pending" for item in result.candidates)
    for item in result.candidates:
        assert item.candidate.confidence is None
        assert item.analyzer_name == "jsonl_observable"
        refs = (*item.candidate.evidence_refs, *item.candidate.counter_evidence_refs)
        assert refs
        assert len(refs) == len(set(refs))
        assert all(ref in {row["message_id"] for row in rows} for ref in refs)
        assert all(ROLE_MAP[next(row["sender"] for row in rows if row["message_id"] == ref)]
                   == item.candidate.subject_id for ref in refs)
    assert "合成文本内容" not in caplog.text
    assert "syn-a-1" not in caplog.text


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"is_ai_generated": None}, "unsafe_security_flags"),
        ({"is_system": "false"}, "unsafe_security_flags"),
        ({"is_ai_generated": True}, "unsafe_security_flags"),
        ({"security_flag_sources": None}, "security_provenance_missing"),
        ({"security_flag_sources": {"is_ai_generated": "unknown", "is_system": "unknown"}},
         "security_provenance_mismatch"),
        ({"security_flag_inputs": {"top_level": {}, "source_metadata": {}}},
         "security_provenance_not_explicitly_safe"),
        ({"message_type": "image", "content": "[合成图片占位]"}, "non_text_message"),
        ({"content": "", "content_status": "empty"}, "content_not_present"),
        ({"content": None, "content_status": "not_text"}, "content_not_present"),
    ],
)
def test_unsafe_or_non_text_messages_are_excluded(overrides, expected_reason):
    rows = synthetic_messages()
    updated = message("syn-a-1", content="不应进入候选")
    updated.update(overrides)
    rows[0] = updated
    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert any(item.reason == expected_reason and item.evidence_id == "syn-a-1"
               for item in result.unmatched_evidence)
    assert all("syn-a-1" not in item.candidate.evidence_refs
               for item in result.candidates)


def test_duplicate_ids_are_rejected_as_a_group_and_unmapped_sender_is_rejected():
    rows = synthetic_messages()
    rows.extend([message("syn-duplicate"), message("syn-duplicate")])
    rows.append(message("syn-unmapped", "未配置的合成昵称"))

    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert sum(item.reason == "duplicate_message_id" for item in result.unmatched_evidence) == 2
    assert any(item.reason == "unmapped_sender" for item in result.unmatched_evidence)
    assert all("syn-duplicate" not in item.candidate.evidence_refs for item in result.candidates)


def test_candidate_review_and_role_config_preview_are_non_persistent_and_role_scoped():
    result = analyze_normalized_messages(
        synthetic_messages(),
        sender_role_map=ROLE_MAP,
        analyzers=(ObservableAnalyzer(), FakeSemanticAnalyzer()),
    )
    semantic = next(
        item
        for item in result.candidates
        if item.candidate.category.startswith("semantic.")
        and item.candidate.subject_id == "role_a"
    )
    reviewed = review_candidate(
        result,
        semantic.candidate.profile_item_id,
        status="accepted",
        reviewer_note="合成测试人工确认",
    )
    preview = build_role_config_preview(
        reviewed,
        subject_id="role_a",
        previous_config={"profile_traits": []},
    )

    assert preview["publishable"] is False
    assert len(preview["preview"]["profile_traits"]) == 1
    assert preview["preview"]["profile_traits"][0]["evidence_ids"]
    assert result.candidates != reviewed.candidates
    assert all(item.review_status == "pending" for item in result.candidates)
    assert all(item.candidate.subject_id == "role_a"
               for item in reviewed.candidates if item.review_status == "accepted")
    with pytest.raises(ValueError, match="unsupported review status"):
        review_candidate(result, semantic.candidate.profile_item_id, status="published")


class InvalidReferenceAnalyzer:
    """模拟输出不存在 message ID 的 Provider。"""

    name = "invalid_stub"
    version = "test"

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        return AnalyzerOutput(
            self.name,
            self.version,
            "ready",
            len(messages),
            (
                {
                    "subject_id": subject_id,
                    "category": "semantic.invalid",
                    "claim": "合成的无效引用",
                    "evidence_ids": ["model-invented-message-id"],
                    "confidence": 0.99,
                },
            ),
        )


def test_nonexistent_model_evidence_is_rejected():
    result = analyze_normalized_messages(
        synthetic_messages(), sender_role_map=ROLE_MAP, analyzers=(InvalidReferenceAnalyzer(),)
    )

    assert all(item.candidate.category != "semantic.invalid" for item in result.candidates)
    assert any(item.reason == "not_found"
               and item.evidence_id == "model-invented-message-id"
               for item in result.unmatched_evidence)


def test_malformed_model_output_is_rejected():
    class MalformedAnalyzer(InvalidReferenceAnalyzer):
        def analyze(self, subject_id, messages):
            return {"signals": "not-an-analyzer-output"}

    with pytest.raises(TypeError, match="AnalyzerOutput"):
        analyze_normalized_messages(
            synthetic_messages(),
            sender_role_map=ROLE_MAP,
            analyzers=(MalformedAnalyzer(),),
        )


class CrossRoleAnalyzer:
    """故意将 B 的证据写入 A 信号，验证 adapter 角色门禁。"""

    name = "cross_role_stub"
    version = "test"

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        if subject_id != "role_a":
            return AnalyzerOutput(self.name, self.version, "ready", len(messages), ())
        return AnalyzerOutput(
            self.name,
            self.version,
            "ready",
            len(messages),
            ({
                "subject_id": "role_a",
                "category": "semantic.cross_role",
                "claim": "合成的跨角色信号",
                "evidence_ids": ["syn-b-1"],
                "confidence": None,
            },),
        )


def test_cross_role_signal_evidence_is_rejected():
    result = analyze_normalized_messages(
        synthetic_messages(), sender_role_map=ROLE_MAP, analyzers=(CrossRoleAnalyzer(),)
    )

    assert all(item.candidate.category != "semantic.cross_role" for item in result.candidates)
    assert any(item.reason == "role_mismatch" and item.evidence_id == "syn-b-1"
               for item in result.unmatched_evidence)


def test_same_inputs_and_mapping_order_produce_stable_candidates_and_holdout_is_read_only():
    rows = synthetic_messages()
    first = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)
    reversed_map = dict(reversed(list(ROLE_MAP.items())))
    second = analyze_normalized_messages(list(reversed(rows)), sender_role_map=reversed_map)
    holdout = [message("syn-holdout", content="固定留出样本不应反写")]
    third = analyze_normalized_messages([*rows, *holdout], sender_role_map=ROLE_MAP)

    assert first.to_dict() == second.to_dict()
    assert first.snapshot_id != third.snapshot_id
    assert all("syn-holdout" not in item.candidate.evidence_refs for item in first.candidates)
    assert holdout[0]["content"] == "固定留出样本不应反写"


def test_jsonl_parser_accepts_only_object_records_and_reports_line_number():
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in synthetic_messages())
    assert len(parse_normalized_jsonl(payload)) == 6
    with pytest.raises(ValueError, match="line 2"):
        parse_normalized_jsonl('{"ok": true}\nnot-json')


def test_normalized_jsonl_contract_runs_without_changing_message_ids():
    rows = synthetic_messages()
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    parsed = parse_normalized_jsonl(payload)
    result = analyze_normalized_messages(parsed, sender_role_map=ROLE_MAP)

    input_ids = {row["message_id"] for row in rows}
    output_refs = {
        evidence_id
        for item in result.candidates
        for evidence_id in (
            *item.candidate.evidence_refs,
            *item.candidate.counter_evidence_refs,
        )
    }
    assert output_refs <= input_ids
    assert {row["message_id"] for row in parsed} == input_ids


def test_role_map_must_be_explicit_and_reference_only_supported_roles():
    with pytest.raises(ValueError, match="explicit sender labels"):
        analyze_normalized_messages(
            synthetic_messages(), sender_role_map={"甲": "guessed_role"}
        )


def test_temporal_signal_requires_parsed_timezone_timestamp():
    class TemporalAnalyzer:
        name = "temporal_stub"
        version = "test"

        def analyze(self, subject_id, messages):
            return AnalyzerOutput(
                self.name,
                self.version,
                "ready",
                len(messages),
                ({
                    "subject_id": subject_id,
                    "category": "observable.temporal",
                    "claim": "合成时序信号",
                    "evidence_ids": ["syn-a-1"],
                    "requires_temporal": True,
                    "confidence": None,
                },),
            )

    rows = synthetic_messages()
    rows[0]["timestamp_status"] = "invalid"
    result = analyze_normalized_messages(
        rows, sender_role_map=ROLE_MAP, analyzers=(TemporalAnalyzer(),)
    )

    assert all(item.candidate.category != "observable.temporal" for item in result.candidates)
    assert any(item.reason == "invalid_timestamp" for item in result.unmatched_evidence)


def test_semantic_fake_analyzer_preserves_positive_and_counter_evidence():
    rows = synthetic_messages()[:3]
    output = FakeSemanticAnalyzer().analyze("role_a", rows)
    signal = output.signals[0]

    assert signal["evidence_ids"] == ["syn-a-1"]
    assert signal["counter_evidence_ids"] == ["syn-a-2"]
    assert signal["confidence"] is None


def test_observable_analyzer_reports_insufficient_samples_and_llm_is_disabled():
    rows = synthetic_messages()[:2]
    observable = ObservableAnalyzer().analyze("role_a", rows)
    llm = DisabledLLMSemanticAnalyzer().analyze("role_a", rows)

    assert observable.status == "insufficient_samples"
    assert observable.signals == ()
    assert llm.status == "provider_disabled"
    assert llm.signals == ()
    with pytest.raises(ValueError, match="not implemented"):
        DisabledLLMSemanticAnalyzer(LLMProviderConfig(enabled=True))


def test_one_role_ready_marks_overall_partial_when_a_is_ready_and_b_is_insufficient():
    rows = [
        *synthetic_messages()[:3],
        message("syn-b-short-1", "合成发言者乙"),
        message("syn-b-short-2", "合成发言者乙"),
    ]

    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert result.role_statuses == {"role_a": "ready", "role_b": "insufficient_samples"}
    assert result.status == "partial"


def test_one_role_ready_marks_overall_partial_when_b_is_ready_and_a_is_insufficient():
    rows = [
        message("syn-a-short-1"),
        message("syn-a-short-2"),
        *synthetic_messages()[3:],
    ]

    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert result.role_statuses == {"role_a": "insufficient_samples", "role_b": "ready"}
    assert result.status == "partial"


def test_two_roles_below_existing_minimum_are_insufficient():
    rows = [
        message("syn-a-short-1"),
        message("syn-a-short-2"),
        message("syn-b-short-1", "合成发言者乙"),
        message("syn-b-short-2", "合成发言者乙"),
    ]

    result = analyze_normalized_messages(rows, sender_role_map=ROLE_MAP)

    assert result.role_statuses == {
        "role_a": "insufficient_samples",
        "role_b": "insufficient_samples",
    }
    assert result.status == "insufficient_samples"


def test_one_explicit_role_remains_valid_without_an_unmapped_second_role_requirement():
    result = analyze_normalized_messages(
        synthetic_messages()[:3],
        sender_role_map={"合成发言者甲": "role_a"},
    )

    assert result.role_statuses == {"role_a": "ready"}
    assert result.status == "ready"


def test_role_status_is_partial_when_required_analyzers_disagree():
    class FixedStatusAnalyzer:
        def __init__(self, name, status):
            self.name = name
            self.version = "test"
            self.status = status

        def analyze(self, subject_id, messages):
            signals = ()
            if self.status == "ready":
                signals = ({
                    "subject_id": subject_id,
                    "category": f"test.{self.name}",
                    "claim": "合成状态测试",
                    "evidence_ids": [str(messages[0]["message_id"])],
                    "confidence": None,
                },)
            return AnalyzerOutput(
                self.name, self.version, self.status, len(messages), signals
            )

    rows = synthetic_messages()[:3]
    result = analyze_normalized_messages(
        rows,
        sender_role_map={"合成发言者甲": "role_a"},
        analyzers=(
            FixedStatusAnalyzer("ready_analyzer", "ready"),
            FixedStatusAnalyzer("waiting_analyzer", "insufficient_samples"),
        ),
    )

    assert [item["status"] for item in result.analyzer_statuses] == [
        "ready",
        "insufficient_samples",
    ]
    assert result.role_statuses == {"role_a": "partial"}
    assert result.status == "partial"


def test_filtered_invalid_messages_cannot_satisfy_analyzer_sample_threshold():
    rows = [
        message("syn-a-valid"),
        message("syn-a-duplicate"),
        message("syn-a-duplicate"),
        message("syn-a-media", message_type="image"),
        message("syn-a-unsafe", is_ai_generated=None),
    ]
    result = analyze_normalized_messages(
        rows,
        sender_role_map={"合成发言者甲": "role_a"},
    )

    assert result.sample_counts == {"role_a": 1}
    assert result.role_statuses == {"role_a": "insufficient_samples"}
    assert result.status == "insufficient_samples"
