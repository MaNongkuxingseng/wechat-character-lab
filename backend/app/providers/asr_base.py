from typing import Protocol


class ASRProvider(Protocol):
    """语音识别 Provider 契约；输入音频由上层负责采集和授权。"""

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        """将一段音频转换为文本。"""


class MockASRProvider:
    """不分析音频内容的 ASR 替身（Mock）。"""

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        del audio, content_type
        return "Mock 语音转写结果"
