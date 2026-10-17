from dataclasses import replace
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.profiles.provider_runtime import (
    ProviderConfigError,
    record_test_result,
    resolve_provider_config,
    save_provider_config,
    test_connection,
)
from app.profiles.semantic_analyzer import OpenAICompatibleSemanticAnalyzer
from app.schemas.providers import (
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderStatusRead,
    ProviderTestResult,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/config", response_model=ProviderConfigRead)
def get_provider_config(db: Session = Depends(get_db)):
    return _config_read(resolve_provider_config(db))


@router.put("/config", response_model=ProviderConfigRead)
def put_provider_config(payload: ProviderConfigUpdate, db: Session = Depends(get_db)):
    try:
        effective = save_provider_config(db, payload)
    except ProviderConfigError as exc:
        status = 503 if exc.code.startswith("windows_dpapi") else 422
        raise HTTPException(status_code=status, detail={"code": exc.code}) from None
    return _config_read(effective)


@router.post("/test-connection", response_model=ProviderTestResult)
def post_test_connection(db: Session = Depends(get_db)):
    effective = resolve_provider_config(db)
    result = test_connection(effective)
    record_test_result(db, "connection", result, effective)
    return result


@router.post("/test-semantic", response_model=ProviderTestResult)
def post_test_semantic(db: Session = Depends(get_db)):
    effective = resolve_provider_config(db)
    tested_at = datetime.now(UTC)
    if not effective.configured:
        result = _semantic_result(effective, tested_at, "configuration_missing")
    else:
        analyzer = OpenAICompatibleSemanticAnalyzer(
            replace(effective.semantic_config(), enabled=True, allow_message_content=True),
            approved_source=True,
        )
        output = analyzer.analyze(
            "synthetic_role",
            (
                {
                    "message_id": "synthetic-provider-test-001",
                    "content": "I prefer making plans before taking action.",
                },
                {
                    "message_id": "synthetic-provider-test-002",
                    "content": "When details are unclear, I ask a short follow-up question.",
                },
            ),
        )
        result = _semantic_result(
            effective,
            tested_at,
            "success" if output.status == "ready" else output.status,
            signal_count=len(output.signals),
        )
    record_test_result(db, "semantic", result, effective)
    return result


@router.get("/status", response_model=ProviderStatusRead)
def get_provider_status(db: Session = Depends(get_db)):
    effective = resolve_provider_config(db)
    read = _config_read(effective)
    semantic_available = (
        effective.configured
        and effective.semantic_enabled
        and effective.allow_message_content
        and effective.connection_test_status == "success"
        and effective.semantic_test_status == "success"
    )
    return {
        "configured": effective.configured,
        "connection_test_status": effective.connection_test_status,
        "semantic_test_status": effective.semantic_test_status,
        "semantic_available": semantic_available,
        "message_content_transfer_ready": semantic_available,
        "dialogue_agent_implemented": True,
        "dialogue_available": (
            effective.configured
            and effective.dialogue_enabled
            and effective.connection_test_status == "success"
        ),
        "effective_config": read,
    }


def _config_read(config) -> dict:
    return {
        "configured": config.configured,
        "provider_type": config.provider_type,
        "endpoint": config.endpoint,
        "model": config.model,
        "api_key_configured": bool(config.api_key),
        "timeout_seconds": config.timeout_seconds,
        "semantic_enabled": config.semantic_enabled,
        "allow_message_content": config.allow_message_content,
        "dialogue_enabled": config.dialogue_enabled,
        "env_overrides": list(config.env_overrides),
        "connection_test_status": config.connection_test_status,
        "semantic_test_status": config.semantic_test_status,
        "connection_tested_at": config.connection_tested_at,
        "semantic_tested_at": config.semantic_tested_at,
        "config_updated_at": config.config_updated_at,
    }


def _semantic_result(config, tested_at, status: str, signal_count: int | None = None) -> dict:
    return {
        "status": status,
        "provider_type": config.provider_type,
        "model": config.model,
        "http_status": None,
        "detail_code": status if status != "success" else None,
        "available_models": [],
        "protocol_version": "profile-semantic-v1",
        "signal_count": signal_count,
        "api_key_configured": bool(config.api_key),
        "tested_at": tested_at,
    }
