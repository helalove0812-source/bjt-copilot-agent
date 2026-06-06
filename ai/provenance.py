from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ProvenanceEvent:
    event_id: str
    event_type: str
    timestamp: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    parent_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProvenanceDAG:
    def __init__(self) -> None:
        self._events: list[ProvenanceEvent] = []
        self._counter = 0

    def record(
        self,
        event_type: str,
        summary: str,
        *,
        payload: dict[str, Any] | None = None,
        parent_ids: list[str] | None = None,
    ) -> ProvenanceEvent:
        self._counter += 1
        event = ProvenanceEvent(
            event_id="evt_{0:04d}".format(self._counter),
            event_type=str(event_type or "event"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary=str(summary or ""),
            payload=_compact(payload or {}),
            parent_ids=list(parent_ids or []),
        )
        self._events.append(event)
        return event

    def record_tool_call(self, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> ProvenanceEvent:
        status = "ok" if result.get("ok", False) else "failed"
        return self.record(
            "tool_call",
            "tool {0} {1}".format(name, status),
            payload={
                "tool": name,
                "arguments": arguments,
                "ok": bool(result.get("ok", False)),
                "blocked_reason": result.get("blocked_reason"),
                "error": result.get("error"),
            },
        )

    def to_dict(self, *, limit: int | None = None) -> dict[str, Any]:
        events = self._events[-limit:] if limit else self._events
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return {
            "event_count": len(self._events),
            "event_type_counts": counts,
            "events": [event.to_dict() for event in events],
        }

    def notebook_lines(self, *, limit: int = 12) -> list[str]:
        return [
            "[{0}] {1}: {2}".format(event.event_id, event.event_type, event.summary)
            for event in self._events[-max(1, int(limit or 12)) :]
        ]


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _scalar_summary(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                result["..."] = "truncated"
                break
            result[str(key)] = _compact(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        compacted = [_compact(item, depth=depth + 1) for item in value[:8]]
        if len(value) > 8:
            compacted.append({"...": "truncated", "total": len(value)})
        return compacted
    return _scalar_summary(value)


def _scalar_summary(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
