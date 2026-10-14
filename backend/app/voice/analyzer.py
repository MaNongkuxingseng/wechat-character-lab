"""本地媒体识别和轻量声学分析。

该模块不调用网络服务，也不把原始音频写入数据库。只有能真正解码的音频
才会计算时长、RMS 和静音比例；SILK 在缺少 decoder 时只做结构校验。
"""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".3gp"}
SUPPORTED_AUDIO_EXTENSIONS = {".aac", ".amr", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
SILK_HEADER = b"#!SILK_V3"


@dataclass
class MediaAnalysisResult:
    """媒体分析结果；字段与 ``VoiceAnalysis`` ORM 模型一一对应。"""

    source_path: str
    source_kind: str
    media_format: str
    status: str
    sha256: str
    derived_from_video: bool = False
    duration_ms: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    rms_db: float | None = None
    silence_ratio: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class MediaAnalyzer:
    """识别本地素材并在能力可用时计算可解释声学摘要。"""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    def analyze(self, path: Path, *, source_kind: str = "local_media") -> MediaAnalysisResult:
        """分析单个文件，拒绝访问项目 data 目录之外的路径。"""
        resolved = path.resolve()
        if not self._within_data_root(resolved):
            return MediaAnalysisResult(
                source_path=str(path),
                source_kind=source_kind,
                media_format=path.suffix.lower().lstrip(".") or "unknown",
                status="rejected_outside_data_root",
                sha256="",
                error="媒体路径必须位于项目 data 目录内",
            )
        if not resolved.is_file():
            return MediaAnalysisResult(
                source_path=self.relative_path(resolved),
                source_kind=source_kind,
                media_format=resolved.suffix.lower().lstrip(".") or "unknown",
                status="missing",
                sha256="",
                error="媒体文件不存在",
            )

        digest = _sha256(resolved)
        suffix = resolved.suffix.lower()
        relative = self.relative_path(resolved)
        if suffix == ".silk" or _has_silk_header(resolved):
            return self._analyze_silk(relative, source_kind, digest, resolved)
        if suffix == ".wav":
            return self._analyze_wav(relative, source_kind, digest, resolved)
        if suffix in SUPPORTED_VIDEO_EXTENSIONS:
            return self._analyze_video(relative, source_kind, digest, resolved)
        if suffix in SUPPORTED_AUDIO_EXTENSIONS:
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format=suffix.lstrip("."),
                status="unsupported_decoder",
                sha256=digest,
                error="当前环境没有该格式的本地解码器；不会凭文件大小推断语音特征",
            )
        return MediaAnalysisResult(
            source_path=relative,
            source_kind=source_kind,
            media_format=suffix.lstrip(".") or "unknown",
            status="unsupported_format",
            sha256=digest,
            error="不支持的媒体格式",
        )

    def analyze_video_audio(self, path: Path) -> MediaAnalysisResult:
        """只分析视频中的音轨，结果明确标记为视频派生素材。"""
        result = self.analyze(path, source_kind="video_audio")
        result.derived_from_video = True
        return result

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.data_root).as_posix()

    def _analyze_silk(
        self, relative: str, source_kind: str, digest: str, path: Path
    ) -> MediaAnalysisResult:
        raw = path.read_bytes()
        header_offset = raw.find(SILK_HEADER, 0, 4 + len(SILK_HEADER))
        valid_header = header_offset in {0, 1, 2}
        frame_markers = raw.count(SILK_HEADER)
        return MediaAnalysisResult(
            source_path=relative,
            source_kind=source_kind,
            media_format="SILK",
            status="validated_pending_decode" if valid_header else "invalid_silk",
            sha256=digest,
            metadata={
                "header": SILK_HEADER.decode("ascii"),
                "header_offset": header_offset,
                "packet_prefix_hex": raw[:header_offset].hex() if header_offset >= 0 else "",
                "header_count": frame_markers,
                "decoder_required": True,
            },
            error=None if valid_header else "未找到 SILK_V3 文件头",
        )

    def _analyze_wav(
        self, relative: str, source_kind: str, digest: str, path: Path
    ) -> MediaAnalysisResult:
        try:
            with wave.open(str(path), "rb") as stream:
                channels = stream.getnchannels()
                sample_rate = stream.getframerate()
                sample_width = stream.getsampwidth()
                frame_count = stream.getnframes()
                frames = stream.readframes(frame_count)
            rms_db, silence_ratio = _pcm_features(frames, sample_width, channels)
            duration_ms = round(frame_count * 1000 / sample_rate) if sample_rate else None
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format="WAV",
                status="decoded",
                sha256=digest,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                channels=channels,
                rms_db=rms_db,
                silence_ratio=silence_ratio,
                metadata={"sample_width_bytes": sample_width, "frame_count": frame_count},
            )
        except (OSError, EOFError, wave.Error, ValueError) as exc:
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format="WAV",
                status="invalid_audio",
                sha256=digest,
                error=f"WAV 解析失败：{exc}",
            )

    def _analyze_video(
        self, relative: str, source_kind: str, digest: str, path: Path
    ) -> MediaAnalysisResult:
        ffprobe, ffmpeg = _ffmpeg_tools()
        if not ffprobe or not ffmpeg:
            pyav_result = self._analyze_video_with_pyav(relative, source_kind, digest, path)
            if pyav_result is not None:
                return pyav_result
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format=path.suffix.lstrip(".").upper(),
                status="video_audio_pending_tool",
                sha256=digest,
                derived_from_video=True,
                metadata={"ffprobe": bool(ffprobe), "ffmpeg": bool(ffmpeg)},
                error="未找到 ffprobe/ffmpeg，无法安全提取视频音轨",
            )
        with tempfile.TemporaryDirectory(prefix="wechat-character-lab-audio-") as temp_dir:
            extracted = Path(temp_dir) / "audio.wav"
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name,sample_rate,channels,duration",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            no_audio_stream = '"streams": []' in probe.stdout
            if probe.returncode != 0 or '"streams"' not in probe.stdout or no_audio_stream:
                return MediaAnalysisResult(
                    source_path=relative,
                    source_kind=source_kind,
                    media_format=path.suffix.lstrip(".").upper(),
                    status="video_without_audio",
                    sha256=digest,
                    derived_from_video=True,
                    error="视频没有可检测的音轨",
                )
            extract = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(path),
                    "-map",
                    "0:a:0",
                    "-acodec",
                    "pcm_s16le",
                    str(extracted),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if extract.returncode != 0 or not extracted.is_file():
                return MediaAnalysisResult(
                    source_path=relative,
                    source_kind=source_kind,
                    media_format=path.suffix.lstrip(".").upper(),
                    status="video_audio_extract_error",
                    sha256=digest,
                    derived_from_video=True,
                    error="ffmpeg 提取视频音轨失败",
                )
            wav_result = self._analyze_wav(relative, "video_audio", digest, extracted)
            wav_result.derived_from_video = True
            wav_result.metadata["extracted_by"] = "ffmpeg"
            return wav_result

    def _analyze_video_with_pyav(
        self, relative: str, source_kind: str, digest: str, path: Path
    ) -> MediaAnalysisResult | None:
        """无 ffprobe 时用 PyAV 直接读取首个音频流，避免解析命令行文本。"""
        try:
            import av
        except ImportError:
            return None
        try:
            container = av.open(str(path))
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                container.close()
                return MediaAnalysisResult(
                    source_path=relative,
                    source_kind=source_kind,
                    media_format=path.suffix.lstrip(".").upper(),
                    status="video_without_audio",
                    sha256=digest,
                    derived_from_video=True,
                    error="视频没有可检测的音轨",
                )
            sample_rate = int(stream.codec_context.sample_rate or 0) or None
            channels = int(stream.codec_context.channels or 0) or None
            sample_count = 0
            energy_sum = 0.0
            silent_count = 0
            try:
                import numpy as np
            except ImportError:
                np = None
            for frame in container.decode(stream):
                if np is None:
                    break
                values = frame.to_ndarray()
                if values.size == 0:
                    continue
                numeric = values.astype(np.float64) / 32768.0
                if numeric.ndim > 1:
                    numeric = numeric.mean(axis=0)
                sample_count += int(numeric.size)
                energy_sum += float(np.square(numeric).sum())
                silent_count += int(np.count_nonzero(np.abs(numeric) < 0.02))
                if sample_rate is None:
                    sample_rate = int(frame.sample_rate or 0) or None
                if channels is None:
                    channels = int(frame.layout.channels or 0) or None
            duration_ms = None
            if sample_rate and sample_count:
                duration_ms = round(sample_count * 1000 / sample_rate)
            elif stream.duration is not None and stream.time_base is not None:
                duration_ms = round(float(stream.duration * stream.time_base) * 1000)
            rms_db = None
            silence_ratio = None
            if sample_count:
                rms_db = round(20 * math.log10(max(math.sqrt(energy_sum / sample_count), 1e-9)), 2)
                silence_ratio = round(silent_count / sample_count, 4)
            metadata = {
                "extracted_by": "pyav",
                "codec": str(stream.codec_context.name or "unknown"),
            }
            container.close()
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format=path.suffix.lstrip(".").upper(),
                status="decoded" if sample_count else "decoded_metadata",
                sha256=digest,
                derived_from_video=True,
                duration_ms=duration_ms,
                sample_rate=sample_rate,
                channels=channels,
                rms_db=rms_db,
                silence_ratio=silence_ratio,
                metadata=metadata,
            )
        except Exception as exc:  # PyAV exposes codec-specific exceptions by version.
            return MediaAnalysisResult(
                source_path=relative,
                source_kind=source_kind,
                media_format=path.suffix.lstrip(".").upper(),
                status="video_audio_extract_error",
                sha256=digest,
                derived_from_video=True,
                error=f"PyAV 读取视频音轨失败：{exc}",
            )

    def _within_data_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.data_root)
        except ValueError:
            return False
        return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_silk_header(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4 + len(SILK_HEADER)).find(SILK_HEADER) in {0, 1, 2}
    except OSError:
        return False


def _ffmpeg_tools() -> tuple[str | None, str | None]:
    """优先使用系统工具，回退到 imageio-ffmpeg 提供的 bundled ffmpeg。"""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return ffprobe, ffmpeg
    try:
        import imageio_ffmpeg

        bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError):
        return ffprobe, ffmpeg
    # imageio-ffmpeg 通常只携带 ffmpeg；没有同版本 ffprobe 时仍保留待工具状态。
    return ffprobe, bundled_ffmpeg


def _pcm_features(
    raw: bytes, sample_width: int, channels: int
) -> tuple[float | None, float | None]:
    """用标准库计算归一化 RMS dB 与近似静音比例。"""
    if not raw or sample_width not in {1, 2, 3, 4} or channels < 1:
        return None, None
    max_value = float((1 << (sample_width * 8 - 1)) - 1)
    values: list[float] = []
    step = sample_width * channels
    for offset in range(0, len(raw) - step + 1, step):
        channel_values = []
        for channel in range(channels):
            start = offset + channel * sample_width
            chunk = raw[start : start + sample_width]
            if sample_width == 3:
                integer = int.from_bytes(chunk, "little", signed=True)
            else:
                integer = int.from_bytes(chunk, "little", signed=(sample_width != 1))
                if sample_width == 1:
                    integer -= 128
            channel_values.append(integer / max_value)
        values.append(sum(channel_values) / len(channel_values))
    if not values:
        return None, None
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    rms_db = round(20 * math.log10(max(rms, 1e-9)), 2)
    silence_ratio = round(sum(abs(value) < 0.02 for value in values) / len(values), 4)
    return rms_db, silence_ratio
