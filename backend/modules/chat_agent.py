"""Conversational AI agent that orchestrates all TCS features with memory and rules."""

from __future__ import annotations

import asyncio
import json
import re
import zipfile
from pathlib import Path
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
- generate_content(project_id, content_type, prompt) - Generate title/script/blog/etc
- color_grade(video_id, preset) - Apply color grading
- auto_reframe(video_id, target_aspect) - Smart crop video
- add_captions(video_id, style) - Add animated captions
- enhance_audio(video_id, preset) - Enhance audio
- smart_stitch(video_ids, duration) - Combine clips
- generate_thumbnail(project_id, prompt) - AI thumbnail
- generate_voiceover(project_id, script_text, voice_id) - TTS narration
- generate_blog(project_id, blog_type, context) - Write blog post
- enhance_photos(image_paths, mode) - Enhance for Shutterstock
- quality_check(video_id, platform) - Pre-publish QC
- run_agents(project_id, agents) - Run travel agent pipeline

When the user asks for something, decide which tool(s) to use. Respond conversationally and explain what you're doing.
If the user uploads a photo, suggest stock photo enhancement or thumbnail creation.
If the user uploads a video, suggest transcription, editing, or content generation.
If unsure, ask clarifying questions.

IMPORTANT RULES:
- When the user attaches files, the EXACT file paths are listed below. Use those exact paths in your tool_calls.
- Do NOT make up project IDs. If no project exists yet, use create_project first.
- For enhance_photos, pass the actual image file paths as a list in "image_paths".
- Only call tools that are relevant to what the user asked. Do not call every tool.

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

REVIEW_PROMPT = """\
You are a quality reviewer for Travel Content Studio. Review the following AI response and tool execution results.
Check for: accuracy, completeness, tone appropriateness, and whether the user's request was fully addressed.

Original user request: {user_message}
AI response: {ai_reply}
Tool results: {tool_results}

Respond in JSON:
{{"quality_score": 1-10, "issues": ["list of issues if any"], "improved_reply": "optional improved version of the reply if score < 7", "passed": true/false}}
"""

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".insv"}
ARCHIVE_EXTENSIONS = {".zip"}

# Keyword-based intent classification for dynamic model routing
INTENT_KEYWORDS: dict[str, list[str]] = {
    "blog": ["blog", "article", "write a post", "travel story", "guide", "long form", "write about"],
    "script": ["script", "narration", "voiceover text", "dialogue", "storyboard"],
    "title": ["title", "headline", "name for", "heading", "hook"],
    "hashtags": ["hashtag", "tags", "keywords", "seo"],
    "scene_classification": ["analyze", "classify", "what kind of", "detect scene", "identify"],
    "photo_scene_detect": ["look at this photo", "describe this image", "what's in this picture"],
    "reel_script": ["reel", "short video", "instagram", "tiktok", "shorts"],
    "thumbnail_text": ["thumbnail", "cover image", "banner"],
    "social_posts": ["caption", "social media", "post for", "tweet", "facebook"],
}


def _classify_attachments(
    paths: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    images, videos, archives, other = [], [], [], []
    for p in paths:
        ext = "." + p.rsplit(".", 1)[-1].lower() if "." in p else ""
        if ext in IMAGE_EXTENSIONS:
            images.append(p)
        elif ext in VIDEO_EXTENSIONS:
            videos.append(p)
        elif ext in ARCHIVE_EXTENSIONS:
            archives.append(p)
        else:
            other.append(p)
    return images, videos, archives, other


_ZIP_MAX_FILES = 500
_ZIP_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
_RGLOB_MAX_DEPTH = 100


def _expand_directories_and_zips(paths: list[str]) -> list[str]:
    """Expand directories to their file contents and extract zip file listings."""
    expanded: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            base_depth = len(path.parts)
            for child in sorted(path.rglob("*")):
                if len(child.parts) - base_depth > _RGLOB_MAX_DEPTH:
                    continue
                if child.is_file() and not child.name.startswith("."):
                    expanded.append(str(child))
        elif path.suffix.lower() == ".zip" and path.is_file():
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    members = zf.infolist()
                    if len(members) > _ZIP_MAX_FILES:
                        raise ValueError(
                            f"Zip contains {len(members)} entries (limit {_ZIP_MAX_FILES})"
                        )
                    total_size = sum(m.file_size for m in members)
                    if total_size > _ZIP_MAX_TOTAL_BYTES:
                        raise ValueError(
                            f"Zip uncompressed size {total_size} exceeds limit "
                            f"{_ZIP_MAX_TOTAL_BYTES}"
                        )

                    extract_dir = (
                        Path(get_settings().data_dir) / "chat_uploads" / path.stem
                    )
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    resolved_base = extract_dir.resolve()

                    for member in members:
                        target = (extract_dir / member.filename).resolve()
                        if not target.is_relative_to(resolved_base):
                            raise ValueError(
                                f"Zip member escapes extract directory: {member.filename}"
                            )

                    zf.extractall(extract_dir)
                    for member in zf.namelist():
                        member_path = extract_dir / member
                        if member_path.resolve().is_file():
                            expanded.append(str(member_path))
            except Exception as exc:
                log.warning("zip_extraction_failed", path=p, error=str(exc))
                expanded.append(p)
        else:
            expanded.append(p)
    return expanded


def _build_attachment_context(
    images: list[str], videos: list[str], archives: list[str], other: list[str]
) -> str:
    parts: list[str] = []
    if images:
        parts.append(
            f"ATTACHED IMAGES ({len(images)} files) -- use these EXACT paths in tool_calls:\n"
            + "\n".join(f"  - {p}" for p in images)
        )
    if videos:
        parts.append(
            f"ATTACHED VIDEOS ({len(videos)} files) -- use these EXACT paths in tool_calls:\n"
            + "\n".join(f"  - {p}" for p in videos)
        )
    if archives:
        parts.append(f"Archives (already extracted above): {', '.join(archives)}")
    if other:
        parts.append(f"Other files: {', '.join(other)}")
    return "\n\n".join(parts)


def _classify_intent(message: str) -> str:
    """Classify user message intent for dynamic model routing."""
    msg_lower = message.lower()
    for task_type, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                return task_type
    return "chat"


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from an LLM response that might contain markdown fences or preamble."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        return {"reply": text, "tool_calls": []}

    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(text, brace_start)
        return obj
    except (json.JSONDecodeError, ValueError):
        return {"reply": text, "tool_calls": []}


TOOL_REGISTRY: dict[str, str] = {
    "create_project": "/projects",
    "import_video": "/videos/import",
    "transcribe": "/transcribe",
    "generate_content": "/generate",
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
    "run_agents": "/agents/run",
}

PROJECT_SCOPED_TOOLS = {
    "import_video", "generate_content", "generate_thumbnail",
    "generate_voiceover", "generate_blog", "run_agents",
}

TOOL_DEPENDENCIES: dict[str, set[str]] = {
    "import_video": {"create_project"},
    "transcribe": {"import_video"},
    "generate_content": {"create_project"},
    "generate_thumbnail": {"create_project"},
    "generate_voiceover": {"create_project"},
    "generate_blog": {"create_project"},
    "run_agents": {"create_project"},
    "color_grade": {"import_video"},
    "auto_reframe": {"import_video"},
    "add_captions": {"import_video"},
    "enhance_audio": {"import_video"},
    "smart_stitch": {"import_video"},
    "quality_check": {"import_video"},
}


def _has_dependency_conflict(tool_calls: list[dict]) -> bool:
    """Return True if any tool in the list depends on another tool also in the list."""
    tool_names = {tc.get("tool", "") for tc in tool_calls}
    for name in tool_names:
        deps = TOOL_DEPENDENCIES.get(name, set())
        if deps & tool_names:
            return True
    return False


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
        skills_summary = self.rules.get_skills_summary()
        return SYSTEM_PROMPT.format(
            rules_injection=rules_injection,
            style_injection=style_injection,
            memory_context="",
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

        # Expand directories and zip files into individual file paths
        expanded = _expand_directories_and_zips(attachments)
        images, videos, archives, other = _classify_attachments(expanded)

        user_parts = [message]
        if expanded:
            user_parts.append(_build_attachment_context(images, videos, archives, other))
        if project_id:
            user_parts.append(f"Current project ID: {project_id}")

        user_content = "\n\n".join(user_parts)

        system_prompt = self._build_system_prompt(project_id)

        # Build multi-turn message history BEFORE saving the current user message
        # to avoid duplicating it in the history
        history_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        recent_history = self.memory.get_recent_messages(project_id, limit=10)
        for hist_msg in recent_history:
            role = hist_msg.get("role", "user")
            content = hist_msg.get("content", "")
            if role in ("user", "assistant") and content:
                history_messages.append({"role": role, "content": content})
        history_messages.append({"role": "user", "content": user_content})

        # Save user message to memory AFTER building history to avoid duplication
        self.memory.add_message(
            project_id, "user", message,
            metadata={"attachments": expanded} if expanded else None,
        )

        # Dynamic model selection: classify intent, then pick the best model
        intent = _classify_intent(message)
        if intent == "chat":
            if images:
                intent = "photo_scene_detect"
            elif videos:
                intent = "script"

        # Check if user has selected a specific model on the dashboard
        from core.database import AsyncSessionLocal
        from models.db_models import Setting
        active_model = None
        try:
            async with AsyncSessionLocal() as session:
                setting = await session.get(Setting, "active_model")
                if setting and setting.value:
                    active_model = setting.value
        except Exception:
            pass

        vision_tasks = {"photo_scene_detect", "image_description", "thumbnail_analysis"}
        if active_model and intent not in vision_tasks:
            model = active_model
        else:
            model = await self._router.get_model(intent)
        model_used = model
        log.info("chat_model_selected", intent=intent, model=model)

        raw_reply = await self._call_ollama(model, system_prompt, user_content, messages=history_messages)
        parsed = _extract_json(raw_reply)

        reply_text = parsed.get("reply", raw_reply)
        tool_calls = parsed.get("tool_calls", [])

        # Handle inline "add_rule" from the LLM
        if parsed.get("add_rule"):
            self.rules.add_rule(parsed["add_rule"])

        actions_taken: list[dict[str, Any]] = []
        suggestions: list[str] = []

        # Execute tool calls: parallel when safe, sequential when dependencies exist
        if len(tool_calls) > 1 and not _has_dependency_conflict(tool_calls):
            actions_taken = await self._run_tools_parallel(
                tool_calls, project_id, images, videos
            )
        else:
            for tc in tool_calls:
                tool_name = tc.get("tool", "")
                args = tc.get("args", {})
                result = await self._execute_tool(
                    tool_name, args, project_id, images, videos
                )
                actions_taken.append(
                    {"tool": tool_name, "args": args, "result": result}
                )

        # Run review agent only when tool errors occurred
        review_result = None
        if actions_taken and any(
            a["result"].get("status") == "error" for a in actions_taken
        ):
            review_result = await self._run_review_agent(
                message, reply_text, actions_taken
            )
            if review_result and not review_result.get("passed", True):
                improved = review_result.get("improved_reply")
                if improved:
                    reply_text = improved

        if images and not tool_calls:
            suggestions.append("Enhance these photos for stock photography")
            suggestions.append("Generate a thumbnail from this image")
        if videos and not tool_calls:
            suggestions.append("Transcribe this video")
            suggestions.append("Apply cinematic color grading")
            suggestions.append("Generate captions for this video")
        if not tool_calls and not expanded:
            suggestions.append("Create a new project")
            suggestions.append("Generate a travel blog post")

        self.memory.add_message(
            project_id, "assistant", reply_text,
            metadata={
                "actions": [a["tool"] for a in actions_taken],
                "suggestions": suggestions,
                "model_used": model_used,
                "intent": intent,
            } if actions_taken or suggestions else None,
        )

        return {
            "reply": reply_text,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
            "model_used": model_used,
            "intent": intent,
            "review": review_result,
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

    async def _run_tools_parallel(
        self,
        tool_calls: list[dict],
        project_id: str | None,
        attached_images: list[str] | None = None,
        attached_videos: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute multiple tool calls concurrently (multi-agent pattern)."""
        async def _run_one(tc: dict) -> dict[str, Any]:
            tool_name = tc.get("tool", "")
            args = tc.get("args", {})
            result = await self._execute_tool(
                tool_name, args, project_id, attached_images, attached_videos
            )
            return {"tool": tool_name, "args": args, "result": result}

        results = await asyncio.gather(
            *[_run_one(tc) for tc in tool_calls],
            return_exceptions=True,
        )
        actions: list[dict[str, Any]] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tc = tool_calls[i]
                actions.append({
                    "tool": tc.get("tool", "unknown"),
                    "args": tc.get("args", {}),
                    "result": {"status": "error", "detail": str(r)},
                })
            else:
                actions.append(r)
        return actions

    async def _run_review_agent(
        self,
        user_message: str,
        ai_reply: str,
        actions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Run a review agent to check quality of the response."""
        try:
            review_model = await self._router.get_model("chat")
            prompt = REVIEW_PROMPT.format(
                user_message=user_message,
                ai_reply=ai_reply,
                tool_results=json.dumps(
                    [{"tool": a["tool"], "status": a["result"].get("status")} for a in actions]
                ),
            )
            raw = await self._call_ollama(review_model, prompt, "Review the above.")
            parsed = _extract_json(raw)
            return {
                "quality_score": parsed.get("quality_score", 0),
                "issues": parsed.get("issues", []),
                "improved_reply": parsed.get("improved_reply"),
                "passed": parsed.get("passed", True),
            }
        except Exception as exc:
            log.warning("review_agent_failed", error=str(exc))
            return None

    async def _call_ollama(
        self, model: str, system_prompt: str, user_message: str,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=600) as client:
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
            return json.dumps({"reply": f"I encountered an error connecting to the AI model: {exc}", "tool_calls": []})

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        project_id: Optional[str],
        attached_images: list[str] | None = None,
        attached_videos: list[str] | None = None,
    ) -> dict[str, Any]:
        endpoint = TOOL_REGISTRY.get(tool_name)
        if not endpoint:
            return {"status": "error", "detail": f"Unknown tool: {tool_name}"}

        if project_id and "project_id" not in args:
            args["project_id"] = project_id

        # Fix hallucinated paths: inject real attachment paths
        if tool_name == "enhance_photos" and attached_images:
            img_paths = args.get("image_paths", [])
            if isinstance(img_paths, str) or not img_paths:
                args["image_paths"] = attached_images
        if tool_name == "import_video" and attached_videos:
            fp = args.get("file_path", "")
            if not fp or not Path(fp).exists():
                if attached_videos:
                    args["file_path"] = attached_videos[0]

        base = f"http://127.0.0.1:{self._settings.api_port}/api/v1"
        if tool_name == "transcribe":
            video_id = args.get("video_id", "")
            url = f"{base}/videos/{video_id}/transcribe"
        elif tool_name in PROJECT_SCOPED_TOOLS and project_id:
            url = f"{base}/projects/{project_id}{endpoint}"
        else:
            url = f"{base}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=300) as client:
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
