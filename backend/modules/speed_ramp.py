"""Speed Ramp — constant speed, slow motion, timelapse, and fit-to-duration effects."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)


async def _run_cmd(args: list[str], timeout: float = 600) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise ProcessingError(f"Command failed: {stderr.decode()[:500]}")
    proc._stdout_data = stdout  # type: ignore[attr-defined]
    return proc


async def _get_video_info(video_path: Path) -> dict:
    proc = await _run_cmd([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ])
    data = json.loads(proc._stdout_data.decode())  # type: ignore[attr-defined]
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = (int(x) for x in fps_str.split("/"))
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(data["format"]["duration"]),
        "fps": num / den if den else 30.0,
    }


def _build_atempo_chain(speed: float) -> str:
    """Build chained atempo filters for speeds outside 0.5-2.0 range."""
    if speed > 2.0:
        parts: list[str] = []
        remaining = speed
        while remaining > 2.0:
            parts.append("atempo=2.0")
            remaining /= 2.0
        parts.append(f"atempo={remaining:.4f}")
        return ",".join(parts)
    elif speed < 0.5:
        parts = []
        remaining = speed
        while remaining < 0.5:
            parts.append("atempo=0.5")
            remaining /= 0.5
        parts.append(f"atempo={remaining:.4f}")
        return ",".join(parts)
    return f"atempo={speed:.4f}"


async def _extract_segment(
    input_path: Path,
    output_path: Path,
    start: float,
    end: float,
    speed: float,
) -> None:
    """Extract a segment and apply speed adjustment."""
    duration = end - start
    pts_mult = 1.0 / speed
    audio_filter = _build_atempo_chain(speed)

    await _run_cmd([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-filter_complex", f"[0:v]setpts={pts_mult}*PTS[v];[0:a]{audio_filter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac",
        str(output_path),
    ], timeout=120)


async def _concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate video segments via concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for seg in segment_paths:
            f.write(f"file '{seg}'\n")
        concat_file = Path(f.name)

    try:
        await _run_cmd([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac",
            str(output_path),
        ], timeout=300)
    finally:
        concat_file.unlink(missing_ok=True)


async def apply_speed_change(
    video_path: Path,
    output_path: Path,
    speed: float = 1.0,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Apply a constant speed multiplier to an entire video."""
    log.info("speed_change_start", video=str(video_path), speed=speed)

    if speed <= 0:
        raise ProcessingError("Speed must be positive")

    if progress_callback:
        await progress_callback({"step": "processing", "progress": 0.20})

    info = await _get_video_info(video_path)
    pts_mult = 1.0 / speed
    audio_filter = _build_atempo_chain(speed)

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex", f"[0:v]setpts={pts_mult}*PTS[v];[0:a]{audio_filter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ])

    new_duration = info["duration"] / speed

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("speed_change_complete", original=info["duration"], new=new_duration)
    return {
        "output_path": str(output_path),
        "speed": speed,
        "original_duration": round(info["duration"], 2),
        "new_duration": round(new_duration, 2),
    }


async def create_slow_motion(
    video_path: Path,
    output_path: Path,
    start_s: float,
    end_s: float,
    factor: float = 0.25,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Create smooth slow motion for a specific time range."""
    log.info("slow_motion_start", start=start_s, end=end_s, factor=factor)

    if factor <= 0 or factor >= 1.0:
        raise ProcessingError("Slow motion factor must be between 0 (exclusive) and 1.0 (exclusive)")

    info = await _get_video_info(video_path)

    if progress_callback:
        await progress_callback({"step": "extracting_segments", "progress": 0.15})

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        segments: list[Path] = []

        if start_s > 0:
            before = tmp / "before.mp4"
            await _extract_segment(video_path, before, 0, start_s, 1.0)
            segments.append(before)

        if progress_callback:
            await progress_callback({"step": "creating_slowmo", "progress": 0.40})

        slomo = tmp / "slomo.mp4"
        duration = end_s - start_s
        pts_mult = 1.0 / factor

        # Try minterpolate for smoother result
        try:
            await _run_cmd([
                "ffmpeg", "-y",
                "-ss", str(start_s), "-i", str(video_path), "-t", str(duration),
                "-vf", f"setpts={pts_mult}*PTS,minterpolate=fps={info['fps']}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                "-an",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                str(slomo),
            ], timeout=300)
        except ProcessingError:
            log.warning("minterpolate_failed_using_basic_slowmo")
            await _extract_segment(video_path, slomo, start_s, end_s, factor)
        segments.append(slomo)

        if end_s < info["duration"]:
            after = tmp / "after.mp4"
            await _extract_segment(video_path, after, end_s, info["duration"], 1.0)
            segments.append(after)

        if progress_callback:
            await progress_callback({"step": "concatenating", "progress": 0.80})

        await _concat_segments(segments, output_path)

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("slow_motion_complete")
    return {
        "output_path": str(output_path),
        "slow_motion": {"start": start_s, "end": end_s, "factor": factor},
        "original_duration": round(info["duration"], 2),
    }


async def create_timelapse(
    video_path: Path,
    output_path: Path,
    speed_factor: int = 20,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Create a timelapse by speeding up video significantly (audio removed)."""
    log.info("timelapse_start", speed_factor=speed_factor)

    if speed_factor < 2:
        raise ProcessingError("Timelapse speed factor must be at least 2")

    if progress_callback:
        await progress_callback({"step": "processing", "progress": 0.20})

    info = await _get_video_info(video_path)
    pts_mult = 1.0 / speed_factor

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"setpts={pts_mult}*PTS",
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        str(output_path),
    ])

    new_duration = info["duration"] / speed_factor

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("timelapse_complete", new_duration=new_duration)
    return {
        "output_path": str(output_path),
        "speed_factor": speed_factor,
        "original_duration": round(info["duration"], 2),
        "new_duration": round(new_duration, 2),
    }


async def fit_to_duration(
    video_path: Path,
    output_path: Path,
    target_duration: float,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Automatically adjust video speed to match a target duration."""
    log.info("fit_to_duration_start", target=target_duration)

    info = await _get_video_info(video_path)
    required_speed = info["duration"] / target_duration

    min_speed, max_speed = 0.5, 4.0
    required_speed = max(min_speed, min(max_speed, required_speed))

    log.info("fit_to_duration_calculated", speed=required_speed)

    return await apply_speed_change(
        video_path, output_path, speed=required_speed,
        progress_callback=progress_callback,
    )
