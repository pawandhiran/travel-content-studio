"""User-defined rules and reusable skills for the AI assistant."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ulid import ULID

from core.logging_config import get_logger

log = get_logger(__name__)


class UserRulesManager:
    """Manages persistent rules (prompt injections) and multi-step skill workflows."""

    def __init__(self, data_dir: Path) -> None:
        self.rules_path = data_dir / "chat_rules.json"
        self.skills_path = data_dir / "chat_skills.json"
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        if not self.rules_path.exists():
            self._save_rules([])
        if not self.skills_path.exists():
            self._save_skills(self._default_skills())

    def _backup_and_reset(self, path: Path) -> None:
        """Rename corrupt file to .bak before returning defaults."""
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            path.rename(bak)
            log.warning("corrupt_file_backed_up", original=str(path), backup=str(bak))
        except OSError:
            log.warning("corrupt_file_delete_failed", path=str(path))

    # ------------------------------------------------------------------
    # Rules -- persistent instructions injected into every prompt
    # ------------------------------------------------------------------

    def _load_rules(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("Expected a list")
            return data
        except (json.JSONDecodeError, ValueError):
            self._backup_and_reset(self.rules_path)
            return []
        except OSError:
            return []

    def _save_rules(self, rules: list[dict[str, Any]]) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.rules_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(rules, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, str(self.rules_path))
        except BaseException:
            os.unlink(tmp_path)
            raise

    def add_rule(self, rule: str, category: str = "general") -> str:
        rules = self._load_rules()
        rule_id = str(ULID())
        rules.append({
            "id": rule_id,
            "rule": rule,
            "category": category,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save_rules(rules)
        log.info("rule_added", rule_id=rule_id, category=category)
        return rule_id

    def remove_rule(self, rule_id: str) -> bool:
        rules = self._load_rules()
        before = len(rules)
        rules = [r for r in rules if r["id"] != rule_id]
        if len(rules) == before:
            return False
        self._save_rules(rules)
        log.info("rule_removed", rule_id=rule_id)
        return True

    def list_rules(self) -> list[dict[str, Any]]:
        return self._load_rules()

    def get_rules_prompt_injection(self) -> str:
        """Format all active rules into a section for the system prompt."""
        rules = self._load_rules()
        if not rules:
            return ""
        lines = ["User-defined rules (always follow these):"]
        for r in rules:
            lines.append(f"- [{r['category']}] {r['rule']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Skills -- reusable multi-step workflows
    # ------------------------------------------------------------------

    def _load_skills(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.skills_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("Expected a list")
            return data
        except (json.JSONDecodeError, ValueError):
            self._backup_and_reset(self.skills_path)
            return self._default_skills()
        except OSError:
            return self._default_skills()

    def _save_skills(self, skills: list[dict[str, Any]]) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.skills_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(skills, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, str(self.skills_path))
        except BaseException:
            os.unlink(tmp_path)
            raise

    def add_skill(
        self, name: str, description: str, steps: list[dict[str, Any]]
    ) -> str:
        skills = self._load_skills()
        skill_id = str(ULID())
        skills.append({
            "id": skill_id,
            "name": name,
            "description": description,
            "steps": steps,
            "built_in": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save_skills(skills)
        log.info("skill_added", skill_id=skill_id, name=name)
        return skill_id

    def remove_skill(self, skill_id: str) -> bool:
        skills = self._load_skills()
        before = len(skills)
        skills = [s for s in skills if s["id"] != skill_id or s.get("built_in")]
        if len(skills) == before:
            return False
        self._save_skills(skills)
        log.info("skill_removed", skill_id=skill_id)
        return True

    def list_skills(self) -> list[dict[str, Any]]:
        return self._load_skills()

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        for s in self._load_skills():
            if s["id"] == skill_id:
                return s
        return None

    def find_skill_by_name(self, name: str) -> dict[str, Any] | None:
        name_lower = name.lower().strip()
        for s in self._load_skills():
            if s["name"].lower() == name_lower:
                return s
        for s in self._load_skills():
            if name_lower in s["name"].lower():
                return s
        return None

    def get_skills_summary(self) -> str:
        """Format skill list for prompt injection."""
        skills = self._load_skills()
        if not skills:
            return ""
        lines = ["Available skills the user has defined:"]
        for s in skills:
            tag = " (built-in)" if s.get("built_in") else ""
            lines.append(f"- {s['name']}{tag}: {s['description']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Default built-in skills
    # ------------------------------------------------------------------

    @staticmethod
    def _default_skills() -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        base = {"built_in": True, "created_at": now}
        return [
            {
                **base,
                "id": "builtin-youtube-package",
                "name": "Full YouTube Package",
                "description": "Transcribe, generate script, titles, description, chapters, tags, thumbnail, and blog post",
                "steps": [
                    {"tool": "transcribe", "args": {}},
                    {"tool": "generate_content", "args": {"type": "script"}},
                    {"tool": "generate_content", "args": {"type": "title"}},
                    {"tool": "generate_content", "args": {"type": "youtube_package"}},
                    {"tool": "generate_thumbnail", "args": {"prompt": "auto"}},
                    {"tool": "generate_blog", "args": {"type": "blog"}},
                ],
            },
            {
                **base,
                "id": "builtin-instagram-reel",
                "name": "Quick Instagram Reel",
                "description": "Reframe to 9:16, color grade, add captions, quality check",
                "steps": [
                    {"tool": "auto_reframe", "args": {"aspect": "9:16"}},
                    {"tool": "color_grade", "args": {"preset": "vibrant"}},
                    {"tool": "add_captions", "args": {"style": "modern"}},
                    {"tool": "quality_check", "args": {"platform": "instagram_reels"}},
                ],
            },
            {
                **base,
                "id": "builtin-stock-photo-batch",
                "name": "Stock Photo Batch",
                "description": "Enhance all photos with Stock Ready mode and generate Shutterstock metadata",
                "steps": [
                    {"tool": "enhance_photos", "args": {"mode": "stock_ready"}},
                ],
            },
            {
                **base,
                "id": "builtin-travel-blog-from-video",
                "name": "Travel Blog from Video",
                "description": "Transcribe video, run trip analyzer agent, generate travel blog",
                "steps": [
                    {"tool": "transcribe", "args": {}},
                    {"tool": "run_agents", "args": {"agents": ["trip_analyzer", "story_generator"]}},
                    {"tool": "generate_blog", "args": {"type": "guide"}},
                ],
            },
        ]
