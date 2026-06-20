"""Video editing API endpoints -- ported from media-pipeline."""

import asyncio
from typing import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Video

router = APIRouter(prefix="/video-editing", tags=["video-editing"])


def _adapt_progress(update_progress: Callable):
    """Adapt task_queue's (int, str) callback to what media-pipeline modules expect.

    Modules from media-pipeline call progress_callback(dict) or
    progress_callback(float, str). This adapter normalizes both to
    the task_queue's await update_progress(int, str) format.
    """

    async def _callback(*args):
        if len(args) == 1 and isinstance(args[0], dict):
            pct = int(args[0].get("progress", 0) * 100) if isinstance(args[0].get("progress"), float) else args[0].get("progress", 0)
            msg = args[0].get("step", "")
            await update_progress(pct, msg)
        elif len(args) == 2:
            pct = int(args[0] * 100) if isinstance(args[0], float) and args[0] <= 1.0 else int(args[0])
            await update_progress(pct, str(args[1]))
        elif len(args) == 1:
            pct = int(args[0] * 100) if isinstance(args[0], float) and args[0] <= 1.0 else int(args[0])
            await update_progress(pct, "")

    return _callback


async def _get_video_path(db: AsyncSession, video_id: str) -> str:
    video = await db.get(Video, video_id)
    if not video:
        raise NotFoundError(f"Video {video_id} not found")
    return video.file_path


@router.post("/smart-stitch")
async def smart_stitch(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Intelligently stitch multiple clips into a cohesive reel."""
    video_ids = body.get("video_ids", [])
    duration = body.get("duration", 30)
    transition = body.get("transition", "mixed")
    aspect = body.get("aspect", "9:16")
    music_path = body.get("music_path")

    video_paths = []
    for vid in video_ids:
        video_paths.append(await _get_video_path(db, vid))

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.smart_stitch import smart_stitch as do_stitch
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"stitched_{job_id}.mp4"
        result = await do_stitch(
            [Path(p) for p in video_paths],
            output,
            duration=duration,
            transition=transition,
            aspect=aspect,
            music_path=Path(music_path) if music_path else None,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("smart_stitch", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/color-grade")
async def color_grade(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Apply cinematic color grading to a video."""
    video_path = await _get_video_path(db, body["video_id"])
    preset = body.get("preset", "cinematic")
    vignette = body.get("vignette", 0)
    grain = body.get("grain", 0)

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.color_grade import apply_color_grade
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"graded_{job_id}.mp4"
        result = await apply_color_grade(
            Path(video_path), output, preset=preset,
            vignette=vignette, grain=grain,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("color_grade", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/audio-enhance")
async def audio_enhance(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Enhance audio with loudness normalization, noise reduction, and optional music."""
    video_path = await _get_video_path(db, body["video_id"])
    preset = body.get("preset", "youtube")
    add_music_path = body.get("add_music_path")
    music_volume = body.get("music_volume", 0.15)

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.audio_enhance import enhance_audio
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"enhanced_{job_id}.mp4"
        result = await enhance_audio(
            Path(video_path), output, preset=preset,
            add_music_path=Path(add_music_path) if add_music_path else None,
            music_volume=music_volume,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("audio_enhance", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/animated-captions")
async def animated_captions(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Add TikTok-style animated captions to a video."""
    video_id = body["video_id"]
    video_path = await _get_video_path(db, video_id)
    style = body.get("style", "modern")
    animation = body.get("animation", "pop")

    async def _run(job_id, update_progress):
        import json
        from pathlib import Path

        from sqlalchemy import select

        from config import get_settings
        from core.database import AsyncSessionLocal
        from models.db_models import Transcript
        from modules.animated_captions import add_animated_captions

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transcript).where(Transcript.video_id == video_id)
            )
            transcript = result.scalar_one_or_none()
            segments = []
            if transcript and transcript.segments_json:
                segments = json.loads(transcript.segments_json)

        settings = get_settings()
        output = Path(settings.projects_dir) / f"captioned_{job_id}.mp4"
        await update_progress(10, "Loading video")
        result = await add_animated_captions(
            Path(video_path), output, style=style, animation=animation,
            transcript_segments=segments,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("animated_captions", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/speed-ramp")
async def speed_ramp(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Apply speed changes, slow-mo, or timelapse effects."""
    video_path = await _get_video_path(db, body["video_id"])

    async def _run(job_id, update_progress):
        from pathlib import Path
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"speed_{job_id}.mp4"

        if body.get("timelapse_factor"):
            from modules.speed_ramp import create_timelapse
            result = await create_timelapse(
                Path(video_path), output,
                speed_factor=body["timelapse_factor"],
                progress_callback=_adapt_progress(update_progress),
            )
        elif body.get("slow_mo_start") is not None:
            from modules.speed_ramp import create_slow_motion
            result = await create_slow_motion(
                Path(video_path), output,
                start_s=body["slow_mo_start"],
                end_s=body["slow_mo_end"],
                factor=body.get("slow_mo_factor", 0.25),
                progress_callback=_adapt_progress(update_progress),
            )
        elif body.get("target_duration"):
            from modules.speed_ramp import fit_to_duration
            result = await fit_to_duration(
                Path(video_path), output,
                target_duration=body["target_duration"],
                progress_callback=_adapt_progress(update_progress),
            )
        else:
            from modules.speed_ramp import apply_speed_change
            result = await apply_speed_change(
                Path(video_path), output,
                speed=body.get("speed", 1.5),
                progress_callback=_adapt_progress(update_progress),
            )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("speed_ramp", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/auto-reframe")
async def auto_reframe(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Smart-crop video for a target aspect ratio with face detection."""
    video_path = await _get_video_path(db, body["video_id"])
    target_aspect = body.get("target_aspect", "9:16")

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.auto_reframe import reframe_video
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"reframed_{job_id}.mp4"
        result = await reframe_video(
            Path(video_path), output,
            target_aspect=target_aspect,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("auto_reframe", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/branding")
async def branding(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Add watermarks, end cards, subscribe buttons, and lower thirds."""
    video_path = await _get_video_path(db, body["video_id"])

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.branding import apply_full_branding
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"branded_{job_id}.mp4"
        result = await apply_full_branding(
            Path(video_path), output,
            watermark_path=Path(body["watermark_path"]) if body.get("watermark_path") else None,
            end_card=body.get("end_card", False),
            subscribe=body.get("subscribe", False),
            lower_third=body.get("lower_third"),
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("branding", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/hook-optimize")
async def hook_optimize(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Move the most engaging moment to the first 3 seconds."""
    video_path = await _get_video_path(db, body["video_id"])
    hook_duration = body.get("hook_duration", 3.0)

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.hook_optimizer import create_hooked_video
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"hooked_{job_id}.mp4"
        result = await create_hooked_video(
            Path(video_path), output,
            hook_duration=hook_duration,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("hook_optimize", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/music-reel")
async def music_reel(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Create a beat-synced music reel from multiple clips."""
    video_ids = body.get("video_ids", [])
    video_paths = []
    for vid in video_ids:
        video_paths.append(await _get_video_path(db, vid))

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.music_reels import create_music_reel
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"music_reel_{job_id}.mp4"
        result = await create_music_reel(
            [Path(p) for p in video_paths],
            output,
            music_path=Path(body["music_path"]) if body.get("music_path") else None,
            duration=body.get("duration", 30),
            transition=body.get("transition", "mixed"),
            effect=body.get("effect", "zoom_pulse"),
            aspect=body.get("aspect", "9:16"),
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("music_reel", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.post("/quality-check")
async def quality_check(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Run pre-publish quality check on a video."""
    video_path = await _get_video_path(db, body["video_id"])
    platform = body.get("platform")
    strict = body.get("strict", False)

    from pathlib import Path
    from modules.quality_check import run_quality_check

    report = await run_quality_check(Path(video_path), platform=platform, strict=strict)
    return report.to_dict() if hasattr(report, "to_dict") else report


@router.post("/smart-thumbnail")
async def smart_thumbnail(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Extract the best frame from video as a smart thumbnail."""
    video_path = await _get_video_path(db, body["video_id"])
    platform = body.get("platform", "youtube")
    text = body.get("text")

    async def _run(job_id, update_progress):
        from pathlib import Path
        from modules.smart_thumbnail import extract_smart_thumbnail
        from config import get_settings

        settings = get_settings()
        output = Path(settings.projects_dir) / f"thumb_{job_id}.jpg"
        result = await extract_smart_thumbnail(
            Path(video_path), output,
            platform=platform, text=text,
            progress_callback=_adapt_progress(update_progress),
        )
        return {"output_path": str(output), **result}

    job_id = await task_queue.submit("smart_thumbnail", None, _run)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_video_editing_job_status(job_id: str):
    """Get status of a video editing job from the in-memory task queue."""
    status = task_queue.get_status(job_id)
    if not status:
        return {"error": "Job not found", "status": "unknown"}
    return {
        "id": status["id"],
        "status": status["status"].value if hasattr(status["status"], "value") else str(status["status"]),
        "progress": status.get("progress", 0),
        "message": status.get("message", ""),
        "error": status.get("error"),
        "result": status.get("result"),
    }


@router.get("/presets")
async def get_presets():
    """List available presets for all video editing features."""
    return {
        "color_grade": ["cinematic", "vibrant", "moody", "warm_vintage", "cool_clean", "sunset_golden"],
        "audio_enhance": ["voice_over", "podcast", "vlog", "music_video", "instagram", "youtube"],
        "caption_style": ["modern", "bold", "minimal", "neon", "classic"],
        "caption_animation": ["pop", "fade", "bounce", "typewriter"],
        "transition": ["cut", "fade", "zoom", "slide", "mixed"],
        "beat_effect": ["zoom_pulse", "flash", "shake", "none"],
        "aspect_ratio": ["9:16", "16:9", "1:1", "4:5"],
        "qc_platform": ["youtube_shorts", "youtube_long", "instagram_reels", "instagram_stories", "tiktok"],
        "thumbnail_platform": ["youtube", "instagram_reel", "instagram_post", "tiktok"],
    }


@router.get("/trending-music")
async def get_trending_music(
    source: str = "local",
    limit: int = 20,
):
    """Fetch trending music from configured sources."""
    from services.trending_service import fetch_trending_music

    songs = await fetch_trending_music(sources=[source], limit=limit)
    return {"songs": songs, "source": source}


@router.get("/instagram-trends")
async def get_instagram_trends(
    content_type: str = None,
    mood: str = None,
    limit: int = 20,
):
    """Fetch Instagram trending reels and audio."""
    from services.trending_service import fetch_instagram_trends

    result = await fetch_instagram_trends(
        content_type=content_type, mood=mood, limit=limit
    )
    return result
