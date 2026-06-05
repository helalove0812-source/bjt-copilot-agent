from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


VALID_TODO_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


@dataclass
class TodoStore:
    items: list[dict[str, str]] = field(default_factory=list)

    def read(self) -> list[dict[str, str]]:
        return [dict(item) for item in self.items]

    def write(self, todos: list[dict[str, Any]], *, merge: bool = False) -> list[dict[str, str]]:
        normalized = [_normalize_todo(item) for item in todos]
        if not merge:
            self.items = _dedupe_todos(normalized)
            return self.read()
        by_id = {item["id"]: dict(item) for item in self.items}
        order = [item["id"] for item in self.items]
        for item in normalized:
            if item["id"] not in by_id:
                order.append(item["id"])
            by_id[item["id"]] = item
        self.items = [by_id[item_id] for item_id in order if item_id in by_id]
        return self.read()

    def summary(self) -> dict:
        return {
            "total": len(self.items),
            "pending": sum(1 for item in self.items if item["status"] == "pending"),
            "in_progress": sum(1 for item in self.items if item["status"] == "in_progress"),
            "completed": sum(1 for item in self.items if item["status"] == "completed"),
            "cancelled": sum(1 for item in self.items if item["status"] == "cancelled"),
        }


class MemoryStore:
    def __init__(self, path: Path | None = None, *, max_entries: int = 80) -> None:
        self.path = path or Path("config/agent_memory.json")
        self.max_entries = max_entries

    def read(self, target: str = "project") -> dict:
        payload = self._load()
        key = _memory_target(target)
        return {"target": key, "entries": list(payload.get(key, []))}

    def add(self, content: str, target: str = "project") -> dict:
        text = str(content or "").strip()
        if not text:
            return {"ok": False, "error": "content is required"}
        block_reason = _memory_block_reason(text)
        if block_reason:
            return {"ok": False, "error": block_reason}
        payload = self._load()
        key = _memory_target(target)
        entries = [str(item) for item in payload.get(key, [])]
        if text not in entries:
            entries.append(text)
        payload[key] = entries[-self.max_entries :]
        self._save(payload)
        return {"ok": True, **self.read(key)}

    def remove(self, needle: str, target: str = "project") -> dict:
        query = str(needle or "").strip()
        if not query:
            return {"ok": False, "error": "needle is required"}
        payload = self._load()
        key = _memory_target(target)
        entries = [str(item) for item in payload.get(key, [])]
        remaining = [item for item in entries if query not in item]
        payload[key] = remaining
        self._save(payload)
        return {"ok": True, "removed": len(entries) - len(remaining), **self.read(key)}

    def _load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {"project": [], "user": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"project": [], "user": []}
        if not isinstance(payload, dict):
            return {"project": [], "user": []}
        return {
            "project": [str(item) for item in payload.get("project", []) if str(item).strip()],
            "user": [str(item) for item in payload.get("user", []) if str(item).strip()],
        }

    def _save(self, payload: dict[str, list[str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        clean = {
            "project": [str(item) for item in payload.get("project", []) if str(item).strip()],
            "user": [str(item) for item in payload.get("user", []) if str(item).strip()],
        }
        self.path.write_text(json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_todo(item: dict[str, Any]) -> dict[str, str]:
    item_id = str(item.get("id") or "").strip() or "?"
    content = str(item.get("content") or "").strip() or "(no description)"
    status = str(item.get("status") or "pending").strip().lower()
    if status not in VALID_TODO_STATUSES:
        status = "pending"
    return {"id": item_id, "content": content, "status": status}


def _dedupe_todos(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for item in items:
        if item["id"] not in seen:
            order.append(item["id"])
        seen[item["id"]] = item
    return [seen[item_id] for item_id in order]


def _memory_target(target: str) -> str:
    return "user" if str(target or "").strip().lower() == "user" else "project"


def _memory_block_reason(content: str) -> str:
    lowered = content.lower()
    risky = (
        "ignore previous instructions",
        "disregard all instructions",
        "system prompt override",
        "do not tell the user",
        "authorized_keys",
        ".env",
        "api_key",
        "secret",
        "password",
    )
    for marker in risky:
        if marker in lowered:
            return "memory content blocked because it looks like prompt-injection or secret material"
    return ""
