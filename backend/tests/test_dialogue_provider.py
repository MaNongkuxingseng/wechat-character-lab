import asyncio
import json
import socket
from urllib.error import HTTPError, URLError

import pytest

from app.profiles.provider_runtime import EffectiveProviderConfig
from app.providers.openai_compatible import DialogueProviderError, OpenAICompatibleLLMProvider


def _config(**updates):
    values = {
        "provider_type": "deepseek",
        "endpoint": "https://provider.example",
        "model": "deepseek-test",
        "api_key": "synthetic-secret",
        "timeout_seconds": 30,
        "max_input_chars": 1000,
        "semantic_enabled": True,
        "allow_message_content": False,
        "dialogue_enabled": True,
        "env_overrides": (),
        "connection_test_status": "success",
        "semantic_test_status": "success",
        "connection_tested_at": None,
        "semantic_tested_at": None,
        "config_updated_at": None,
    }
    values.update(updates)
    return EffectiveProviderConfig(**values)


def test_dialogue_provider_parses_text_and_reuses_trace_id(monkeypatch):
    provider = OpenAICompatibleLLMProvider(_config())
    captured = {}

    def request(body, trace_id):
        captured["body"] = json.loads(body)
        captured["trace_id"] = trace_id
        return json.dumps({"choices": [{"message": {"content": " answer "}}]}).encode()

    monkeypatch.setattr(provider, "_request", request)
    result = asyncio.run(provider.generate("system", "user"))
    assert result.text == "answer"
    assert result.trace_id == captured["trace_id"]
    assert captured["body"]["model"] == "deepseek-test"
    assert captured["body"]["messages"][-1]["content"] == "user"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (b"not-json", "invalid_response"),
        (json.dumps({"choices": []}).encode(), "invalid_response"),
        (json.dumps({"choices": [{"message": {"content": ""}}]}).encode(), "invalid_response"),
    ],
)
def test_dialogue_provider_rejects_invalid_responses(monkeypatch, response, code):
    provider = OpenAICompatibleLLMProvider(_config())
    monkeypatch.setattr(provider, "_request", lambda body, trace_id: response)
    with pytest.raises(DialogueProviderError, match=code):
        asyncio.run(provider.generate("system", "user"))


def test_dialogue_provider_classifies_authentication_failure(monkeypatch):
    provider = OpenAICompatibleLLMProvider(_config())

    class FailingOpener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("app.providers.openai_compatible._HTTP_OPENER", FailingOpener())
    with pytest.raises(DialogueProviderError, match="authentication_failed"):
        asyncio.run(provider.generate("system", "user"))


def test_dialogue_provider_requires_explicit_enablement():
    provider = OpenAICompatibleLLMProvider(_config(dialogue_enabled=False))
    with pytest.raises(DialogueProviderError, match="dialogue_disabled"):
        asyncio.run(provider.generate("system", "user"))


def test_dialogue_provider_classifies_dns_failure(monkeypatch):
    provider = OpenAICompatibleLLMProvider(_config())

    def fail(body, trace_id):
        raise URLError(socket.gaierror("synthetic dns failure"))

    monkeypatch.setattr(provider, "_request", fail)
    with pytest.raises(DialogueProviderError, match="dns_error"):
        asyncio.run(provider.generate("system", "user"))
