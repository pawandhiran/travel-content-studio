"""FFmpeg / ffprobe helpers for video processing."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from core.errors import ExternalServiceError, ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)


def _ms_to_timecode(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS.mmm timecode."""
    total_seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


async def _run_ffmpeg(args: list[str]) -> tuple[str, str]:
    """Run an ffmpeg/ffprobe subprocess and return (stdout, stderr)."""
    executable = args[0]
    if not shutil.which(executable):
        raise ExternalServiceError(f"{executable} not found on PATH")

    log.debug("ffmpeg_exec", cmd=" ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise ProcessingError(
            f"{executable} failed (exit {proc.returncode}): {stderr.decode(errors='replace')[:500]}"
        )
    return stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def get_video_metadata(file_path: str) -> dict:
    """Probe a media file and return normalised metadata."""
    stdout, _ = await _run_ffmpeg(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
    )
    data = json.loads(stdout)
    fmt = data.get("format", {})
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )

    duration_s = float(fmt.get("duration", 0))
    fps_parts = video_stream.get("r_frame_rate", "0/1").split("/")
    fps = round(int(fps_parts[0]) / max(int(fps_parts[1]), 1), 2) if len(fps_parts) == 2 else 0

    return {
        "duration_ms": int(duration_s * 1000),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "codec": video_stream.get("codec_name", ""),
        "format": fmt.get("format_name", ""),
    }


async def generate_proxy(
    input_path: str, output_path: str, width: int = 854
) -> str:
    """Generate a low-res 480p proxy for timeline scrubbing."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", f"scale={width}:-2",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "28",
            output_path,
        ]
    )
    log.info("proxy_generated", input=input_path, output=output_path)
    return output_path


async def extract_thumbnail(
    input_path: str, output_path: str, time_s: float = 1.0
) -> str:
    """Extract a single frame as a thumbnail image."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-ss", str(time_s),
            "-i", input_path,
            "-frames:v", "1",
            output_path,
        ]
    )
    log.info("thumbnail_extracted", input=input_path, output=output_path)
    return output_path


async def extract_audio(input_path: str, output_path: str) -> str:
    """Extract mono 16kHz WAV audio suitable for Whisper."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ]
    )
    log.info("audio_extracted", input=input_path, output=output_path)
    return output_path


async def trim_video(
    input_path: str, output_path: str, start_ms: int, end_ms: int
) -> str:
    """Trim a video between start_ms and end_ms (copy codec for speed)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-ss", _ms_to_timecode(start_ms),
            "-to", _ms_to_timecode(end_ms),
            "-i", input_path,
            "-c", "copy",
            output_path,
        ]
    )
    log.info("video_trimmed", input=input_path, output=output_path, start_ms=start_ms, end_ms=end_ms)
    return output_path
