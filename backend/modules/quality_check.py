"""Automated video quality control checks before publishing.

Validates resolution, codec, bitrate, loudness, black frames, silence, fps,
and checks compliance against platform-specific specs.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class QualityIssue:
    severity: Severity
    category: str
    message: str
    fix_suggestion: Optional[str] = None


@dataclass
class PlatformCompliance:
    platform: str
    compliant: bool
    issues: list[QualityIssue] = field(default_factory=list)


@dataclass
class QualityReport:
    passed: bool
    score: float
    issues: list[QualityIssue] = field(default_factory=list)
    platform_compliance: Optional[PlatformCompliance] = None

    def to_dict(self) -> dict:
        issues = [
            {
                "severity": i.severity.value,
                "category": i.category,
                "message": i.message,
                "fix_suggestion": i.fix_suggestion,
            }
            for i in self.issues
        ]
        result: dict = {
            "passed": self.passed,
            "score": round(self.score, 2),
            "issues": issues,
        }
        if self.platform_compliance is not None:
            pc = self.platform_compliance
            result["platform_compliance"] = {
                "platform": pc.platform,
                "compliant": pc.compliant,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "category": i.category,
                        "message": i.message,
                        "fix_suggestion": i.fix_suggestion,
                    }
                    for i in pc.issues
                ],
            }
        return result


# ---------------------------------------------------------------------------
# Platform specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PlatformSpec:
    name: str
    min_width: int
    min_height: int
    max_width: int
    max_height: int
    aspect_ratios: tuple[float, ...]
    min_duration: float
    max_duration: float
    max_file_size_mb: float
    min_audio_bitrate: int
    required_audio: bool
    max_fps: int
    recommended_loudness: float


PLATFORM_SPECS: dict[str, _PlatformSpec] = {
    "youtube_shorts": _PlatformSpec(
        name="YouTube Shorts",
        min_width=720, min_height=1280,
        max_width=1080, max_height=1920,
        aspect_ratios=(9 / 16,),
        min_duration=1, max_duration=60,
        max_file_size_mb=500,
        min_audio_bitrate=128,
        required_audio=True,
        max_fps=60,
        recommended_loudness=-14.0,
    ),
    "youtube_long": _PlatformSpec(
        name="YouTube Long-form",
        min_width=1280, min_height=720,
        max_width=3840, max_height=2160,
        aspect_ratios=(16 / 9,),
        min_duration=1, max_duration=43200,
        max_file_size_mb=256_000,
        min_audio_bitrate=128,
        required_audio=True,
        max_fps=60,
        recommended_loudness=-14.0,
    ),
    "instagram_reels": _PlatformSpec(
        name="Instagram Reels",
        min_width=500, min_height=888,
        max_width=1080, max_height=1920,
        aspect_ratios=(9 / 16, 4 / 5),
        min_duration=3, max_duration=90,
        max_file_size_mb=650,
        min_audio_bitrate=128,
        required_audio=True,
        max_fps=30,
        recommended_loudness=-14.0,
    ),
    "instagram_stories": _PlatformSpec(
        name="Instagram Stories",
        min_width=500, min_height=888,
        max_width=1080, max_height=1920,
        aspect_ratios=(9 / 16,),
        min_duration=1, max_duration=60,
        max_file_size_mb=250,
        min_audio_bitrate=128,
        required_audio=False,
        max_fps=30,
        recommended_loudness=-14.0,
    ),
    "tiktok": _PlatformSpec(
        name="TikTok",
        min_width=720, min_height=1280,
        max_width=1080, max_height=1920,
        aspect_ratios=(9 / 16,),
        min_duration=1, max_duration=180,
        max_file_size_mb=287,
        min_audio_bitrate=128,
        required_audio=True,
        max_fps=60,
        recommended_loudness=-14.0,
    ),
}


# ---------------------------------------------------------------------------
# FFmpeg / ffprobe helpers (async)
# ---------------------------------------------------------------------------


async def _run(args: list[str]) -> tuple[str, str]:
    """Run a subprocess and return (stdout, stderr)."""
    exe = args[0]
    if not shutil.which(exe):
        raise ProcessingError(f"{exe} not found on PATH")

    log.debug("qc_exec", cmd=" ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _probe(video_path: Path) -> dict:
    """Return comprehensive video metadata via ffprobe."""
    stdout, _ = await _run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ])

    data = json.loads(stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
        None,
    )

    fmt = data.get("format", {})
    info: dict = {
        "file_size_mb": video_path.stat().st_size / (1024 * 1024),
        "duration": float(fmt.get("duration", 0)),
        "bitrate": int(fmt.get("bit_rate", 0)) / 1000,
        "format": fmt.get("format_name", "unknown"),
        "has_video": video_stream is not None,
        "has_audio": audio_stream is not None,
    }

    if video_stream:
        fps_parts = video_stream.get("r_frame_rate", "30/1").split("/")
        fps = round(int(fps_parts[0]) / max(int(fps_parts[1]), 1), 2) if len(fps_parts) == 2 else 30.0
        info.update({
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "fps": fps,
            "video_codec": video_stream.get("codec_name"),
            "video_bitrate": (
                int(video_stream["bit_rate"]) / 1000
                if video_stream.get("bit_rate") else None
            ),
            "pix_fmt": video_stream.get("pix_fmt"),
            "aspect_ratio": int(video_stream["width"]) / int(video_stream["height"]),
        })

    if audio_stream:
        info.update({
            "audio_codec": audio_stream.get("codec_name"),
            "audio_bitrate": (
                int(audio_stream["bit_rate"]) / 1000
                if audio_stream.get("bit_rate") else None
            ),
            "sample_rate": int(audio_stream.get("sample_rate", 0)),
            "channels": int(audio_stream.get("channels", 0)),
        })

    return info


# ---------------------------------------------------------------------------
# Individual check routines
# ---------------------------------------------------------------------------


async def _check_loudness(video_path: Path) -> dict:
    """Analyze audio loudness via ffmpeg loudnorm filter."""
    _, stderr = await _run([
        "ffmpeg", "-i", str(video_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ])
    try:
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start != -1:
            return json.loads(stderr[json_start:json_end])
    except Exception:
        pass
    return {}


async def _check_black_frames(video_path: Path) -> dict:
    """Detect black frames at video start."""
    _, stderr = await _run([
        "ffmpeg", "-i", str(video_path),
        "-t", "3",
        "-vf", "blackdetect=d=0.1:pix_th=0.1",
        "-an", "-f", "null", "-",
    ])

    result = {"start_black": False, "end_black": False}
    for line in stderr.split("\n"):
        if "black_start" in line:
            try:
                start = float(line.split("black_start:")[1].split()[0])
                if start < 0.5:
                    result["start_black"] = True
            except Exception:
                pass
    return result


async def _check_silence(video_path: Path) -> list[dict]:
    """Detect silent segments via ffmpeg silencedetect."""
    _, stderr = await _run([
        "ffmpeg", "-i", str(video_path),
        "-af", "silencedetect=n=-40dB:d=2",
        "-f", "null", "-",
    ])

    segments: list[dict] = []
    for line in stderr.split("\n"):
        if "silence_start" in line:
            try:
                start = float(line.split("silence_start:")[1].strip().split()[0])
                segments.append({"start": start})
            except Exception:
                pass
        elif "silence_end" in line and segments:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                segments[-1]["end"] = end
            except Exception:
                pass
    return segments


def _video_quality_issues(info: dict) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    width = info.get("width", 0)
    height = info.get("height", 0)

    if width < 720 or height < 720:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="resolution",
            message=f"Low resolution: {width}x{height}",
            fix_suggestion="Minimum recommended: 720p for most platforms",
        ))

    aspect = info.get("aspect_ratio", 0)
    standard_aspects = [16 / 9, 9 / 16, 1.0, 4 / 5, 4 / 3]
    if not any(abs(aspect - std) < 0.05 for std in standard_aspects):
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="aspect_ratio",
            message=f"Non-standard aspect ratio: {aspect:.2f}",
            fix_suggestion="May cause letterboxing/pillarboxing on platforms",
        ))

    codec = info.get("video_codec", "")
    if codec not in ("h264", "hevc", "h265", "vp9"):
        issues.append(QualityIssue(
            severity=Severity.INFO,
            category="codec",
            message=f"Non-optimal codec: {codec}",
            fix_suggestion="H.264 recommended for maximum compatibility",
        ))

    video_bitrate = info.get("video_bitrate")
    if video_bitrate:
        pixels = width * height
        if pixels >= 2_073_600:
            min_br = 5000
        elif pixels >= 921_600:
            min_br = 2500
        else:
            min_br = 1000
        if video_bitrate < min_br:
            issues.append(QualityIssue(
                severity=Severity.WARNING,
                category="bitrate",
                message=f"Low video bitrate: {video_bitrate:.0f} kbps",
                fix_suggestion=f"Recommended: at least {min_br} kbps for {width}x{height}",
            ))

    fps = info.get("fps", 30)
    if fps < 24:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="fps",
            message=f"Low frame rate: {fps:.1f} fps",
            fix_suggestion="Minimum recommended: 24 fps",
        ))
    elif fps > 60:
        issues.append(QualityIssue(
            severity=Severity.INFO,
            category="fps",
            message=f"High frame rate: {fps:.1f} fps",
            fix_suggestion="Most platforms cap at 60 fps",
        ))

    return issues


def _audio_issues(info: dict, loudness: dict) -> list[QualityIssue]:
    issues: list[QualityIssue] = []

    if not info.get("has_audio"):
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="audio",
            message="No audio track found",
            fix_suggestion="Most platforms recommend audio for engagement",
        ))
        return issues

    sample_rate = info.get("sample_rate", 0)
    if sample_rate and sample_rate < 44100:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="audio",
            message=f"Low sample rate: {sample_rate} Hz",
            fix_suggestion="Recommended: 44100 Hz or higher",
        ))

    channels = info.get("channels", 0)
    if channels == 1:
        issues.append(QualityIssue(
            severity=Severity.INFO,
            category="audio",
            message="Mono audio detected",
            fix_suggestion="Consider stereo for better listening experience",
        ))

    if loudness:
        integrated = float(loudness.get("input_i", -24))
        true_peak = float(loudness.get("input_tp", 0))

        if integrated < -20:
            issues.append(QualityIssue(
                severity=Severity.WARNING,
                category="loudness",
                message=f"Audio too quiet: {integrated:.1f} LUFS",
                fix_suggestion="Recommended: -14 LUFS for social media",
            ))
        elif integrated > -10:
            issues.append(QualityIssue(
                severity=Severity.WARNING,
                category="loudness",
                message=f"Audio may be too loud: {integrated:.1f} LUFS",
                fix_suggestion="Recommended: -14 LUFS to avoid platform limiting",
            ))

        if true_peak > -1:
            issues.append(QualityIssue(
                severity=Severity.WARNING,
                category="loudness",
                message=f"True peak too high: {true_peak:.1f} dB",
                fix_suggestion="Should be below -1.0 dB to prevent clipping",
            ))

    return issues


def _content_issues(info: dict, black_frames: dict, silence_segments: list[dict]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    duration = info.get("duration", 0)

    if duration < 3:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="duration",
            message="Video is very short (under 3 seconds)",
            fix_suggestion="May not engage viewers effectively",
        ))
    elif 600 < duration < 900:
        issues.append(QualityIssue(
            severity=Severity.INFO,
            category="duration",
            message="Video length is in 10-15 minute range",
            fix_suggestion="Consider shortening to under 10 min or extending past 15 min for better retention",
        ))

    if black_frames.get("start_black"):
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="black_frames",
            message="Black frames detected at video start",
            fix_suggestion="Trim black frames or add an attention-grabbing hook",
        ))

    long_silence = [s for s in silence_segments if s.get("end", s["start"]) - s["start"] > 5]
    if long_silence:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="silence",
            message=f"{len(long_silence)} silent segment(s) longer than 5 seconds detected",
            fix_suggestion="Consider adding background music or trimming dead air",
        ))

    return issues


def _platform_compliance_issues(info: dict, platform: str) -> PlatformCompliance:
    spec = PLATFORM_SPECS[platform]
    issues: list[QualityIssue] = []

    duration = info.get("duration", 0)
    if duration < spec.min_duration:
        issues.append(QualityIssue(
            severity=Severity.ERROR,
            category="duration",
            message=f"Video too short: {duration:.1f}s (min: {spec.min_duration}s)",
            fix_suggestion=f"{spec.name} requires minimum {spec.min_duration} seconds",
        ))
    elif duration > spec.max_duration:
        issues.append(QualityIssue(
            severity=Severity.ERROR,
            category="duration",
            message=f"Video too long: {duration:.1f}s (max: {spec.max_duration}s)",
            fix_suggestion=f"Trim to {spec.max_duration} seconds or shorter",
        ))

    file_size = info.get("file_size_mb", 0)
    if file_size > spec.max_file_size_mb:
        issues.append(QualityIssue(
            severity=Severity.ERROR,
            category="file_size",
            message=f"File too large: {file_size:.1f} MB (max: {spec.max_file_size_mb} MB)",
            fix_suggestion="Reduce bitrate or duration",
        ))

    width = info.get("width", 0)
    height = info.get("height", 0)
    if width < spec.min_width or height < spec.min_height:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="resolution",
            message=f"Resolution below recommended: {width}x{height}",
            fix_suggestion=f"Recommended minimum: {spec.min_width}x{spec.min_height}",
        ))

    aspect = width / height if height > 0 else 0
    if not any(abs(aspect - ar) < 0.05 for ar in spec.aspect_ratios):
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="aspect_ratio",
            message=f"Aspect ratio {aspect:.2f} not optimal for {spec.name}",
            fix_suggestion="Use auto-reframe to match platform requirements",
        ))

    if spec.required_audio and not info.get("has_audio"):
        issues.append(QualityIssue(
            severity=Severity.ERROR,
            category="audio",
            message=f"{spec.name} requires audio",
            fix_suggestion="Add audio track or background music",
        ))

    fps = info.get("fps", 30)
    if fps > spec.max_fps:
        issues.append(QualityIssue(
            severity=Severity.WARNING,
            category="fps",
            message=f"Frame rate {fps:.0f} fps exceeds {spec.name} limit of {spec.max_fps}",
            fix_suggestion="Video will be re-encoded on upload; consider converting beforehand",
        ))

    compliant = not any(i.severity == Severity.ERROR for i in issues)
    return PlatformCompliance(platform=platform, compliant=compliant, issues=issues)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_quality_check(
    video_path: Path,
    platform: str | None = None,
    strict: bool = False,
) -> QualityReport:
    """Run comprehensive quality checks on a video file.

    Args:
        video_path: Path to the video file.
        platform: Optional target platform key (e.g. ``youtube_shorts``).
        strict: When ``True``, treat warnings as errors for pass/fail.

    Returns:
        A :class:`QualityReport` with all findings.
    """
    video_path = Path(video_path)
    log.info("quality_check_start", video=str(video_path), platform=platform)

    if not video_path.exists():
        return QualityReport(
            passed=False,
            score=0.0,
            issues=[QualityIssue(Severity.ERROR, "file", "File not found")],
        )

    try:
        info = await _probe(video_path)
    except Exception as exc:
        raise ProcessingError(f"Cannot read video metadata: {exc}") from exc

    # Run analysis in parallel where possible
    loudness_task = asyncio.ensure_future(_check_loudness(video_path))
    black_task = asyncio.ensure_future(_check_black_frames(video_path))
    silence_task = asyncio.ensure_future(_check_silence(video_path))

    loudness, black_frames, silence_segments = await asyncio.gather(
        loudness_task, black_task, silence_task,
    )

    all_issues: list[QualityIssue] = []
    all_issues.extend(_video_quality_issues(info))
    all_issues.extend(_audio_issues(info, loudness))
    all_issues.extend(_content_issues(info, black_frames, silence_segments))

    compliance: PlatformCompliance | None = None
    if platform and platform in PLATFORM_SPECS:
        compliance = _platform_compliance_issues(info, platform)
        all_issues.extend(compliance.issues)

    errors = [i for i in all_issues if i.severity == Severity.ERROR]
    warnings = [i for i in all_issues if i.severity == Severity.WARNING]

    if strict:
        passed = len(errors) == 0 and len(warnings) == 0
    else:
        passed = len(errors) == 0

    max_possible = 10
    deductions = len(errors) * 3 + len(warnings) * 1
    score = max(0.0, min(10.0, max_possible - deductions))

    report = QualityReport(
        passed=passed,
        score=score,
        issues=all_issues,
        platform_compliance=compliance,
    )

    log.info(
        "quality_check_done",
        video=str(video_path),
        passed=passed,
        score=score,
        errors=len(errors),
        warnings=len(warnings),
    )
    return report
