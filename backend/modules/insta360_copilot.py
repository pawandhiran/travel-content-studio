"""Insta360-specific footage analysis and editing recommendations."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Content, ContentType, Video
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()

_FOOTAGE_TYPES = ("hyperlapse", "timelapse", "walking", "selfie", "panorama", "scenic")

_SYSTEM_PROMPT = (
    "You are an expert Insta360 video editor. Analyze the footage metadata and "
    "provide specific editing recommendations for Insta360 Studio or the Insta360 app. "
    "Consider reframe keyframes, stabilization, aspect ratio, speed ramps, and effects."
)


async def analyze_insta360(db: AsyncSession, video_id: str) -> dict:
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")

    if video.camera_type != "insta360":
        raise ProcessingError(f"Video {video_id} is not Insta360 footage (detected: {video.camera_type})")

    metadata = json.loads(video.metadata_json or "{}")
    footage_type = _detect_footage_type(metadata, video)

    prompt = (
        f"Analyze this Insta360 footage and provide editing recommendations.\n\n"
        f"Footage type: {footage_type}\n"
        f"Resolution: {video.width}x{video.height}\n"
        f"Duration: {video.duration_ms / 1000:.1f}s\n"
        f"FPS: {video.fps}\n"
        f"Codec: {video.codec}\n"
        f"Metadata: {json.dumps(metadata, indent=2)[:2000]}\n\n"
        f"Provide:\n"
        f"1. Detected footage type and confidence\n"
        f"2. Recommended export settings (resolution, framerate, stabilization)\n"
        f"3. Suggested reframe keyframe strategy\n"
        f"4. Speed ramp suggestions if applicable\n"
        f"5. Best aspect ratio for social media platforms\n"
    )

    try:
        response = await _ollama.generate(
            model="llama3.2",
            prompt=prompt,
            system=_SYSTEM_PROMPT,
        )
    except Exception as exc:
        raise ProcessingError(f"Insta360 analysis failed: {exc}") from exc

    result = {
        "video_id": video_id,
        "footage_type": footage_type,
        "recommendations": response,
        "metadata_summary": {
            "resolution": f"{video.width}x{video.height}",
            "duration_s": video.duration_ms / 1000,
            "fps": video.fps,
        },
    }

    content = Content(
        id=str(ULID()),
        project_id=video.project_id,
        content_type=ContentType.script,
        title=f"Insta360 Analysis: {video.filename}",
        body=response,
        metadata_json=json.dumps({"footage_type": footage_type, "video_id": video_id}),
        version=1,
    )
    db.add(content)
    await db.commit()

    log.info("insta360_analyzed", video_id=video_id, footage_type=footage_type)
    return result


async def get_recommendations(db: AsyncSession, video_id: str) -> Content:
    result = await db.execute(
        select(Content).where(
            Content.metadata_json.contains(video_id),
            Content.title.like("Insta360 Analysis%"),
        ).order_by(Content.created_at.desc())
    )
    content = result.scalar_one_or_none()
    if not content:
        raise NotFoundError(f"No Insta360 recommendations found for video {video_id}")
    return content


def _detect_footage_type(metadata: dict, video: Video) -> str:
    """Heuristic detection of Insta360 footage type."""
    duration_s = video.duration_ms / 1000

    if video.fps >= 100:
        return "hyperlapse"
    if duration_s > 60 and video.fps <= 5:
        return "timelapse"
    if video.width == video.height or (video.width > 4000 and video.height > 4000):
        return "panorama"

    raw = json.dumps(metadata).lower()
    if "selfie" in raw or "front" in raw:
        return "selfie"
    if "walk" in raw or "stabiliz" in raw:
        return "walking"

    return "scenic"
