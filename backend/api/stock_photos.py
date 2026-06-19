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
    """
    image_paths = body.get("image_paths", [])
    mode = body.get("mode", "standard")
    if not image_paths:
        return {"error": "No image paths provided"}

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.stock_photo_studio import process_photos

        settings = get_settings()
        output_dir = Path(settings.data_dir) / "stock_photos" / job_id
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
            "csv_path": str(result.csv_path),
            "package_path": str(result.package_path),
            "photos": [
                {
                    "original_path": str(p.original_path),
                    "enhanced_path": str(p.enhanced_path),
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
