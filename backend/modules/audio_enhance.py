"""Audio Enhancement — normalization, noise reduction, EQ, compression, and music mixing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

AUDIO_PRESETS: dict[str, dict] = {
    "voice_over": {
        "target_loudness": -16.0,
        "true_peak": -1.0,
        "noise_reduction": 0.4,
        "voice_enhance": True,
        "compression": True,
        "compression_ratio": 3.0,
        "de_ess": True,
    },
    "podcast": {
        "target_loudness": -16.0,
        "true_peak": -1.0,
        "noise_reduction": 0.3,
        "voice_enhance": True,
        "compression": True,
        "compression_ratio": 2.5,
        "bass_boost": 1.0,
    },
    "vlog": {
        "target_loudness": -14.0,
        "true_peak": -1.0,
        "noise_reduction": 0.3,
        "voice_enhance": True,
        "compression": True,
        "compression_ratio": 4.0,
    },
    "music_video": {
        "target_loudness": -14.0,
        "true_peak": -1.0,
        "noise_reduction": 0.0,
        "voice_enhance": False,
        "compression": True,
        "compression_ratio": 2.0,
        "bass_boost": 2.0,
        "treble_boost": 1.0,
    },
    "instagram": {
        "target_loudness": -14.0,
        "true_peak": -1.0,
        "noise_reduction": 0.25,
        "voice_enhance": True,
        "compression": True,
        "compression_ratio": 4.0,
    },
    "youtube": {
        "target_loudness": -14.0,
        "true_peak": -1.0,
        "noise_reduction": 0.3,
        "voice_enhance": True,
        "compression": True,
        "compression_ratio": 3.0,
    },
}


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
    proc._stderr_data = stderr  # type: ignore[attr-defined]
    return proc


def _build_audio_filter(preset_cfg: dict) -> str:
    """Build FFmpeg audio filter chain from preset config."""
    filters: list[str] = []

    filters.append("highpass=f=80")

    nr = preset_cfg.get("noise_reduction", 0.0)
    if nr > 0:
        nr_strength = nr * 20
        filters.append(f"afftdn=nr={nr_strength}:nf=-20")

    if preset_cfg.get("de_ess"):
        filters.append(
            "highpass=f=4000,compand=attacks=0:decays=0.3:"
            "points=-80/-80|-45/-45|-30/-35|-20/-25:soft-knee=6,lowpass=f=8000"
        )

    if preset_cfg.get("voice_enhance"):
        filters.append("equalizer=f=300:t=q:w=1:g=-2")
        filters.append("equalizer=f=3000:t=q:w=1:g=3")
        filters.append("equalizer=f=8000:t=h:w=1:g=1")

    bass = preset_cfg.get("bass_boost", 0.0)
    if bass:
        filters.append(f"equalizer=f=100:t=q:w=1:g={bass}")
    treble = preset_cfg.get("treble_boost", 0.0)
    if treble:
        filters.append(f"equalizer=f=10000:t=h:w=1:g={treble}")

    if preset_cfg.get("compression"):
        ratio = preset_cfg.get("compression_ratio", 4.0)
        threshold = -20.0
        filters.append(
            f"compand=attacks=0.1:decays=0.3:"
            f"points=-80/-80|{threshold}/{threshold}|"
            f"0/{-threshold/ratio}:"
            f"soft-knee=6:gain=3"
        )

    target = preset_cfg.get("target_loudness", -14.0)
    tp = preset_cfg.get("true_peak", -1.0)
    filters.append(f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=none")

    filters.append("alimiter=limit=0.89:level=1")

    return ",".join(filters)


async def analyze_loudness(video_path: Path) -> dict:
    """Analyze audio loudness of a file using FFmpeg's loudnorm filter."""
    log.info("analyze_loudness", path=str(video_path))
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", str(video_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    output = stderr.decode()

    try:
        json_start = output.rfind("{")
        json_end = output.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            data = json.loads(output[json_start:json_end])
            return {
                "integrated_loudness": float(data.get("input_i", -24)),
                "loudness_range": float(data.get("input_lra", 7)),
                "true_peak": float(data.get("input_tp", -1)),
                "threshold": float(data.get("input_thresh", -34)),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    return {"integrated_loudness": -24.0, "loudness_range": 7.0, "true_peak": -1.0, "threshold": -34.0}


async def enhance_audio(
    video_path: Path,
    output_path: Path,
    preset: str = "youtube",
    add_music_path: Optional[Path] = None,
    music_volume: float = 0.15,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Enhance audio in a video or audio file using a named preset."""
    log.info("enhance_audio_start", video=str(video_path), preset=preset)

    if preset not in AUDIO_PRESETS:
        raise ProcessingError(f"Unknown audio preset '{preset}'. Available: {list(AUDIO_PRESETS.keys())}")

    preset_cfg = AUDIO_PRESETS[preset]

    if progress_callback:
        await progress_callback({"step": "analyzing", "progress": 0.10})

    loudness_before = await analyze_loudness(video_path)
    log.info("current_loudness", lufs=loudness_before["integrated_loudness"])

    if progress_callback:
        await progress_callback({"step": "processing", "progress": 0.30})

    audio_filter = _build_audio_filter(preset_cfg)

    is_video = video_path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-af", audio_filter]
    if is_video:
        cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])
    else:
        codec = "libmp3lame" if output_path.suffix == ".mp3" else "aac"
        cmd.extend(["-c:a", codec, "-b:a", "192k"])
    cmd.append(str(output_path))

    await _run_cmd(cmd)

    if progress_callback:
        await progress_callback({"step": "mixing_music", "progress": 0.70})

    # Add background music if requested
    if add_music_path and add_music_path.exists():
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        # Move enhanced to temp, mix with music to output
        import shutil
        shutil.move(str(output_path), str(tmp_path))

        # Get duration for fade-out
        proc = await _run_cmd([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "json", str(tmp_path),
        ])
        dur = float(json.loads(proc._stdout_data.decode())["format"]["duration"])  # type: ignore[attr-defined]

        filter_complex = (
            f"[1:a]volume={music_volume},afade=t=in:st=0:d=1.0,"
            f"afade=t=out:st={dur - 2.0}:d=2.0[music];"
            f"[music][0:a]sidechaincompress=threshold=0.02:ratio=4:attack=0.2:release=0.5:level_sc=1[ducked];"
            f"[0:a][ducked]amix=inputs=2:duration=first:weights=1 0.8[aout]"
        )
        await _run_cmd([
            "ffmpeg", "-y",
            "-i", str(tmp_path),
            "-stream_loop", "-1", "-i", str(add_music_path),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(dur), "-shortest",
            str(output_path),
        ])
        tmp_path.unlink(missing_ok=True)

    if progress_callback:
        await progress_callback({"step": "verifying", "progress": 0.90})

    loudness_after = await analyze_loudness(output_path)

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("enhance_audio_complete", preset=preset, output_lufs=loudness_after["integrated_loudness"])
    return {
        "output_path": str(output_path),
        "preset": preset,
        "input_loudness": loudness_before["integrated_loudness"],
        "output_loudness": loudness_after["integrated_loudness"],
        "target_loudness": preset_cfg["target_loudness"],
        "music_added": add_music_path is not None and add_music_path.exists(),
    }
