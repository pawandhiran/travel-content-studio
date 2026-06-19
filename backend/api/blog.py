"""Blog studio endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Blog, Project, ProjectStatus
from models.schemas import BlogGenerateRequest, BlogResponse, JobResponse

router = APIRouter(tags=["blog"])


@router.post("/projects/{project_id}/blog", response_model=JobResponse)
async def generate_blog(
    project_id: str,
    body: BlogGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue blog generation for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    blog_type = body.blog_type
    context = body.context

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.blog_studio import generate_blog as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting blog generation")
            result = await do_generate(session, project_id, blog_type, context={"text": context} if context else None)
            await session.commit()
            await update_progress(100, "Blog generation complete")
            return {"blog_id": result.id, "title": result.title}

    job_id = await task_queue.submit("blog_generation", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "blog_generation", "status": "pending"}


@router.get("/projects/{project_id}/blogs", response_model=list[BlogResponse])
async def list_blogs(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all generated blogs for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Blog).where(Blog.project_id == project_id).order_by(Blog.created_at.desc())
    )
    return result.scalars().all()


@router.get("/blogs/{blog_id}/export")
async def export_blog(
    blog_id: str,
    format: str = Query("md", pattern="^(md|html|docx)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export a blog in Markdown, HTML, or DOCX format."""
    blog = await db.get(Blog, blog_id)
    if not blog:
        raise NotFoundError(f"Blog {blog_id} not found")

    if format == "md":
        content = f"# {blog.title}\n\n{blog.body}"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{blog.title}.md"'},
        )
    elif format == "html":
        content = f"<html><body><h1>{blog.title}</h1><div>{blog.body}</div></body></html>"
        return Response(
            content=content,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{blog.title}.html"'},
        )
    else:
        # DOCX generation would use python-docx in production
        content = f"{blog.title}\n\n{blog.body}"
        return Response(
            content=content.encode(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{blog.title}.docx"'},
        )
