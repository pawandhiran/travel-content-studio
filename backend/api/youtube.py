"""YouTube copilot endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Content, ContentType, Job, JobStatus, Project, ProjectStatus
from models.schemas import ContentListResponse, JobResponse
from services.task_queue import submit_job

router = APIRouter(tags=["youtube"])

_YOUTUBE_CONTENT_TYPES = [
    ContentType.title,
    ContentType.hook,
    ContentType.script,
    ContentType.chapter_markers,
    ContentType.hashtags,
    ContentType.seo_description,
    ContentType.seo_keywords,
]


async def _generate_youtube_content(job_id: str, project_id: str):
    """Background task: generate YouTube-optimized content package."""
    pass


@router.post("/projects/{project_id}/youtube", response_model=JobResponse)
async def generate_youtube_content(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Queue YouTube content generation (titles, hooks, chapters, SEO, etc.)."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    job = Job(
        id=str(ULID()),
        project_id=project_id,
        job_type="youtube_content",
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()

    await submit_job(job.id, _generate_youtube_content, job.id, project_id)
    return job


@router.get("/projects/{project_id}/youtube", response_model=ContentListResponse)
async def list_youtube_content(project_id: str, db: AsyncSession = Depends(get_db)):
    """List YouTube-related content for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Content)
        .where(Content.project_id == project_id)
        .where(Content.content_type.in_(_YOUTUBE_CONTENT_TYPES))
    )
    contents = result.scalars().all()
    return ContentListResponse(contents=contents, total=len(contents))
