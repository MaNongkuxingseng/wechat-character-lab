from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from app.models import ImportedMessage


@dataclass(frozen=True)
class TraitDraft:
    """分析器产生的单项画像草稿及其可追溯消息依据。"""

    category: str
    key: str
    description: str
    confidence: float
    message_ids: tuple[str, ...]
    rationale: str


class ObservableTextAnalyzer:
    """只计算可直接观察的文本统计，不推断人格或声音特征。"""

    name = "local_observable_v1"
    minimum_sample_count = 3
    maximum_sample_count = 1000

    def analyze(self, messages: Sequence[ImportedMessage]) -> list[TraitDraft]:
        """根据有限样本生成可解释的语言行为观察。"""
        sample = list(messages[: self.maximum_sample_count])
        if len(sample) < self.minimum_sample_count:
            raise ValueError(f"至少需要 {self.minimum_sample_count} 条已审核且已映射的消息")

        sample_ids = tuple(message.id for message in sample)
        adequacy = min(0.95, round(len(sample) / 20, 2))
        lengths = [len(message.text.strip()) for message in sample]
        question_messages = [
            message for message in sample if "?" in message.text or "？" in message.text
        ]
        question_ratio = len(question_messages) / len(sample)
        question_ids = tuple(message.id for message in question_messages) or sample_ids
        question_rationale = (
            "证据消息包含问号。" if question_messages else "样本消息均未发现问号，比例为零。"
        )

        return [
            TraitDraft(
                category="language_style",
                key="message_length_median",
                description=(
                    f"这批文字消息的单条长度中位数为 "
                    f"{int(median(lengths))} 字，样本数 {len(sample)}。"
                ),
                confidence=adequacy,
                message_ids=sample_ids,
                rationale="该统计基于此版本全部分析样本，描述文字长度，不代表性格判断。",
            ),
            TraitDraft(
                category="language_style",
                key="question_ratio",
                description=(
                    f"这批文字消息中约 {question_ratio:.0%} 含有问号，样本数 {len(sample)}。"
                ),
                confidence=adequacy,
                message_ids=question_ids,
                rationale=(f"{question_rationale}该比例只描述标点行为，不代表好奇心或人格特质。"),
            ),
        ]
