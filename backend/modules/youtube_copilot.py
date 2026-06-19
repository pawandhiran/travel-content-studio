"""YouTube content package generation: titles, descriptions, chapters, tags, SEO."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Content, ContentType, Project
from modules.content_engine import _get_project_context
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()

_SYSTEM_PROMPT = (
    "You are a YouTube SEO expert and content strategist for travel channels. "
    "Generate optimized metadata that maximizes CTR and watch time. "
    "Always respond in valid JSON format with keys: "
    "title, description, chapters (array of {timestamp, title}), "
    "tags (array of strings), seo_keywords (array of strings)."
)


async def generate_youtube_package(db: AsyncSession, project_id: str) -> dict:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    context = await _get_project_context(db, project_id)

    prompt = (
        f"Generate a complete YouTube metadata package for this travel video.\n\n"
        f"Project: {context['project_name']}\n"
        f"Description: {context['project_description']}\n\n"
        f"Video transcript:\n{context['transcript_text'][:3000]}\n\n"
        f"Scene breakdown:\n{context['scenes_summary'][:1500]}\n\n"
        f"Total duration: {context['total_duration_ms'] / 1000:.0f}s\n\n"
        f"Generate:\n"
        f"1. An attention-grabbing title (under 60 chars)\n"
        f"2. SEO-optimized description with timestamps\n"
        f"3. Chapter markers based on scenes\n"
        f"4. 15-20 relevant tags\n"
        f"5. Top SEO keywords\n\n"
        f"Respond as JSON."
    )

    try:
        response = await _ollama.generate(
            model="llama3.2",
            prompt=prompt,
            system=_SYSTEM_PROMPT,
        )
    except Exception as exc:
        raise ProcessingError(f"YouTube package generation failed: {exc}") from exc

    try:
        package = json.loads(response)
    except json.JSONDecodeError:
        package = {
            "title": response[:60],
            "description": response,
            "chapters": [],
            "tags": [],
            "seo_keywords": [],
        }

    content_records = [
        (ContentType.title, "title", package.get("title", "")),
        (ContentType.seo_description, "description", package.get("description", "")),
        (ContentType.chapter_markers, "chapters", json.dumps(package.get("chapters", []))),
        (ContentType.hashtags, "tags", json.dumps(package.get("tags", []))),
        (ContentType.seo_keywords, "seo_keywords", json.dumps(package.get("seo_keywords", []))),
    ]

    for ct, field_name, body in content_records:
        content = Content(
            id=str(ULID()),
            project_id=project_id,
            content_type=ct,
            title=f"YouTube {field_name.replace('_', ' ').title()}",
            body=body,
            metadata_json=json.dumps({"source": "youtube_copilot"}),
            version=1,
        )
        db.add(content)

    await db.commit()

    log.info("youtube_package_generated", project_id=project_id)
    return package
