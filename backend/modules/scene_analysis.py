"""Scene detection, segmentation, and highlight identification."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.event_bus import EventBus
from core.logging_config import get_logger
from models.db_models import Highlight, Scene, Video
from services.ffmpeg_service import extract_thumbnail

log = get_logger(__name__)


async def analyze_scenes(
    db: AsyncSession,
    video_id: str,
    event_bus: EventBus,
) -> list[Scene]:
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        raise ProcessingError(
            "PySceneDetect is not installed. Install with: pip install scenedetect[opencv]"
        )

    await event_bus.broadcast("scene_analysis_progress", {"video_id": video_id, "progress": 0})

    try:
        sv = open_video(video.file_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(sv)
        scene_list = scene_manager.get_scene_list()
    except Exception as exc:
        raise ProcessingError(f"Scene detection failed: {exc}") from exc

    await event_bus.broadcast("scene_analysis_progress", {"video_id": video_id, "progress": 60})

    video_dir = Path(video.file_path).parent
    scenes_dir = video_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)

    # Clear existing scenes for this video
    existing = await db.execute(select(Scene).where(Scene.video_id == video_id))
    for old_scene in existing.scalars().all():
        await db.delete(old_scene)

    scenes: list[Scene] = []
    for i, (start, end) in enumerate(scene_list):
        scene_id = str(ULID())
        start_ms = int(start.get_seconds() * 1000)
        end_ms = int(end.get_seconds() * 1000)

        mid_seconds = (start.get_seconds() + end.get_seconds()) / 2
        thumb_path = str(scenes_dir / f"scene_{i:04d}.jpg")
        try:
            await extract_thumbnail(video.file_path, thumb_path, time_s=mid_seconds)
        except Exception:
            thumb_path = None

        scene = Scene(
            id=scene_id,
            video_id=video_id,
            start_ms=start_ms,
            end_ms=end_ms,
            confidence=1.0,
            thumbnail_path=thumb_path,
        )
        db.add(scene)
        scenes.append(scene)

    # Identify highlights (long scenes or high-motion segments)
    existing_hl = await db.execute(select(Highlight).where(Highlight.video_id == video_id))
    for old_hl in existing_hl.scalars().all():
        await db.delete(old_hl)

    avg_duration = (
        sum((s.end_ms - s.start_ms) for s in scenes) / len(scenes) if scenes else 0
    )
    for scene in scenes:
        duration = scene.end_ms - scene.start_ms
        if duration > avg_duration * 1.5:
            highlight = Highlight(
                id=str(ULID()),
                video_id=video_id,
                start_ms=scene.start_ms,
                end_ms=scene.end_ms,
                highlight_type="scenic",
                description="Extended scene — likely scenic or important",
                score=min(duration / avg_duration, 3.0) if avg_duration > 0 else 1.0,
            )
            db.add(highlight)

    await db.commit()
    for scene in scenes:
        await db.refresh(scene)

    await event_bus.broadcast("scene_analysis_progress", {"video_id": video_id, "progress": 100})
    log.info("scene_analysis_complete", video_id=video_id, scene_count=len(scenes))
    return scenes


async def get_scenes(db: AsyncSession, video_id: str) -> list[Scene]:
    result = await db.execute(
        select(Scene).where(Scene.video_id == video_id).order_by(Scene.start_ms)
    )
    return list(result.scalars().all())


async def get_highlights(db: AsyncSession, video_id: str) -> list[Highlight]:
    result = await db.execute(
        select(Highlight).where(Highlight.video_id == video_id).order_by(Highlight.score.desc())
    )
    return list(result.scalars().all())
