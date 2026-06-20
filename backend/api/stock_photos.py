"""Stock Photo Studio API endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.database import get_db
from core.task_queue import task_queue

router = APIRouter(prefix="/stock-photos", tags=["stock-photos"])


@router.post("/analyze")
async def analyze_photos(body: dict):
    """Analyze photos and return scene types, issues, and descriptions."""
    image_paths = body.get("image_paths", [])
    if not image_paths:
        return {"error": "No image paths provided", "results": []}

    from pathlib import Path
    from modules.stock_photo_studio import analyze_only

    paths = [Path(p) for p in image_paths]
    results = await analyze_only(paths)
    return {"results": results}


@router.post("/enhance")
async def enhance_photos(body: dict):
    """Run the full stock photo pipeline in the background.

    Pass mode='stock_ready' for minimal authentic edits optimized for
    Shutterstock acceptance (no heavy processing, demand-aligned metadata).
    Pass output_dir to choose where enhanced photos are saved.
    """
    image_paths = body.get("image_paths", [])
    mode = body.get("mode", "standard")
    custom_output_dir = body.get("output_dir", "")
    if not image_paths:
        return {"error": "No image paths provided"}

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.stock_photo_studio import process_photos

        if custom_output_dir:
            output_dir = Path(custom_output_dir)
        else:
            output_dir = Path.home() / "Pictures" / "TravelContentStudio" / "StockPhotos"

        paths = [Path(p) for p in image_paths]

        result = await process_photos(
            paths, output_dir, progress_callback=update_progress,
            mode=mode,
        )
        return {
            "total": result.total,
            "enhanced": result.enhanced,
            "passed_qc": result.passed_qc,
            "failed_qc": result.failed_qc,
            "csv_path": str(result.csv_path.resolve()) if result.csv_path != Path() else "",
            "package_path": str(result.package_path.resolve()) if result.package_path != Path() else "",
            "output_dir": str(output_dir.resolve()),
            "photos": [
                {
                    "original_path": str(p.original_path.resolve()) if p.original_path != Path() else "",
                    "enhanced_path": str(p.enhanced_path.resolve()) if p.enhanced_path != Path() else "",
                    "scene_type": p.scene_type,
                    "quality_score": p.quality_score,
                    "passed_qc": p.passed_qc,
                    "issues": p.issues,
                    "metadata": p.metadata,
                }
                for p in result.photos
            ],
        }

    job_id = await task_queue.submit("stock_photo_enhance", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get the processing status of a stock photo job."""
    status = task_queue.get_status(job_id)
    if not status:
        return {"error": "Job not found"}
    return status


@router.get("/presets")
async def get_presets():
    """Return available scene types and their descriptions."""
    return {
        "scene_types": {
            "landscape": "Wide vistas, horizons, mountains, beaches, skylines",
            "portrait": "People as primary subject, headshots, environmental portraits",
            "food": "Dishes, ingredients, beverages, restaurant settings",
            "architecture": "Buildings, interiors, structural details, urban geometry",
            "street": "Candid urban life, markets, city scenes with activity",
            "nature_wildlife": "Animals, plants, macro nature, forests, underwater",
            "abstract_texture": "Patterns, textures, surfaces, geometric shapes, bokeh",
            "business_lifestyle": "Office settings, professional scenarios, lifestyle shots",
        }
    }


@router.post("/metadata")
async def generate_metadata_only(body: dict):
    """Generate metadata for already-enhanced photos without running the full pipeline."""
    photos = body.get("photos", [])
    if not photos:
        return {"error": "No photos provided", "results": []}

    from modules.photo_metadata import batch_generate_metadata

    results = await batch_generate_metadata(photos)
    return {"results": results}


@router.get("/history")
async def list_previous_edits(output_dir: str = ""):
    """List previously enhanced photos from the output directory."""
    from pathlib import Path
    import os

    if output_dir:
        base = Path(output_dir)
    else:
        base = Path.home() / "Pictures" / "TravelContentStudio" / "StockPhotos"

    # Also scan the legacy per-job directory
    legacy_base = Path(get_settings().data_dir) / "stock_photos"

    photos: list[dict] = []
    seen: set[str] = set()

    for search_dir in [base, legacy_base]:
        if not search_dir.exists():
            continue
        for root, _dirs, files in os.walk(str(search_dir)):
            for fname in sorted(files):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                full = Path(root) / fname
                key = str(full)
                if key in seen:
                    continue
                seen.add(key)
                stat = full.stat()
                photos.append({
                    "path": key,
                    "name": fname,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": stat.st_mtime,
                    "folder": str(Path(root).relative_to(search_dir)) if root != str(search_dir) else "",
                })

    photos.sort(key=lambda p: p["modified"], reverse=True)

    return {"photos": photos, "total": len(photos)}


@router.get("/export/{job_id}")
async def export_package(job_id: str):
    """Download the zip package for a completed stock photo job."""
    from pathlib import Path

    status = task_queue.get_status(job_id)
    if not status:
        return {"error": "Job not found"}

    result = status.get("result")
    if not result or not result.get("package_path"):
        return {"error": "Package not yet available"}

    package_path = Path(result["package_path"])
    if not package_path.exists():
        return {"error": "Package file not found on disk"}

    return FileResponse(
        path=str(package_path),
        media_type="application/zip",
        filename=f"stock_photos_{job_id}.zip",
    )
