"""Thumbnail studio endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Job, JobStatus, Project, ProjectStatus, Thumbnail
from models.schemas import JobResponse, ThumbnailGenerateRequest, ThumbnailResponse
from services.task_queue import submit_job

router = APIRouter(tags=["thumbnails"])


async def _generate_thumbnail(job_id: str, project_id: str, prompt: str, style: str | None):
    """Background task: generate thumbnail image via ComfyUI/Stable Diffusion."""
    pass


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

    job = Job(
        id=str(ULID()),
        project_id=project_id,
        job_type="thumbnail_generation",
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()

    await submit_job(job.id, _generate_thumbnail, job.id, project_id, body.prompt, body.style)
    return job


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
