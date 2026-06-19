"""Conversational AI agent that orchestrates all TCS features with memory and rules."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from config import get_settings
from core.logging_config import get_logger
from core.model_router import ModelRouter
from core.chat_memory import ChatMemory
from core.user_rules import UserRulesManager
from core.feedback_engine import feedback_engine

log = get_logger(__name__)

SYSTEM_PROMPT = """\
You are the AI assistant inside Travel Content Studio. You help users create travel content.

You have access to these tools:
- create_project(name, description) - Create a new project
- import_video(project_id, file_path) - Import a video file
- transcribe(video_id) - Transcribe video audio
- generate_content(project_id, type, prompt) - Generate title/script/blog/etc
- color_grade(video_id, preset) - Apply color grading
- auto_reframe(video_id, aspect) - Smart crop video
- add_captions(video_id, style) - Add animated captions
- enhance_audio(video_id, preset) - Enhance audio
- smart_stitch(video_ids, duration) - Combine clips
- generate_thumbnail(project_id, prompt) - AI thumbnail
- generate_voiceover(project_id, text, voice) - TTS narration
- generate_blog(project_id, type, context) - Write blog post
- enhance_photos(image_paths, mode) - Enhance for Shutterstock
- quality_check(video_id, platform) - Pre-publish QC
- run_agents(project_id, agents) - Run travel agent pipeline

When the user asks for something, decide which tool(s) to use. Respond conversationally and explain what you're doing.
If the user uploads a photo, suggest stock photo enhancement or thumbnail creation.
If the user uploads a video, suggest transcription, editing, or content generation.
If unsure, ask clarifying questions.

{rules_injection}

{style_injection}

{memory_context}

{skills_summary}

When the user says "remember this: [something]", add it as a new rule and confirm with "Got it, I'll remember that."
When the user gives feedback like "that was good" or "too formal", acknowledge it and learn from it.
When the user says "run [skill name]", look up the skill and execute its steps sequentially.
You can reference past conversations: "Last time you asked me to generate a blog about Bali, you liked the casual tone."

Respond in JSON with this exact schema:
{{"reply": "your conversational message", "tool_calls": [{{"tool": "tool_name", "args": {{...}}}}], "add_rule": "optional rule text if user asked to remember something"}}

Always return valid JSON. Do not include anything outside the JSON object.\
"""

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".insv"}


def _classify_attachments(
    paths: list[str],
) -> tuple[list[str], list[str], list[str]]:
    images, videos, other = [], [], []
    for p in paths:
        ext = "." + p.rsplit(".", 1)[-1].lower() if "." in p else ""
        if ext in IMAGE_EXTENSIONS:
            images.append(p)
        elif ext in VIDEO_EXTENSIONS:
            videos.append(p)
        else:
            other.append(p)
    return images, videos, other


def _build_attachment_context(
    images: list[str], videos: list[str], other: list[str]
) -> str:
    parts: list[str] = []
    if images:
        parts.append(f"The user attached {len(images)} image(s): {', '.join(images)}")
    if videos:
        parts.append(f"The user attached {len(videos)} video(s): {', '.join(videos)}")
    if other:
        parts.append(f"The user also attached: {', '.join(other)}")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from an LLM response that might contain markdown fences or preamble."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        return {"reply": text, "tool_calls": []}

    depth = 0
    end = brace_start
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        return json.loads(text[brace_start:end])
    except json.JSONDecodeError:
        return {"reply": text, "tool_calls": []}


TOOL_REGISTRY: dict[str, str] = {
    "create_project": "/projects",
    "import_video": "/videos/import",
    "transcribe": "/transcription",
    "generate_content": "/content",
    "color_grade": "/video-editing/color-grade",
    "auto_reframe": "/video-editing/auto-reframe",
    "add_captions": "/video-editing/animated-captions",
    "enhance_audio": "/video-editing/audio-enhance",
    "smart_stitch": "/video-editing/smart-stitch",
    "generate_thumbnail": "/thumbnails",
    "generate_voiceover": "/voiceover",
    "generate_blog": "/blog",
    "enhance_photos": "/stock-photos/enhance",
    "quality_check": "/video-editing/quality-check",
    "run_agents": "/agents",
}

# Slash-command patterns detected before sending to the LLM
_REMEMBER_RE = re.compile(
    r"^/remember\s+(.+)", re.IGNORECASE | re.DOTALL
)
_RUN_RE = re.compile(r"^/run\s+(.+)", re.IGNORECASE)


class ChatAgent:
    """Conversational AI with memory, rules, skills, and feedback integration."""

    def __init__(self) -> None:
        self._router = ModelRouter()
        self._settings = get_settings()
        self._memory: ChatMemory | None = None
        self._rules: UserRulesManager | None = None

    def initialize(self, data_dir=None) -> None:
        """Set up memory and rules managers (called during app lifespan)."""
        data_dir = data_dir or self._settings.data_dir
        self._memory = ChatMemory(data_dir)
        self._rules = UserRulesManager(data_dir)
        log.info("chat_agent_initialized")

    @property
    def memory(self) -> ChatMemory:
        if self._memory is None:
            self.initialize()
        return self._memory  # type: ignore[return-value]

    @property
    def rules(self) -> UserRulesManager:
        if self._rules is None:
            self.initialize()
        return self._rules  # type: ignore[return-value]

    def _build_system_prompt(self, project_id: str | None) -> str:
        rules_injection = self.rules.get_rules_prompt_injection()
        style_injection = feedback_engine.get_style_prompt_injection()
        memory_context = self.memory.get_context_summary(project_id)
        skills_summary = self.rules.get_skills_summary()
        return SYSTEM_PROMPT.format(
            rules_injection=rules_injection,
            style_injection=style_injection,
            memory_context=memory_context,
            skills_summary=skills_summary,
        )

    async def process_message(
        self,
        message: str,
        project_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        attachments = attachments or []

        # Handle slash commands locally
        slash_result = self._handle_slash_command(message, project_id)
        if slash_result is not None:
            self.memory.add_message(project_id, "user", message)
            self.memory.add_message(project_id, "assistant", slash_result["reply"])
            return slash_result

        images, videos, other = _classify_attachments(attachments)

        user_parts = [message]
        if attachments:
            user_parts.append(_build_attachment_context(images, videos, other))
        if project_id:
            user_parts.append(f"Current project ID: {project_id}")

        user_content = "\n\n".join(user_parts)

        self.memory.add_message(
            project_id, "user", message,
            metadata={"attachments": attachments} if attachments else None,
        )

        system_prompt = self._build_system_prompt(project_id)
        model = await self._router.get_model("agent_trip_analyzer")
        raw_reply = await self._call_ollama(model, system_prompt, user_content)
        parsed = _extract_json(raw_reply)

        reply_text = parsed.get("reply", raw_reply)
        tool_calls = parsed.get("tool_calls", [])

        # Handle inline "add_rule" from the LLM
        if parsed.get("add_rule"):
            self.rules.add_rule(parsed["add_rule"])

        actions_taken: list[dict[str, Any]] = []
        suggestions: list[str] = []

        for tc in tool_calls:
            tool_name = tc.get("tool", "")
            args = tc.get("args", {})
            result = await self._execute_tool(tool_name, args, project_id)
            actions_taken.append(
                {"tool": tool_name, "args": args, "result": result}
            )

        if images and not tool_calls:
            suggestions.append("Enhance these photos for stock photography")
            suggestions.append("Generate a thumbnail from this image")
        if videos and not tool_calls:
            suggestions.append("Transcribe this video")
            suggestions.append("Apply cinematic color grading")
            suggestions.append("Generate captions for this video")
        if not tool_calls and not attachments:
            suggestions.append("Create a new project")
            suggestions.append("Generate a travel blog post")

        self.memory.add_message(
            project_id, "assistant", reply_text,
            metadata={
                "actions": [a["tool"] for a in actions_taken],
                "suggestions": suggestions,
            } if actions_taken or suggestions else None,
        )

        return {
            "reply": reply_text,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
        }

    async def run_skill(
        self, skill_id: str, project_id: str | None = None
    ) -> dict[str, Any]:
        """Execute a multi-step skill by running each tool step sequentially."""
        skill = self.rules.get_skill(skill_id)
        if not skill:
            return {"reply": f"Skill '{skill_id}' not found.", "actions_taken": [], "suggestions": []}

        actions: list[dict[str, Any]] = []
        for step in skill.get("steps", []):
            tool_name = step.get("tool", "")
            args = dict(step.get("args", {}))
            result = await self._execute_tool(tool_name, args, project_id)
            actions.append({"tool": tool_name, "args": args, "result": result})

        reply = f"Completed skill '{skill['name']}' -- ran {len(actions)} step(s)."
        self.memory.add_message(
            project_id, "assistant", reply,
            metadata={"skill": skill["name"], "actions": [a["tool"] for a in actions]},
        )
        return {"reply": reply, "actions_taken": actions, "suggestions": []}

    def record_feedback(
        self,
        message_id: str,
        rating: str,
        project_id: str | None = None,
    ) -> None:
        """Record thumbs-up / thumbs-down feedback on a specific AI message."""
        numeric = 5 if rating == "up" else 1
        feedback_engine.record_rating("chat", "ollama", message_id, numeric)
        log.info("chat_feedback", message_id=message_id, rating=rating)

    def _handle_slash_command(
        self, message: str, project_id: str | None
    ) -> dict[str, Any] | None:
        """Intercept slash commands before sending to the LLM."""
        msg = message.strip()

        if msg.lower() == "/rules":
            rules = self.rules.list_rules()
            if not rules:
                return {"reply": "You have no custom rules set. Use /remember to add one.", "actions_taken": [], "suggestions": []}
            lines = ["Here are your current rules:"]
            for r in rules:
                lines.append(f"- [{r['category']}] {r['rule']}")
            return {"reply": "\n".join(lines), "actions_taken": [], "suggestions": []}

        if msg.lower() == "/skills":
            skills = self.rules.list_skills()
            if not skills:
                return {"reply": "No skills available.", "actions_taken": [], "suggestions": []}
            lines = ["Available skills:"]
            for s in skills:
                tag = " (built-in)" if s.get("built_in") else ""
                lines.append(f"- **{s['name']}**{tag}: {s['description']}")
            return {"reply": "\n".join(lines), "actions_taken": [], "suggestions": []}

        if msg.lower() == "/forget":
            self.memory.clear_history(project_id)
            return {"reply": "Conversation history cleared.", "actions_taken": [], "suggestions": []}

        m = _REMEMBER_RE.match(msg)
        if m:
            rule_text = m.group(1).strip()
            self.rules.add_rule(rule_text)
            return {
                "reply": f"Got it, I'll remember that: \"{rule_text}\"",
                "actions_taken": [],
                "suggestions": [],
            }

        m = _RUN_RE.match(msg)
        if m:
            skill_name = m.group(1).strip()
            skill = self.rules.find_skill_by_name(skill_name)
            if not skill:
                return {
                    "reply": f"I couldn't find a skill named \"{skill_name}\". Use /skills to see available skills.",
                    "actions_taken": [],
                    "suggestions": [],
                }
            return None  # handled async in process_message caller

        return None

    async def _call_ollama(
        self, model: str, system_prompt: str, user_message: str
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self._settings.ollama_host}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except httpx.TimeoutException:
            log.error("ollama_timeout", model=model)
            return '{"reply": "Sorry, the AI model took too long to respond. Please try again.", "tool_calls": []}'
        except Exception as exc:
            log.error("ollama_error", model=model, error=str(exc))
            return f'{{"reply": "I encountered an error connecting to the AI model: {exc}", "tool_calls": []}}'

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        project_id: Optional[str],
    ) -> dict[str, Any]:
        endpoint = TOOL_REGISTRY.get(tool_name)
        if not endpoint:
            return {"status": "error", "detail": f"Unknown tool: {tool_name}"}

        if project_id and "project_id" not in args:
            args["project_id"] = project_id

        base = f"http://127.0.0.1:{self._settings.api_port}/api/v1"
        url = f"{base}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=args)
                if resp.status_code < 300:
                    return {"status": "success", "data": resp.json()}
                return {
                    "status": "error",
                    "detail": resp.text[:500],
                }
        except Exception as exc:
            log.warning("tool_execution_failed", tool=tool_name, error=str(exc))
            return {"status": "error", "detail": str(exc)}


chat_agent = ChatAgent()
