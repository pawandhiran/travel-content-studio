"""Stock Photo Studio — scene-aware photo enhancement for Shutterstock submission.

Applies scene-type-specific edits (exposure, contrast, white balance, noise
reduction, sharpening, vibrance, dust removal, cropping) driven by the
editing knowledge base.  Primary image operations use Pillow; OpenCV is an
optional accelerator for noise reduction and dust-spot inpainting.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageStat
from PIL.ExifTags import TAGS as EXIF_TAGS

from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import cv2
    import numpy as np

    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


# ---------------------------------------------------------------------------
# sRGB ICC profile (minimal, ~588 bytes) embedded as a constant so we never
# depend on an external .icc file at runtime.
# ---------------------------------------------------------------------------

_SRGB_PROFILE: bytes | None = None


def _get_srgb_profile() -> bytes:
    """Return an sRGB ICC profile, preferring Pillow's built-in helper."""
    global _SRGB_PROFILE  # noqa: PLW0603
    if _SRGB_PROFILE is not None:
        return _SRGB_PROFILE

    try:
        from PIL.ImageCms import createProfile, ImageCmsProfile

        profile = createProfile("sRGB")
        _SRGB_PROFILE = ImageCmsProfile(profile).tobytes()
    except Exception:
        _SRGB_PROFILE = b""
    return _SRGB_PROFILE


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SCENE_TYPES: set[str] = {
    "landscape",
    "portrait",
    "food",
    "architecture",
    "street",
    "nature_wildlife",
    "abstract_texture",
    "business_lifestyle",
    "stock_ready",
}

STANDARD_RATIOS: list[tuple[int, int]] = [
    (3, 2),
    (2, 3),
    (4, 3),
    (3, 4),
    (16, 9),
    (9, 16),
    (1, 1),
]

_KNOWLEDGE_BASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "editing_knowledge_base.json"
)
_PHILOSOPHY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "stock_photo_philosophy.json"
)

_kb_cache: dict | None = None
_philosophy_cache: dict | None = None


# ---------------------------------------------------------------------------
# Knowledge-base helpers
# ---------------------------------------------------------------------------


def _load_knowledge_base() -> dict:
    """Load and cache the editing knowledge base JSON."""
    global _kb_cache  # noqa: PLW0603
    if _kb_cache is not None:
        return _kb_cache

    try:
        _kb_cache = json.loads(_KNOWLEDGE_BASE_PATH.read_text())
    except Exception as exc:
        log.warning("kb_load_failed", path=str(_KNOWLEDGE_BASE_PATH), error=str(exc))
        _kb_cache = {}
    return _kb_cache


def _load_philosophy() -> dict:
    """Load and cache the stock photo philosophy JSON."""
    global _philosophy_cache  # noqa: PLW0603
    if _philosophy_cache is not None:
        return _philosophy_cache
    try:
        _philosophy_cache = json.loads(_PHILOSOPHY_PATH.read_text())
    except Exception as exc:
        log.warning("philosophy_load_failed", path=str(_PHILOSOPHY_PATH), error=str(exc))
        _philosophy_cache = {}
    return _philosophy_cache


def _get_scene_settings(scene_type: str) -> dict:
    """Return the technique settings for *scene_type* from the knowledge base.

    If scene_type is 'stock_ready', returns the minimal authentic edit settings
    from the stock photo philosophy -- optimized for Shutterstock acceptance.
    """
    if scene_type == "stock_ready":
        kb = _load_knowledge_base()
        stock_settings = kb.get("stock_ready_mode", {}).get("adjustments", {})
        return {
            "exposure": {
                "brightness_adjust": stock_settings.get("brightness_adjust", 1.02),
                "contrast_adjust": stock_settings.get("contrast_adjust", 1.05),
                "shadow_lift": False,
                "highlight_recovery": True,
            },
            "color": {
                "vibrance_boost": stock_settings.get("vibrance_boost", 1.05),
                "saturation_adjust": stock_settings.get("saturation_adjust", 1.0),
                "warmth_shift": stock_settings.get("warmth_shift", 0),
            },
            "sharpening": {
                "amount": stock_settings.get("sharpening_amount", 30),
                "radius": stock_settings.get("sharpening_radius", 0.8),
                "threshold": 2,
            },
            "noise_reduction": {
                "strength": stock_settings.get("noise_reduction_strength", 3),
                "selective": False,
            },
            "common_mistakes": [
                "Over-editing is the #1 rejection reason -- keep it invisible",
                "Never add vignette or grain for stock",
                "Sharpening above 30 creates halos visible at 100%",
            ],
        }

    kb = _load_knowledge_base()
    techniques: dict = kb.get("techniques", {})
    return techniques.get(scene_type, techniques.get("landscape", {}))


# ---------------------------------------------------------------------------
# EXIF helpers
# ---------------------------------------------------------------------------


def _read_exif(image: Image.Image) -> dict[str, Any]:
    """Extract a flat dict of human-readable EXIF tags."""
    raw = image.getexif()
    if not raw:
        return {}
    decoded: dict[str, Any] = {}
    for tag_id, value in raw.items():
        name = EXIF_TAGS.get(tag_id, str(tag_id))
        decoded[name] = value
    return decoded


# ---------------------------------------------------------------------------
# Scene detection heuristics
# ---------------------------------------------------------------------------


def _detect_scene_type(image: Image.Image, exif_data: dict) -> str:
    """Heuristic scene classification from histogram shape, colour
    distribution, and EXIF metadata."""

    width, height = image.size
    aspect = width / height if height else 1.0
    stat = ImageStat.Stat(image.convert("RGB"))
    means = stat.mean  # [R, G, B]
    stddevs = stat.stddev

    focal_length = exif_data.get("FocalLength")
    if isinstance(focal_length, tuple):
        focal_length = focal_length[0] / focal_length[1] if focal_length[1] else None

    avg_brightness = sum(means) / 3.0
    avg_stddev = sum(stddevs) / 3.0
    green_dominant = means[1] > means[0] and means[1] > means[2]
    warm_dominant = means[0] > means[2]

    # Portrait: narrow DOF proxy — low stddev in outer regions
    if focal_length and focal_length >= 50 and aspect >= 0.6 and aspect <= 1.0:
        return "portrait"

    # Architecture: wide aspect + high contrast + low saturation proxy
    if aspect >= 1.3 and avg_stddev > 55 and not green_dominant:
        return "architecture"

    # Food: warm colours, moderate brightness, squarish
    if warm_dominant and avg_brightness > 110 and 0.8 <= aspect <= 1.4:
        return "food"

    # Nature / wildlife: green dominant + bright
    if green_dominant and avg_brightness > 90:
        return "nature_wildlife"

    # Abstract / texture: very high contrast, no dominant channel
    max_diff = max(stddevs) - min(stddevs)
    if avg_stddev > 65 and max_diff < 15:
        return "abstract_texture"

    # Street: moderate contrast, desaturated proxy
    if avg_stddev > 45 and avg_brightness < 140:
        return "street"

    # Business / lifestyle: bright, low contrast
    if avg_brightness > 150 and avg_stddev < 50:
        return "business_lifestyle"

    # Default
    return "landscape"


# ---------------------------------------------------------------------------
# Image-processing primitives
# ---------------------------------------------------------------------------


def _apply_vibrance(image: Image.Image, amount: float) -> Image.Image:
    """Boost saturation of under-saturated pixels (vibrance), leaving already
    vivid colours mostly untouched.

    *amount* is a multiplier (e.g. 1.15 = +15 %).
    """
    if abs(amount - 1.0) < 0.01:
        return image

    hsv = image.convert("HSV")
    h, s, v = hsv.split()
    s_data = bytearray(s.tobytes())
    for i, val in enumerate(s_data):
        # Pixels with low saturation get a bigger boost
        factor = amount + (amount - 1.0) * (1.0 - val / 255.0)
        s_data[i] = min(255, max(0, int(val * factor)))
    s = Image.frombytes("L", s.size, bytes(s_data))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _correct_white_balance(image: Image.Image, warmth_shift: int) -> Image.Image:
    """Shift colour temperature by adjusting R and B channels.

    Positive *warmth_shift* warms (more red, less blue); negative cools.
    """
    if warmth_shift == 0:
        return image

    r, g, b = image.split()
    r = r.point(lambda p: min(255, max(0, p + warmth_shift)))
    b = b.point(lambda p: min(255, max(0, p - warmth_shift)))
    return Image.merge("RGB", (r, g, b))


def _crop_to_standard_ratio(image: Image.Image) -> Image.Image:
    """Centre-crop to the nearest standard aspect ratio."""
    width, height = image.size
    current = width / height

    best_ratio = min(STANDARD_RATIOS, key=lambda r: abs(r[0] / r[1] - current))
    target = best_ratio[0] / best_ratio[1]

    if abs(current - target) < 0.02:
        return image

    if current > target:
        new_w = int(height * target)
        left = (width - new_w) // 2
        return image.crop((left, 0, left + new_w, height))
    else:
        new_h = int(width / target)
        top = (height - new_h) // 2
        return image.crop((0, top, width, top + new_h))


def _embed_srgb_profile(image: Image.Image) -> Image.Image:
    """Attach the sRGB ICC profile to *image*."""
    profile = _get_srgb_profile()
    if profile:
        image.info["icc_profile"] = profile
    return image


def _denoise_cv2(image: Image.Image, strength: int) -> Image.Image:
    """OpenCV fast non-local-means denoising (colour)."""
    arr = np.array(image)
    denoised = cv2.fastNlMeansDenoisingColored(arr, None, strength, strength, 7, 21)
    return Image.fromarray(denoised)


def _denoise_pillow(image: Image.Image, strength: int) -> Image.Image:
    """Pillow-only fallback: light Gaussian blur proportional to *strength*."""
    radius = max(0.5, strength / 10.0)
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def _detect_dust_spots_cv2(image: Image.Image) -> list[tuple[int, int, int]]:
    """Return a list of (x, y, radius) for candidate dust spots using OpenCV."""
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=30,
        param1=50,
        param2=30,
        minRadius=3,
        maxRadius=20,
    )
    if circles is None:
        return []
    spots: list[tuple[int, int, int]] = []
    for c in circles[0]:
        x, y, r = int(c[0]), int(c[1]), int(c[2])
        patch = gray[max(0, y - r) : y + r, max(0, x - r) : x + r]
        if patch.size == 0:
            continue
        local_mean = float(patch.mean())
        surround_y0 = max(0, y - r * 3)
        surround_y1 = min(gray.shape[0], y + r * 3)
        surround_x0 = max(0, x - r * 3)
        surround_x1 = min(gray.shape[1], x + r * 3)
        surround = gray[surround_y0:surround_y1, surround_x0:surround_x1]
        surround_mean = float(surround.mean()) if surround.size else local_mean
        if abs(local_mean - surround_mean) > 15:
            spots.append((x, y, r))
    return spots


def _remove_dust_spots_cv2(image: Image.Image) -> tuple[Image.Image, int]:
    """Inpaint detected dust spots.  Returns (image, spots_removed)."""
    spots = _detect_dust_spots_cv2(image)
    if not spots:
        return image, 0
    arr = np.array(image)
    mask = np.zeros(arr.shape[:2], dtype=np.uint8)
    for x, y, r in spots:
        cv2.circle(mask, (x, y), r + 2, 255, -1)
    inpainted = cv2.inpaint(arr, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    return Image.fromarray(inpainted), len(spots)


# ---------------------------------------------------------------------------
# Noise estimation
# ---------------------------------------------------------------------------


def _estimate_noise(image: Image.Image) -> float:
    """Return a 0-1 noise estimate.

    With OpenCV available, uses Laplacian variance on uniform patches.
    Pillow-only fallback computes variance in five sub-patches.
    """
    gray = image.convert("L")
    width, height = gray.size

    if _CV2_AVAILABLE:
        arr = np.array(gray)
        lap_var = cv2.Laplacian(arr, cv2.CV_64F).var()
        # Empirical mapping: lap_var < 100 → clean, > 1500 → very noisy
        return min(1.0, max(0.0, lap_var / 1500.0))

    # Pillow fallback: sample 5 small patches, measure stddev
    patch_size = min(64, width // 4, height // 4)
    if patch_size < 8:
        return 0.0

    coords = [
        (width // 4, height // 4),
        (3 * width // 4, height // 4),
        (width // 2, height // 2),
        (width // 4, 3 * height // 4),
        (3 * width // 4, 3 * height // 4),
    ]
    variances: list[float] = []
    for cx, cy in coords:
        x0 = max(0, cx - patch_size // 2)
        y0 = max(0, cy - patch_size // 2)
        patch = gray.crop((x0, y0, x0 + patch_size, y0 + patch_size))
        stat = ImageStat.Stat(patch)
        variances.append(stat.var[0])

    min_var = min(variances) if variances else 0.0
    # Low-variance patches represent uniform areas; high variance there → noise
    return min(1.0, max(0.0, min_var / 600.0))


# ---------------------------------------------------------------------------
# Colour-cast detection
# ---------------------------------------------------------------------------


def _has_color_cast(image: Image.Image) -> bool:
    """Return True if R/G/B channel means deviate from the luminance mean by
    more than a threshold, suggesting a colour cast."""
    stat = ImageStat.Stat(image.convert("RGB"))
    means = stat.mean
    lum = sum(means) / 3.0
    return any(abs(m - lum) > 12 for m in means)


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------


def _image_stats(image: Image.Image) -> dict:
    stat = ImageStat.Stat(image.convert("RGB"))
    return {
        "mean_brightness": sum(stat.mean) / 3.0,
        "channel_means": {"r": stat.mean[0], "g": stat.mean[1], "b": stat.mean[2]},
        "stddev": sum(stat.stddev) / 3.0,
        "size": list(image.size),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_photo(image_path: Path) -> dict:
    """Analyze a photo and return metadata, scene type, and quality signals."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise ProcessingError(f"Image not found: {image_path}")

    log.info("analyze_start", path=str(image_path))
    loop = asyncio.get_running_loop()

    def _analyze() -> dict:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        exif = _read_exif(Image.open(image_path))  # re-open to preserve raw EXIF

        scene = _detect_scene_type(image, exif)
        stat = ImageStat.Stat(image)
        mean_brightness = sum(stat.mean) / 3.0

        if mean_brightness < 70:
            exposure = "underexposed"
        elif mean_brightness > 185:
            exposure = "overexposed"
        else:
            exposure = "normal"

        noise = _estimate_noise(image)
        cast = _has_color_cast(image)

        issues: list[str] = []
        if exposure != "normal":
            issues.append(exposure)
        if noise > 0.4:
            issues.append("noisy")
        if cast:
            issues.append("color_cast")
        if width * height < 4_000_000:
            issues.append("low_resolution")

        iso = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")

        return {
            "scene_type": scene,
            "resolution": (width, height),
            "megapixels": round(width * height / 1_000_000, 2),
            "exposure_assessment": exposure,
            "noise_estimate": round(noise, 3),
            "has_color_cast": cast,
            "iso": iso,
            "issues": issues,
        }

    result = await loop.run_in_executor(None, _analyze)
    log.info("analyze_done", scene=result["scene_type"], issues=result["issues"])
    return result


async def enhance_photo(
    image_path: Path,
    output_path: Path,
    scene_type: str | None = None,
    settings: dict | None = None,
    progress_callback: Optional[Callable[[float, str], Any]] = None,
) -> dict:
    """Apply scene-aware enhancements and save as Shutterstock-ready JPEG.

    Args:
        image_path: Source image.
        output_path: Destination JPEG.
        scene_type: Override automatic scene detection.
        settings: Override knowledge-base settings (partial merge).
        progress_callback: ``callback(progress_pct, step_name)``.

    Returns:
        Dict with *output_path*, *scene_type*, *operations_applied*,
        *before_stats*, *after_stats*.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)

    if not image_path.exists():
        raise ProcessingError(f"Image not found: {image_path}")

    log.info("enhance_start", src=str(image_path), dst=str(output_path))
    loop = asyncio.get_running_loop()

    if scene_type is None:
        analysis = await analyze_photo(image_path)
        scene_type = analysis["scene_type"]
    elif scene_type not in VALID_SCENE_TYPES:
        raise ProcessingError(f"Unknown scene type: {scene_type}")

    kb_settings = _get_scene_settings(scene_type)
    if settings:
        for section in ("exposure", "color", "sharpening", "noise_reduction"):
            if section in settings:
                kb_settings.setdefault(section, {}).update(settings[section])

    async def _progress(pct: float, step: str) -> None:
        if progress_callback:
            try:
                result = progress_callback(pct, step)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def _process() -> dict:
        image = Image.open(image_path).convert("RGB")
        before = _image_stats(image)
        operations: list[str] = []

        exp = kb_settings.get("exposure", {})
        color = kb_settings.get("color", {})
        sharp = kb_settings.get("sharpening", {})
        nr = kb_settings.get("noise_reduction", {})

        # 1. Exposure
        brightness_factor = exp.get("brightness_adjust", 1.0)
        if abs(brightness_factor - 1.0) > 0.005:
            image = ImageEnhance.Brightness(image).enhance(brightness_factor)
            operations.append(f"brightness×{brightness_factor}")

        # 2. Contrast
        contrast_factor = exp.get("contrast_adjust", 1.0)
        if abs(contrast_factor - 1.0) > 0.005:
            image = ImageEnhance.Contrast(image).enhance(contrast_factor)
            operations.append(f"contrast×{contrast_factor}")

        # 3. White balance
        warmth = color.get("warmth_shift", 0)
        if warmth != 0 or _has_color_cast(image):
            effective_warmth = warmth if warmth != 0 else 3
            image = _correct_white_balance(image, effective_warmth)
            operations.append(f"wb_warmth={effective_warmth}")

        # 4. Noise reduction
        noise_est = _estimate_noise(image)
        nr_strength = nr.get("strength", 5)
        if noise_est > 0.2:
            if _CV2_AVAILABLE:
                image = _denoise_cv2(image, nr_strength)
                operations.append(f"denoise_cv2(s={nr_strength})")
            else:
                image = _denoise_pillow(image, nr_strength)
                operations.append(f"denoise_pil(s={nr_strength})")

        # 5. Sharpening
        s_amount = sharp.get("amount", 50)
        s_radius = sharp.get("radius", 1.0)
        s_threshold = sharp.get("threshold", 2)
        image = image.filter(
            ImageFilter.UnsharpMask(
                radius=s_radius, percent=s_amount, threshold=s_threshold
            )
        )
        operations.append(f"sharpen(a={s_amount},r={s_radius},t={s_threshold})")

        # 6. Vibrance
        vib = color.get("vibrance_boost", 1.0)
        if abs(vib - 1.0) > 0.01:
            image = _apply_vibrance(image, vib)
            operations.append(f"vibrance×{vib}")

        # 7. Saturation tweak
        sat = color.get("saturation_adjust", 1.0)
        if abs(sat - 1.0) > 0.01:
            image = ImageEnhance.Color(image).enhance(sat)
            operations.append(f"saturation×{sat}")

        # 8. Dust spot removal (OpenCV only)
        if _CV2_AVAILABLE:
            image, spots = _remove_dust_spots_cv2(image)
            if spots:
                operations.append(f"dust_spots_removed={spots}")

        # 9. Crop to standard ratio
        before_size = image.size
        image = _crop_to_standard_ratio(image)
        if image.size != before_size:
            operations.append(f"crop_{image.size[0]}x{image.size[1]}")

        # 10. Embed sRGB
        image = _embed_srgb_profile(image)
        operations.append("srgb_profile")

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs: dict[str, Any] = {
            "quality": 95,
            "subsampling": 0,  # 4:4:4 chroma
        }
        if image.info.get("icc_profile"):
            save_kwargs["icc_profile"] = image.info["icc_profile"]
        image.save(str(output_path), "JPEG", **save_kwargs)

        after = _image_stats(image)

        return {
            "output_path": str(output_path),
            "scene_type": scene_type,
            "operations_applied": operations,
            "before_stats": before,
            "after_stats": after,
        }

    await _progress(0.0, "loading")

    result = await loop.run_in_executor(None, _process)

    await _progress(1.0, "complete")
    log.info(
        "enhance_done",
        scene=result["scene_type"],
        ops=len(result["operations_applied"]),
        output=result["output_path"],
    )
    return result


async def batch_enhance(
    image_paths: list[Path],
    output_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None,
) -> list[dict]:
    """Enhance multiple photos, writing results into *output_dir*.

    Args:
        image_paths: Source images.
        output_dir: Destination folder.
        progress_callback: ``callback(current_index, total, filename)``.

    Returns:
        List of per-image result dicts (same shape as :func:`enhance_photo`).
        Failed images include an ``error`` key instead.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(image_paths)
    results: list[dict] = []

    for idx, src in enumerate(image_paths):
        src = Path(src)
        dst = output_dir / f"{src.stem}_enhanced.jpg"

        if progress_callback:
            try:
                rv = progress_callback(idx, total, src.name)
                if asyncio.iscoroutine(rv):
                    await rv
            except Exception:
                pass

        try:
            result = await enhance_photo(src, dst)
            results.append(result)
        except Exception as exc:
            log.error("batch_enhance_fail", file=str(src), error=str(exc))
            results.append({"input_path": str(src), "error": str(exc)})

    log.info("batch_enhance_done", total=total, success=sum(1 for r in results if "error" not in r))
    return results
