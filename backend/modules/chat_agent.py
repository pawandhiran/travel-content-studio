"""Conversational AI agent that orchestrates all TCS features."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from config import get_settings
from core.logging_config import get_logger
from core.model_router import ModelRouter

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

Respond in JSON with this exact schema:
{"reply": "your conversational message", "tool_calls": [{"tool": "tool_name", "args": {...}}]}

Always return valid JSON. Do not include anything outside the JSON object.\
"""

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".insv"}


def _classify_attachments(
    paths: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Classify attachment paths into images, videos, and other."""
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


class ChatAgent:
    """Conversational AI that orchestrates all TCS features via Ollama."""

    def __init__(self) -> None:
        self._router = ModelRouter()
        self._settings = get_settings()

    async def process_message(
        self,
        message: str,
        project_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        attachments = attachments or []
        images, videos, other = _classify_attachments(attachments)

        user_parts = [message]
        if attachments:
            user_parts.append(_build_attachment_context(images, videos, other))
        if project_id:
            user_parts.append(f"Current project ID: {project_id}")

        user_content = "\n\n".join(user_parts)

        model = await self._router.get_model("agent_trip_analyzer")
        raw_reply = await self._call_ollama(model, user_content)
        parsed = _extract_json(raw_reply)

        reply_text = parsed.get("reply", raw_reply)
        tool_calls = parsed.get("tool_calls", [])

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

        return {
            "reply": reply_text,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
        }

    async def _call_ollama(self, model: str, user_message: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
        """Execute a tool via the internal API endpoints."""
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
