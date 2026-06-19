"""Scene analysis endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Highlight, Scene, Video
from models.schemas import HighlightResponse, JobResponse, SceneResponse

router = APIRouter(tags=["scenes"])


@router.post("/videos/{video_id}/analyze-scenes", response_model=JobResponse)
async def start_scene_analysis(video_id: str, db: AsyncSession = Depends(get_db)):
    """Queue a scene analysis job for the given video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    project_id = video.project_id

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from core.event_bus import event_bus
        from modules.scene_analysis import analyze_scenes

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting scene analysis")
            scenes = await analyze_scenes(session, video_id, event_bus)
            await session.commit()
            await update_progress(100, "Scene analysis complete")
            return {"video_id": video_id, "scenes_detected": len(scenes)}

    job_id = await task_queue.submit("scene_analysis", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "scene_analysis", "status": "pending"}


@router.get("/videos/{video_id}/scenes", response_model=list[SceneResponse])
async def list_scenes(video_id: str, db: AsyncSession = Depends(get_db)):
    """List detected scenes for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    result = await db.execute(
        select(Scene).where(Scene.video_id == video_id).order_by(Scene.start_ms)
    )
    return result.scalars().all()


@router.get("/videos/{video_id}/highlights", response_model=list[HighlightResponse])
async def list_highlights(video_id: str, db: AsyncSession = Depends(get_db)):
    """List detected highlights for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    result = await db.execute(
        select(Highlight).where(Highlight.video_id == video_id).order_by(Highlight.score.desc())
    )
    return result.scalars().all()
