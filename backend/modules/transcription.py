"""Video transcription via Whisper with subtitle export."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.event_bus import EventBus
from core.logging_config import get_logger
from models.db_models import Transcript, Video
from services.ffmpeg_service import extract_audio

log = get_logger(__name__)


async def transcribe_video(
    db: AsyncSession,
    video_id: str,
    event_bus: EventBus,
) -> Transcript:
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    await event_bus.broadcast("transcription_progress", {"video_id": video_id, "progress": 0})

    video_dir = Path(video.file_path).parent
    audio_path = video_dir / f"{video_id}_audio.wav"

    try:
        await extract_audio(video.file_path, str(audio_path))
    except Exception as exc:
        raise ProcessingError(f"Audio extraction failed: {exc}") from exc

    await event_bus.broadcast("transcription_progress", {"video_id": video_id, "progress": 20})

    try:
        import whisper

        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path))
    except ImportError:
        raise ProcessingError("Whisper is not installed. Install with: pip install openai-whisper")
    except Exception as exc:
        raise ProcessingError(f"Transcription failed: {exc}") from exc

    await event_bus.broadcast("transcription_progress", {"video_id": video_id, "progress": 80})

    segments = result.get("segments", [])
    full_text = result.get("text", "")
    language = result.get("language", "en")

    srt_content = _segments_to_srt(segments)
    vtt_content = _segments_to_vtt(segments)

    srt_path = video_dir / f"{video_id}.srt"
    vtt_path = video_dir / f"{video_id}.vtt"
    srt_path.write_text(srt_content, encoding="utf-8")
    vtt_path.write_text(vtt_content, encoding="utf-8")

    existing = await db.execute(
        select(Transcript).where(Transcript.video_id == video_id)
    )
    old_transcript = existing.scalar_one_or_none()
    if old_transcript:
        await db.delete(old_transcript)

    transcript = Transcript(
        id=str(ULID()),
        video_id=video_id,
        language=language,
        full_text=full_text,
        segments_json=json.dumps(segments),
        srt_path=str(srt_path),
        vtt_path=str(vtt_path),
    )
    db.add(transcript)
    await db.commit()
    await db.refresh(transcript)

    await event_bus.broadcast("transcription_progress", {"video_id": video_id, "progress": 100})
    log.info("transcription_complete", video_id=video_id, language=language)
    return transcript


async def get_transcript(db: AsyncSession, video_id: str) -> Transcript:
    result = await db.execute(
        select(Transcript).where(Transcript.video_id == video_id)
    )
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise NotFoundError(f"Transcript for video {video_id} not found")
    return transcript


async def update_transcript(
    db: AsyncSession,
    video_id: str,
    updates: dict,
) -> Transcript:
    transcript = await get_transcript(db, video_id)

    for key, value in updates.items():
        if hasattr(transcript, key) and key not in ("id", "video_id", "created_at"):
            setattr(transcript, key, value)

    await db.commit()
    await db.refresh(transcript)
    log.info("transcript_updated", video_id=video_id)
    return transcript


async def export_subtitles(db: AsyncSession, video_id: str, format: str) -> str:
    transcript = await get_transcript(db, video_id)
    segments = json.loads(transcript.segments_json)

    if format == "srt":
        return _segments_to_srt(segments)
    elif format == "vtt":
        return _segments_to_vtt(segments)
    elif format == "txt":
        return transcript.full_text
    else:
        raise ProcessingError(f"Unsupported subtitle format: {format}")


def _segments_to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg.get("start", 0))
        end = _format_timestamp_srt(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _segments_to_vtt(segments: list[dict]) -> str:
    lines: list[str] = ["WEBVTT\n"]
    for seg in segments:
        start = _format_timestamp_vtt(seg.get("start", 0))
        end = _format_timestamp_vtt(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _format_timestamp_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
