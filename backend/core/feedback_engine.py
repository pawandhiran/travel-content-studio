"""Feedback engine -- learns from user behavior to improve AI outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from config import get_settings

log = get_logger(__name__)


class FeedbackEngine:
    """Tracks user preferences and adapts AI behavior over time."""

    _instance: FeedbackEngine | None = None

    def __new__(cls) -> FeedbackEngine:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._profile: dict[str, Any] = {}
            inst._feedback_log: list[dict] = []
            inst._profile_path: Path | None = None
            cls._instance = inst
        return cls._instance

    def initialize(self, data_dir: Path | None = None) -> None:
        """Load existing profile from disk."""
        if data_dir is None:
            data_dir = get_settings().data_dir
        self._profile_path = data_dir / "user_profile.json"
        if self._profile_path.exists():
            self._profile = json.loads(self._profile_path.read_text())
            log.info("profile_loaded", preferences=len(self._profile))
        else:
            self._profile = self._default_profile()

    def _default_profile(self) -> dict:
        return {
            "writing_style": {
                "tone": "neutral",
                "detail_level": "medium",
                "vocabulary": "general",
                "humor": False,
                "emoji_use": False,
            },
            "content_preferences": {
                "title_style": "descriptive",
                "blog_length": "medium",
                "hashtag_count": 20,
                "keyword_density": "moderate",
            },
            "photo_preferences": {
                "color_grade_preset": None,
                "sharpening_level": "medium",
                "noise_reduction_level": "moderate",
                "preferred_crop_ratio": None,
            },
            "model_performance": {},
            "task_history": {},
            "feedback_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save(self) -> None:
        """Persist profile to disk."""
        if self._profile_path:
            self._profile["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._profile_path.write_text(json.dumps(self._profile, indent=2))

    # --- Feedback recording ---

    def record_generation(
        self, task_type: str, model: str, content_id: str, params: dict | None = None,
    ) -> None:
        """Record that content was generated (before user interacts with it)."""
        self._feedback_log.append({
            "event": "generated",
            "task_type": task_type,
            "model": model,
            "content_id": content_id,
            "params": params,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_regeneration(
        self, task_type: str, model: str, content_id: str, reason: str | None = None,
    ) -> None:
        """User regenerated content -- they didn't like the first output."""
        self._update_model_stats(model, kept=False)
        self._update_task_stats(task_type, regenerated=True)
        self._profile["feedback_count"] += 1
        self._save()
        log.info("feedback_regeneration", task=task_type, model=model, reason=reason)

    def record_edit(self, task_type: str, content_id: str, original: str, edited: str) -> None:
        """User manually edited AI output -- analyze what changed."""
        changes = self._analyze_edit(original, edited)
        if changes.get("length_change"):
            if changes["length_ratio"] > 1.3:
                self._adjust_preference("detail_level", "detailed")
            elif changes["length_ratio"] < 0.7:
                self._adjust_preference("detail_level", "brief")

        self._profile["feedback_count"] += 1
        self._save()
        log.info("feedback_edit", task=task_type, changes=changes)

    def record_rating(self, task_type: str, model: str, content_id: str, rating: int) -> None:
        """User rated content 1-5."""
        self._update_model_stats(model, kept=(rating >= 3), rating=rating)
        self._update_task_stats(task_type, rating=rating)
        self._profile["feedback_count"] += 1
        self._save()
        log.info("feedback_rating", task=task_type, model=model, rating=rating)

    def record_kept(self, task_type: str, model: str, content_id: str) -> None:
        """User accepted/used the generated content without changes."""
        self._update_model_stats(model, kept=True)
        self._update_task_stats(task_type, kept=True)
        self._save()

    def record_photo_override(self, auto_preset: str, user_preset: str, scene_type: str) -> None:
        """User changed the auto-selected photo preset."""
        photo_prefs = self._profile["photo_preferences"]
        if not photo_prefs.get("scene_overrides"):
            photo_prefs["scene_overrides"] = {}
        photo_prefs["scene_overrides"][scene_type] = user_preset
        self._save()
        log.info("feedback_photo_override", scene=scene_type, auto=auto_preset, user=user_preset)

    # --- Preference retrieval ---

    def get_style_prompt_injection(self) -> str:
        """Generate a prompt snippet reflecting learned user preferences."""
        style = self._profile.get("writing_style", {})
        prefs = self._profile.get("content_preferences", {})

        parts: list[str] = []
        if style.get("tone") == "casual":
            parts.append("Use a casual, conversational tone.")
        elif style.get("tone") == "formal":
            parts.append("Use a professional, formal tone.")

        if style.get("detail_level") == "detailed":
            parts.append("Be thorough and detailed in your response.")
        elif style.get("detail_level") == "brief":
            parts.append("Keep your response concise and brief.")

        if style.get("humor"):
            parts.append("Feel free to include light humor where appropriate.")

        if prefs.get("title_style") == "clickbait":
            parts.append("Make titles attention-grabbing and curiosity-driven.")
        elif prefs.get("title_style") == "minimal":
            parts.append("Keep titles simple and straightforward.")

        if not parts:
            return ""
        return (
            "\n\nUser style preferences (learned from past feedback):\n"
            + "\n".join(f"- {p}" for p in parts)
        )

    def get_preferred_model_for_task(self, task_type: str) -> str | None:
        """If user consistently rates one model higher for a task, recommend it."""
        task_stats = self._profile.get("task_history", {}).get(task_type, {})
        return task_stats.get("preferred_model")

    def get_photo_preset_override(self, scene_type: str) -> str | None:
        """If user always overrides a scene type preset, use their preference."""
        return (
            self._profile
            .get("photo_preferences", {})
            .get("scene_overrides", {})
            .get(scene_type)
        )

    def get_profile_summary(self) -> dict:
        """Return profile for display in Settings UI."""
        return {
            "feedback_count": self._profile.get("feedback_count", 0),
            "writing_style": self._profile.get("writing_style", {}),
            "content_preferences": self._profile.get("content_preferences", {}),
            "photo_preferences": self._profile.get("photo_preferences", {}),
            "model_performance": self._profile.get("model_performance", {}),
            "updated_at": self._profile.get("updated_at"),
        }

    def reset_profile(self) -> None:
        """Reset all learned preferences."""
        self._profile = self._default_profile()
        self._save()
        log.info("profile_reset")

    # --- Internal helpers ---

    def _update_model_stats(
        self, model: str, kept: bool = True, rating: int | None = None,
    ) -> None:
        stats = self._profile.setdefault("model_performance", {})
        if model not in stats:
            stats[model] = {"kept": 0, "regenerated": 0, "total_rating": 0, "rating_count": 0}
        if kept:
            stats[model]["kept"] += 1
        else:
            stats[model]["regenerated"] += 1
        if rating is not None:
            stats[model]["total_rating"] += rating
            stats[model]["rating_count"] += 1

    def _update_task_stats(
        self,
        task_type: str,
        kept: bool = False,
        regenerated: bool = False,
        rating: int | None = None,
    ) -> None:
        history = self._profile.setdefault("task_history", {})
        if task_type not in history:
            history[task_type] = {
                "count": 0, "kept": 0, "regenerated": 0,
                "total_rating": 0, "rating_count": 0,
            }
        history[task_type]["count"] += 1
        if kept:
            history[task_type]["kept"] += 1
        if regenerated:
            history[task_type]["regenerated"] += 1
        if rating is not None:
            history[task_type]["total_rating"] += rating
            history[task_type]["rating_count"] += 1

    def _adjust_preference(self, key: str, value: str) -> None:
        """Gradually shift a preference based on repeated signals."""
        style = self._profile["writing_style"]
        current = style.get(key)
        if current != value:
            style[key] = value
            log.info("preference_adjusted", key=key, old=current, new=value)

    def _analyze_edit(self, original: str, edited: str) -> dict:
        """Analyze what the user changed in the AI output."""
        orig_len = len(original)
        edit_len = len(edited)
        return {
            "original_length": orig_len,
            "edited_length": edit_len,
            "length_change": edit_len - orig_len,
            "length_ratio": edit_len / max(orig_len, 1),
        }


feedback_engine = FeedbackEngine()
