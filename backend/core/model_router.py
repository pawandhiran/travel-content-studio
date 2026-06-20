"""Intelligent model router -- selects the best LLM per task type."""

from __future__ import annotations

import time
from typing import Any

from core.logging_config import get_logger
from config import get_settings

log = get_logger(__name__)

TASK_MODEL_MAP: dict[str, dict[str, str]] = {
    "light": {
        "default": "qwen3:8b",
        "tasks": [
            "title", "hashtags", "seo_keywords", "hook", "chapter_markers",
            "captions", "reel_cta", "thumbnail_text",
        ],
    },
    "medium": {
        "default": "qwen3:14b",
        "tasks": [
            "chat", "script", "narration", "youtube_desc", "social_posts",
            "seo_description", "reel_script", "youtube_tags",
        ],
    },
    "heavy": {
        "default": "qwen3:32b",
        "fallback": "qwen3:14b",
        "tasks": [
            "blog", "guide", "article", "travel_story", "documentary",
            "video_script", "agent_publishing", "agent_story",
        ],
    },
    "analysis": {
        "default": "gemma3:12b",
        "fallback": "qwen3:14b",
        "tasks": [
            "scene_classification", "trip_analysis", "content_grouping",
            "fact_checking", "agent_trip_analyzer", "agent_seo",
            "agent_fact_checker", "quality_assessment",
        ],
    },
    "vision": {
        "default": "llava:13b",
        "fallback": "gemma3:12b",
        "tasks": [
            "photo_scene_detect", "thumbnail_analysis", "image_description",
        ],
    },
}


class ModelRouter:
    """Selects the optimal model for each task based on complexity and available models."""

    _instance: ModelRouter | None = None
    _available_models: list[str] | None = None
    _overrides: dict[str, str] = {}
    _cache_ttl: float = 300
    _last_refresh: float = 0

    def __new__(cls) -> ModelRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_model(self, task_type: str) -> str:
        """Get the best available model for a task type."""
        if task_type in self._overrides:
            return self._overrides[task_type]

        tier = self._get_tier(task_type)
        if not tier:
            log.warning("unknown_task_type", task=task_type)
            return "qwen3:14b"

        tier_config = TASK_MODEL_MAP[tier]
        preferred = tier_config["default"]
        fallback = tier_config.get("fallback", "qwen3:14b")

        available = await self._get_available_models()
        if preferred in available:
            return preferred
        if fallback in available:
            log.info("model_fallback", task=task_type, preferred=preferred, using=fallback)
            return fallback

        if available:
            model = available[0]
            log.warning("model_last_resort", task=task_type, using=model)
            return model

        return preferred

    def _get_tier(self, task_type: str) -> str | None:
        for tier_name, config in TASK_MODEL_MAP.items():
            if task_type in config["tasks"]:
                return tier_name
        return None

    async def _get_available_models(self) -> list[str]:
        """Query Ollama for installed models, cached for 5 min."""
        now = time.time()
        if self._available_models is not None and (now - self._last_refresh) < self._cache_ttl:
            return self._available_models

        try:
            import httpx

            settings = get_settings()
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.ollama_host}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    self._available_models = [m["name"] for m in data.get("models", [])]
                    self._last_refresh = now
                    log.info("models_refreshed", count=len(self._available_models))
                    return self._available_models
        except Exception:
            log.debug("ollama_model_list_failed")

        return self._available_models or []

    def set_override(self, task_type: str, model: str) -> None:
        self._overrides[task_type] = model

    def clear_override(self, task_type: str) -> None:
        self._overrides.pop(task_type, None)

    def get_task_map(self) -> dict:
        """Return the full task-to-model mapping for UI display."""
        result: dict[str, Any] = {}
        for tier_name, config in TASK_MODEL_MAP.items():
            for task in config["tasks"]:
                result[task] = {
                    "tier": tier_name,
                    "default_model": config["default"],
                    "fallback": config.get("fallback"),
                    "override": self._overrides.get(task),
                }
        return result

    def get_recommended_downloads(self, ram_gb: float) -> list[str]:
        """Models to download based on system RAM."""
        if ram_gb >= 32:
            return ["qwen3:8b", "qwen3:14b", "qwen3:32b", "gemma3:12b", "llava:13b"]
        elif ram_gb >= 16:
            return ["qwen3:8b", "qwen3:14b", "gemma3:12b"]
        else:
            return ["qwen3:8b"]


model_router = ModelRouter()
