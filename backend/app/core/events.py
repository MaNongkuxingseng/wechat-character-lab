from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """内部领域事件；序列化为客户端协议由 API 层负责。"""

    type: str
    payload: dict[str, Any]
