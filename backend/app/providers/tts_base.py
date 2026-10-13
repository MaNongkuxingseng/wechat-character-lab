from typing import Protocol


class TTSProvider(Protocol):
    """语音合成 Provider 契约；不负责选择说话角色或调度轮次。"""

    async def synthesize(self, text: str, voice_id: str) -> bytes:
        """将文本和音色 ID 转换为音频字节。"""


class MockTTSProvider:
    """不产生真实音频的 TTS 替身（Mock）。"""

    async def synthesize(self, text: str, voice_id: str) -> bytes:
        del text, voice_id
        return b""
