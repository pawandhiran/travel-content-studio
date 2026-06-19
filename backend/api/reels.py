"""Reel generator endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Job, JobStatus, Project, ProjectStatus, Reel
from models.schemas import JobResponse, ReelGenerateRequest, ReelResponse
from services.task_queue import submit_job

router = APIRouter(tags=["reels"])


async def _generate_reel(job_id: str, project_id: str, duration_type: str, context: str):
    """Background task: generate reel script, hooks, and shot list."""
    pass


@router.post("/projects/{project_id}/reels", response_model=JobResponse)
async def generate_reel(
    project_id: str,
    body: ReelGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue reel generation for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    job = Job(
        id=str(ULID()),
        project_id=project_id,
        job_type="reel_generation",
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()

    await submit_job(job.id, _generate_reel, job.id, project_id, body.duration_type, body.context)
    return job


@router.get("/projects/{project_id}/reels", response_model=list[ReelResponse])
async def list_reels(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all generated reels for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Reel).where(Reel.project_id == project_id).order_by(Reel.created_at.desc())
    )
    return result.scalars().all()
