"""Social Media Creator agent: generates platform-specific content."""

from __future__ import annotations

import json

from core.logging_config import get_logger

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class SocialMediaCreatorAgent(BaseAgent):
    name = "social_media_creator"
    description = "Creates platform-specific social media content for Instagram, Facebook, and YouTube Community"
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
                "You are a social media content strategist specializing in travel creators. "
                "You understand the unique culture, algorithm preferences, and audience behavior "
                "on each platform.\n\n"
                "Platform guidelines:\n"
                "- Instagram: Visual-first, use line breaks, max 2200 chars caption, 30 hashtags, "
                "Story text should be punchy and curiosity-driven\n"
                "- Facebook: Longer form OK, conversation starters, community engagement focus, "
                "fewer hashtags (3-5), question hooks work well\n"
                "- YouTube Community: Poll-friendly, behind-the-scenes teasers, "
                "drive engagement for algorithm boost, 1-2 hashtags max\n\n"
                "You MUST respond with valid JSON only, no markdown fences.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "instagram": {\n'
                '    "caption": str,  // Full caption with line breaks and emojis\n'
                '    "hashtags": [str],  // 20-30 relevant hashtags\n'
                '    "story_text": str  // Short, punchy story slide text\n'
                "  },\n"
                '  "facebook": {\n'
                '    "post": str,  // Engaging post with question hook\n'
                '    "hashtags": [str]  // 3-5 hashtags\n'
                "  },\n"
                '  "youtube_community": {\n'
                '    "post": str  // Community tab post with engagement hook\n'
                "  }\n"
                "}"
            )

            user_prompt = self._build_user_prompt(story_data)
            output = await self._generate_json(system_prompt, user_prompt)

            output.setdefault("instagram", {"caption": "", "hashtags": [], "story_text": ""})
            output.setdefault("facebook", {"post": "", "hashtags": []})
            output.setdefault("youtube_community", {"post": ""})

            log.info("social_media_creation_complete", project_id=project_id)
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("social_media_creator_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    def _build_user_prompt(self, story_data: dict) -> str:
        parts = ["Create social media content for all platforms from this travel story.\n"]

        story_preview = story_data.get("story", "")
        if len(story_preview) > 2000:
            story_preview = story_preview[:2000] + "..."
        parts.append(f"## Story\n{story_preview}\n")

        if story_data.get("key_themes"):
            parts.append(f"## Key Themes\n{', '.join(story_data['key_themes'])}\n")

        if story_data.get("emotional_arc"):
            parts.append(f"## Emotional Arc\n{story_data['emotional_arc']}\n")

        parts.append(
            "Create platform-optimized content that drives engagement. "
            "Instagram caption should tell a micro-story. Facebook post should start a conversation. "
            "YouTube Community post should tease the video and ask for engagement. "
            "All content should feel authentic, not promotional."
        )
        return "\n".join(parts)
