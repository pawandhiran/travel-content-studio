"""Voiceover studio endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Job, JobStatus, Project, ProjectStatus, Voiceover
from models.schemas import JobResponse, VoiceListResponse, VoiceoverGenerateRequest, VoiceoverResponse
from services.task_queue import submit_job

router = APIRouter(tags=["voiceover"])


AVAILABLE_VOICES = [
    {"id": "alloy", "name": "Alloy", "language": "en", "gender": "neutral"},
    {"id": "echo", "name": "Echo", "language": "en", "gender": "male"},
    {"id": "fable", "name": "Fable", "language": "en", "gender": "female"},
    {"id": "nova", "name": "Nova", "language": "en", "gender": "female"},
    {"id": "onyx", "name": "Onyx", "language": "en", "gender": "male"},
    {"id": "shimmer", "name": "Shimmer", "language": "en", "gender": "female"},
]


async def _generate_voiceover(job_id: str, project_id: str, script_text: str, voice_id: str):
    """Background task: generate voiceover audio via TTS engine."""
    pass


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

    job = Job(
        id=str(ULID()),
        project_id=project_id,
        job_type="voiceover_generation",
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()

    await submit_job(job.id, _generate_voiceover, job.id, project_id, body.script_text, body.voice_id)
    return job


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
