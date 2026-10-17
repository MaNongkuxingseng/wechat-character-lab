"""OpenAI-compatible text generation for real conversation agents.

Author: valen MPF
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4

from app.profiles.provider_runtime import (
    EffectiveProviderConfig,
    classify_network_error,
    semantic_endpoint,
)
from app.profiles.semantic_analyzer import _HTTP_OPENER


@dataclass(frozen=True)
class LLMGeneration:
    text: str
    provider: str
    model: str
    latency_ms: int
    trace_id: str


class DialogueProviderError(RuntimeError):
    """A classified failure safe to persist and expose without credentials."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OpenAICompatibleLLMProvider:
    """Generate one bounded dialogue turn using the effective Provider config."""

    def __init__(self, config: EffectiveProviderConfig) -> None:
        self.config = config

    async def generate(self, system_prompt: str, user_prompt: str) -> LLMGeneration:
        if not self.config.configured:
            raise DialogueProviderError("provider_misconfigured")
        if not self.config.dialogue_enabled:
            raise DialogueProviderError("dialogue_disabled")
        if self.config.connection_test_status != "success":
            raise DialogueProviderError("provider_not_verified")
        bounded_prompt = user_prompt[-min(self.config.max_input_chars, 100_000) :]
        body = json.dumps(
            {
                "model": self.config.model,
                "temperature": 0.4,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": bounded_prompt},
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        trace_id = str(uuid4())
        started = time.perf_counter()
        try:
            payload = await asyncio.to_thread(self._request, body, trace_id)
            parsed = json.loads(payload.decode("utf-8"))
            text = parsed["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise DialogueProviderError("invalid_response")
        except DialogueProviderError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise DialogueProviderError("invalid_response") from None
        except TimeoutError:
            raise DialogueProviderError("timeout") from None
        except URLError as exc:
            raise DialogueProviderError(classify_network_error(exc.reason)) from None
        except OSError as exc:
            raise DialogueProviderError(classify_network_error(exc)) from None
        return LLMGeneration(
            text=text.strip(),
            provider=self.config.provider_type,
            model=self.config.model or "",
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            trace_id=trace_id,
        )

    def _request(self, body: bytes, trace_id: str) -> bytes:
        endpoint = semantic_endpoint(self.config.endpoint or "")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "X-Client-Trace-Id": trace_id,
            },
            method="POST",
        )
        try:
            with _HTTP_OPENER.open(request, timeout=self.config.timeout_seconds) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise DialogueProviderError("response_too_large")
            return payload
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status in {401, 403}:
                code = "authentication_failed"
            elif status == 404:
                code = "model_unavailable"
            elif status == 429:
                code = "rate_limited"
            elif status >= 500:
                code = "provider_error"
            else:
                code = "provider_rejected_request"
            raise DialogueProviderError(code) from None
