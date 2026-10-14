import math
import wave
from pathlib import Path

from app.voice.analyzer import MediaAnalyzer


def _write_wav(path: Path) -> None:
    """写入一段 16-bit 单声道正弦波，测试只使用合成数据。"""
    sample_rate = 8000
    samples = bytearray()
    for index in range(sample_rate // 2):
        value = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        samples.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples)


def test_wav_analysis_returns_real_acoustic_summary(tmp_path: Path):
    path = tmp_path / "data" / "sample.wav"
    path.parent.mkdir()
    _write_wav(path)

    result = MediaAnalyzer(path.parent.parent).analyze(path)

    assert result.status == "decoded"
    assert result.media_format == "WAV"
    assert result.duration_ms == 500
    assert result.sample_rate == 8000
    assert result.channels == 1
    assert result.rms_db is not None and result.rms_db < 0
    assert result.silence_ratio is not None and result.silence_ratio < 0.1


def test_silk_analysis_is_explicitly_pending_decode(tmp_path: Path):
    path = tmp_path / "data" / "voice.silk"
    path.parent.mkdir()
    path.write_bytes(b"\x02#!SILK_V3\x00payload")

    result = MediaAnalyzer(path.parent.parent).analyze(path, source_kind="wechat_voice")

    assert result.status == "validated_pending_decode"
    assert result.duration_ms is None
    assert result.metadata["decoder_required"] is True


def test_media_path_outside_data_root_is_rejected(tmp_path: Path):
    inside = tmp_path / "data"
    inside.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"not audio")

    result = MediaAnalyzer(inside).analyze(outside)

    assert result.status == "rejected_outside_data_root"
