from typing import Protocol


class LLMProvider(Protocol):
    """语言模型 Provider 契约；Provider 不决定发言人或会话状态。"""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """生成文本；真实实现应在此统一处理超时和供应商错误。"""


class MockLLMProvider:
    """无网络依赖的 LLM 替身（Mock）。"""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt
        return f"Mock 生成结果：{user_prompt[:80]}"
