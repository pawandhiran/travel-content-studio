"""Music reel generator with beat-synced transitions and effects.

Creates rendered video reels by combining clips with background music,
applying beat-synchronized transitions via FFmpeg xfade/zoompan, and
mixing audio with fade in/out.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger
from services.beat_sync_service import (
    BeatAnalysis,
    analyze_beats,
    generate_beat_effects,
    generate_transition_markers,
)

log = get_logger(__name__)

ProgressCallback = Optional[Callable[[float, str], None]]

_ASPECT_CONFIGS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_cmd(args: list[str], timeout: float = 600) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise ProcessingError(f"Command failed: {stderr.decode()[:500]}")
    return stdout, stderr


async def _get_video_info(video_path: Path) -> dict:
    stdout, _ = await _run_cmd(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(video_path),
        ]
    )
    data = json.loads(stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "video"), None
    )
    if not video_stream:
        raise ProcessingError(f"No video stream in {video_path.name}")

    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = int(num) / int(den) if int(den) else 30.0
    else:
        fps = float(fps_str)

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(data["format"].get("duration", 0)),
        "fps": fps,
        "has_audio": any(s["codec_type"] == "audio" for s in data.get("streams", [])),
    }


async def _prepare_clip(
    input_path: Path,
    output_path: Path,
    target_width: int,
    target_height: int,
    duration: float | None = None,
) -> None:
    """Resize, crop, and optionally trim a clip to target dimensions."""
    info = await _get_video_info(input_path)
    target_aspect = target_width / target_height
    source_aspect = info["width"] / info["height"]

    if source_aspect > target_aspect:
        scale_filter = f"scale=-1:{target_height}"
    else:
        scale_filter = f"scale={target_width}:-1"

    crop_filter = f"crop={target_width}:{target_height}"

    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    if duration:
        cmd.extend(["-t", str(duration)])
    cmd.extend([
        "-vf", f"{scale_filter},{crop_filter},setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",
        str(output_path),
    ])
    await _run_cmd(cmd)


async def _create_segment(
    clip_path: Path,
    output_path: Path,
    duration: float,
) -> None:
    """Extract a segment from a clip, looping if necessary."""
    await _run_cmd(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(clip_path),
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",
            str(output_path),
        ]
    )


async def _apply_transitions(
    segment_files: list[Path],
    transitions: list[float],
    output_path: Path,
    tempo: float,
) -> Path:
    """Apply xfade transitions between segments."""
    if len(segment_files) < 2:
        shutil.copy(segment_files[0], output_path)
        return output_path

    base_duration = min(0.3, 60.0 / tempo / 4) if tempo > 0 else 0.3

    cmd = ["ffmpeg", "-y"]
    for seg in segment_files:
        cmd.extend(["-i", str(seg)])

    filter_parts: list[str] = []
    current_output = "[0:v]"
    cumulative_offset = 0.0

    for i in range(1, len(segment_files)):
        prev_info = await _get_video_info(segment_files[i - 1])
        prev_dur = prev_info["duration"]
        offset = cumulative_offset + prev_dur - base_duration
        cumulative_offset = offset

        transition_type = "fade"
        if transitions and i - 1 < len(transitions):
            idx = i - 1
            if idx % 3 == 0:
                transition_type = "fadeblack"
            elif idx % 3 == 1:
                transition_type = "slideleft"

        out_label = f"[v{i}]" if i < len(segment_files) - 1 else "[vout]"
        filter_parts.append(
            f"{current_output}[{i}:v]xfade=transition={transition_type}:"
            f"duration={base_duration}:offset={offset:.3f}{out_label}"
        )
        current_output = out_label

    cmd.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",
        str(output_path),
    ])

    try:
        await _run_cmd(cmd, timeout=300)
    except ProcessingError:
        log.warning("music_reels.xfade_failed", fallback="concat")
        await _concat_videos(segment_files, output_path)

    return output_path


async def _concat_videos(video_files: list[Path], output_path: Path) -> None:
    """Simple concatenation without transitions."""
    concat_file = Path(tempfile.mktemp(suffix=".txt"))
    try:
        concat_file.write_text(
            "\n".join(f"file '{f}'" for f in video_files)
        )
        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an",
                str(output_path),
            ]
        )
    finally:
        concat_file.unlink(missing_ok=True)


async def _apply_beat_effects(
    video_path: Path,
    beat_analysis: BeatAnalysis,
    effect_type: str,
    output_path: Path,
) -> Path:
    """Apply beat-synchronized zoom pulse effects via FFmpeg filters."""
    effects = generate_beat_effects(beat_analysis, effect_type)

    if not effects or effect_type == "none":
        shutil.copy(video_path, output_path)
        return output_path

    if effect_type == "zoom_pulse":
        zoom_points: list[str] = []
        for effect in effects[:20]:
            t = effect["time"]
            scale = effect.get("scale", 1.02)
            zoom_points.append(f"if(between(t,{t:.2f},{t + 0.15:.2f}),{scale},1)")

        if zoom_points:
            zoom_expr = "+".join([f"({zp}-1)" for zp in zoom_points]) + "+1"
            filter_str = (
                f"scale=iw*({zoom_expr}):ih*({zoom_expr}),"
                f"crop=iw/{zoom_expr}:ih/{zoom_expr}"
            )
        else:
            filter_str = "null"
    else:
        filter_str = "null"

    try:
        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an",
                str(output_path),
            ]
        )
    except ProcessingError:
        shutil.copy(video_path, output_path)

    return output_path


async def _add_music(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    duration: float,
    volume: float,
    fade_in: float = 0.5,
    fade_out: float = 1.0,
) -> None:
    """Overlay music with fade in/out onto the video."""
    audio_filter = (
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={max(0, duration - fade_out)}:d={fade_out},"
        f"volume={volume}"
    )
    await _run_cmd(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(music_path),
            "-t", str(duration),
            "-filter_complex", f"[1:a]{audio_filter}[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_music_reel(
    clip_paths: list[Path],
    output_path: Path,
    music_path: Path | None = None,
    duration: int = 30,
    transition: str = "mixed",
    effect: str = "zoom_pulse",
    aspect: str = "9:16",
    volume: float = 0.7,
    progress_callback: ProgressCallback = None,
) -> dict:
    """
    Create a rendered video reel with beat-synced transitions and optional music.

    Args:
        clip_paths: Source video clips.
        output_path: Where to write the final MP4.
        music_path: Background music file (optional -- without music, transitions are evenly spaced).
        duration: Target reel duration in seconds.
        transition: Transition style (cut, fade, zoom, slide, mixed).
        effect: Beat effect type (zoom_pulse, flash, shake, none).
        aspect: Output aspect ratio (9:16, 16:9, 1:1, 4:5).
        volume: Music volume 0.0-1.0.
        progress_callback: Optional (progress_fraction, status_message) callback.

    Returns:
        Metadata dict with output path, tempo, beat count, etc.
    """
    if not clip_paths:
        raise ProcessingError("At least one video clip is required")
    if music_path and not Path(music_path).exists():
        raise ProcessingError(f"Music file not found: {music_path}")

    for cp in clip_paths:
        if not Path(cp).exists():
            raise ProcessingError(f"Clip not found: {cp}")

    width, height = _ASPECT_CONFIGS.get(aspect, (1080, 1920))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _progress(frac: float, msg: str) -> None:
        if progress_callback:
            progress_callback(frac, msg)

    beat_analysis = None
    if music_path:
        _progress(0.05, "Analyzing beats...")
        beat_analysis = await analyze_beats(Path(music_path), fps=30)
    else:
        _progress(0.05, "No music provided, using even transitions...")
        beat_analysis = BeatAnalysis(bpm=120, beats=[], downbeats=[], duration=float(duration))
    log.info("music_reels.beats_analyzed", bpm=beat_analysis.bpm, beats=len(beat_analysis.beats))

    tmpdir = Path(tempfile.mkdtemp(prefix="tcs_reel_"))
    try:
        # Prepare clips
        _progress(0.15, "Preparing clips...")
        prepared: list[Path] = []
        for i, clip in enumerate(clip_paths):
            out_clip = tmpdir / f"clip_{i:03d}.mp4"
            await _prepare_clip(Path(clip), out_clip, width, height)
            prepared.append(out_clip)
            _progress(0.15 + 0.20 * (i + 1) / len(clip_paths), f"Prepared clip {i + 1}/{len(clip_paths)}")

        # Create beat-synced segments
        _progress(0.40, "Creating beat-synced segments...")
        transition_times = beat_analysis.get_transition_times(
            num_transitions=max(len(prepared) - 1, 1),
            prefer_downbeats=True,
            min_interval=1.0,
        )

        switch_times = [0.0] + [t for t in beat_analysis.downbeats if t < duration]
        if not switch_times or switch_times[-1] < duration:
            switch_times.append(float(duration))

        segment_files: list[Path] = []
        for i in range(len(switch_times) - 1):
            seg_dur = switch_times[i + 1] - switch_times[i]
            if seg_dur <= 0:
                continue
            clip_idx = i % len(prepared)
            seg_out = tmpdir / f"seg_{i:03d}.mp4"
            await _create_segment(prepared[clip_idx], seg_out, seg_dur)
            segment_files.append(seg_out)

        if not segment_files:
            raise ProcessingError("No segments could be created")

        # Apply transitions
        _progress(0.60, "Applying transitions...")
        video_only = tmpdir / "video_only.mp4"
        markers = generate_transition_markers(beat_analysis, intensity="medium")
        await _apply_transitions(segment_files, markers, video_only, beat_analysis.bpm)

        # Apply beat effects
        if effect and effect != "none":
            _progress(0.75, "Applying beat effects...")
            video_effects = tmpdir / "video_effects.mp4"
            await _apply_beat_effects(video_only, beat_analysis, effect, video_effects)
        else:
            video_effects = video_only

        # Add music (skip if no music provided)
        if music_path and Path(music_path).exists():
            _progress(0.85, "Adding music...")
            await _add_music(video_effects, music_path, output_path, float(duration), volume)
        else:
            _progress(0.85, "Finalizing video (no music)...")
            shutil.copy2(str(video_effects), str(output_path))

        _progress(1.0, "Complete")
        log.info("music_reels.complete", output=str(output_path))

        return {
            "output": str(output_path),
            "duration": duration,
            "bpm": beat_analysis.bpm,
            "beat_count": len(beat_analysis.beats),
            "segment_count": len(segment_files),
            "transition_count": len(markers),
            "aspect_ratio": aspect,
            "resolution": f"{width}x{height}",
            "effect": effect,
            "music": str(music_path) if music_path else None,
        }

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
