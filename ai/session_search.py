from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class SessionSearchHit:
    kind: str
    title: str
    text: str
    score: int
    payload: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "score": self.score,
            "payload": self.payload,
        }


class SessionSearchStore:
    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self.context = context if isinstance(context, dict) else {}
        self._documents = _build_documents(self.context)

    def search(self, query: str = "", kind: str = "", limit: int = 5) -> dict:
        terms = _terms(query)
        wanted_kind = str(kind or "").strip()
        scored: list[SessionSearchHit] = []
        for item in self._documents:
            if wanted_kind and item.kind != wanted_kind:
                continue
            score = _score(item, terms)
            if terms and score <= 0:
                continue
            scored.append(
                SessionSearchHit(
                    kind=item.kind,
                    title=item.title,
                    text=item.text,
                    score=score,
                    payload=item.payload,
                )
            )
        scored.sort(key=lambda item: (item.score, item.kind, item.title), reverse=True)
        capped = max(1, min(int(limit or 5), 12))
        return {
            "ok": True,
            "query": query,
            "kind": wanted_kind or "all",
            "hits": [item.to_dict() for item in scored[:capped]],
            "summary": {
                "total_documents": len(self._documents),
                "matched": len(scored),
            },
        }


@dataclass(frozen=True)
class _SessionDocument:
    kind: str
    title: str
    text: str
    payload: dict[str, Any]


def _build_documents(context: dict[str, Any]) -> list[_SessionDocument]:
    docs: list[_SessionDocument] = []
    state = context.get("conversation_state") if isinstance(context.get("conversation_state"), dict) else {}
    current_plan = context.get("current_plan") if isinstance(context.get("current_plan"), dict) else {}
    if not current_plan and isinstance(state, dict):
        current_plan = state.get("current_plan") if isinstance(state.get("current_plan"), dict) else {}
    if current_plan:
        model = str(current_plan.get("model") or "UNKNOWN")
        goal = str(current_plan.get("goal") or "")
        docs.append(
            _SessionDocument(
                kind="plan",
                title=f"当前计划 {model}",
                text=" ".join(
                    str(item)
                    for item in [
                        model,
                        goal,
                        current_plan.get("mode"),
                        current_plan.get("safety_summary"),
                        current_plan.get("safety_notes"),
                    ]
                    if item
                ),
                payload=current_plan,
            )
        )

    messages = context.get("messages")
    if isinstance(messages, list):
        for index, item in enumerate(messages[-24:]):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            docs.append(
                _SessionDocument(
                    kind="message",
                    title=f"{role or 'message'} #{index + 1}",
                    text=content,
                    payload={"role": role, "content": content},
                )
            )

    logs = context.get("logs")
    if isinstance(logs, list):
        for index, item in enumerate(logs[-40:]):
            text = str(item or "").strip()
            if text:
                docs.append(_SessionDocument(kind="log", title=f"日志 #{index + 1}", text=text, payload={"text": text}))

    measurements = context.get("measurements")
    if isinstance(measurements, list) and measurements:
        summary = _measurement_summary(measurements)
        docs.append(_SessionDocument(kind="measurement", title="测量摘要", text=summary, payload={"count": len(measurements)}))

    if isinstance(state, dict):
        for key in ("pending_profile_model", "pending_profile_fields", "candidate_profile", "pending_library_action"):
            value = state.get(key)
            if value:
                docs.append(
                    _SessionDocument(
                        kind="state",
                        title=key,
                        text=f"{key}: {value}",
                        payload={key: value},
                    )
                )
    task_graph = context.get("task_graph")
    if not isinstance(task_graph, dict) and isinstance(state, dict):
        task_graph = state.get("task_graph")
    if isinstance(task_graph, dict):
        subtasks = task_graph.get("subtasks")
        if isinstance(subtasks, list) and subtasks:
            text = " ".join(
                "{0} {1} {2} {3}".format(
                    item.get("id", ""),
                    item.get("status", ""),
                    item.get("objective", ""),
                    item.get("suggested_tool", ""),
                )
                for item in subtasks
                if isinstance(item, dict)
            )
            docs.append(_SessionDocument(kind="task_graph", title="任务图", text=text, payload=task_graph))
    return docs


def _measurement_summary(measurements: list[Any]) -> str:
    numeric: dict[str, list[float]] = {}
    for item in measurements:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            try:
                numeric.setdefault(str(key), []).append(float(value))
            except (TypeError, ValueError):
                continue
    parts = [f"count {len(measurements)}"]
    for key in ("beta", "ic", "Ic", "vce", "Vce", "vbe", "Vbe"):
        values = numeric.get(key)
        if values:
            parts.append(f"{key} {min(values):.4g}..{max(values):.4g}")
    return " ".join(parts)


def _terms(query: str) -> list[str]:
    raw = str(query or "").lower()
    terms = [part for part in raw.replace("/", " ").split() if part.strip()]
    terms.extend(re.findall(r"[a-z]+[0-9][a-z0-9-]*|[0-9]+[a-z][a-z0-9-]*", raw))
    for keyword in ("当前", "计划", "历史", "日志", "结果", "上次", "已有", "会话", "测量", "任务", "继续", "下一步"):
        if keyword in raw:
            terms.append(keyword)
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped


def _score(item: _SessionDocument | SessionSearchHit, terms: list[str]) -> int:
    if not terms:
        return 1
    haystack = f"{item.kind} {item.title} {item.text}".lower()
    return sum(haystack.count(term) for term in terms)
