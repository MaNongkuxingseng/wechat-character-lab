from fastapi import APIRouter

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/capabilities")
def voice_capabilities() -> dict[str, object]:
    """报告当前 Mock 语音能力；此端点不采集或上传音频。"""
    return {
        "asr": {"provider": "mock", "available": True},
        "tts": {"provider": "mock", "available": True},
    }
