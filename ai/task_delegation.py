from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TASK_TYPES = {
    "profile_review",
    "plan_build",
    "safety_review",
    "simulation_review",
    "answer_synthesis",
    "full_test",
}


@dataclass
class AgentSubtask:
    id: str
    task_type: str
    objective: str
    status: str
    suggested_tool: str
    context_query: str = ""
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "objective": self.objective,
            "status": self.status,
            "suggested_tool": self.suggested_tool,
            "context_query": self.context_query,
            "result": self.result,
        }


class AgentTaskGraph:
    def __init__(self) -> None:
        self.subtasks: list[AgentSubtask] = []

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgentTaskGraph":
        graph = cls()
        subtasks = data.get("subtasks") if isinstance(data, dict) else []
        if not isinstance(subtasks, list):
            return graph
        for item in subtasks:
            if not isinstance(item, dict):
                continue
            subtask = AgentSubtask(
                id=str(item.get("id") or ""),
                task_type=str(item.get("task_type") or ""),
                objective=str(item.get("objective") or ""),
                status=_status(item.get("status")),
                suggested_tool=str(item.get("suggested_tool") or ""),
                context_query=str(item.get("context_query") or ""),
                result=str(item.get("result") or ""),
            )
            if subtask.id and subtask.suggested_tool:
                graph.subtasks.append(subtask)
        graph._ensure_progress_marker()
        return graph

    def delegate(
        self,
        *,
        task_type: str,
        objective: str,
        context_query: str = "",
    ) -> dict:
        normalized_type = task_type if task_type in TASK_TYPES else "full_test"
        self.subtasks = _subtasks_for(normalized_type, objective=objective, context_query=context_query)
        return {
            "ok": True,
            "task_graph": self.to_dict(),
            "next_tool": self.next_tool(),
        }

    def next_tool(self) -> str:
        for item in self.subtasks:
            if item.status in {"pending", "in_progress"} and item.suggested_tool:
                return item.suggested_tool
        return ""

    def mark_tool_result(self, tool_name: str, result: dict[str, Any]) -> None:
        if not self.subtasks or tool_name == "delegate_task":
            return
        subtask = self._subtask_for_tool(tool_name)
        if subtask is None:
            return
        ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
        subtask.status = "completed" if ok else "blocked"
        subtask.result = _result_summary(tool_name, result)
        if ok:
            self._start_next_pending()

    def _subtask_for_tool(self, tool_name: str) -> AgentSubtask | None:
        for item in self.subtasks:
            if item.suggested_tool == tool_name and item.status in {"pending", "in_progress"}:
                return item
        for item in self.subtasks:
            if item.suggested_tool == tool_name:
                return item
        return None

    def _start_next_pending(self) -> None:
        if any(item.status == "in_progress" for item in self.subtasks):
            return
        for item in self.subtasks:
            if item.status == "pending":
                item.status = "in_progress"
                return

    def _ensure_progress_marker(self) -> None:
        if any(item.status == "in_progress" for item in self.subtasks):
            return
        for item in self.subtasks:
            if item.status == "pending":
                item.status = "in_progress"
                return

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtasks": [item.to_dict() for item in self.subtasks],
            "summary": {
                "total": len(self.subtasks),
                "pending": sum(1 for item in self.subtasks if item.status == "pending"),
                "in_progress": sum(1 for item in self.subtasks if item.status == "in_progress"),
                "completed": sum(1 for item in self.subtasks if item.status == "completed"),
                "blocked": sum(1 for item in self.subtasks if item.status == "blocked"),
            },
        }


def _subtasks_for(task_type: str, *, objective: str, context_query: str) -> list[AgentSubtask]:
    objective_text = str(objective or "完成 BJT 测试任务")
    context_text = str(context_query or objective_text)
    if task_type == "profile_review":
        return [
            AgentSubtask("profile", "profile_review", objective_text, "in_progress", "lookup_transistor", context_text),
            AgentSubtask("answer", "answer_synthesis", "汇总器件资料结论", "pending", "memory", context_text),
        ]
    if task_type == "plan_build":
        return [
            AgentSubtask("profile", "profile_review", "确认器件资料", "pending", "lookup_transistor", context_text),
            AgentSubtask("plan", "plan_build", objective_text, "in_progress", "build_test_plan", context_text),
        ]
    if task_type == "safety_review":
        return [AgentSubtask("safety", "safety_review", objective_text, "in_progress", "evaluate_plan_safety", context_text)]
    if task_type == "simulation_review":
        return [
            AgentSubtask("safety", "safety_review", "仿真前检查计划边界", "pending", "evaluate_plan_safety", context_text),
            AgentSubtask("simulation", "simulation_review", objective_text, "in_progress", "run_simulation", context_text),
            AgentSubtask("diagnosis", "answer_synthesis", "诊断仿真结果", "pending", "diagnose_result", context_text),
        ]
    if task_type == "answer_synthesis":
        return [AgentSubtask("answer", "answer_synthesis", objective_text, "in_progress", "session_search", context_text)]
    return [
        AgentSubtask("profile", "profile_review", "确认器件资料和本地库记录", "in_progress", "lookup_transistor", context_text),
        AgentSubtask("plan", "plan_build", "生成测试计划", "pending", "build_test_plan", context_text),
        AgentSubtask("safety", "safety_review", "评审计划安全边界", "pending", "evaluate_plan_safety", context_text),
        AgentSubtask("simulation", "simulation_review", "运行仿真", "pending", "run_simulation", context_text),
        AgentSubtask("diagnosis", "answer_synthesis", "诊断结果并生成回答", "pending", "diagnose_result", context_text),
    ]


def _result_summary(tool_name: str, result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    if not result.get("ok", False):
        return str(result.get("error") or "工具调用失败")
    if tool_name == "lookup_transistor":
        profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
        return "已确认 {0} 资料".format(profile.get("model", "器件"))
    if tool_name == "build_test_plan":
        plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
        return "已生成 {0} / {1} 计划".format(plan.get("model", "UNKNOWN"), plan.get("goal", "auto"))
    if tool_name == "evaluate_plan_safety":
        return "安全状态：{0}".format(result.get("status", "unknown"))
    if tool_name == "run_simulation":
        execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
        return "仿真完成" if not execution.get("aborted") else "仿真中止：{0}".format(execution.get("abort_reason", "unknown"))
    if tool_name == "diagnose_result":
        return "诊断标签：{0}".format(", ".join(result.get("diagnosis_tags", [])))
    if tool_name == "session_search":
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        return "检索命中 {0} 条".format(summary.get("matched", 0))
    return "工具调用完成"


def _status(value: Any) -> str:
    status = str(value or "pending")
    return status if status in {"pending", "in_progress", "completed", "blocked"} else "pending"
