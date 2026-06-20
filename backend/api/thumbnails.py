"""Thumbnail studio endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Project, ProjectStatus, Thumbnail
from models.schemas import JobResponse, ThumbnailGenerateRequest, ThumbnailResponse

router = APIRouter(tags=["thumbnails"])


@router.post("/projects/{project_id}/thumbnails", response_model=JobResponse)
async def generate_thumbnail(
    project_id: str,
    body: ThumbnailGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue thumbnail generation for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    prompt = body.prompt
    style = body.style

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.thumbnail_studio import generate_thumbnail as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting thumbnail generation")
            result = await do_generate(session, project_id, prompt, style)
            await session.commit()
            await update_progress(100, "Thumbnail generation complete")
            return {"id": result.id}

    job_id = await task_queue.submit("thumbnail_generation", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "thumbnail_generation", "status": "pending"}


@router.get("/thumbnails/jobs/{job_id}")
async def get_thumbnail_job_status(job_id: str):
    """Get status of a thumbnail job from the in-memory task queue."""
    status = task_queue.get_status(job_id)
    if not status:
        return {"error": "Job not found", "status": "unknown"}
    return {
        "id": status["id"],
        "status": status["status"].value if hasattr(status["status"], "value") else str(status["status"]),
        "progress": status.get("progress", 0),
        "message": status.get("message", ""),
        "error": status.get("error"),
        "result": status.get("result"),
    }


@router.get("/projects/{project_id}/thumbnails", response_model=list[ThumbnailResponse])
async def list_thumbnails(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all generated thumbnails for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Thumbnail).where(Thumbnail.project_id == project_id).order_by(Thumbnail.created_at.desc())
    )
    return result.scalars().all()


@router.get("/thumbnails/{thumbnail_id}/image")
async def get_thumbnail_image(thumbnail_id: str, db: AsyncSession = Depends(get_db)):
    """Return the generated thumbnail image file."""
    thumbnail = await db.get(Thumbnail, thumbnail_id)
    if not thumbnail:
        raise NotFoundError(f"Thumbnail {thumbnail_id} not found")

    image_path = Path(thumbnail.image_path)
    if not image_path.exists():
        raise NotFoundError("Thumbnail image file not found on disk")

    return FileResponse(str(image_path), media_type="image/png")
