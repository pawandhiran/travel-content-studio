"""Smart thumbnail extraction, scoring, and enhancement.

Complements :mod:`thumbnail_studio` (AI-generated thumbnails via ComfyUI) by
extracting the best *existing* frame from a video, scoring it on visual quality,
and enhancing it with colour correction, vignette, and optional text overlay.

Uses ffmpeg for frame extraction, OpenCV for scoring (graceful fallback when
``cv2`` is unavailable), and Pillow for enhancement.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import cv2
    import numpy as np

    _OPENCV_AVAILABLE = True
except ImportError:
    _OPENCV_AVAILABLE = False
    log.warning("opencv_unavailable", hint="Frame scoring will use basic fallback")

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    log.warning("pillow_unavailable", hint="Thumbnail enhancement disabled")


# ---------------------------------------------------------------------------
# Platform thumbnail specs
# ---------------------------------------------------------------------------

THUMBNAIL_SPECS: dict[str, dict[str, Any]] = {
    "youtube": {"width": 1280, "height": 720, "aspect": 16 / 9},
    "youtube_shorts": {"width": 1080, "height": 1920, "aspect": 9 / 16},
    "instagram_post": {"width": 1080, "height": 1080, "aspect": 1.0},
    "instagram_story": {"width": 1080, "height": 1920, "aspect": 9 / 16},
    "instagram_reel": {"width": 1080, "height": 1920, "aspect": 9 / 16},
}


def get_platform_specs(platform: str) -> dict[str, Any]:
    """Return thumbnail dimensions for a platform, defaulting to YouTube."""
    return THUMBNAIL_SPECS.get(platform, THUMBNAIL_SPECS["youtube"])


# ---------------------------------------------------------------------------
# FFmpeg helpers (async)
# ---------------------------------------------------------------------------


async def _run(args: list[str], *, check: bool = True) -> tuple[str, str]:
    exe = args[0]
    if not shutil.which(exe):
        raise ProcessingError(f"{exe} not found on PATH")

    log.debug("thumb_exec", cmd=" ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if check and proc.returncode != 0:
        raise ProcessingError(
            f"{exe} failed (exit {proc.returncode}): "
            f"{stderr.decode(errors='replace')[:500]}"
        )
    return stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _probe(video_path: Path) -> dict:
    stdout, _ = await _run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ])
    data = json.loads(stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )
    fmt = data.get("format", {})
    fps_parts = video_stream.get("r_frame_rate", "30/1").split("/")
    fps = (
        round(int(fps_parts[0]) / max(int(fps_parts[1]), 1), 2)
        if len(fps_parts) == 2
        else 30.0
    )
    return {
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "duration": float(fmt.get("duration", 0)),
        "fps": fps,
    }


async def _extract_frame(video_path: Path, time_s: float, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    await _run([
        "ffmpeg", "-y",
        "-ss", str(time_s),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output),
    ])
    return output


# ---------------------------------------------------------------------------
# Frame scoring (OpenCV)
# ---------------------------------------------------------------------------


def _score_frame_cv2(frame: Any) -> dict:
    """Score a single OpenCV frame for thumbnail suitability."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    mean_brightness = float(np.mean(gray)) / 255.0
    brightness_score = 1.0 - abs(mean_brightness - 0.5) * 2

    contrast_score = min(float(np.std(gray)) / 255.0 * 3, 1.0)

    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = min(laplacian_var / 1000.0, 1.0)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(50, 50))
    face_count = len(faces)
    face_score = min(face_count * 0.3, 1.0)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    vibrancy = float(np.mean(hsv[:, :, 1])) / 255.0

    h, w = frame.shape[:2]
    third_h, third_w = h // 3, w // 3
    roi_regions = [
        gray[0:third_h, 0:third_w],
        gray[0:third_h, 2 * third_w:],
        gray[2 * third_h:, 0:third_w],
        gray[2 * third_h:, 2 * third_w:],
    ]
    composition = min(float(np.mean([np.var(r) for r in roi_regions])) / 2000.0, 1.0)

    weights = {
        "brightness": 0.15,
        "contrast": 0.15,
        "sharpness": 0.20,
        "faces": 0.25,
        "vibrancy": 0.15,
        "composition": 0.10,
    }
    scored = {
        "brightness": brightness_score,
        "contrast": contrast_score,
        "sharpness": sharpness_score,
        "faces": face_score,
        "vibrancy": vibrancy,
        "composition": composition,
    }
    total = sum(scored[k] * weights[k] for k in weights)

    return {
        "brightness": round(brightness_score, 3),
        "contrast": round(contrast_score, 3),
        "sharpness": round(sharpness_score, 3),
        "face_count": face_count,
        "vibrancy": round(vibrancy, 3),
        "composition": round(composition, 3),
        "total": round(total, 3),
    }


# ---------------------------------------------------------------------------
# Thumbnail enhancement (Pillow)
# ---------------------------------------------------------------------------


def _add_vignette(img: "Image.Image", strength: float = 0.3) -> "Image.Image":
    """Apply a radial vignette overlay."""
    if not _OPENCV_AVAILABLE:
        return img
    width, height = img.size
    x = np.linspace(-1, 1, width)
    y = np.linspace(-1, 1, height)
    X, Y = np.meshgrid(x, y)
    dist = np.sqrt(X ** 2 + Y ** 2)
    mask = np.clip(1 - dist * strength, 0, 1)
    mask = (mask * 255).astype(np.uint8)
    mask_img = Image.fromarray(mask).convert("L")

    r, g, b = img.split()[:3]
    black = Image.new("L", img.size, 0)
    r = Image.composite(r, black, mask_img)
    g = Image.composite(g, black, mask_img)
    b = Image.composite(b, black, mask_img)
    return Image.merge("RGB", (r, g, b))


def _add_text_overlay(
    img: "Image.Image",
    text: str,
    font_size: int = 72,
    position: str = "bottom",
) -> "Image.Image":
    """Render uppercase text with an outline onto the image."""
    draw = ImageDraw.Draw(img)

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.load_default()
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    display_text = text.upper()
    bbox = draw.textbbox((0, 0), display_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x = (img.width - tw) // 2
    if position == "top":
        y = 50
    elif position == "center":
        y = (img.height - th) // 2
    else:
        y = img.height - th - 80

    outline_width = 4
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), display_text, font=font, fill=(0, 0, 0))
    draw.text((x, y), display_text, font=font, fill=(255, 255, 255))

    return img


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def find_best_frames(
    video_path: Path,
    count: int = 5,
) -> list[dict]:
    """Analyze the video and return the *count* best-scoring frames.

    Each returned dict contains ``time``, ``scores``, and ``total_score``.
    Falls back to evenly-spaced timestamps when OpenCV is unavailable.
    """
    video_path = Path(video_path)
    log.info("find_best_frames_start", video=str(video_path), count=count)

    info = await _probe(video_path)
    duration = info["duration"]

    num_candidates = max(count * 4, 20)
    start_time = duration * 0.05
    end_time = duration * 0.95
    interval = (end_time - start_time) / num_candidates

    candidates: list[dict] = []

    if _OPENCV_AVAILABLE:
        cap = cv2.VideoCapture(str(video_path))
        try:
            for i in range(num_candidates):
                t = start_time + i * interval
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ret, frame = cap.read()
                if not ret:
                    continue
                scores = _score_frame_cv2(frame)
                candidates.append({
                    "time": round(t, 3),
                    "scores": scores,
                    "total_score": scores["total"],
                })
        finally:
            cap.release()
    else:
        for i in range(num_candidates):
            t = start_time + i * interval
            candidates.append({
                "time": round(t, 3),
                "scores": {"total": 0.5},
                "total_score": 0.5,
            })

    candidates.sort(key=lambda c: c["total_score"], reverse=True)

    top = candidates[:count]
    if top:
        log.info("find_best_frames_done", top_score=top[0]["total_score"], found=len(top))
    return top


async def enhance_thumbnail(
    image_path: Path,
    output_path: Path,
    text: str | None = None,
    vignette: bool = True,
) -> dict:
    """Enhance a thumbnail image with colour correction, vignette, and optional text.

    Returns a dict with ``output_path``, ``width``, ``height``.
    """
    image_path, output_path = Path(image_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not _PIL_AVAILABLE:
        shutil.copy(image_path, output_path)
        return {"output_path": str(output_path), "width": 0, "height": 0}

    img = Image.open(image_path).convert("RGB")

    img = ImageEnhance.Brightness(img).enhance(1.1)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    img = ImageEnhance.Color(img).enhance(1.15)

    if vignette:
        img = _add_vignette(img)

    if text:
        img = _add_text_overlay(img, text)

    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=50))
    img.save(str(output_path), quality=95)

    log.info("thumbnail_enhanced", output=str(output_path))
    return {
        "output_path": str(output_path),
        "width": img.width,
        "height": img.height,
    }


async def extract_smart_thumbnail(
    video_path: Path,
    output_path: Path,
    platform: str = "youtube",
    text: str | None = None,
    progress_callback: Optional[Callable[[int], Any]] = None,
) -> dict:
    """End-to-end smart thumbnail: find best frame, crop to platform, enhance.

    Args:
        video_path: Source video.
        output_path: Where to save the finished thumbnail.
        platform: Target platform key (see :data:`THUMBNAIL_SPECS`).
        text: Optional text overlay.
        progress_callback: Optional ``async`` or sync callable receiving
            progress percentage (0-100).

    Returns:
        Dict with ``output_path``, ``frame_time``, ``scores``, ``platform``,
        ``width``, ``height``.
    """
    video_path, output_path = Path(video_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log.info(
        "smart_thumbnail_start",
        video=str(video_path),
        platform=platform,
    )

    async def _notify(pct: int) -> None:
        if progress_callback is None:
            return
        result = progress_callback(pct)
        if asyncio.iscoroutine(result):
            await result

    await _notify(0)

    # Step 1 -- find best frame
    best = await find_best_frames(video_path, count=1)
    if not best:
        raise ProcessingError("Could not extract any frames from video")

    frame_time = best[0]["time"]
    scores = best[0]["scores"]
    await _notify(30)

    # Step 2 -- extract raw frame
    spec = get_platform_specs(platform)
    with tempfile.TemporaryDirectory() as tmpdir:
        raw = Path(tmpdir) / "raw_frame.jpg"
        await _extract_frame(video_path, frame_time, raw)
        await _notify(50)

        # Step 3 -- crop / resize to platform dimensions
        if _PIL_AVAILABLE:
            img = Image.open(raw).convert("RGB")
            target_w, target_h = spec["width"], spec["height"]
            target_aspect = spec["aspect"]
            img_aspect = img.width / img.height

            if img_aspect > target_aspect:
                new_w = int(img.height * target_aspect)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target_aspect)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))

            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            cropped = Path(tmpdir) / "cropped.jpg"
            img.save(str(cropped), quality=95)
        else:
            cropped = raw

        await _notify(70)

        # Step 4 -- enhance
        result = await enhance_thumbnail(cropped, output_path, text=text)

    await _notify(100)

    final = {
        "output_path": str(output_path),
        "frame_time": frame_time,
        "scores": scores,
        "platform": platform,
        "width": result.get("width", spec["width"]),
        "height": result.get("height", spec["height"]),
    }

    log.info("smart_thumbnail_done", **final)
    return final
