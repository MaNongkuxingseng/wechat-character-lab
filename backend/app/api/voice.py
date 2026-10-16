import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.providers.asr_base import MockASRProvider
from app.providers.tts_base import MockTTSProvider
from app.voice.service import _video_tools_available, analyze_voice_assets, list_voice_analyses

router = APIRouter(prefix="/api/voice", tags=["voice"])
MAX_AUDIO_UPLOAD_BYTES = 15 * 1024 * 1024


class SynthesizeRequest(BaseModel):
    """TTS 请求；voice_id 仅是本地 Provider 的配置标识。"""

    text: str = Field(min_length=1, max_length=4000)
    voice_id: str = Field(default="preset-neutral", min_length=1, max_length=120)


class VoiceAnalysisRequest(BaseModel):
    """触发本地媒体解析；视频补充分析可显式关闭。"""

    include_videos: bool = True
    minimum_samples: int = Field(default=3, ge=1, le=100)


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, object]:
    """调用本地 ASR Provider；当前不保存上传音频，也不上传到网络。"""
    content_type = file.content_type or "application/octet-stream"
    audio = await file.read(MAX_AUDIO_UPLOAD_BYTES + 1)
    if len(audio) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"code": "audio_too_large"})
    if not audio:
        raise HTTPException(status_code=400, detail={"code": "empty_audio"})
    text = await MockASRProvider().transcribe(audio, content_type)
    return {
        "provider": "mock",
        "available": True,
        "filename": file.filename,
        "content_type": content_type,
        "text": text,
        "notice": "这是 Mock 转写结果，未解析真实音频内容。",
    }


@router.post("/synthesize")
async def synthesize_audio(payload: SynthesizeRequest) -> dict[str, object]:
    """调用 TTS Provider；Mock 不产生假音频，故返回不可播放状态。"""
    audio = await MockTTSProvider().synthesize(payload.text, payload.voice_id)
    if not audio:
        return {
            "provider": "mock",
            "available": False,
            "voice_id": payload.voice_id,
            "text": payload.text,
            "audio_url": None,
            "notice": "未配置真实 TTS Provider，Mock 不生成可播放音频。",
        }
    return {
        "provider": "mock",
        "available": True,
        "voice_id": payload.voice_id,
        "text": payload.text,
        "audio_url": None,
    }


@router.get("/capabilities")
def voice_capabilities() -> dict[str, object]:
    """报告当前 Mock 语音能力；此端点不采集或上传音频。"""
    return {
        "asr": {"provider": "mock", "available": True, "streaming": False},
        "tts": {"provider": "mock", "available": False, "streaming": False},
        "media_analysis": {
            "provider": "local",
            "available": True,
            "silk_decoder": False,
            "video_audio": _video_tools_available(),
        },
    }


@router.get("/assets")
def voice_assets() -> dict[str, object]:
    """读取本地语音清单；不返回音频字节，也不触发播放或上传。"""
    root = Path(__file__).resolve().parents[3]
    manifest = root / "data" / "audio" / "pengna_20261014" / "manifest.json"
    if not manifest.is_file():
        return {"available": False, "format": "SILK", "count": 0, "bytes_total": 0, "files": []}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        files = payload.get("files", [])
        if not isinstance(files, list):
            raise ValueError("语音清单 files 不是数组")
        files = [item for item in files if isinstance(item, dict)]
    except (OSError, ValueError, json.JSONDecodeError):
        return {"available": False, "format": "SILK", "count": 0, "bytes_total": 0, "files": []}
    return {
        "available": True,
        "format": str(payload.get("format") or "SILK"),
        "count": len(files),
        "bytes_total": sum(int(item.get("bytes") or 0) for item in files),
        "files": files,
    }


@router.post("/analyze")
def analyze_voice(
    payload: VoiceAnalysisRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """解析现有微信语音，并在样本不足时探测视频音轨。"""
    request = payload or VoiceAnalysisRequest()
    return analyze_voice_assets(
        db,
        include_videos=request.include_videos,
        minimum_samples=request.minimum_samples,
    )


@router.get("/analyses")
def voice_analyses(role_id: str | None = None, db: Session = Depends(get_db)) -> dict[str, object]:
    """读取语音分析摘要，不返回音频字节。"""
    return {"items": list_voice_analyses(db, role_id=role_id)}
