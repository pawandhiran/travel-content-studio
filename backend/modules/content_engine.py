"""AI content generation engine with Ollama and Jinja2 prompt templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from config import get_settings
from core.errors import NotFoundError, ProcessingError
from core.feedback_engine import feedback_engine
from core.logging_config import get_logger
from core.model_router import model_router
from models.db_models import Content, ContentType, ContentVersion, Project, Transcript, Video
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()


async def generate_content(
    db: AsyncSession,
    project_id: str,
    content_type: str,
    prompt: str | None = None,
    parameters: dict | None = None,
) -> Content:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    context = await _get_project_context(db, project_id)
    parameters = parameters or {}

    if prompt:
        full_prompt = prompt
    else:
        full_prompt = _build_prompt(content_type, context)

    style_injection = feedback_engine.get_style_prompt_injection()
    if style_injection:
        full_prompt = full_prompt + "\n" + style_injection

    model = parameters.get("model") or await model_router.get_model(content_type)
    system_prompt = parameters.get("system_prompt")

    try:
        response = await _ollama.generate(
            model=model,
            prompt=full_prompt,
            system=system_prompt,
        )
    except Exception as exc:
        raise ProcessingError(f"Content generation failed: {exc}") from exc

    feedback_engine.record_generation(content_type, model, str(ULID()))

    content = Content(
        id=str(ULID()),
        project_id=project_id,
        content_type=ContentType(content_type),
        title=parameters.get("title"),
        body=response,
        metadata_json=json.dumps({"model": model, "parameters": parameters}),
        version=1,
    )
    db.add(content)

    version = ContentVersion(
        id=str(ULID()),
        content_id=content.id,
        version=1,
        body=response,
    )
    db.add(version)

    await db.commit()
    await db.refresh(content)

    log.info("content_generated", content_id=content.id, content_type=content_type)
    return content


async def get_content(db: AsyncSession, content_id: str) -> Content:
    content = await db.get(Content, content_id)
    if not content:
        raise NotFoundError(f"Content {content_id} not found")
    return content


async def list_content(
    db: AsyncSession,
    project_id: str,
    content_type: str | None = None,
) -> list[Content]:
    stmt = select(Content).where(Content.project_id == project_id)
    if content_type:
        stmt = stmt.where(Content.content_type == content_type)
    stmt = stmt.order_by(Content.created_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def regenerate_content(db: AsyncSession, content_id: str) -> Content:
    content = await get_content(db, content_id)
    metadata = json.loads(content.metadata_json or "{}")
    parameters = metadata.get("parameters", {})
    model = metadata.get("model", "llama3.2")

    context = await _get_project_context(db, content.project_id)
    full_prompt = _build_prompt(content.content_type.value, context)

    try:
        response = await _ollama.generate(
            model=model,
            prompt=full_prompt,
            system=parameters.get("system_prompt"),
        )
    except Exception as exc:
        raise ProcessingError(f"Content regeneration failed: {exc}") from exc

    content.version += 1
    content.body = response

    version = ContentVersion(
        id=str(ULID()),
        content_id=content.id,
        version=content.version,
        body=response,
    )
    db.add(version)

    await db.commit()
    await db.refresh(content)

    log.info("content_regenerated", content_id=content_id, version=content.version)
    return content


def _build_prompt(template_name: str, context: dict[str, Any]) -> str:
    """Build a prompt from a Jinja2 template file or fall back to inline template."""
    try:
        from jinja2 import Environment, FileSystemLoader

        templates_dir = Path(__file__).parent.parent / "prompts"
        if templates_dir.exists():
            env = Environment(loader=FileSystemLoader(str(templates_dir)))
            try:
                template = env.get_template(f"{template_name}.j2")
                return template.render(**context)
            except Exception:
                pass
    except ImportError:
        pass

    # Fallback inline prompt
    transcript_text = context.get("transcript_text", "No transcript available.")
    scenes_summary = context.get("scenes_summary", "No scene data available.")
    project_name = context.get("project_name", "Untitled Project")

    return (
        f"Project: {project_name}\n\n"
        f"Transcript:\n{transcript_text}\n\n"
        f"Scenes:\n{scenes_summary}\n\n"
        f"Task: Generate {template_name} content for this travel video project."
    )


async def _get_project_context(db: AsyncSession, project_id: str) -> dict[str, Any]:
    """Gather all available context for a project."""
    project = await db.get(Project, project_id)

    videos_result = await db.execute(
        select(Video).where(Video.project_id == project_id)
    )
    videos = videos_result.scalars().all()

    transcripts: list[str] = []
    for video in videos:
        t_result = await db.execute(
            select(Transcript).where(Transcript.video_id == video.id)
        )
        transcript = t_result.scalar_one_or_none()
        if transcript:
            transcripts.append(transcript.full_text)

    from models.db_models import Scene

    scenes_result = await db.execute(
        select(Scene).join(Video).where(Video.project_id == project_id).order_by(Scene.start_ms)
    )
    scenes = scenes_result.scalars().all()
    scenes_summary = "\n".join(
        f"Scene {i+1}: {s.start_ms}ms - {s.end_ms}ms ({s.scene_type or 'unknown'})"
        for i, s in enumerate(scenes)
    )

    return {
        "project_name": project.name if project else "Untitled",
        "project_description": project.description if project else "",
        "transcript_text": "\n\n".join(transcripts) if transcripts else "No transcript available.",
        "scenes_summary": scenes_summary or "No scene data available.",
        "video_count": len(videos),
        "total_duration_ms": sum(v.duration_ms for v in videos),
    }
