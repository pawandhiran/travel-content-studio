"""Pipeline orchestrator: resolves dependency order and runs agents."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Any

from core.event_bus import event_bus
from core.logging_config import get_logger
from services.ollama_client import OllamaClient

from .base import AgentResult

log = get_logger(__name__)

AGENT_REGISTRY: dict[str, type] = {}

DEPENDENCY_GRAPH: dict[str, list[str]] = {
    "trip_analyzer": [],
    "story_generator": ["trip_analyzer"],
    "seo_optimizer": ["trip_analyzer"],
    "thumbnail_planner": ["trip_analyzer"],
    "video_script_writer": ["story_generator"],
    "social_media_creator": ["story_generator"],
    "fact_checker": ["story_generator", "video_script_writer"],
    "publishing_assistant": [
        "seo_optimizer",
        "video_script_writer",
        "social_media_creator",
        "thumbnail_planner",
        "fact_checker",
    ],
}


def _register_agents() -> None:
    """Lazily import and register all agent classes."""
    if AGENT_REGISTRY:
        return

    from .fact_checker import FactCheckerAgent
    from .publishing_assistant import PublishingAssistantAgent
    from .seo_optimizer import SEOOptimizerAgent
    from .social_media_creator import SocialMediaCreatorAgent
    from .story_generator import StoryGeneratorAgent
    from .thumbnail_planner import ThumbnailPlannerAgent
    from .trip_analyzer import TripAnalyzerAgent
    from .video_script_writer import VideoScriptWriterAgent

    for cls in (
        TripAnalyzerAgent,
        StoryGeneratorAgent,
        SEOOptimizerAgent,
        ThumbnailPlannerAgent,
        VideoScriptWriterAgent,
        SocialMediaCreatorAgent,
        FactCheckerAgent,
        PublishingAssistantAgent,
    ):
        AGENT_REGISTRY[cls.name] = cls


def _topological_sort(agent_names: list[str]) -> list[str]:
    """Return *agent_names* in dependency-first order (Kahn's algorithm)."""
    relevant = set(agent_names)
    in_degree: dict[str, int] = {n: 0 for n in relevant}
    adj: dict[str, list[str]] = defaultdict(list)

    for name in relevant:
        for dep in DEPENDENCY_GRAPH.get(name, []):
            if dep in relevant:
                adj[dep].append(name)
                in_degree[name] += 1

    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child in adj[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(ordered) != len(relevant):
        cycle = relevant - set(ordered)
        raise ValueError(f"Circular dependency detected among agents: {cycle}")

    return ordered


class AgentOrchestrator:
    """Resolves dependencies and runs agents in correct order."""

    def __init__(self, ollama_client: OllamaClient, db_session):
        _register_agents()
        self.ollama = ollama_client
        self.db = db_session
        self._status: dict[str, str] = {}

    async def run_pipeline(
        self,
        project_id: str,
        agent_names: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, AgentResult]:
        context = dict(context) if context else {}
        results: dict[str, AgentResult] = {}
        skipped: set[str] = set()

        ordered = _topological_sort(agent_names)
        total = len(ordered)
        log.info("pipeline_start", project_id=project_id, agents=ordered)

        await event_bus.broadcast("agent_pipeline", {
            "project_id": project_id,
            "status": "started",
            "agents": ordered,
        })

        for idx, name in enumerate(ordered):
            deps = DEPENDENCY_GRAPH.get(name, [])
            failed_deps = [d for d in deps if d in skipped]
            if failed_deps:
                log.warning("agent_skipped", agent=name, reason=f"dependency failed: {failed_deps}")
                self._status[name] = "skipped"
                skipped.add(name)
                results[name] = AgentResult(
                    agent_name=name,
                    success=False,
                    output={},
                    error=f"Skipped: upstream dependency failed ({', '.join(failed_deps)})",
                )
                await self._broadcast_progress(project_id, name, "skipped", idx, total)
                continue

            self._status[name] = "running"
            await self._broadcast_progress(project_id, name, "running", idx, total)

            try:
                agent_cls = AGENT_REGISTRY[name]
                agent = agent_cls(self.ollama, self.db)

                dep_context = dict(context)
                for dep in deps:
                    if dep in results and results[dep].success:
                        dep_context[dep] = results[dep].output

                result = await agent.execute(project_id, dep_context)
                results[name] = result

                if result.success:
                    self._status[name] = "completed"
                    context[name] = result.output
                    log.info("agent_completed", agent=name)
                else:
                    self._status[name] = "failed"
                    skipped.add(name)
                    log.error("agent_failed", agent=name, error=result.error)

                await self._broadcast_progress(
                    project_id, name, self._status[name], idx + 1, total
                )

            except Exception as exc:
                log.exception("agent_exception", agent=name)
                self._status[name] = "failed"
                skipped.add(name)
                results[name] = AgentResult(
                    agent_name=name,
                    success=False,
                    output={},
                    error=str(exc),
                )
                await self._broadcast_progress(project_id, name, "failed", idx + 1, total)

        await event_bus.broadcast("agent_pipeline", {
            "project_id": project_id,
            "status": "completed",
            "results": {n: r.success for n, r in results.items()},
        })

        log.info("pipeline_complete", project_id=project_id, results={n: r.success for n, r in results.items()})
        return results

    async def _broadcast_progress(
        self, project_id: str, agent: str, status: str, current: int, total: int
    ) -> None:
        await event_bus.broadcast("agent_progress", {
            "project_id": project_id,
            "agent": agent,
            "status": status,
            "current": current,
            "total": total,
            "progress_pct": int((current / total) * 100) if total else 0,
        })
