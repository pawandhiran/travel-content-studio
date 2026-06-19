"""Fact Checker agent: identifies and flags factual claims for verification."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class FactCheckerAgent(BaseAgent):
    name = "fact_checker"
    description = "Identifies factual claims in content and flags items that need verification"
    dependencies = ["story_generator", "video_script_writer"]

    async def execute(self, project_id: str, context: dict) -> AgentResult:
        try:
            story_data = context.get("story_generator", {})
            script_data = context.get("video_script_writer", {})

            if not story_data and not script_data:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output={},
                    error="Missing both story_generator and video_script_writer output",
                )

            system_prompt = (
                "You are a meticulous travel content fact-checker. Your job is to identify "
                "every factual claim in the provided content and assess its verifiability.\n\n"
                "Categories of claims to check:\n"
                "- Geographic facts (distances, elevations, coordinates, borders)\n"
                "- Historical facts (dates, events, historical figures)\n"
                "- Cultural claims (traditions, customs, languages)\n"
                "- Practical info (prices, opening hours, visa requirements, transport schedules)\n"
                "- Statistical claims (population, area, rankings)\n"
                "- Safety/health claims (travel advisories, health risks)\n"
                "- Superlatives (tallest, oldest, biggest, most popular)\n\n"
                "Confidence levels:\n"
                "- high: Commonly known facts unlikely to be wrong\n"
                "- medium: Plausible but should be double-checked\n"
                "- low: Specific numbers, prices, or time-sensitive info that changes frequently\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "claims": [\n'
                "    {\n"
                '      "claim": str,  // The exact factual claim\n'
                '      "category": str,  // geographic|historical|cultural|practical|statistical|safety|superlative\n'
                '      "confidence": "high"|"medium"|"low",\n'
                '      "suggestion": str  // How to verify or correct this claim\n'
                "    }\n"
                "  ],\n"
                '  "verified_count": int,  // Claims rated high confidence\n'
                '  "flagged_count": int  // Claims rated medium or low confidence\n'
                "}"
            )

            user_prompt = self._build_user_prompt(story_data, script_data)
            output = await self._generate_json(system_prompt, user_prompt)

            output.setdefault("claims", [])
            if "verified_count" not in output or "flagged_count" not in output:
                claims = output["claims"]
                output["verified_count"] = sum(1 for c in claims if c.get("confidence") == "high")
                output["flagged_count"] = sum(1 for c in claims if c.get("confidence") in ("medium", "low"))

            log.info(
                "fact_check_complete",
                project_id=project_id,
                total_claims=len(output["claims"]),
                flagged=output["flagged_count"],
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("fact_checker_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(self, story_data: dict, script_data: dict) -> str:
        parts = ["Review the following travel content and identify ALL factual claims.\n"]

        if story_data.get("story"):
            parts.append(f"## Travel Story\n{story_data['story']}\n")

        if script_data.get("script"):
            parts.append(f"## Video Script\n{script_data['script']}\n")

        parts.append(
            "Extract every factual claim (names, dates, distances, prices, historical facts, "
            "cultural assertions, superlatives, etc.). Rate each claim's confidence level. "
            "For low-confidence claims, suggest specific ways to verify them. "
            "Be thorough -- even small factual errors damage creator credibility."
        )
        return "\n".join(parts)
