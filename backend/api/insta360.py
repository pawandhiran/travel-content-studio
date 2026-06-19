"""Insta360 copilot endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Content, ContentType, Job, JobStatus, Video
from models.schemas import ContentResponse, JobResponse
from services.task_queue import submit_job

router = APIRouter(tags=["insta360"])


async def _analyze_insta360(job_id: str, video_id: str):
    """Background task: analyze 360 video and generate edit recommendations."""
    pass


@router.post("/videos/{video_id}/insta360-analyze", response_model=JobResponse)
async def analyze_insta360(video_id: str, db: AsyncSession = Depends(get_db)):
    """Queue Insta360 video analysis for keyframe and edit recommendations."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    job = Job(
        id=str(ULID()),
        project_id=video.project_id,
        job_type="insta360_analysis",
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()

    await submit_job(job.id, _analyze_insta360, job.id, video_id)
    return job


@router.get("/videos/{video_id}/insta360-recommendations", response_model=ContentResponse)
async def get_insta360_recommendations(video_id: str, db: AsyncSession = Depends(get_db)):
    """Get Insta360 edit recommendations for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    result = await db.execute(
        select(Content)
        .where(Content.project_id == video.project_id)
        .where(Content.content_type == ContentType.guide)
        .order_by(Content.created_at.desc())
        .limit(1)
    )
    content = result.scalar_one_or_none()
    if not content:
        raise NotFoundError(f"No Insta360 recommendations found for video {video_id}")
    return content
