"""Social media reel generation: hooks, scripts, shot lists, CTAs, and captions."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from core.model_router import model_router
from models.db_models import DurationType, Project, Reel
from modules.content_engine import _get_project_context
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()

_DURATION_GUIDANCE = {
    "15s": "Ultra-short format. One hook, 2-3 quick shots, one CTA. Maximum impact, minimal words.",
    "30s": "Short format. Hook + 3-5 shots with brief narration + CTA. Fast pace, punchy editing.",
    "60s": "Standard reel. Hook + story arc (setup, journey, payoff) + CTA. Room for personality.",
}

_SYSTEM_PROMPT = (
    "You are a social media content strategist specializing in travel reels. "
    "Create scroll-stopping content with strong hooks, dynamic pacing, and clear CTAs. "
    "Always respond in valid JSON format with the following keys: "
    "hook, script, shot_list (array of objects with 'shot', 'duration_s', 'description'), "
    "cta, captions."
)


async def generate_reel(
    db: AsyncSession,
    project_id: str,
    duration_type: str,
    context: dict | None = None,
) -> Reel:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    if duration_type not in _DURATION_GUIDANCE:
        raise ProcessingError(
            f"Invalid duration type: {duration_type}. Valid: {list(_DURATION_GUIDANCE.keys())}"
        )

    project_context = await _get_project_context(db, project_id)
    if context:
        project_context.update(context)

    prompt = (
        f"Create a {duration_type} travel reel plan.\n\n"
        f"Duration guidance: {_DURATION_GUIDANCE[duration_type]}\n\n"
        f"Project: {project_context['project_name']}\n"
        f"Description: {project_context['project_description']}\n\n"
        f"Available footage:\n"
        f"- {project_context['video_count']} videos\n"
        f"- Total duration: {project_context['total_duration_ms'] / 1000:.0f}s\n\n"
        f"Transcript excerpt:\n{project_context['transcript_text'][:2000]}\n\n"
        f"Scene breakdown:\n{project_context['scenes_summary'][:1000]}\n\n"
        f"Generate the reel plan as JSON."
    )

    try:
        model = await model_router.get_model("reel_script")
        response = await _ollama.generate(
            model=model,
            prompt=prompt,
            system=_SYSTEM_PROMPT,
        )
    except Exception as exc:
        raise ProcessingError(f"Reel generation failed: {exc}") from exc

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        data = {
            "hook": response[:200],
            "script": response,
            "shot_list": [],
            "cta": "",
            "captions": "",
        }

    reel = Reel(
        id=str(ULID()),
        project_id=project_id,
        duration_type=DurationType(duration_type),
        hook=data.get("hook", ""),
        script=data.get("script", ""),
        shot_list_json=json.dumps(data.get("shot_list", [])),
        cta=data.get("cta"),
        captions=data.get("captions"),
    )
    db.add(reel)
    await db.commit()
    await db.refresh(reel)

    log.info("reel_generated", reel_id=reel.id, duration_type=duration_type)
    return reel
