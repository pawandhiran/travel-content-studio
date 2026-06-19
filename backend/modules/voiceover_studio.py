"""Text-to-speech voiceover generation and voice management."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import AudioFormat, Project, Voiceover
from services.tts_service import TTSService, Voice

log = get_logger(__name__)


async def generate_voiceover(
    db: AsyncSession,
    project_id: str,
    script_text: str,
    voice_id: str,
) -> Voiceover:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    project_folder = Path(project.folder_path)
    voiceovers_dir = project_folder / "voiceovers"
    voiceovers_dir.mkdir(parents=True, exist_ok=True)

    voiceover_id = str(ULID())
    output_path = voiceovers_dir / f"{voiceover_id}.wav"

    tts = TTSService()
    try:
        result = await tts.generate_speech(
            text=script_text,
            voice_id=voice_id,
            output_path=str(output_path),
        )
    except Exception as exc:
        raise ProcessingError(f"Voiceover generation failed: {exc}") from exc

    voiceover = Voiceover(
        id=voiceover_id,
        project_id=project_id,
        script_text=script_text,
        voice_id=voice_id,
        audio_path=str(output_path),
        duration_ms=result.duration_ms,
        format=AudioFormat.wav,
    )
    db.add(voiceover)
    await db.commit()
    await db.refresh(voiceover)

    log.info("voiceover_generated", voiceover_id=voiceover_id, voice_id=voice_id)
    return voiceover


async def list_voiceovers(db: AsyncSession, project_id: str) -> list[Voiceover]:
    result = await db.execute(
        select(Voiceover)
        .where(Voiceover.project_id == project_id)
        .order_by(Voiceover.created_at.desc())
    )
    return list(result.scalars().all())


async def list_voices() -> list[Voice]:
    """Return available TTS voices."""
    tts = TTSService()
    try:
        return await tts.list_voices()
    except Exception as exc:
        raise ProcessingError(f"Failed to list voices: {exc}") from exc
