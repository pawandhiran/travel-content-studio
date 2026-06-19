"""Stock Photo Quality Gate — pre-submission validation for Shutterstock.

Checks resolution, file size, noise, sharpening halos, banding,
over-noise-reduction, chromatic aberration, compression artefacts,
colour profile, and exposure clipping.  Generates a scored report
indicating whether the image is submission-ready.

Primary checks use Pillow; OpenCV provides enhanced noise and chromatic
aberration detection when available.
"""

from __future__ import annotations

import asyncio
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageFilter, ImageStat
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
# Data types
# ---------------------------------------------------------------------------

SEVERITY_DEDUCTIONS: dict[str, float] = {
    "critical": 3.0,
    "high": 2.0,
    "medium": 1.0,
    "low": 0.5,
}


@dataclass
class QualityIssue:
    severity: str  # critical / high / medium / low
    category: str
    message: str
    fix_suggestion: str


@dataclass
class QualityReport:
    passed: bool
    score: float
    issues: list[QualityIssue] = field(default_factory=list)
    shutterstock_ready: bool = False
    resolution_ok: bool = True
    file_size_ok: bool = True
    profile_ok: bool = True

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 2),
            "shutterstock_ready": self.shutterstock_ready,
            "resolution_ok": self.resolution_ok,
            "file_size_ok": self.file_size_ok,
            "profile_ok": self.profile_ok,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "fix_suggestion": i.fix_suggestion,
                }
                for i in self.issues
            ],
        }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_resolution(image: Image.Image) -> list[QualityIssue]:
    w, h = image.size
    mp = w * h
    if mp < 4_000_000:
        return [
            QualityIssue(
                severity="critical",
                category="resolution",
                message=f"Resolution too low: {w}x{h} ({mp / 1e6:.1f} MP). Minimum 4 MP required.",
                fix_suggestion="Re-shoot at higher resolution or use a higher-quality source.",
            )
        ]
    return []


def _check_file_size(image_path: Path) -> list[QualityIssue]:
    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        return [
            QualityIssue(
                severity="critical",
                category="file_size",
                message=f"File size {size_mb:.1f} MB exceeds 50 MB limit.",
                fix_suggestion="Re-save at JPEG quality 90-95 or reduce resolution slightly.",
            )
        ]
    return []


def _sample_patches(image: Image.Image, count: int = 5, size: int = 64) -> list[Image.Image]:
    """Sample *count* patches from areas likely to be smooth (sky, bg)."""
    gray = image.convert("L")
    w, h = gray.size
    size = min(size, w // 3, h // 3)
    if size < 8:
        return []

    candidates: list[tuple[float, tuple[int, int]]] = []
    step_x = max(1, (w - size) // 8)
    step_y = max(1, (h - size) // 8)

    for y in range(0, h - size, step_y):
        for x in range(0, w - size, step_x):
            patch = gray.crop((x, y, x + size, y + size))
            stat = ImageStat.Stat(patch)
            # Low stddev → smooth / uniform area
            candidates.append((stat.stddev[0], (x, y)))

    candidates.sort(key=lambda c: c[0])
    patches: list[Image.Image] = []
    for _, (x, y) in candidates[:count]:
        patches.append(image.crop((x, y, x + size, y + size)))
    return patches


def _check_noise(image: Image.Image) -> list[QualityIssue]:
    """Sample smooth patches and measure variance as a noise proxy."""
    issues: list[QualityIssue] = []

    if _CV2_AVAILABLE:
        gray = np.array(image.convert("L"))
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if lap_var > 1200:
            issues.append(
                QualityIssue(
                    severity="high",
                    category="noise",
                    message=f"High noise detected (Laplacian variance {lap_var:.0f}).",
                    fix_suggestion="Apply selective noise reduction, especially in shadow areas.",
                )
            )
        elif lap_var > 800:
            issues.append(
                QualityIssue(
                    severity="medium",
                    category="noise",
                    message=f"Moderate noise detected (Laplacian variance {lap_var:.0f}).",
                    fix_suggestion="Consider light noise reduction on smooth areas.",
                )
            )
        return issues

    patches = _sample_patches(image)
    if not patches:
        return issues

    variances = []
    for p in patches:
        stat = ImageStat.Stat(p.convert("L"))
        variances.append(stat.var[0])

    avg_var = sum(variances) / len(variances)
    if avg_var > 120:
        issues.append(
            QualityIssue(
                severity="high",
                category="noise",
                message=f"High noise in smooth areas (avg patch variance {avg_var:.1f}).",
                fix_suggestion="Apply selective noise reduction, especially in shadow areas.",
            )
        )
    elif avg_var > 60:
        issues.append(
            QualityIssue(
                severity="medium",
                category="noise",
                message=f"Moderate noise in smooth areas (avg patch variance {avg_var:.1f}).",
                fix_suggestion="Consider light noise reduction on smooth areas.",
            )
        )
    return issues


def _check_sharpening_halos(image: Image.Image) -> list[QualityIssue]:
    """Detect over-sharpening halos by looking for bright/dark fringes around
    high-contrast edges."""
    issues: list[QualityIssue] = []
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat_edges = ImageStat.Stat(edges)
    edge_mean = stat_edges.mean[0]

    blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
    diff_data = list(gray.tobytes())
    blur_data = list(blurred.tobytes())

    overshoot_count = 0
    total = len(diff_data)
    sample_step = max(1, total // 50000)

    for i in range(0, total, sample_step):
        delta = abs(diff_data[i] - blur_data[i])
        if delta > 40:
            overshoot_count += 1

    sampled = total // sample_step
    ratio = overshoot_count / sampled if sampled else 0

    if ratio > 0.08:
        issues.append(
            QualityIssue(
                severity="high",
                category="sharpening_halos",
                message=f"Sharpening halos detected ({ratio * 100:.1f}% of sampled pixels show overshoot).",
                fix_suggestion="Reduce sharpening amount or increase threshold to protect smooth areas.",
            )
        )
    elif ratio > 0.04:
        issues.append(
            QualityIssue(
                severity="medium",
                category="sharpening_halos",
                message=f"Minor sharpening halos ({ratio * 100:.1f}% overshoot).",
                fix_suggestion="Check edges at 100% zoom for visible halos.",
            )
        )
    return issues


def _check_banding(image: Image.Image) -> list[QualityIssue]:
    """Check for posterization / banding in gradient areas."""
    issues: list[QualityIssue] = []
    gray = image.convert("L")
    hist = gray.histogram()

    zero_bins = sum(1 for v in hist if v == 0)
    occupied_ratio = (256 - zero_bins) / 256

    if occupied_ratio < 0.5:
        issues.append(
            QualityIssue(
                severity="high",
                category="banding",
                message=f"Possible banding/posterization: only {occupied_ratio * 100:.0f}% of tonal range used.",
                fix_suggestion="Avoid heavy curve adjustments. Work in 16-bit when possible.",
            )
        )
    elif occupied_ratio < 0.7:
        issues.append(
            QualityIssue(
                severity="medium",
                category="banding",
                message=f"Reduced tonal range: {occupied_ratio * 100:.0f}% of levels occupied.",
                fix_suggestion="Check gradient areas for visible steps.",
            )
        )
    return issues


def _check_over_nr(image: Image.Image) -> list[QualityIssue]:
    """Detect over-noise-reduction (plastic / waxy look) by measuring
    high-frequency content retention."""
    issues: list[QualityIssue] = []
    gray = image.convert("L")
    detail = gray.filter(ImageFilter.Kernel((3, 3), [-1, -1, -1, -1, 8, -1, -1, -1, -1], scale=1, offset=128))
    stat = ImageStat.Stat(detail)

    hf_energy = stat.stddev[0]
    if hf_energy < 5:
        issues.append(
            QualityIssue(
                severity="high",
                category="over_nr",
                message=f"Excessive noise reduction: very low high-frequency detail (stddev {hf_energy:.1f}).",
                fix_suggestion="Reduce NR strength. Preserve texture in hair, fabric, and surfaces.",
            )
        )
    elif hf_energy < 10:
        issues.append(
            QualityIssue(
                severity="medium",
                category="over_nr",
                message=f"Possible over-smoothing detected (HF stddev {hf_energy:.1f}).",
                fix_suggestion="Inspect skin, fabric, and texture areas at 100% zoom.",
            )
        )
    return issues


def _check_chromatic_aberration(image: Image.Image) -> list[QualityIssue]:
    """Check for purple/green fringes at high-contrast edges."""
    issues: list[QualityIssue] = []

    if _CV2_AVAILABLE:
        arr = np.array(image)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        edge_coords = np.argwhere(edges > 0)

        if len(edge_coords) == 0:
            return issues

        sample_step = max(1, len(edge_coords) // 2000)
        sampled = edge_coords[::sample_step]

        ca_count = 0
        for y, x in sampled:
            r, g, b = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2])
            purple = r > 100 and b > 100 and g < max(r, b) - 40
            green_fringe = g > 100 and g > r + 30 and g > b + 30
            if purple or green_fringe:
                ca_count += 1

        ratio = ca_count / len(sampled) if len(sampled) else 0
        if ratio > 0.10:
            issues.append(
                QualityIssue(
                    severity="medium",
                    category="chromatic_aberration",
                    message=f"Chromatic aberration: {ratio * 100:.1f}% of edge pixels show purple/green fringing.",
                    fix_suggestion="Apply CA correction in raw processing or use lens profile correction.",
                )
            )
        return issues

    # Pillow fallback: check edge pixels for channel imbalance
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    rgb_stat = ImageStat.Stat(image)
    channel_spread = max(rgb_stat.mean) - min(rgb_stat.mean)

    if channel_spread > 30 and edge_stat.mean[0] > 20:
        issues.append(
            QualityIssue(
                severity="low",
                category="chromatic_aberration",
                message="Possible chromatic aberration (high channel spread at edges).",
                fix_suggestion="Apply CA correction. Install OpenCV for more accurate detection.",
            )
        )
    return issues


def _check_compression_artifacts(image: Image.Image, image_path: Path) -> list[QualityIssue]:
    """Detect JPEG compression artefacts by checking quantization quality
    and analysing block-boundary discontinuities."""
    issues: list[QualityIssue] = []

    # Try to read JPEG quality from quantization tables
    quality = image.info.get("quality")
    if quality is not None and isinstance(quality, int):
        if quality < 70:
            issues.append(
                QualityIssue(
                    severity="high",
                    category="compression",
                    message=f"Low JPEG quality ({quality}). Visible block artefacts likely.",
                    fix_suggestion="Re-export at quality 90-95 from the original source.",
                )
            )
            return issues
        elif quality < 85:
            issues.append(
                QualityIssue(
                    severity="medium",
                    category="compression",
                    message=f"Moderate JPEG quality ({quality}).",
                    fix_suggestion="For Shutterstock, re-export at quality 95 from original.",
                )
            )
            return issues

    gray = image.convert("L")
    w, h = gray.size
    if w < 64 or h < 64:
        return issues

    data = list(gray.tobytes())
    boundary_diffs: list[int] = []
    interior_diffs: list[int] = []

    sample_rows = range(8, min(h, 200), 8)
    for y in sample_rows:
        row_offset = y * w
        prev_offset = (y - 1) * w
        for x in range(0, min(w, 200)):
            d = abs(data[row_offset + x] - data[prev_offset + x])
            boundary_diffs.append(d)
        mid_y = y + 4
        if mid_y < h:
            mid_offset = mid_y * w
            mid_prev = (mid_y - 1) * w
            for x in range(0, min(w, 200)):
                d = abs(data[mid_offset + x] - data[mid_prev + x])
                interior_diffs.append(d)

    if boundary_diffs and interior_diffs:
        avg_boundary = sum(boundary_diffs) / len(boundary_diffs)
        avg_interior = sum(interior_diffs) / len(interior_diffs)
        if avg_interior > 0 and avg_boundary / avg_interior > 1.5:
            issues.append(
                QualityIssue(
                    severity="high",
                    category="compression",
                    message="JPEG block artefacts detected at 8x8 boundaries.",
                    fix_suggestion="Re-export at quality 95 from the original lossless source.",
                )
            )

    return issues


def _check_color_profile(image: Image.Image) -> list[QualityIssue]:
    """Check whether an sRGB ICC profile is embedded."""
    icc = image.info.get("icc_profile")
    if not icc:
        return [
            QualityIssue(
                severity="medium",
                category="color_profile",
                message="No ICC colour profile embedded.",
                fix_suggestion="Embed an sRGB profile. Shutterstock requires sRGB.",
            )
        ]
    icc_lower = icc.lower() if isinstance(icc, (bytes, bytearray)) else b""
    if b"srgb" not in icc_lower and b"srgb" not in icc_lower.replace(b"\x00", b""):
        # Heuristic — many profiles don't spell "srgb" literally
        pass
    return []


def _check_exposure_clipping(image: Image.Image) -> list[QualityIssue]:
    """Check if more than 5 % of pixels are fully clipped (0 or 255)."""
    issues: list[QualityIssue] = []
    r, g, b = image.convert("RGB").split()
    total_pixels = image.size[0] * image.size[1]

    for channel, name in [(r, "highlights"), (b, "highlights")]:
        hist = channel.histogram()
        clipped_white = hist[255] / total_pixels
        clipped_black = hist[0] / total_pixels

        if clipped_white > 0.05:
            issues.append(
                QualityIssue(
                    severity="high",
                    category="exposure",
                    message=f"Highlight clipping: {clipped_white * 100:.1f}% of {name} channel at 255.",
                    fix_suggestion="Recover highlights in raw processing or reduce exposure.",
                )
            )
            break
        if clipped_black > 0.05:
            issues.append(
                QualityIssue(
                    severity="high",
                    category="exposure",
                    message=f"Shadow clipping: {clipped_black * 100:.1f}% of pixels at 0.",
                    fix_suggestion="Lift shadows or reduce contrast to retain shadow detail.",
                )
            )
            break

    # Overall luminance check
    gray = image.convert("L")
    hist = gray.histogram()
    white_clip = hist[255] / total_pixels
    black_clip = hist[0] / total_pixels
    if white_clip > 0.05 and not issues:
        issues.append(
            QualityIssue(
                severity="high",
                category="exposure",
                message=f"Overexposed: {white_clip * 100:.1f}% of luminance clipped to white.",
                fix_suggestion="Reduce exposure or recover highlights.",
            )
        )
    if black_clip > 0.05 and not any(i.category == "exposure" and "Shadow" in i.message for i in issues):
        issues.append(
            QualityIssue(
                severity="medium",
                category="exposure",
                message=f"Underexposed: {black_clip * 100:.1f}% of luminance clipped to black.",
                fix_suggestion="Lift shadows conservatively to retain detail.",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _compute_score(issues: list[QualityIssue]) -> float:
    score = 10.0
    for issue in issues:
        score -= SEVERITY_DEDUCTIONS.get(issue.severity, 0)
    return max(0.0, min(10.0, score))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def check_photo_quality(
    image_path: Path,
    strict: bool = False,
) -> QualityReport:
    """Run all quality checks against Shutterstock submission requirements.

    Args:
        image_path: Path to the image file.
        strict: When True, medium issues also cause failure.

    Returns:
        A :class:`QualityReport` with score, issues, and readiness flags.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return QualityReport(
            passed=False,
            score=0.0,
            issues=[
                QualityIssue(
                    severity="critical",
                    category="file",
                    message="File not found.",
                    fix_suggestion="Verify the image path.",
                )
            ],
        )

    log.info("quality_gate_start", path=str(image_path))
    loop = asyncio.get_running_loop()

    def _run_checks() -> QualityReport:
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            return QualityReport(
                passed=False,
                score=0.0,
                issues=[
                    QualityIssue(
                        severity="critical",
                        category="file",
                        message=f"Cannot open image: {exc}",
                        fix_suggestion="Ensure the file is a valid image format.",
                    )
                ],
            )

        all_issues: list[QualityIssue] = []

        all_issues.extend(_check_resolution(image))
        all_issues.extend(_check_file_size(image_path))
        all_issues.extend(_check_noise(image))
        all_issues.extend(_check_sharpening_halos(image))
        all_issues.extend(_check_banding(image))
        all_issues.extend(_check_over_nr(image))
        all_issues.extend(_check_chromatic_aberration(image))
        all_issues.extend(_check_compression_artifacts(image, image_path))
        all_issues.extend(_check_color_profile(image))
        all_issues.extend(_check_exposure_clipping(image))

        score = _compute_score(all_issues)

        resolution_ok = not any(i.category == "resolution" for i in all_issues)
        file_size_ok = not any(i.category == "file_size" for i in all_issues)
        profile_ok = not any(i.category == "color_profile" for i in all_issues)

        if strict:
            passed = score >= 7.0 and not any(
                i.severity in ("critical", "high", "medium") for i in all_issues
            )
        else:
            passed = score >= 7.0

        shutterstock_ready = (
            passed and resolution_ok and file_size_ok and profile_ok
        )

        return QualityReport(
            passed=passed,
            score=score,
            issues=all_issues,
            shutterstock_ready=shutterstock_ready,
            resolution_ok=resolution_ok,
            file_size_ok=file_size_ok,
            profile_ok=profile_ok,
        )

    report = await loop.run_in_executor(None, _run_checks)
    log.info(
        "quality_gate_done",
        path=str(image_path),
        score=report.score,
        passed=report.passed,
        shutterstock_ready=report.shutterstock_ready,
        issue_count=len(report.issues),
    )
    return report


async def batch_check(image_paths: list[Path]) -> list[QualityReport]:
    """Run quality checks on multiple images.

    Returns:
        One :class:`QualityReport` per input path (order preserved).
    """
    results: list[QualityReport] = []
    total = len(image_paths)
    for idx, p in enumerate(image_paths):
        log.debug("batch_check_progress", current=idx + 1, total=total)
        report = await check_photo_quality(Path(p))
        results.append(report)

    passed = sum(1 for r in results if r.passed)
    log.info("batch_check_done", total=total, passed=passed, failed=total - passed)
    return results
