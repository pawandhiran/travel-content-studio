"""API router aggregator for Travel Content Studio."""

from fastapi import APIRouter

from .agents import router as agents_router
from .blog import router as blog_router
from .content import router as content_router
from .insta360 import router as insta360_router
from .jobs import router as jobs_router
from .projects import router as projects_router
from .reels import router as reels_router
from .scenes import router as scenes_router
from .system import router as system_router
from .thumbnails import router as thumbnails_router
from .transcription import router as transcription_router
from .videos import router as videos_router
from .voiceover import router as voiceover_router
from .stock_photos import router as stock_photos_router
from .chat import router as chat_router
from .feedback import router as feedback_router
from .logs import router as logs_router
from .video_editing import router as video_editing_router
from .youtube import router as youtube_router


def create_api_router() -> APIRouter:
    """Create the top-level API router with all sub-routers mounted."""
    api = APIRouter(prefix="/api/v1")

    api.include_router(system_router)
    api.include_router(projects_router)
    api.include_router(videos_router)
    api.include_router(transcription_router)
    api.include_router(scenes_router)
    api.include_router(content_router)
    api.include_router(thumbnails_router)
    api.include_router(voiceover_router)
    api.include_router(blog_router)
    api.include_router(reels_router)
    api.include_router(youtube_router)
    api.include_router(insta360_router)
    api.include_router(agents_router)
    api.include_router(jobs_router)
    api.include_router(video_editing_router)
    api.include_router(stock_photos_router)
    api.include_router(feedback_router)
    api.include_router(logs_router)
    api.include_router(chat_router)

    return api
