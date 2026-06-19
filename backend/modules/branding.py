"""Branding — watermarks, end cards, subscribe overlays, and full branding packages."""

from __future__ import annotations

import asyncio
import json
import shutil
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


async def add_watermark(
    video_path: Path,
    output_path: Path,
    watermark_path: Path,
    position: str = "bottom_right",
    opacity: float = 0.7,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Overlay a watermark/logo image on a video."""
    log.info("add_watermark_start", position=position, opacity=opacity)

    if not watermark_path.exists():
        raise ProcessingError(f"Watermark file not found: {watermark_path}")

    if progress_callback:
        await progress_callback({"step": "processing", "progress": 0.20})

    info = await _get_video_info(video_path)
    watermark_width = int(info["width"] * 0.15)
    margin = 20

    positions = {
        "top_left": f"{margin}:{margin}",
        "top_right": f"W-w-{margin}:{margin}",
        "bottom_left": f"{margin}:H-h-{margin}",
        "bottom_right": f"W-w-{margin}:H-h-{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }
    pos = positions.get(position, positions["bottom_right"])

    watermark_filter = (
        f"[1:v]scale={watermark_width}:-1,format=rgba,"
        f"colorchannelmixer=aa={opacity},"
        f"fade=t=in:st=0:d=0.5:alpha=1,"
        f"fade=t=out:st={info['duration'] - 0.5}:d=0.5:alpha=1[watermark]"
    )
    filter_complex = f"{watermark_filter};[0:v][watermark]overlay={pos}[v]"

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(watermark_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ])

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("add_watermark_complete", output=str(output_path))
    return {
        "output_path": str(output_path),
        "watermark": str(watermark_path),
        "position": position,
        "opacity": opacity,
    }


async def add_end_card(
    video_path: Path,
    output_path: Path,
    text: str = "Thanks for watching!",
    duration: float = 5.0,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Append a text end card/outro to the video."""
    log.info("add_end_card_start", text=text, duration=duration)

    if progress_callback:
        await progress_callback({"step": "creating_end_card", "progress": 0.20})

    info = await _get_video_info(video_path)
    bg_color = "0x000000"
    font_color = "0xFFFFFF"
    escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        end_card_path = tmp / "end_card.mp4"

        await _run_cmd([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={info['width']}x{info['height']}:d={duration}:r={info['fps']}",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo:d={duration}",
            "-vf", (
                f"drawtext=text='{escaped_text}':"
                f"fontsize=48:fontcolor={font_color}:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac",
            "-t", str(duration), "-shortest",
            str(end_card_path),
        ])

        if progress_callback:
            await progress_callback({"step": "concatenating", "progress": 0.60})

        concat_file = tmp / "concat.txt"
        concat_file.write_text(f"file '{video_path}'\nfile '{end_card_path}'\n")

        await _run_cmd([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac",
            str(output_path),
        ])

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("add_end_card_complete", output=str(output_path))
    return {
        "output_path": str(output_path),
        "end_card_text": text,
        "end_card_duration": duration,
    }


async def _add_subscribe_button(
    video_path: Path,
    output_path: Path,
) -> None:
    """Internal helper to add an animated subscribe button overlay."""
    info = await _get_video_info(video_path)
    start_time = max(0, info["duration"] - 7.0)
    end_time = info["duration"] - 2.0

    subscribe_filter = (
        f"drawtext=text='SUBSCRIBE':"
        f"fontsize=28:fontcolor=white:"
        f"x=W-250:y=H-80-5*sin(t*10)*if(between(t\\,{start_time}\\,{start_time}+0.5)\\,1\\,0):"
        f"box=1:boxcolor=red@0.9:boxborderw=10:"
        f"enable='between(t,{start_time},{end_time})'"
    )

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", subscribe_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ])


async def _add_lower_third(
    video_path: Path,
    output_path: Path,
    title: str,
    start_time: float = 2.0,
    duration: float = 4.0,
) -> None:
    """Internal helper for a lower-third name graphic."""
    end_time = start_time + duration
    escaped = title.replace("'", "'\\''").replace(":", "\\:")

    filter_chain = (
        f"drawbox=x=0:y=h-120:w=400:h=50:color=0xFF0000@0.8:t=fill:"
        f"enable='between(t,{start_time},{end_time})',"
        f"drawtext=text='{escaped}':"
        f"fontsize=32:fontcolor=0xFFFFFF:"
        f"x=20:y=h-110:"
        f"enable='between(t,{start_time},{end_time})'"
    )

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ])


async def apply_full_branding(
    video_path: Path,
    output_path: Path,
    watermark_path: Optional[Path] = None,
    end_card: bool = False,
    subscribe: bool = False,
    lower_third: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Apply a complete branding package (watermark + lower third + subscribe + end card)."""
    log.info("full_branding_start")

    steps_total = sum([
        watermark_path is not None,
        lower_third is not None,
        subscribe,
        end_card,
    ])
    if steps_total == 0:
        shutil.copy2(str(video_path), str(output_path))
        return {"output_path": str(output_path), "steps_applied": 0}

    step_done = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        current = video_path

        if watermark_path and watermark_path.exists():
            step_done += 1
            step_out = tmp / f"step_{step_done}.mp4"
            if progress_callback:
                await progress_callback({"step": "watermark", "progress": step_done / (steps_total + 1)})
            await add_watermark(current, step_out, watermark_path)
            current = step_out

        if lower_third:
            step_done += 1
            step_out = tmp / f"step_{step_done}.mp4"
            if progress_callback:
                await progress_callback({"step": "lower_third", "progress": step_done / (steps_total + 1)})
            await _add_lower_third(current, step_out, lower_third)
            current = step_out

        if subscribe:
            step_done += 1
            step_out = tmp / f"step_{step_done}.mp4"
            if progress_callback:
                await progress_callback({"step": "subscribe_button", "progress": step_done / (steps_total + 1)})
            await _add_subscribe_button(current, step_out)
            current = step_out

        if end_card:
            step_done += 1
            step_out = tmp / f"step_{step_done}.mp4"
            if progress_callback:
                await progress_callback({"step": "end_card", "progress": step_done / (steps_total + 1)})
            await add_end_card(current, step_out)
            current = step_out

        shutil.copy2(str(current), str(output_path))

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("full_branding_complete", steps=step_done)
    return {
        "output_path": str(output_path),
        "steps_applied": step_done,
        "watermark": str(watermark_path) if watermark_path else None,
        "end_card": end_card,
        "subscribe": subscribe,
        "lower_third": lower_third,
    }
