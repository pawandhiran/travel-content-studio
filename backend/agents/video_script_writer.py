"""Video Script Writer agent: creates full video scripts with B-roll and transitions."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class VideoScriptWriterAgent(BaseAgent):
    name = "video_script_writer"
    description = "Creates full video scripts with intro, sections, B-roll suggestions, and transitions"
    dependencies = ["story_generator"]

    async def execute(self, project_id: str, context: dict) -> AgentResult:
        try:
            story_data = context.get("story_generator", {})
            if not story_data:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output={},
                    error="Missing story_generator output",
                )

            system_prompt = (
                "You are a professional YouTube video script writer specializing in travel content. "
                "You understand pacing, audience retention, and the visual medium of video.\n\n"
                "Your scripts should:\n"
                "- Open with a hook that grabs attention in the first 5 seconds\n"
                "- Use a mix of narration, on-camera dialogue, and ambient moments\n"
                "- Include specific B-roll suggestions for every section\n"
                "- Mark transition points with style suggestions (cut, dissolve, whip pan, etc.)\n"
                "- Have a clear call-to-action and memorable outro\n"
                "- Target 8-15 minutes for a standard travel video\n"
                "- Include timestamps for each section\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "script": str,  // The complete script with speaker directions\n'
                '  "sections": [\n'
                "    {\n"
                '      "title": str,\n'
                '      "type": "hook"|"intro"|"body"|"climax"|"outro"|"cta",\n'
                '      "duration_sec": int,\n'
                '      "narration": str,\n'
                '      "visual_notes": str\n'
                "    }\n"
                "  ],\n"
                '  "b_roll_suggestions": [\n'
                '    {"timestamp": str, "description": str, "duration_sec": int, "mood": str}\n'
                "  ],\n"
                '  "transitions": [\n'
                '    {"between": str, "type": str, "notes": str}\n'
                "  ],\n"
                '  "estimated_duration_min": int\n'
                "}"
            )

            user_prompt = self._build_user_prompt(story_data)
            output = await self._generate_json(system_prompt, user_prompt)

            for key in ("script", "sections", "b_roll_suggestions", "transitions"):
                if key not in output:
                    output[key] = [] if key != "script" else ""
            output.setdefault("estimated_duration_min", 10)

            log.info(
                "video_script_complete",
                project_id=project_id,
                sections=len(output["sections"]),
                duration_min=output["estimated_duration_min"],
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("video_script_writer_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(self, story_data: dict) -> str:
        parts = ["Write a complete YouTube video script from the following travel story.\n"]

        parts.append(f"## Story\n{story_data.get('story', 'N/A')}\n")

        if story_data.get("chapters"):
            parts.append(f"## Story Chapters\n{json.dumps(story_data['chapters'], indent=2)}\n")

        if story_data.get("emotional_arc"):
            parts.append(f"## Emotional Arc\n{story_data['emotional_arc']}\n")

        if story_data.get("key_themes"):
            parts.append(f"## Key Themes\n{', '.join(story_data['key_themes'])}\n")

        parts.append(
            "Transform this story into a professional video script. Include a 5-second hook, "
            "engaging intro (30s), well-paced body sections, a climactic moment, "
            "clear CTA, and memorable outro. Suggest specific B-roll shots for every section "
            "and transition styles between segments."
        )
        return "\n".join(parts)
