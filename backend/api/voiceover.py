"""Voiceover studio endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Project, ProjectStatus, Voiceover
from models.schemas import JobResponse, VoiceListResponse, VoiceoverGenerateRequest, VoiceoverResponse

router = APIRouter(tags=["voiceover"])


AVAILABLE_VOICES = [
    {"id": "alloy", "name": "Alloy", "language": "en", "gender": "neutral"},
    {"id": "echo", "name": "Echo", "language": "en", "gender": "male"},
    {"id": "fable", "name": "Fable", "language": "en", "gender": "female"},
    {"id": "nova", "name": "Nova", "language": "en", "gender": "female"},
    {"id": "onyx", "name": "Onyx", "language": "en", "gender": "male"},
    {"id": "shimmer", "name": "Shimmer", "language": "en", "gender": "female"},
]


@router.get("/voiceover/jobs/{job_id}")
async def get_voiceover_job_status(job_id: str):
    """Get status of a voiceover job from the in-memory task queue."""
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


@router.get("/voiceover/voices", response_model=VoiceListResponse)
async def list_voices():
    """List available TTS voices."""
    return VoiceListResponse(voices=AVAILABLE_VOICES)


@router.post("/projects/{project_id}/voiceover", response_model=JobResponse)
async def generate_voiceover(
    project_id: str,
    body: VoiceoverGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue voiceover generation for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    script_text = body.script_text
    voice_id = body.voice_id

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from modules.voiceover_studio import generate_voiceover as do_generate

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting voiceover generation")
            result = await do_generate(session, project_id, script_text, voice_id)
            await session.commit()
            await update_progress(100, "Voiceover generation complete")
            return {"id": result.id}

    job_id = await task_queue.submit("voiceover_generation", project_id, _run)
    return {"id": job_id, "project_id": project_id, "job_type": "voiceover_generation", "status": "pending"}


@router.get("/projects/{project_id}/voiceovers", response_model=list[VoiceoverResponse])
async def list_voiceovers(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all generated voiceovers for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Voiceover).where(Voiceover.project_id == project_id).order_by(Voiceover.created_at.desc())
    )
    return result.scalars().all()


@router.get("/voiceovers/{voiceover_id}/audio")
async def get_voiceover_audio(voiceover_id: str, db: AsyncSession = Depends(get_db)):
    """Return the generated voiceover audio file."""
    voiceover = await db.get(Voiceover, voiceover_id)
    if not voiceover:
        raise NotFoundError(f"Voiceover {voiceover_id} not found")

    audio_path = Path(voiceover.audio_path)
    if not audio_path.exists():
        raise NotFoundError("Voiceover audio file not found on disk")

    media_type = "audio/wav" if voiceover.format.value == "wav" else "audio/mpeg"
    return FileResponse(str(audio_path), media_type=media_type)
