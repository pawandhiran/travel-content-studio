"""Stock Photo Studio -- orchestrates the full photo-to-Shutterstock pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.errors import ProcessingError
from core.logging_config import get_logger
from modules.photo_enhance import analyze_photo, enhance_photo
from modules.photo_metadata import (
    export_package,
    export_shutterstock_csv,
    generate_metadata,
)
from modules.photo_quality_gate import check_photo_quality

log = get_logger(__name__)


@dataclass
class PhotoResult:
    original_path: Path
    enhanced_path: Path
    scene_type: str
    quality_score: float
    passed_qc: bool
    issues: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class StudioResult:
    total: int
    enhanced: int
    passed_qc: int
    failed_qc: int
    photos: list[PhotoResult] = field(default_factory=list)
    csv_path: Path = Path()
    package_path: Path = Path()


async def process_photos(
    image_paths: list[Path],
    output_dir: Path,
    progress_callback: Optional[Callable] = None,
    mode: str = "standard",
) -> StudioResult:
    """Run the full stock photo pipeline: analyze -> enhance -> QC -> metadata -> export.

    Args:
        mode: 'standard' for full scene-aware enhancement, 'stock_ready' for minimal
              authentic edits optimized for Shutterstock acceptance.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    enhanced_dir = output_dir / "enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)

    total = len(image_paths)
    results: list[PhotoResult] = []

    for idx, image_path in enumerate(image_paths):
        try:
            result = await _process_single(image_path, enhanced_dir, mode=mode)
            results.append(result)
        except Exception as exc:
            log.error("photo_processing_failed", image=str(image_path), error=str(exc))
            results.append(PhotoResult(
                original_path=image_path,
                enhanced_path=Path(),
                scene_type="unknown",
                quality_score=0.0,
                passed_qc=False,
                issues=[str(exc)],
                metadata={},
            ))

        if progress_callback:
            pct = int(((idx + 1) / total) * 90)
            await progress_callback(pct, f"Processed {idx + 1}/{total} photos")

    passed = [r for r in results if r.passed_qc]
    failed = [r for r in results if not r.passed_qc]

    photos_metadata = [
        {**r.metadata, "filename": r.enhanced_path.name}
        for r in passed
        if r.metadata
    ]

    csv_path = Path()
    package_path = Path()

    if photos_metadata:
        csv_path = export_shutterstock_csv(photos_metadata, output_dir / "shutterstock.csv")
        package_path = export_package(enhanced_dir, photos_metadata, output_dir / "stock_package.zip")

    if progress_callback:
        await progress_callback(100, "Pipeline complete")

    return StudioResult(
        total=total,
        enhanced=len([r for r in results if r.enhanced_path != Path()]),
        passed_qc=len(passed),
        failed_qc=len(failed),
        photos=results,
        csv_path=csv_path,
        package_path=package_path,
    )


async def _process_single(
    image_path: Path, enhanced_dir: Path, mode: str = "standard"
) -> PhotoResult:
    """Process a single photo through the full pipeline."""
    log.info("processing_photo", image=str(image_path), mode=mode)

    analysis = await analyze_photo(image_path)
    scene_type = analysis.get("scene_type", "landscape")
    issues = analysis.get("issues", [])

    enhanced_path = enhanced_dir / f"{image_path.stem}_enhanced.jpg"

    if mode == "stock_ready":
        await enhance_photo(
            image_path, enhanced_path,
            scene_type="stock_ready",
            settings=_get_stock_ready_settings(),
        )
    else:
        await enhance_photo(image_path, enhanced_path, scene_type=scene_type)

    qc_result = await check_photo_quality(enhanced_path)
    quality_score = qc_result.score if hasattr(qc_result, "score") else qc_result.get("score", 0.0)
    passed_qc = qc_result.passed if hasattr(qc_result, "passed") else qc_result.get("passed", False)
    qc_issues = qc_result.issues if hasattr(qc_result, "issues") else qc_result.get("issues", [])

    metadata = {}
    if passed_qc:
        try:
            metadata = await generate_metadata(
                enhanced_path,
                scene_type,
                image_description=analysis.get("description"),
            )
        except ProcessingError as exc:
            log.warning("metadata_generation_skipped", image=str(image_path), error=str(exc))

    serializable_issues = []
    for issue in issues + qc_issues:
        if hasattr(issue, '__dataclass_fields__'):
            serializable_issues.append(asdict(issue))
        else:
            serializable_issues.append(issue)

    return PhotoResult(
        original_path=image_path,
        enhanced_path=enhanced_path,
        scene_type=scene_type,
        quality_score=quality_score,
        passed_qc=passed_qc,
        issues=serializable_issues,
        metadata=metadata,
    )


async def analyze_only(image_paths: list[Path]) -> list[dict]:
    """Run analysis without enhancement -- for preview purposes."""
    results = []
    for image_path in image_paths:
        try:
            analysis = await analyze_photo(image_path)
            analysis["image_path"] = str(image_path)
            results.append(analysis)
        except Exception as exc:
            log.warning("analysis_failed", image=str(image_path), error=str(exc))
            results.append({
                "image_path": str(image_path),
                "scene_type": "unknown",
                "confidence": 0.0,
                "description": f"Analysis failed: {exc}",
                "issues": [str(exc)],
            })
    return results


def _get_stock_ready_settings() -> dict:
    """Return minimal, authentic edit settings for stock photography."""
    return {
        "exposure": {
            "brightness_adjust": 1.02,
            "contrast_adjust": 1.05,
            "shadow_lift": False,
            "highlight_recovery": True,
        },
        "color": {
            "vibrance_boost": 1.05,
            "saturation_adjust": 1.0,
            "warmth_shift": 0,
        },
        "sharpening": {
            "amount": 30,
            "radius": 0.8,
            "threshold": 2,
        },
        "noise_reduction": {
            "strength": 3,
            "selective": False,
        },
    }
