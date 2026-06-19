"""Thumbnail Planner agent: suggests YouTube thumbnail compositions."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class ThumbnailPlannerAgent(BaseAgent):
    name = "thumbnail_planner"
    description = "Suggests YouTube thumbnail compositions with text overlays and color schemes"
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

            system_prompt = (
                "You are a YouTube thumbnail design strategist with deep knowledge of "
                "what makes travel thumbnails get clicks. You understand color psychology, "
                "composition rules, and platform-specific best practices.\n\n"
                "Your thumbnail suggestions should:\n"
                "- Maximize click-through rate (CTR)\n"
                "- Use proven travel thumbnail patterns (destination beauty shots, reaction faces, contrast)\n"
                "- Include specific text overlay suggestions (3-5 words max)\n"
                "- Specify color palettes that pop on YouTube's interface\n"
                "- Consider mobile viewing (60%+ of YouTube traffic)\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "suggestions": [\n'
                "    {\n"
                '      "concept": str,  // One-line concept description\n'
                '      "text_overlay": str,  // The text on the thumbnail (3-5 words)\n'
                '      "color_scheme": {"primary": str, "secondary": str, "accent": str},\n'
                '      "layout": str,  // Composition description (e.g., "rule of thirds, subject left")\n'
                '      "emotion": str,  // Target emotion (awe, curiosity, excitement, etc.)\n'
                '      "background_suggestion": str,  // What scene/frame to use\n'
                '      "style_notes": str  // Font style, effects, etc.\n'
                "    }\n"
                "  ]\n"
                "}"
            )

            user_prompt = self._build_user_prompt(trip_data)
            output = await self._generate_json(system_prompt, user_prompt)

            if "suggestions" not in output:
                output["suggestions"] = []

            log.info(
                "thumbnail_planning_complete",
                project_id=project_id,
                suggestions=len(output["suggestions"]),
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("thumbnail_planner_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(self, trip_data: dict) -> str:
        parts = ["Design 4-6 YouTube thumbnail concepts for the following travel content.\n"]

        parts.append(f"## Trip Summary\n{trip_data.get('summary', 'N/A')}\n")

        if trip_data.get("locations"):
            parts.append(f"## Locations\n{json.dumps(trip_data['locations'], indent=2)}\n")

        if trip_data.get("key_moments"):
            parts.append(f"## Key Moments (potential thumbnail scenes)\n{json.dumps(trip_data['key_moments'], indent=2)}\n")

        parts.append(
            "Create thumbnail concepts that would achieve 8%+ CTR on YouTube. "
            "Include a mix of styles: one with a bold text focus, one scenic beauty shot, "
            "one with contrast/before-after feel, and one curiosity-gap style. "
            "Each suggestion must be specific enough for a designer to execute."
        )
        return "\n".join(parts)
