"""Trip Analyzer agent: extracts locations, activities, timeline, and key moments."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.logging_config import get_logger
from models.db_models import Project, Transcript, Video

from .base import AgentResult, BaseAgent

log = get_logger(__name__)


class TripAnalyzerAgent(BaseAgent):
    name = "trip_analyzer"
    description = "Analyzes trip data to extract locations, activities, timeline, and key moments"
    dependencies: list[str] = []

    async def execute(self, project_id: str, context: dict) -> AgentResult:
        try:
            project_data = await self._gather_project_data(project_id)
            if not project_data["transcripts"] and not project_data["metadata"]:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output={},
                    error="No transcripts or video metadata available for analysis",
                )

            system_prompt = (
                "You are an expert travel content analyst. Your job is to analyze raw "
                "travel video transcripts and metadata to extract structured trip information.\n\n"
                "You MUST respond with valid JSON only, no markdown fences, no commentary.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "locations": [{"name": str, "type": str, "details": str}],\n'
                '  "activities": [{"name": str, "category": str, "duration_estimate": str}],\n'
                '  "timeline": [{"order": int, "event": str, "location": str, "time_of_day": str}],\n'
                '  "key_moments": [{"description": str, "why_memorable": str, "emotion": str}],\n'
                '  "summary": str\n'
                "}"
            )

            user_prompt = self._build_user_prompt(project_data, context)
            output = await self._generate_json(system_prompt, user_prompt)

            for key in ("locations", "activities", "timeline", "key_moments", "summary"):
                if key not in output:
                    output[key] = [] if key != "summary" else ""

            log.info(
                "trip_analysis_complete",
                project_id=project_id,
                locations=len(output["locations"]),
                activities=len(output["activities"]),
            )
            return AgentResult(agent_name=self.name, success=True, output=output)

        except Exception as exc:
            log.exception("trip_analyzer_failed", project_id=project_id)
            return AgentResult(agent_name=self.name, success=False, output={}, error=str(exc))

    async def _gather_project_data(self, project_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            select(Video)
            .where(Video.project_id == project_id)
            .options(selectinload(Video.transcript), selectinload(Video.scenes))
        )
        videos = result.scalars().all()

        transcripts: list[str] = []
        metadata: list[dict] = []
        scenes: list[dict] = []

        for video in videos:
            metadata.append({
                "filename": video.filename,
                "duration_ms": video.duration_ms,
                "camera_type": video.camera_type,
                "metadata": video.metadata_json,
            })
            if video.transcript:
                transcripts.append(video.transcript.full_text)
            for scene in video.scenes:
                scenes.append({
                    "start_ms": scene.start_ms,
                    "end_ms": scene.end_ms,
                    "scene_type": scene.scene_type,
                })

        return {"transcripts": transcripts, "metadata": metadata, "scenes": scenes}

    def _build_user_prompt(self, data: dict[str, Any], context: dict | None = None) -> str:
        parts = ["Analyze the following travel content and extract trip information.\n"]

        if data["transcripts"]:
            combined = "\n---\n".join(data["transcripts"])
            parts.append(f"## Transcripts\n{combined}\n")

        if data["metadata"]:
            parts.append(f"## Video Metadata\n{json.dumps(data['metadata'], indent=2)}\n")

        if data["scenes"]:
            parts.append(f"## Detected Scenes\n{json.dumps(data['scenes'], indent=2)}\n")

        user_text = (context or {}).get("text", "")
        if user_text:
            parts.append(f"## Additional User Instructions\n{user_text}\n")

        parts.append(
            "Extract ALL locations mentioned, activities performed, build a chronological "
            "timeline, and identify the most memorable key moments. Write a concise trip summary."
        )
        return "\n".join(parts)
