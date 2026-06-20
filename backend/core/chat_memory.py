"""Persistent conversation memory for the AI chat agent."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ulid import ULID

from core.logging_config import get_logger

log = get_logger(__name__)

_SAFE_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ChatMemory:
    """Stores and retrieves conversation history per project with full-text search."""

    def __init__(self, data_dir: Path) -> None:
        self.history_dir = data_dir / "chat_history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _conversation_path(self, project_id: str | None) -> Path:
        key = project_id or "__global__"
        if key != "__global__" and not _SAFE_PROJECT_ID_RE.match(key):
            raise ValueError(f"Invalid project_id: {key!r}")
        return self.history_dir / f"{key}.json"

    def _load_conversation(self, project_id: str | None) -> dict[str, Any]:
        path = self._conversation_path(project_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("corrupt_conversation_file", path=str(path))
        now = datetime.now(timezone.utc).isoformat()
        return {
            "project_id": project_id,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

    def _save_conversation(
        self, project_id: str | None, data: dict[str, Any]
    ) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = self._conversation_path(project_id)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, str(path))
        except BaseException:
            os.unlink(tmp_path)
            raise

    def add_message(
        self,
        project_id: str | None,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append a message and return its id."""
        conv = self._load_conversation(project_id)
        msg_id = str(ULID())
        entry: dict[str, Any] = {
            "id": msg_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            entry["metadata"] = metadata
        conv["messages"].append(entry)
        self._save_conversation(project_id, conv)
        return msg_id

    def get_recent_messages(
        self, project_id: str | None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the most recent *limit* messages for a project (or global)."""
        conv = self._load_conversation(project_id)
        return conv["messages"][-limit:]

    def get_context_summary(self, project_id: str | None) -> str:
        """Build a human-readable summary of past interactions for prompt injection."""
        recent = self.get_recent_messages(project_id, limit=20)
        if not recent:
            return ""

        lines: list[str] = ["Previous conversation context:"]
        for msg in recent:
            role = msg["role"].capitalize()
            text = msg["content"]
            if len(text) > 300:
                text = text[:297] + "..."
            lines.append(f"  {role}: {text}")
        return "\n".join(lines)

    def search_history(self, query: str) -> list[dict[str, Any]]:
        """Search all conversations for messages containing the query string."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for path in self.history_dir.glob("*.json"):
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            pid = conv.get("project_id")
            for msg in conv.get("messages", []):
                if query_lower in msg.get("content", "").lower():
                    results.append({**msg, "project_id": pid})
        results.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        return results[:50]

    def get_history(
        self, project_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return conversation history. If project_id is None, returns global."""
        conv = self._load_conversation(project_id)
        return conv["messages"][-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate stats across all conversations."""
        total_messages = 0
        total_conversations = 0
        for path in self.history_dir.glob("*.json"):
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
                total_conversations += 1
                total_messages += len(conv.get("messages", []))
            except (json.JSONDecodeError, OSError):
                continue
        return {
            "total_messages": total_messages,
            "total_conversations": total_conversations,
        }

    def list_conversations(self) -> list[dict[str, Any]]:
        """Return a summary of all saved conversations, newest first."""
        conversations: list[dict[str, Any]] = []
        for path in self.history_dir.glob("*.json"):
            if path.suffix != ".json" or path.name.endswith(".tmp"):
                continue
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
                msgs = conv.get("messages", [])
                if not msgs:
                    continue
                first_user_msg = ""
                for m in msgs:
                    if m.get("role") == "user" and m.get("content", "").strip():
                        first_user_msg = m["content"][:100]
                        break
                last_msg = msgs[-1]
                conv_id = path.stem
                conversations.append({
                    "id": conv_id,
                    "project_id": conv.get("project_id"),
                    "title": first_user_msg or "New conversation",
                    "message_count": len(msgs),
                    "last_message": last_msg.get("content", "")[:80],
                    "last_role": last_msg.get("role", ""),
                    "updated_at": conv.get("updated_at", ""),
                    "created_at": conv.get("created_at", ""),
                })
            except (json.JSONDecodeError, OSError):
                continue
        conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return conversations

    def start_new_conversation(self, project_id: str | None = None) -> str:
        """Start a new conversation and return its ID. Does NOT delete old ones."""
        import uuid
        conv_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "project_id": project_id,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        path = self.history_dir / f"{conv_id}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return conv_id

    def clear_history(self, project_id: str | None = None) -> None:
        """Clear history for a project, or all history if project_id is None."""
        if project_id is not None:
            path = self._conversation_path(project_id)
            if path.exists():
                path.unlink()
            log.info("history_cleared", project_id=project_id)
        else:
            for path in self.history_dir.glob("*.json"):
                path.unlink()
            log.info("all_history_cleared")
