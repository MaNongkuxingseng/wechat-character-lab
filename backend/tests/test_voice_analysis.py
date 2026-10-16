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


def test_video_audio_extracts_real_pcm_without_numpy(tmp_path: Path):
    """以合成音频生成 MP4，验证 PyAV float 解码及可追溯派生 WAV。"""
    import subprocess

    import pytest

    from app.voice.analyzer import _ffmpeg_tools

    pytest.importorskip("av")
    _, ffmpeg = _ffmpeg_tools()
    if not ffmpeg:
        pytest.skip("合成 MP4 需要 ffmpeg")
    data = tmp_path / "data"
    data.mkdir()
    wav = data / "tone.wav"
    _write_wav(wav)
    video = data / "sample.mp4"
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", str(video)],
        check=True,
        capture_output=True,
    )
    result = MediaAnalyzer(data).analyze_video_audio(video)
    assert result.status == "decoded", result.error
    assert result.derived_from_video is True
    assert result.source_path == "sample.mp4"
    assert 450 <= result.duration_ms <= 700
    assert result.sample_rate == 16000
    assert -25 < result.rms_db < -8
    assert result.silence_ratio < 0.4
    assert result.metadata["tool_version"]
    extracted = data / result.metadata["decoded_path"]
    assert extracted.is_file()
    assert MediaAnalyzer(data).analyze(extracted).duration_ms == result.duration_ms


def test_compressed_audio_uses_ffmpeg_without_ffprobe(tmp_path: Path, monkeypatch):
    """只有 bundled ffmpeg 时仍可提取，不强依赖 ffprobe/PyAV。"""
    import subprocess
    import sys

    import pytest

    from app.voice import analyzer as module

    _, ffmpeg = module._ffmpeg_tools()
    if not ffmpeg:
        pytest.skip("需要 bundled ffmpeg")
    data = tmp_path / "data"
    data.mkdir()
    wav = data / "tone.wav"
    _write_wav(wav)
    audio = data / "tone.m4a"
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", str(audio)],
        check=True,
        capture_output=True,
    )
    monkeypatch.setitem(sys.modules, "av", None)
    monkeypatch.setattr(module, "_ffmpeg_tools", lambda: (None, ffmpeg))
    result = MediaAnalyzer(data).analyze(audio)
    assert result.status == "decoded", result.error
    assert result.derived_from_video is False
    assert result.metadata["extracted_by"] == "ffmpeg"
    assert -25 < result.rms_db < -8


def test_bad_video_reports_error_without_derived_file(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    video = data / "bad.mp4"
    video.write_bytes(b"invalid media")
    result = MediaAnalyzer(data).analyze_video_audio(video)
    assert result.status in {"video_audio_extract_error", "video_audio_pending_tool"}
    assert result.error
    assert not list(data.rglob("*.wav"))
