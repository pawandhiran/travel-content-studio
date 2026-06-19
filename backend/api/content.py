"""AI content generation endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Content, Project, ProjectStatus
from models.schemas import (
    ContentGenerateRequest,
    ContentListResponse,
    ContentResponse,
    JobResponse,
)

router = APIRouter(tags=["content"])


@router.post("/projects/{project_id}/generate", response_model=JobResponse)
async def generate_content(
    project_id: str,
    body: ContentGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue AI content generation for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    content_type = body.content_type
    prompt = body.prompt or None
    parameters = body.parameters

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.content_engine import generate_content as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting content generation")
            result = await do_generate(
                session, project_id, content_type, prompt=prompt, parameters=parameters
            )
            await session.commit()
            await update_progress(100, "Content generation complete")
            return {"content_id": result.id, "content_type": content_type}

    job_id = await task_queue.submit("content_generation", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "content_generation", "status": "pending"}


@router.get("/projects/{project_id}/content", response_model=ContentListResponse)
async def list_content(
    project_id: str,
    content_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List generated content for a project, optionally filtered by type."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    query = select(Content).where(Content.project_id == project_id)
    if content_type:
        query = query.where(Content.content_type == content_type)

    result = await db.execute(query)
    contents = result.scalars().all()
    return ContentListResponse(contents=contents, total=len(contents))


@router.get("/content/{content_id}", response_model=ContentResponse)
async def get_content(content_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single content item by ID."""
    content = await db.get(Content, content_id)
    if not content:
        raise NotFoundError(f"Content {content_id} not found")
    return content


@router.put("/content/{content_id}", response_model=ContentResponse)
async def update_content(
    content_id: str,
    body: ContentGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually edit a content item."""
    content = await db.get(Content, content_id)
    if not content:
        raise NotFoundError(f"Content {content_id} not found")

    if body.context:
        content.body = body.context
    content.version += 1
    await db.flush()
    return content


@router.post("/content/{content_id}/regenerate", response_model=JobResponse)
async def regenerate_content(content_id: str, db: AsyncSession = Depends(get_db)):
    """Queue regeneration of an existing content item."""
    content = await db.get(Content, content_id)
    if not content:
        raise NotFoundError(f"Content {content_id} not found")

    regen_project_id = content.project_id
    regen_content_type = content.content_type.value

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.content_engine import generate_content as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting content regeneration")
            result = await do_generate(session, regen_project_id, regen_content_type)
            await session.commit()
            await update_progress(100, "Regeneration complete")
            return {"content_id": result.id, "content_type": regen_content_type}

    job_id = await task_queue.submit("content_regeneration", regen_project_id, _run)
    return {"id": job_id, "project_id": regen_project_id, "job_type": "content_regeneration", "status": "pending"}
