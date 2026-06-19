"""Story Generator agent: creates a cohesive travel narrative from trip analysis."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.logging_config import get_logger
from models.db_models import Video

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class StoryGeneratorAgent(BaseAgent):
    name = "story_generator"
    description = "Generates a cohesive travel narrative with chapters and emotional arc"
    dependencies = ["trip_analyzer"]

    async def execute(self, project_id: str, context: dict) -> AgentResult:
        try:
            trip_data = context.get("trip_analyzer", {})
            if not trip_data:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output={},
                    error="Missing trip_analyzer output",
                )

            transcripts = await self._get_transcripts(project_id)

            system_prompt = (
                "You are a world-class travel storyteller and narrative designer. "
                "You transform raw trip data into compelling, emotionally resonant travel stories "
                "that captivate audiences on YouTube, blogs, and social media.\n\n"
                "Your stories should:\n"
                "- Have a clear narrative arc (setup, rising action, climax, resolution)\n"
                "- Use vivid sensory language that transports the reader\n"
                "- Weave in personal reflections and cultural insights\n"
                "- Balance information with entertainment\n"
                "- Feel authentic, not like a travel brochure\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "story": str,  // The full narrative (1500-3000 words)\n'
                '  "chapters": [\n'
                '    {"title": str, "summary": str, "word_count": int}\n'
                "  ],\n"
                '  "emotional_arc": str,  // Description of the emotional journey\n'
                '  "key_themes": [str]  // 3-6 central themes\n'
                "}"
            )

            user_prompt = self._build_user_prompt(trip_data, transcripts)
            output = await self._generate_json(system_prompt, user_prompt)

            for key in ("story", "chapters", "emotional_arc", "key_themes"):
                if key not in output:
                    output[key] = [] if key in ("chapters", "key_themes") else ""

            log.info(
                "story_generation_complete",
                project_id=project_id,
                chapters=len(output["chapters"]),
                themes=len(output["key_themes"]),
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("story_generator_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    async def _get_transcripts(self, project_id: str) -> list[str]:
        result = await self.db.execute(
            select(Video)
            .where(Video.project_id == project_id)
            .options(selectinload(Video.transcript))
        )
        videos = result.scalars().all()
        return [v.transcript.full_text for v in videos if v.transcript]

    def _build_user_prompt(self, trip_data: dict, transcripts: list[str]) -> str:
        parts = ["Create a compelling travel story from the following trip analysis.\n"]

        parts.append(f"## Trip Summary\n{trip_data.get('summary', 'N/A')}\n")

        if trip_data.get("locations"):
            parts.append(f"## Locations Visited\n{json.dumps(trip_data['locations'], indent=2)}\n")

        if trip_data.get("timeline"):
            parts.append(f"## Trip Timeline\n{json.dumps(trip_data['timeline'], indent=2)}\n")

        if trip_data.get("key_moments"):
            parts.append(f"## Key Moments\n{json.dumps(trip_data['key_moments'], indent=2)}\n")

        if trip_data.get("activities"):
            parts.append(f"## Activities\n{json.dumps(trip_data['activities'], indent=2)}\n")

        if transcripts:
            combined = "\n---\n".join(transcripts[:3])
            parts.append(f"## Raw Transcripts (for voice and details)\n{combined}\n")

        parts.append(
            "Weave all of this into a single cohesive narrative. Organize into clear chapters. "
            "Capture the emotional journey from start to finish. Use the speaker's own words "
            "from the transcripts where they add authenticity."
        )
        return "\n".join(parts)
