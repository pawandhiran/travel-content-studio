"""Color Grading — applies LUTs, presets, vignette, and grain to videos."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

BUILTIN_GRADES: dict[str, dict] = {
    "cinematic": {
        "contrast": 1.1,
        "saturation": 0.95,
        "gamma": 0.95,
        "shadows": {"r": 0.0, "g": -0.02, "b": 0.03},
        "highlights": {"r": 0.03, "g": 0.01, "b": -0.02},
        "description": "Cinematic teal & orange look",
    },
    "vibrant": {
        "contrast": 1.15,
        "saturation": 1.25,
        "gamma": 1.0,
        "shadows": {"r": 0.0, "g": 0.0, "b": 0.0},
        "highlights": {"r": 0.0, "g": 0.0, "b": 0.0},
        "description": "Punchy, saturated social media look",
    },
    "moody": {
        "contrast": 1.2,
        "saturation": 0.85,
        "gamma": 0.9,
        "shadows": {"r": 0.02, "g": 0.0, "b": 0.04},
        "highlights": {"r": -0.02, "g": 0.0, "b": 0.0},
        "description": "Dark, desaturated moody look",
    },
    "warm_vintage": {
        "contrast": 1.05,
        "saturation": 0.9,
        "gamma": 1.05,
        "shadows": {"r": 0.03, "g": 0.02, "b": -0.02},
        "highlights": {"r": 0.02, "g": 0.01, "b": -0.03},
        "description": "Warm, nostalgic vintage feel",
    },
    "cool_clean": {
        "contrast": 1.08,
        "saturation": 0.95,
        "gamma": 1.02,
        "shadows": {"r": -0.02, "g": 0.0, "b": 0.03},
        "highlights": {"r": 0.0, "g": 0.0, "b": 0.0},
        "description": "Clean, professional cool tones",
    },
    "sunset_golden": {
        "contrast": 1.1,
        "saturation": 1.15,
        "gamma": 1.0,
        "shadows": {"r": 0.02, "g": 0.0, "b": -0.02},
        "highlights": {"r": 0.05, "g": 0.02, "b": -0.04},
        "description": "Warm golden hour look",
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
    return proc


def _build_color_filter(
    preset: str,
    vignette: float = 0.0,
    grain: float = 0.0,
    lut_path: Optional[Path] = None,
) -> str:
    """Build the FFmpeg video filter chain for color grading."""
    filters: list[str] = []
    grade = BUILTIN_GRADES.get(preset, BUILTIN_GRADES["cinematic"])

    contrast = grade["contrast"]
    saturation = grade["saturation"]
    gamma = grade["gamma"]
    shadows = grade["shadows"]
    highlights = grade["highlights"]

    # EQ filter
    eq_parts: list[str] = []
    if contrast != 1.0:
        eq_parts.append(f"contrast={contrast:.3f}")
    if saturation != 1.0:
        eq_parts.append(f"saturation={saturation:.3f}")
    if gamma != 1.0:
        eq_parts.append(f"gamma={gamma:.3f}")
    if eq_parts:
        filters.append(f"eq={':'.join(eq_parts)}")

    # Shadow/highlight color shifts via colorbalance
    if any(shadows.values()) or any(highlights.values()):
        filters.append(
            f"colorbalance="
            f"rs={shadows['r']:.2f}:gs={shadows['g']:.2f}:bs={shadows['b']:.2f}:"
            f"rh={highlights['r']:.2f}:gh={highlights['g']:.2f}:bh={highlights['b']:.2f}"
        )

    # LUT
    if lut_path and lut_path.exists():
        lut_escaped = str(lut_path).replace(":", r"\:")
        filters.append(f"lut3d={lut_escaped}")

    # Vignette
    if vignette > 0:
        angle = f"PI/4*{vignette:.2f}"
        filters.append(f"vignette=angle={angle}")

    # Film grain
    if grain > 0:
        strength = int(grain * 15)
        filters.append(f"noise=alls={strength}:allf=t")

    return ",".join(filters) if filters else "null"


def get_available_presets() -> list[str]:
    """Return list of available color grade preset names."""
    return list(BUILTIN_GRADES.keys())


async def apply_color_grade(
    video_path: Path,
    output_path: Path,
    preset: str = "cinematic",
    vignette: float = 0.0,
    grain: float = 0.0,
    lut_path: Optional[Path] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Apply a color grade preset to a video."""
    log.info("color_grade_start", video=str(video_path), preset=preset)

    if preset not in BUILTIN_GRADES:
        raise ProcessingError(f"Unknown preset '{preset}'. Available: {get_available_presets()}")

    if progress_callback:
        await progress_callback({"step": "building_filter", "progress": 0.10})

    filter_chain = _build_color_filter(preset, vignette, grain, lut_path)
    log.debug("color_filter_built", filter=filter_chain[:120])

    if progress_callback:
        await progress_callback({"step": "processing", "progress": 0.30})

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ])

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("color_grade_complete", preset=preset, output=str(output_path))
    return {
        "output_path": str(output_path),
        "preset": preset,
        "description": BUILTIN_GRADES[preset]["description"],
        "filter_chain": filter_chain,
        "vignette": vignette,
        "grain": grain,
    }
