"""规范化 JSONL 的可替换分析器 / Analyzers for canonical JSONL records.

此模块仅产生结构化信号，不负责读取文件、写入数据库或调用在线模型。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any, Protocol


@dataclass(frozen=True)
class AnalyzerOutput:
    """分析器结果及其样本充分性状态。"""

    analyzer_name: str
    analyzer_version: str
    status: str
    sample_count: int
    signals: tuple[Mapping[str, Any], ...]


class ProfileAnalyzer(Protocol):
    """JSONL 画像分析器契约；输出只能引用输入中已有的 message_id。"""

    name: str
    version: str

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        """对单一显式角色的安全文本样本生成信号。"""


class ObservableAnalyzer:
    """只生成可直接复核的文字统计，不推断人格或声音特征。"""

    name = "jsonl_observable"
    version = "1.0.0"
    minimum_sample_count = 3
    maximum_sample_count = 1000

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        sample = tuple(messages[: self.maximum_sample_count])
        if len(sample) < self.minimum_sample_count:
            return AnalyzerOutput(self.name, self.version, "insufficient_samples", len(sample), ())

        message_ids = tuple(str(message["message_id"]) for message in sample)
        lengths = [len(str(message["content"]).strip()) for message in sample]
        question_ids = tuple(
            str(message["message_id"])
            for message in sample
            if "?" in str(message["content"]) or "？" in str(message["content"])
        )
        non_question_ids = tuple(item for item in message_ids if item not in set(question_ids))
        punctuation_ids = tuple(
            str(message["message_id"])
            for message in sample
            if re.search(r"[，。！？!?；;：:,\.]+", str(message["content"]))
        )
        emoji_ids = tuple(
            str(message["message_id"])
            for message in sample
            if _contains_emoji(str(message["content"]))
        )
        colloquial_counts = Counter(
            phrase
            for message in sample
            for phrase in _COLLOQUIAL_PHRASES
            if phrase in str(message["content"])
        )

        signals: list[Mapping[str, Any]] = [
            _signal(
                subject_id,
                "observable.message_length_median",
                f"消息长度中位数为 {int(median(lengths))} 个字符，样本数 {len(sample)}。",
                message_ids,
            ),
            _signal(
                subject_id,
                "observable.question_ratio",
                f"约 {len(question_ids) / len(sample):.0%} 的消息含问号，样本数 {len(sample)}。",
                question_ids or message_ids,
                tuple(non_question_ids) if question_ids else (),
            ),
            _signal(
                subject_id,
                "observable.punctuation_usage",
                f"{len(punctuation_ids)} / {len(sample)} 条消息包含常见标点。",
                punctuation_ids or message_ids,
                tuple(item for item in message_ids if item not in set(punctuation_ids))
                if punctuation_ids
                else (),
            ),
            _signal(
                subject_id,
                "observable.emoji_usage",
                f"{len(emoji_ids)} / {len(sample)} 条消息包含可识别的 emoji 字符。",
                emoji_ids or message_ids,
                tuple(item for item in message_ids if item not in set(emoji_ids))
                if emoji_ids
                else (),
            ),
        ]
        for phrase, count in sorted(colloquial_counts.items()):
            refs = tuple(
                str(message["message_id"])
                for message in sample
                if phrase in str(message["content"])
            )
            signals.append(
                _signal(
                    subject_id,
                    f"observable.colloquial.{phrase}",
                    f"可识别口语表达“{phrase}”出现 {count} 次。",
                    refs,
                )
            )
        return AnalyzerOutput(self.name, self.version, "ready", len(sample), tuple(signals))


class FakeSemanticAnalyzer:
    """用于离线契约验证的确定性词项规则，不代表语义理解能力。"""

    name = "fake_semantic"
    version = "1.0.0"

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        if len(messages) < 3:
            return AnalyzerOutput(
                self.name, self.version, "insufficient_samples", len(messages), ()
            )
        negative = tuple(
            str(item["message_id"])
            for item in messages
            if any(term in str(item["content"]) for term in ("不喜欢", "不愿意", "不太想"))
        )
        negative_set = set(negative)
        positive = tuple(
            str(item["message_id"])
            for item in messages
            if str(item["message_id"]) not in negative_set
            and any(term in str(item["content"]) for term in ("喜欢", "愿意", "更偏好"))
        )
        signals: tuple[Mapping[str, Any], ...] = ()
        if positive or negative:
            primary_ids = positive or negative
            counter_ids = negative if positive else ()
            signals = (
                _signal(
                    subject_id,
                    "semantic.lexical_preference",
                    "合成词项规则检测到偏好或回避表达，需人工核对上下文。",
                    primary_ids,
                    counter_ids,
                ),
            )
        return AnalyzerOutput(self.name, self.version, "ready", len(messages), signals)


@dataclass(frozen=True)
class LLMProviderConfig:
    """后续模型 Provider 配置；外部调用默认关闭。"""

    enabled: bool = False
    provider_name: str = "disabled"


class DisabledLLMSemanticAnalyzer:
    """不联网的 LLM 边界占位，避免测试或默认服务意外外发数据。"""

    name = "llm_semantic"
    version = "disabled-v1"

    def __init__(self, config: LLMProviderConfig | None = None) -> None:
        self.config = config or LLMProviderConfig()
        if self.config.enabled:
            raise ValueError("real LLM provider is not implemented in P3-A")

    def analyze(
        self, subject_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> AnalyzerOutput:
        return AnalyzerOutput(
            self.name,
            self.version,
            "provider_disabled",
            len(messages),
            (),
        )


_COLLOQUIAL_PHRASES = ("哈哈", "嗯嗯", "好的", "可以呀", "没事")


def _signal(
    subject_id: str,
    category: str,
    claim: str,
    evidence_ids: Sequence[str],
    counter_evidence_ids: Sequence[str] = (),
) -> Mapping[str, Any]:
    """构造 adapter 契约信号；置信度未知，且不携带原文。"""
    return {
        "subject_id": subject_id,
        "category": category,
        "claim": claim,
        "evidence_ids": list(evidence_ids),
        "confidence": None,
        **(
            {"counter_evidence_ids": list(counter_evidence_ids)}
            if counter_evidence_ids
            else {}
        ),
    }


def _contains_emoji(text: str) -> bool:
    """识别常见 emoji Unicode 区段，不引入外部分类依赖。"""
    return any(
        0x1F300 <= ord(char) <= 0x1FAFF
        or 0x2600 <= ord(char) <= 0x27BF
        or ord(char) in {0xFE0F, 0x200D}
        for char in text
    )
