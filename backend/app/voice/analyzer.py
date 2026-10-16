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
            return self._decode_audio(relative, source_kind, digest, resolved)
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
        return self._decode_audio(relative, source_kind, digest, path, derived=True)

    def _decode_audio(
        self, relative: str, source_kind: str, digest: str, path: Path, *, derived: bool = False
    ) -> MediaAnalysisResult:
        """统一提取 mono/s16 PCM；派生 WAV 仅保存于 data/derived/audio。"""
        result = MediaAnalysisResult(
            source_path=relative,
            source_kind=source_kind,
            media_format=path.suffix.lstrip(".").upper(),
            status="video_audio_pending_tool" if derived else "unsupported_decoder",
            sha256=digest,
            derived_from_video=derived,
        )
        output = self.data_root / "derived" / "audio" / f"{digest}.wav"
        if not self._within_data_root(output.resolve()):
            result.status = "rejected_outside_data_root"
            result.error = "派生音频目录必须位于 data 内"
            return result
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import av
        except ImportError:
            av = None
        try:
            with tempfile.TemporaryDirectory(prefix="wechat-character-lab-audio-") as temp_dir:
                extracted = Path(temp_dir) / "audio.wav"
                if av is not None:
                    # AudioResampler 正确处理 float/planar/interleaved，不依赖 numpy。
                    with av.open(str(path)) as container:
                        stream = next(iter(container.streams.audio), None)
                        if stream is None:
                            result.status = "video_without_audio" if derived else "invalid_audio"
                            result.error = "媒体没有可解码的音轨"
                            return result
                        codec = stream.codec_context.name
                        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                        with wave.open(str(extracted), "wb") as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(16000)
                            for frame in container.decode(stream):
                                for pcm in resampler.resample(frame):
                                    wav.writeframesraw(bytes(pcm.planes[0])[: pcm.samples * 2])
                            for pcm in resampler.resample(None):
                                wav.writeframesraw(bytes(pcm.planes[0])[: pcm.samples * 2])
                    metadata = {
                        "extracted_by": "pyav",
                        "tool_version": av.__version__,
                        "codec": codec,
                    }
                else:
                    _, ffmpeg = _ffmpeg_tools()
                    if not ffmpeg:
                        result.error = "缺少 PyAV 或 ffmpeg，无法解码音轨"
                        return result
                    command = subprocess.run(
                        [
                            ffmpeg,
                            "-v",
                            "error",
                            "-nostdin",
                            "-y",
                            "-i",
                            str(path),
                            "-map",
                            "0:a:0",
                            "-vn",
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            "-acodec",
                            "pcm_s16le",
                            str(extracted),
                        ],
                        capture_output=True,
                        check=False,
                        timeout=60,
                    )
                    if command.returncode != 0:
                        result.status = "video_audio_extract_error" if derived else "invalid_audio"
                        result.error = "ffmpeg 未能解码音轨，请检查文件及 audio stream"
                        return result
                    version = (
                        subprocess.run(
                            [ffmpeg, "-version"], capture_output=True, check=False, timeout=5
                        )
                        .stdout.decode("utf-8", errors="replace")
                        .splitlines()
                    )
                    metadata = {
                        "extracted_by": "ffmpeg",
                        "tool_version": version[0] if version else "unknown",
                    }
                decoded = self._analyze_wav(relative, source_kind, digest, extracted)
                if decoded.status != "decoded" or not decoded.duration_ms:
                    result.status = "invalid_audio"
                    result.error = "音轨未包含可解码 PCM 样本"
                    return result
                # 只在解码完整成功后落盘，失败不会覆盖上次有效派生文件。
                shutil.copyfile(extracted, output)
                decoded.media_format = result.media_format
                decoded.derived_from_video = derived
                decoded.metadata.update(metadata)
                decoded.metadata["decoded_path"] = self.relative_path(output)
                decoded.metadata["original_source_path"] = relative
                return decoded
        except (OSError, ValueError, EOFError, subprocess.SubprocessError) as exc:
            result.error = f"本地音轨解码失败：{exc}"
        except Exception as exc:
            # PyAV 各版本 codec 异常类型不同，统一转换为明确的分析失败。
            result.error = f"PyAV 音轨解码失败：{exc}"
        result.status = "video_audio_extract_error" if derived else "invalid_audio"
        return result

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
