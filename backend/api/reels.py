"""Reel generator endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Project, ProjectStatus, Reel
from models.schemas import JobResponse, ReelGenerateRequest, ReelResponse

router = APIRouter(tags=["reels"])


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

    duration_type = body.duration_type
    context = body.context

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.reel_generator import generate_reel as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting reel generation")
            result = await do_generate(session, project_id, duration_type, context)
            await session.commit()
            await update_progress(100, "Reel generation complete")
            return {"id": result.id}

    job_id = await task_queue.submit("reel_generation", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "reel_generation", "status": "pending"}


@router.get("/reels/jobs/{job_id}")
async def get_reel_job_status(job_id: str):
    """Get status of a reel job from the in-memory task queue."""
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
