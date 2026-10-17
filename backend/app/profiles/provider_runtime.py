"""Resolve persisted provider preferences and explicit environment overrides."""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.provider import ProviderConfiguration
from app.profiles.semantic_analyzer import _HTTP_OPENER, SemanticProviderConfig
from app.providers.secret_store import SecretStoreUnavailable, protect_secret, unprotect_secret

_SETTING_MAP = {
    "semantic_enabled": "semantic_llm_enabled",
    "allow_message_content": "semantic_llm_allow_message_content",
    "endpoint": "semantic_llm_endpoint",
    "model": "semantic_llm_model",
    "timeout_seconds": "semantic_llm_timeout_seconds",
}


@dataclass(frozen=True)
class EffectiveProviderConfig:
    provider_type: str
    endpoint: str | None
    model: str | None
    api_key: str | None
    timeout_seconds: int
    max_input_chars: int
    semantic_enabled: bool
    allow_message_content: bool
    dialogue_enabled: bool
    env_overrides: tuple[str, ...]
    connection_test_status: str
    semantic_test_status: str
    connection_tested_at: datetime | None
    semantic_tested_at: datetime | None
    config_updated_at: datetime | None

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.model and self.api_key)

    def semantic_config(self) -> SemanticProviderConfig:
        return SemanticProviderConfig(
            enabled=self.semantic_enabled,
            allow_message_content=self.allow_message_content,
            endpoint=semantic_endpoint(self.endpoint) if self.endpoint else None,
            model=self.model,
            api_key=self.api_key,
            timeout_seconds=float(self.timeout_seconds),
            max_input_chars=self.max_input_chars,
        )


class ProviderConfigError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def resolve_provider_config(
    db: Session, settings: Settings | None = None
) -> EffectiveProviderConfig:
    current = settings or Settings()
    row = db.get(ProviderConfiguration, "default")
    overrides: list[str] = []

    def effective(field: str, fallback):
        setting_name = _SETTING_MAP.get(field)
        if setting_name and setting_name in current.model_fields_set:
            overrides.append(field)
            return getattr(current, setting_name)
        return getattr(row, field) if row is not None else fallback

    if "semantic_llm_api_key" in current.model_fields_set:
        overrides.append("api_key")
        secret = current.semantic_llm_api_key
        api_key = secret.get_secret_value().strip() if secret else None
        api_key = api_key or None
    else:
        try:
            api_key = (
                unprotect_secret(row.api_key_ciphertext)
                if row and row.api_key_ciphertext
                else None
            )
        except (SecretStoreUnavailable, UnicodeDecodeError):
            api_key = None

    endpoint = effective("endpoint", None)
    model = effective("model", None)
    timeout = effective("timeout_seconds", 60)
    if "semantic_llm_max_input_chars" in current.model_fields_set:
        overrides.append("max_input_chars")
        max_input_chars = current.semantic_llm_max_input_chars
    else:
        max_input_chars = 100_000
    current_digest = _config_digest_values(
        endpoint, model, int(timeout), int(max_input_chars), api_key
    )
    connection_test_is_current = bool(
        row and row.connection_test_config_digest == current_digest
    )
    semantic_test_is_current = bool(row and row.semantic_test_config_digest == current_digest)
    return EffectiveProviderConfig(
        provider_type=(row.provider_type if row is not None else "deepseek"),
        endpoint=endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None,
        model=model.strip() if isinstance(model, str) and model.strip() else None,
        api_key=api_key,
        timeout_seconds=int(timeout),
        max_input_chars=int(max_input_chars),
        semantic_enabled=bool(effective("semantic_enabled", False)),
        allow_message_content=bool(effective("allow_message_content", False)),
        dialogue_enabled=bool(row.dialogue_enabled if row is not None else False),
        env_overrides=tuple(sorted(set(overrides))),
        connection_test_status=(
            row.connection_test_status if connection_test_is_current else "not_tested"
        ),
        semantic_test_status=(
            row.semantic_test_status if semantic_test_is_current else "not_tested"
        ),
        connection_tested_at=(
            row.connection_tested_at if connection_test_is_current else None
        ),
        semantic_tested_at=(
            row.semantic_tested_at if semantic_test_is_current else None
        ),
        config_updated_at=row.config_updated_at if row else None,
    )


def save_provider_config(db: Session, payload) -> EffectiveProviderConfig:
    validate_base_endpoint(payload.endpoint)
    if not payload.model.strip():
        raise ProviderConfigError("invalid_model")
    row = db.get(ProviderConfiguration, "default")
    if row is None:
        row = ProviderConfiguration(
            id="default",
            provider_type=payload.provider_type,
            endpoint=payload.endpoint.rstrip("/"),
            model=payload.model.strip(),
            timeout_seconds=payload.timeout_seconds,
            semantic_enabled=payload.semantic_enabled,
            allow_message_content=payload.allow_message_content,
            dialogue_enabled=payload.dialogue_enabled,
        )
        db.add(row)
    row.provider_type = payload.provider_type
    row.endpoint = payload.endpoint.rstrip("/")
    row.model = payload.model.strip()
    row.timeout_seconds = payload.timeout_seconds
    row.semantic_enabled = payload.semantic_enabled
    row.allow_message_content = payload.allow_message_content
    row.dialogue_enabled = payload.dialogue_enabled
    if payload.clear_api_key:
        row.api_key_ciphertext = None
    elif payload.api_key is not None:
        try:
            row.api_key_ciphertext = protect_secret(payload.api_key)
        except SecretStoreUnavailable as exc:
            raise ProviderConfigError(exc.args[0]) from None
    row.connection_test_status = "not_tested"
    row.connection_test_config_digest = None
    row.semantic_test_status = "not_tested"
    row.semantic_test_config_digest = None
    row.connection_tested_at = None
    row.semantic_tested_at = None
    db.commit()
    return resolve_provider_config(db)


def provider_config_digest(config: EffectiveProviderConfig) -> str:
    return _config_digest_values(
        config.endpoint,
        config.model,
        config.timeout_seconds,
        config.max_input_chars,
        config.api_key,
    )


def _config_digest_values(
    endpoint: str | None,
    model: str | None,
    timeout_seconds: int,
    max_input_chars: int,
    api_key: str | None,
) -> str:
    data = json.dumps(
        [endpoint, model, timeout_seconds, max_input_chars, api_key],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def validate_base_endpoint(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError("invalid_url")
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigError("invalid_url")
        if parsed.path.rstrip("/").endswith("/chat/completions"):
            raise ProviderConfigError("endpoint_must_be_base_url")
        return value.strip().rstrip("/")
    except ValueError:
        raise ProviderConfigError("invalid_url") from None


def api_url(base: str, suffix: str) -> str:
    root = validate_base_endpoint(base)
    parsed = urlsplit(root)
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/{suffix.lstrip('/')}", "", ""))


def semantic_endpoint(base: str) -> str:
    return api_url(base, "chat/completions")


def test_connection(config: EffectiveProviderConfig) -> dict:
    tested_at = datetime.now(UTC)
    if not config.endpoint or not config.model or not config.api_key:
        return _test_result(config, tested_at, "configuration_missing")
    try:
        models_url = api_url(config.endpoint, "models")
    except ProviderConfigError as exc:
        return _test_result(config, tested_at, exc.code)

    request = Request(models_url, headers={"Authorization": f"Bearer {config.api_key}"})
    try:
        with _HTTP_OPENER.open(request, timeout=config.timeout_seconds) as response:
            raw = response.read(1_000_001)
            status = response.status
        if len(raw) > 1_000_000:
            return _test_result(config, tested_at, "response_too_large", status)
        import json

        payload = json.loads(raw.decode("utf-8"))
        models = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return _test_result(config, tested_at, "invalid_response", status)
        model_ids = sorted(
            {
                item.get("id")
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        )
        if config.model not in model_ids:
            return _test_result(config, tested_at, "model_unavailable", status, model_ids)
        return _test_result(config, tested_at, "success", status, model_ids)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        return _test_result(config, tested_at, classify_http_status(status), status)
    except TimeoutError:
        return _test_result(config, tested_at, "timeout")
    except URLError as exc:
        return _test_result(config, tested_at, classify_network_error(exc.reason))
    except ssl.SSLError:
        return _test_result(config, tested_at, "tls_error")
    except (UnicodeDecodeError, ValueError, TypeError, AttributeError):
        return _test_result(config, tested_at, "invalid_response")
    except OSError as exc:
        return _test_result(config, tested_at, classify_network_error(exc))


def classify_http_status(status: int) -> str:
    if status in {401, 403}:
        return "authentication_failed"
    if status == 404:
        return "model_unavailable"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "provider_error"
    return "http_error"


def classify_network_error(error: object) -> str:
    if isinstance(error, ssl.SSLError):
        return "tls_error"
    if isinstance(error, socket.gaierror):
        return "dns_error"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    return "network_error"


def record_test_result(
    db: Session, kind: str, result: dict, config: EffectiveProviderConfig
) -> None:
    row = db.get(ProviderConfiguration, "default")
    if row is None:
        row = ProviderConfiguration(
            id="default",
            provider_type=config.provider_type,
            endpoint=config.endpoint or "",
            model=config.model or "",
            timeout_seconds=config.timeout_seconds,
            semantic_enabled=config.semantic_enabled,
            allow_message_content=config.allow_message_content,
            dialogue_enabled=config.dialogue_enabled,
        )
        db.add(row)
    tested_at = result["tested_at"]
    if kind == "connection":
        row.connection_test_status = result["status"]
        row.connection_test_config_digest = provider_config_digest(config)
        row.connection_tested_at = tested_at
    else:
        row.semantic_test_status = result["status"]
        row.semantic_test_config_digest = provider_config_digest(config)
        row.semantic_tested_at = tested_at
    db.commit()


def _test_result(
    config: EffectiveProviderConfig,
    tested_at: datetime,
    status: str,
    http_status: int | None = None,
    models: list[str] | None = None,
) -> dict:
    return {
        "status": status,
        "provider_type": config.provider_type,
        "model": config.model,
        "http_status": http_status,
        "detail_code": status if status != "success" else None,
        "available_models": models or [],
        "api_key_configured": bool(config.api_key),
        "tested_at": tested_at,
    }
