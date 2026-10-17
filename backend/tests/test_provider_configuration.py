from datetime import UTC

from app.api import providers as provider_api
from app.models.provider import ProviderConfiguration
from app.profiles import provider_runtime
from app.profiles.provider_runtime import (
    ProviderConfigError,
    api_url,
    classify_http_status,
    resolve_provider_config,
    save_provider_config,
)
from app.providers.secret_store import SecretStoreUnavailable


class ConfigInput:
    provider_type = "deepseek"
    endpoint = "https://api.deepseek.com"
    model = "deepseek-chat"
    api_key = None
    clear_api_key = False
    timeout_seconds = 60
    semantic_enabled = True
    allow_message_content = False
    dialogue_enabled = True


def test_config_api_never_returns_secret_and_keeps_existing_key(client, monkeypatch):
    from app.db import get_db

    factory = client.app.dependency_overrides[get_db]
    session = next(iter(factory()))
    monkeypatch.setattr(provider_runtime, "protect_secret", lambda value: b"encrypted")
    monkeypatch.setattr(provider_runtime, "unprotect_secret", lambda value: "synthetic-secret")
    try:
        payload = ConfigInput()
        payload.api_key = "first-synthetic-secret"
        saved = save_provider_config(session, payload)
        assert saved.api_key == "synthetic-secret"

        response = client.get("/api/providers/config")
        assert response.status_code == 200
        assert response.json()["api_key_configured"] is True
        assert "api_key" not in response.json()
        assert "first-synthetic-secret" not in response.text

        update = ConfigInput()
        updated = save_provider_config(session, update)
        assert updated.api_key == "synthetic-secret"
        row = session.get(ProviderConfiguration, "default")
        assert row is not None and row.api_key_ciphertext == b"encrypted"
    finally:
        session.close()


def test_config_clear_key_is_explicit_and_clears_test_status(test_session_factory, monkeypatch):
    monkeypatch.setattr(provider_runtime, "protect_secret", lambda value: b"encrypted")
    monkeypatch.setattr(provider_runtime, "unprotect_secret", lambda value: "synthetic-secret")
    with test_session_factory() as db:
        first = ConfigInput()
        first.api_key = "synthetic-secret"
        save_provider_config(db, first)
        row = db.get(ProviderConfiguration, "default")
        assert row is not None
        row.connection_test_status = "success"
        row.semantic_test_status = "success"
        db.commit()

        clear = ConfigInput()
        clear.clear_api_key = True
        result = save_provider_config(db, clear)
        assert result.api_key is None
        assert result.connection_test_status == "not_tested"
        assert result.semantic_test_status == "not_tested"


def test_environment_values_override_ui_values_and_show_fields(test_session_factory, monkeypatch):
    with test_session_factory() as db:
        save_provider_config(db, ConfigInput())
        row = db.get(ProviderConfiguration, "default")
        assert row is not None
        row.connection_test_status = "success"
        row.semantic_test_status = "success"
        db.commit()
        monkeypatch.setenv("SEMANTIC_LLM_ENABLED", "false")
        monkeypatch.setenv("SEMANTIC_LLM_ENDPOINT", "https://override.example/v1")
        config = resolve_provider_config(db)
        assert config.semantic_enabled is False
        assert config.endpoint == "https://override.example/v1"
        assert set(config.env_overrides) == {"endpoint", "semantic_enabled"}
        assert config.connection_test_status == "not_tested"
        assert config.semantic_test_status == "not_tested"
        assert config.connection_tested_at is None


def test_test_status_is_bound_to_effective_config(test_session_factory, monkeypatch):
    from datetime import datetime

    with test_session_factory() as db:
        monkeypatch.setattr(provider_runtime, "protect_secret", lambda value: b"encrypted")
        monkeypatch.setattr(provider_runtime, "unprotect_secret", lambda value: "first-key")
        payload = ConfigInput()
        payload.api_key = "first-key"
        config = save_provider_config(db, payload)
        provider_runtime.record_test_result(
            db,
            "connection",
            {"status": "success", "tested_at": datetime.now(UTC)},
            config,
        )
        assert resolve_provider_config(db).connection_test_status == "success"

        monkeypatch.setattr(provider_runtime, "unprotect_secret", lambda value: "replacement-key")
        assert resolve_provider_config(db).connection_test_status == "not_tested"


def test_endpoint_resolution_and_rejection():
    assert api_url("https://api.deepseek.com", "models") == "https://api.deepseek.com/v1/models"
    assert api_url("https://aihub.example/v1", "chat/completions") == (
        "https://aihub.example/v1/chat/completions"
    )
    for endpoint in (
        "http://provider.example",
        "https://user:pass@provider.example",
        "https://provider.example/?x=1",
    ):
        try:
            provider_runtime.validate_base_endpoint(endpoint)
        except ProviderConfigError as exc:
            assert exc.code == "invalid_url"
        else:
            raise AssertionError("invalid endpoint was accepted")


def test_connection_error_classification():
    assert classify_http_status(401) == "authentication_failed"
    assert classify_http_status(404) == "model_unavailable"
    assert classify_http_status(429) == "rate_limited"
    assert classify_http_status(503) == "provider_error"


def test_semantic_protocol_endpoint_uses_only_synthetic_text(client, monkeypatch):
    from app.profiles.jsonl_analyzer import AnalyzerOutput

    monkeypatch.setattr(provider_runtime, "protect_secret", lambda value: b"ciphertext")
    monkeypatch.setattr(provider_runtime, "unprotect_secret", lambda value: "synthetic-key")
    monkeypatch.setattr(
        provider_api,
        "test_connection",
        lambda config: {
            "status": "success",
            "provider_type": config.provider_type,
            "model": config.model,
            "http_status": 200,
            "available_models": [config.model],
            "api_key_configured": True,
            "tested_at": __import__("datetime").datetime.now(UTC),
        },
    )
    calls = []

    class FakeAnalyzer:
        def __init__(self, config, *, approved_source=False):
            self.config = config
            self.approved_source = approved_source

        def analyze(self, subject_id, messages):
            calls.append((subject_id, tuple(messages)))
            return AnalyzerOutput(
                "llm_semantic_openai_compatible", "profile-semantic-v1", "ready", 2, ()
            )

    monkeypatch.setattr(provider_api, "OpenAICompatibleSemanticAnalyzer", FakeAnalyzer)
    response = client.put(
        "/api/providers/config",
        json={
            "provider_type": "deepseek",
            "endpoint": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key": "synthetic-test-key",
            "timeout_seconds": 60,
            "semantic_enabled": False,
            "allow_message_content": False,
            "dialogue_enabled": True,
        },
    )
    assert response.status_code == 200
    tested = client.post("/api/providers/test-semantic")
    assert tested.status_code == 200
    assert tested.json()["status"] == "success"
    assert tested.json()["signal_count"] == 0
    assert calls[0][0] == "synthetic_role"
    assert all(item["message_id"].startswith("synthetic-provider-test-") for item in calls[0][1])
    assert all(item["content"] != "" for item in calls[0][1])

    status = client.get("/api/providers/status").json()
    assert status["dialogue_agent_implemented"] is False
    assert status["dialogue_available"] is False


def test_dpapi_unavailable_does_not_persist_plaintext_key(test_session_factory, monkeypatch):
    def unavailable(_):
        raise SecretStoreUnavailable("windows_dpapi_unavailable")

    monkeypatch.setattr(provider_runtime, "protect_secret", unavailable)
    with test_session_factory() as db:
        payload = ConfigInput()
        payload.api_key = "synthetic-secret"
        try:
            save_provider_config(db, payload)
        except ProviderConfigError as exc:
            assert exc.code == "windows_dpapi_unavailable"
        else:
            raise AssertionError("secret store failure should reject the save")
        assert db.get(ProviderConfiguration, "default") is None
