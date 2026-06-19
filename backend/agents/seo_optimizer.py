"""SEO Optimizer agent: generates keywords, meta descriptions, titles, and tags."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class SEOOptimizerAgent(BaseAgent):
    name = "seo_optimizer"
    description = "Generates SEO-optimized keywords, titles, descriptions, and tags"
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
                "You are an expert YouTube and travel blog SEO strategist. "
                "You understand search algorithms, keyword research, and how travelers "
                "search for content online.\n\n"
                "Your SEO recommendations should:\n"
                "- Target high-volume, low-competition keywords where possible\n"
                "- Include both short-tail and long-tail keywords\n"
                "- Consider search intent (informational, navigational, transactional)\n"
                "- Follow current YouTube SEO best practices\n"
                "- Include trending and evergreen keyword mixes\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "keywords": [\n'
                '    {"keyword": str, "type": "short-tail"|"long-tail", "volume_estimate": "high"|"medium"|"low", "intent": str}\n'
                "  ],\n"
                '  "meta_description": str,  // 150-160 chars, compelling, keyword-rich\n'
                '  "suggested_titles": [\n'
                '    {"title": str, "style": str, "target_keyword": str}\n'
                "  ],\n"
                '  "tags": [str],  // 15-30 YouTube tags\n'
                '  "search_intent": str  // Primary search intent this content serves\n'
                "}"
            )

            user_prompt = self._build_user_prompt(trip_data)
            output = await self._generate_json(system_prompt, user_prompt)

            for key in ("keywords", "meta_description", "suggested_titles", "tags", "search_intent"):
                if key not in output:
                    output[key] = [] if key in ("keywords", "suggested_titles", "tags") else ""

            log.info(
                "seo_optimization_complete",
                project_id=project_id,
                keywords=len(output["keywords"]),
                titles=len(output["suggested_titles"]),
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("seo_optimizer_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(self, trip_data: dict) -> str:
        parts = ["Generate comprehensive SEO optimization for the following travel content.\n"]

        parts.append(f"## Trip Summary\n{trip_data.get('summary', 'N/A')}\n")

        if trip_data.get("locations"):
            location_names = [loc["name"] for loc in trip_data["locations"] if isinstance(loc, dict)]
            parts.append(f"## Locations\n{', '.join(location_names)}\n")

        if trip_data.get("activities"):
            activity_names = [act["name"] for act in trip_data["activities"] if isinstance(act, dict)]
            parts.append(f"## Activities\n{', '.join(activity_names)}\n")

        if trip_data.get("key_moments"):
            parts.append(f"## Key Moments\n{json.dumps(trip_data['key_moments'], indent=2)}\n")

        parts.append(
            "Generate SEO content optimized for YouTube search, Google search, and travel blog "
            "discoverability. Provide at least 5 title variations with different styles "
            "(question, listicle, emotional, clickbait-lite, descriptive). Include 20+ tags."
        )
        return "\n".join(parts)
