"""Video import, metadata extraction, and lifecycle management."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from config import get_settings
from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Project, Video
from services.ffmpeg_service import (
    extract_thumbnail,
    generate_proxy,
    get_video_metadata,
)

log = get_logger(__name__)


async def import_video(
    db: AsyncSession,
    project_id: str,
    file_path: str | Path,
) -> Video:
    file_path = Path(file_path)
    if not file_path.exists():
        raise NotFoundError(f"Video file not found: {file_path}")

    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    project_folder = Path(project.folder_path)
    videos_dir = project_folder / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    video_id = str(ULID())
    dest_path = videos_dir / f"{video_id}_{file_path.name}"

    shutil.copy2(file_path, dest_path)
    log.info("video_file_copied", video_id=video_id, dest=str(dest_path))

    try:
        metadata = await get_video_metadata(str(dest_path))
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise ProcessingError(f"Failed to extract video metadata: {exc}") from exc

    proxy_path = await generate_proxy(str(dest_path), str(videos_dir / f"{video_id}_proxy.mp4"))
    thumb_path = await extract_thumbnail(str(dest_path), str(videos_dir / f"{video_id}_thumb.jpg"))

    camera_type = _detect_camera_type(metadata)

    video = Video(
        id=video_id,
        project_id=project_id,
        filename=file_path.name,
        file_path=str(dest_path),
        proxy_path=proxy_path,
        thumbnail_path=thumb_path,
        format=metadata.get("format", file_path.suffix.lstrip(".")),
        duration_ms=int(metadata.get("duration_ms", 0)),
        width=int(metadata.get("width", 0)),
        height=int(metadata.get("height", 0)),
        fps=float(metadata.get("fps", 0)),
        codec=metadata.get("codec", "unknown"),
        camera_type=camera_type,
        metadata_json=json.dumps(metadata),
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    log.info("video_imported", video_id=video_id, project_id=project_id, camera=camera_type)
    return video


async def list_videos(db: AsyncSession, project_id: str) -> list[Video]:
    stmt = select(Video).where(Video.project_id == project_id).order_by(Video.imported_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_video(db: AsyncSession, video_id: str) -> Video:
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    return video


async def delete_video(db: AsyncSession, video_id: str) -> None:
    video = await get_video(db, video_id)

    for path_attr in ("file_path", "proxy_path", "thumbnail_path"):
        path_str = getattr(video, path_attr, None)
        if path_str:
            Path(path_str).unlink(missing_ok=True)

    await db.delete(video)
    await db.commit()
    log.info("video_deleted", video_id=video_id)


def _detect_camera_type(metadata: dict) -> str:
    """Detect camera type from video metadata tags."""
    raw = json.dumps(metadata).lower()

    if "insta360" in raw or "insv" in raw:
        return "insta360"
    if "dji" in raw or "djig" in raw:
        return "dji"
    if "gopro" in raw or "gpmf" in raw:
        return "gopro"
    return "generic"
