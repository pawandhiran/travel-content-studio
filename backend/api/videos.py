"""Video management endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError, ProcessingError, ValidationError
from models.db_models import Project, ProjectStatus, Video
from models.schemas import VideoListResponse, VideoResponse
from modules import video_ingest

router = APIRouter(tags=["videos"])


class VideoImportRequest(BaseModel):
    file_path: str


async def _extract_metadata(file_path: Path) -> dict:
    """Extract real metadata from video file via ffprobe."""
    from services.ffmpeg_service import get_video_metadata

    try:
        return await get_video_metadata(str(file_path))
    except Exception as exc:
        raise ProcessingError(
            f"Failed to extract metadata from {file_path.name}: {exc}"
        ) from exc


@router.post(
    "/projects/{project_id}/videos",
    response_model=VideoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    project_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Upload a video file to a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    video_id = str(ULID())
    project_folder = Path(project.folder_path)
    videos_dir = project_folder / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    dest = videos_dir / f"{video_id}_{file.filename}"
    content = await file.read()
    dest.write_bytes(content)

    meta = await _extract_metadata(dest)

    video = Video(
        id=video_id,
        project_id=project_id,
        filename=file.filename or "unknown",
        file_path=str(dest),
        format=meta["format"],
        duration_ms=meta["duration_ms"],
        width=meta["width"],
        height=meta["height"],
        fps=meta["fps"],
        codec=meta["codec"],
        metadata_json=json.dumps(meta),
    )
    db.add(video)
    await db.flush()
    return video


@router.post(
    "/projects/{project_id}/videos/import",
    response_model=VideoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_video_by_path(
    project_id: str,
    body: VideoImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import a video from a local file path (Electron desktop use case)."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    video = await video_ingest.import_video(db, project_id, body.file_path)
    return video


@router.get("/projects/{project_id}/videos", response_model=VideoListResponse)
async def list_videos(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all videos belonging to a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(select(Video).where(Video.project_id == project_id))
    videos = result.scalars().all()
    return VideoListResponse(videos=videos, total=len(videos))


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single video by ID."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    return video


@router.get("/videos/{video_id}/proxy")
async def stream_proxy(video_id: str, db: AsyncSession = Depends(get_db)):
    """Stream the proxy file for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    proxy_path = Path(video.proxy_path) if video.proxy_path else None
    if not proxy_path or not proxy_path.exists():
        raise NotFoundError("Proxy file not available")

    def iterfile():
        with open(proxy_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(iterfile(), media_type="video/mp4")


@router.get("/videos/{video_id}/thumbnail")
async def get_thumbnail(video_id: str, db: AsyncSession = Depends(get_db)):
    """Return the thumbnail image for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    thumb_path = Path(video.thumbnail_path) if video.thumbnail_path else None
    if not thumb_path or not thumb_path.exists():
        raise NotFoundError("Thumbnail not available")

    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a video and its files (source, proxy, thumbnail) from disk."""
    await video_ingest.delete_video(db, video_id)
