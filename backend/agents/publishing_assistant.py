"""Publishing Assistant agent: packages everything into platform-ready formats."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class PublishingAssistantAgent(BaseAgent):
    name = "publishing_assistant"
    description = "Packages all agent outputs into platform-ready publishing formats"
    dependencies = [
        "seo_optimizer",
        "video_script_writer",
        "social_media_creator",
        "thumbnail_planner",
        "fact_checker",
    ]

    async def execute(self, project_id: str, context: dict) -> AgentResult:
        try:
            seo = context.get("seo_optimizer", {})
            script = context.get("video_script_writer", {})
            social = context.get("social_media_creator", {})
            thumbnails = context.get("thumbnail_planner", {})
            facts = context.get("fact_checker", {})

            system_prompt = (
                "You are a travel content publishing coordinator. Your job is to take "
                "outputs from multiple content creation agents and package them into "
                "final, platform-ready publishing formats.\n\n"
                "You should:\n"
                "- Ensure consistency across all platforms (tone, facts, branding)\n"
                "- Optimize YouTube metadata using SEO data\n"
                "- Format blog content with proper markdown structure\n"
                "- Create Instagram-ready content packages (Reels concepts + posts)\n"
                "- Flag any inconsistencies between content pieces\n"
                "- Generate a publishing summary with recommended posting schedule\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "youtube": {\n'
                '    "title": str,\n'
                '    "description": str,  // Full YouTube description with links, timestamps, etc.\n'
                '    "tags": [str],\n'
                '    "chapters": [{"timestamp": str, "title": str}]\n'
                "  },\n"
                '  "instagram": {\n'
                '    "reels": [{"concept": str, "caption": str, "hashtags": [str]}],\n'
                '    "posts": [{"caption": str, "hashtags": [str], "type": str}]\n'
                "  },\n"
                '  "blog": {\n'
                '    "title": str,\n'
                '    "body": str,  // Full blog post in markdown\n'
                '    "seo_meta": {"description": str, "keywords": [str]}\n'
                "  },\n"
                '  "summary": str  // Publishing strategy summary\n'
                "}"
            )

            user_prompt = self._build_user_prompt(seo, script, social, thumbnails, facts)
            output = await self._generate_json(system_prompt, user_prompt)

            output.setdefault("youtube", {"title": "", "description": "", "tags": [], "chapters": []})
            output.setdefault("instagram", {"reels": [], "posts": []})
            output.setdefault("blog", {"title": "", "body": "", "seo_meta": {"description": "", "keywords": []}})
            output.setdefault("summary", "")

            log.info("publishing_assistant_complete", project_id=project_id)
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("publishing_assistant_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(
        self,
        seo: dict,
        script: dict,
        social: dict,
        thumbnails: dict,
        facts: dict,
    ) -> str:
        parts = ["Package the following agent outputs into platform-ready publishing formats.\n"]

        if seo:
            parts.append(f"## SEO Data\n{json.dumps(seo, indent=2)}\n")

        if script:
            script_summary = {
                "sections": script.get("sections", []),
                "estimated_duration_min": script.get("estimated_duration_min"),
                "transitions": script.get("transitions", []),
            }
            script_text = script.get("script", "")
            if len(script_text) > 1500:
                script_text = script_text[:1500] + "..."
            script_summary["script_preview"] = script_text
            parts.append(f"## Video Script Data\n{json.dumps(script_summary, indent=2)}\n")

        if social:
            parts.append(f"## Social Media Content\n{json.dumps(social, indent=2)}\n")

        if thumbnails:
            parts.append(f"## Thumbnail Plans\n{json.dumps(thumbnails, indent=2)}\n")

        if facts:
            flagged = [c for c in facts.get("claims", []) if c.get("confidence") != "high"]
            if flagged:
                parts.append(f"## Fact-Check Flags (review before publishing)\n{json.dumps(flagged, indent=2)}\n")

        parts.append(
            "Create final publishing packages for YouTube (title, description with timestamps, tags), "
            "Instagram (2-3 Reel concepts + 2 feed posts), and a full blog post. "
            "Use the SEO data to optimize all metadata. Incorporate fact-check flags as needed. "
            "End with a publishing strategy summary including recommended posting order and timing."
        )
        return "\n".join(parts)
