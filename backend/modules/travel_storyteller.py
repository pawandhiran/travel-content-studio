"""Travel narrative generation: stories, documentaries, and voiceover scripts."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Project, Story, StoryType
from modules.content_engine import _get_project_context
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()

_SYSTEM_PROMPTS = {
    "travel_story": (
        "You are a travel writer crafting engaging first-person narratives. "
        "Write vivid, sensory-rich stories that transport the reader to the destination. "
        "Include personal observations, cultural details, and emotional moments."
    ),
    "documentary": (
        "You are a documentary scriptwriter. Write informative, compelling narration "
        "that balances factual content with storytelling. Structure it for a visual medium "
        "with clear scene references and pacing notes."
    ),
    "voiceover_script": (
        "You are writing a voiceover script for a travel video. Keep sentences concise "
        "and rhythmic. Leave room for visuals to breathe. Include timing cues in brackets. "
        "Match the energy of the footage described."
    ),
}


async def generate_story(
    db: AsyncSession,
    project_id: str,
    story_type: str,
    context: dict | None = None,
) -> Story:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    if story_type not in _SYSTEM_PROMPTS:
        raise ProcessingError(f"Invalid story type: {story_type}. Valid: {list(_SYSTEM_PROMPTS.keys())}")

    project_context = await _get_project_context(db, project_id)
    if context:
        project_context.update(context)

    prompt = (
        f"Create a {story_type.replace('_', ' ')} for this travel project.\n\n"
        f"Project: {project_context['project_name']}\n"
        f"Description: {project_context['project_description']}\n\n"
        f"Available transcript:\n{project_context['transcript_text'][:3000]}\n\n"
        f"Scene breakdown:\n{project_context['scenes_summary'][:1000]}\n\n"
        f"Total footage: {project_context['video_count']} videos, "
        f"{project_context['total_duration_ms'] / 1000:.0f}s total\n\n"
        f"Write the full {story_type.replace('_', ' ')}."
    )

    try:
        response = await _ollama.generate(
            model="llama3.2",
            prompt=prompt,
            system=_SYSTEM_PROMPTS[story_type],
        )
    except Exception as exc:
        raise ProcessingError(f"Story generation failed: {exc}") from exc

    title = f"{project.name} - {story_type.replace('_', ' ').title()}"

    story = Story(
        id=str(ULID()),
        project_id=project_id,
        title=title,
        story_text=response,
        story_type=StoryType(story_type),
    )
    db.add(story)
    await db.commit()
    await db.refresh(story)

    log.info("story_generated", story_id=story.id, story_type=story_type)
    return story
