"""Transcription endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Transcript, Video
from models.schemas import JobResponse, TranscriptResponse, TranscriptUpdate

router = APIRouter(tags=["transcription"])


@router.post("/videos/{video_id}/transcribe", response_model=JobResponse)
async def start_transcription(video_id: str, db: AsyncSession = Depends(get_db)):
    """Queue a transcription job for the given video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    project_id = video.project_id

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from core.event_bus import event_bus
        from modules.transcription import transcribe_video

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting transcription")
            result = await transcribe_video(session, video_id, event_bus)
            await session.commit()
            await update_progress(100, "Transcription complete")
            return {"transcript_id": result.id, "video_id": video_id}

    job_id = await task_queue.submit("transcription", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "transcription", "status": "pending"}


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(video_id: str, db: AsyncSession = Depends(get_db)):
    """Get the transcript for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    if not video.transcript:
        raise NotFoundError(f"Transcript not found for video {video_id}")
    return video.transcript


@router.put("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def update_transcript(
    video_id: str,
    body: TranscriptUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Manually edit an existing transcript."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    if not video.transcript:
        raise NotFoundError(f"Transcript not found for video {video_id}")

    transcript = video.transcript
    if body.full_text is not None:
        transcript.full_text = body.full_text
    if body.segments_json is not None:
        transcript.segments_json = body.segments_json
    if body.speakers_json is not None:
        transcript.speakers_json = body.speakers_json

    await db.flush()
    return transcript


@router.get("/videos/{video_id}/subtitles")
async def get_subtitles(
    video_id: str,
    format: str = Query("srt", pattern="^(srt|vtt)$"),
    db: AsyncSession = Depends(get_db),
):
    """Return subtitles in SRT or VTT format."""
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    if not video.transcript:
        raise NotFoundError(f"Transcript not found for video {video_id}")

    transcript = video.transcript
    if format == "srt" and transcript.srt_path:
        from pathlib import Path

        content = Path(transcript.srt_path).read_text()
        return PlainTextResponse(content, media_type="text/plain")
    elif format == "vtt" and transcript.vtt_path:
        from pathlib import Path

        content = Path(transcript.vtt_path).read_text()
        return PlainTextResponse(content, media_type="text/vtt")

    return PlainTextResponse(
        transcript.full_text,
        media_type="text/plain",
    )
