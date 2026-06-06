from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from core.types import HwConfig

from ai.assistant import summarize_execution_with_ai, summarize_plan_with_ai
from ai.experiment_summary import summarize_experiment_records
from ai.llm_client import LLMUnavailable, chat_text
from ai.prompt_layers import PromptLayers, make_volatile
from ai.session_search import SessionSearchStore
from ai.task_delegation import AgentTaskGraph
from ai.test_planner import TestPlan, extract_model_guess
from ai.tool_runtime import BJTToolRuntime, ToolCallRecord


@dataclass(frozen=True)
class ToolCallingAgentResult:
    response: str
    tool_calls: list[dict] = field(default_factory=list)
    plan: dict | None = None
    execution: dict | None = None
    used_ai_api: bool = False
    llm_provider: str = "local"
    llm_usage: dict = field(default_factory=dict)
    agent_state: str = "idle"
    next_actions: list[str] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    memory: dict = field(default_factory=dict)
    task_graph: dict = field(default_factory=dict)
    pending_plan_update: dict | None = None

    def to_dict(self) -> dict:
        return {
            "response": self.response,
            "tool_calls": self.tool_calls,
            "plan": self.plan,
            "execution": self.execution,
            "used_ai_api": self.used_ai_api,
            "llm_provider": self.llm_provider,
            "llm_usage": self.llm_usage,
            "agent_state": self.agent_state,
            "next_actions": self.next_actions,
            "todos": self.todos,
            "memory": self.memory,
            "task_graph": self.task_graph,
            "pending_plan_update": self.pending_plan_update,
            "agent_mode": "tool_calling",
        }


class ToolCallingAgent:
    def __init__(
        self,
        *,
        cfg: HwConfig | None = None,
        output_dir: Path | None = None,
        max_steps: int = 7,
        runtime: BJTToolRuntime | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        restored_context = context if isinstance(context, dict) else {}
        self.context = restored_context
        self.runtime = runtime or BJTToolRuntime(
            cfg=cfg,
            output_dir=output_dir,
            session_search_store=SessionSearchStore(restored_context),
            task_graph=AgentTaskGraph.from_dict(_task_graph_from_context(restored_context)),
            current_plan=_plan_from_context(restored_context),
            pending_plan_update=_pending_plan_update_from_context(restored_context),
        )
        self.max_steps = max_steps

    def run_turn(self, text: str, *, mode: str = "simulation") -> ToolCallingAgentResult:
        records: list[ToolCallRecord] = []
        provider = "local"
        usage: dict = {}
        used_ai = False
        final_response = ""
        next_actions: list[str] = []

        for step_index in range(self.max_steps):
            decision, decision_used_ai, decision_provider, decision_usage = self._decide_next_tool(
                text=text,
                mode=mode,
                records=records,
                step_index=step_index,
            )
            used_ai = used_ai or decision_used_ai
            provider = _merge_provider(provider, decision_provider if decision_used_ai else "")
            usage = _merge_usage(usage, decision_usage)

            if decision.get("action") == "final":
                final_response = str(decision.get("response") or "")
                next_actions = [str(item) for item in decision.get("next_actions", []) if str(item).strip()]
                if not final_response:
                    final_response = summarize_experiment_records([record.to_dict() for record in records])
                break

            tool_name = str(decision.get("tool") or "")
            arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
            record = self.runtime.dispatch(tool_name, arguments)
            records.append(record)
            if not record.result.get("ok", False) and step_index >= 1:
                final_response = "工具调用失败：{0}".format(record.result.get("error", "未知错误"))
                break

        plan = self.runtime.current_plan.to_dict() if self.runtime.current_plan else None
        execution = self.runtime.current_execution
        if not final_response:
            experiment_response = summarize_experiment_records([record.to_dict() for record in records])
            if experiment_response:
                final_response = experiment_response
            else:
                final_response, summary_used_ai, summary_provider, summary_usage = self._summarize(text, plan, execution)
                used_ai = used_ai or summary_used_ai
                provider = _merge_provider(provider, summary_provider if summary_used_ai else "")
                usage = _merge_usage(usage, summary_usage)

        if not next_actions:
            next_actions = _default_next_actions(plan, execution)

        return ToolCallingAgentResult(
            response=final_response,
            tool_calls=[record.to_dict() for record in records],
            plan=plan,
            execution=execution,
            used_ai_api=used_ai,
            llm_provider=provider,
            llm_usage=usage,
            agent_state=_agent_state(plan, execution),
            next_actions=next_actions,
            todos=self.runtime.todo_store.read(),
            memory={
                "project": self.runtime.memory_store.read("project").get("entries", []),
                "user": self.runtime.memory_store.read("user").get("entries", []),
            },
            task_graph=self.runtime.task_graph.to_dict(),
            pending_plan_update=self.runtime.pending_plan_update,
        )

    def _decide_next_tool(
        self,
        *,
        text: str,
        mode: str,
        records: list[ToolCallRecord],
        step_index: int,
    ) -> tuple[dict, bool, str, dict]:
        if os.getenv("BJT_AI_MODE", "local") != "cloud":
            return _local_decision(
                text,
                mode,
                records,
                self.runtime.task_graph.to_dict(),
                current_plan=self.runtime.current_plan,
                context=self.context,
            ), False, "local", {}

        layers = _tool_call_prompt_layers(
            text=text,
            mode=mode,
            step_index=step_index,
            runtime=self.runtime,
            records=records,
        )
        try:
            result = chat_text(system_text=layers.system_text(), user_text=layers.user_text(), timeout_s=20)
            decision = _parse_json_object(result.text)
            decision = _normalize_decision(decision, self.runtime.schemas())
            forced_decision = _required_pending_plan_update_decision(text, records, context=self.context)
            forced_decision = forced_decision or _required_grid_refine_decision(
                text,
                records,
                decision,
                current_plan=self.runtime.current_plan,
                context=self.context,
            )
            forced_decision = forced_decision or _required_task_graph_decision(text, mode, records, self.runtime.task_graph.to_dict())
            forced_decision = forced_decision or _required_plan_only_decision(text, mode, records, decision)
            if forced_decision:
                decision = forced_decision
            return decision, True, "{0}:{1}".format(result.provider, result.model), result.usage
        except (LLMUnavailable, ValueError, TypeError) as exc:
            decision = _local_decision(
                text,
                mode,
                records,
                self.runtime.task_graph.to_dict(),
                current_plan=self.runtime.current_plan,
                context=self.context,
            )
            decision["fallback_reason"] = str(exc) or exc.__class__.__name__
            return decision, False, "local", {}

    def _summarize(self, text: str, plan: dict | None, execution: dict | None) -> tuple[str, bool, str, dict]:
        if execution:
            return summarize_execution_with_ai(execution)
        if self.runtime.pending_plan_update:
            return _pending_plan_update_response(self.runtime.pending_plan_update), False, "local", {}
        if self.runtime.current_plan:
            return summarize_plan_with_ai(self.runtime.current_plan, text)
        return "我还没有形成可执行计划。请提供晶体管型号和测试目标。", False, "local", {}


def _local_decision(
    text: str,
    mode: str,
    records: list[ToolCallRecord],
    task_graph: dict | None = None,
    current_plan: TestPlan | None = None,
    context: dict[str, Any] | None = None,
) -> dict:
    called = [record.name for record in records]
    model = _model_from_text_or_records(text, records)
    wants_execute = any(word in text for word in ("执行", "仿真", "运行", "跑一下", "开始"))
    wants_adaptive = any(word in text for word in ("自适应", "主动布点", "表征", "研究这个器件", "研究这个管子", "characterize", "adaptive"))
    wants_spice = any(word in text.lower() for word in ("spice", "digital twin", "model card", ".model")) or any(
        word in text for word in ("数字孪生", "模型卡", "器件模型", "生成模型")
    )
    wants_residual_followup = any(word in text for word in ("残差", "补测", "下一步测什么", "继续测什么", "诊断补测")) or any(
        word in text.lower() for word in ("residual", "followup", "follow-up")
    )
    wants_run_followup = wants_residual_followup and (
        any(word in text for word in ("执行补测", "跑补测", "继续补测", "按补测计划测", "执行这些补测"))
        or any(word in text.lower() for word in ("run followup", "execute followup", "run follow-up"))
    )
    wants_unknown_device = _wants_unknown_device_autonomy(text)
    plan_only = _wants_plan_only(text)
    complex_task = wants_execute or wants_adaptive or any(word in text for word in ("完整", "全套", "然后", "并", "先", "再"))
    wants_session = any(word in text for word in ("之前", "刚才", "当前", "历史", "日志", "结果", "上次", "已有", "会话"))
    has_task_graph = bool((task_graph or {}).get("subtasks"))

    if _pending_plan_update_from_context(context) and _is_affirmation(text) and "apply_plan_update" not in called:
        return {"action": "call_tool", "tool": "apply_plan_update", "arguments": {"confirmed": True}}
    if "apply_plan_update" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["运行仿真", "继续调整计划", "查看器件资料"],
        }
    if current_plan and _wants_grid_refinement(text, context) and "propose_plan_update" not in called:
        return _propose_grid_update_decision()
    if current_plan and "propose_plan_update" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["确认应用修改", "继续调整计划", "取消修改"],
        }
    if wants_unknown_device and "autonomous_unknown_device_report" not in called:
        return {
            "action": "call_tool",
            "tool": "autonomous_unknown_device_report",
            "arguments": {
                "mode": mode if mode in {"simulation", "hardware"} else "simulation",
                "goal": text,
                "allow_hardware": False,
                "token_valid": True,
                "characterization_iterations": 3,
                "batch_size": 2,
                "followup_budget": 3,
            },
        }
    if wants_unknown_device and "autonomous_unknown_device_report" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["查看候选 pinout", "继续残差补测", "导出 SPICE 模型卡"],
        }
    if complex_task and not has_task_graph and "delegate_task" not in called:
        return _delegate_task_decision(text, wants_execute=(wants_execute or wants_adaptive) and not plan_only)
    if wants_adaptive and current_plan and "run_adaptive_characterization" not in called:
        return {
            "action": "call_tool",
            "tool": "run_adaptive_characterization",
            "arguments": {
                "mode": mode if mode in {"simulation", "hardware"} else "simulation",
                "iterations": 3,
                "batch_size": 2,
                "allow_hardware": False,
                "token_valid": True,
            },
        }
    if wants_adaptive and "run_adaptive_characterization" in called:
        if wants_spice and "extract_spice_twin" not in called:
            return {"action": "call_tool", "tool": "extract_spice_twin", "arguments": {"include_model_card": True}}
        if wants_run_followup and "run_residual_followup" not in called:
            return {
                "action": "call_tool",
                "tool": "run_residual_followup",
                "arguments": {"mode": mode if mode in {"simulation", "hardware"} else "simulation", "budget": 3, "allow_hardware": False, "token_valid": True},
            }
        if wants_run_followup and "run_residual_followup" in called:
            return {
                "action": "final",
                "response": "",
                "next_actions": ["查看补测残差变化", "继续补测", "导出模型卡"],
            }
        if wants_residual_followup and "plan_residual_followup" not in called:
            return {"action": "call_tool", "tool": "plan_residual_followup", "arguments": {"budget": 4}}
        return {
            "action": "final",
            "response": "",
            "next_actions": ["查看 belief", "继续补测", "生成模型"],
        }
    delegated = _decision_from_task_graph(text, mode, records, task_graph or {})
    if delegated:
        return delegated
    if wants_session and "session_search" not in called:
        return {"action": "call_tool", "tool": "session_search", "arguments": {"query": text, "limit": 5}}
    if wants_session and "session_search" in called:
        return {
            "action": "final",
            "response": _session_search_response(records),
            "next_actions": ["继续生成计划", "查看执行日志", "运行仿真"],
        }
    if wants_spice and "extract_spice_twin" not in called:
        return {"action": "call_tool", "tool": "extract_spice_twin", "arguments": {"include_model_card": True}}
    if wants_run_followup and "run_residual_followup" not in called:
        return {
            "action": "call_tool",
            "tool": "run_residual_followup",
            "arguments": {"mode": mode if mode in {"simulation", "hardware"} else "simulation", "budget": 3, "allow_hardware": False, "token_valid": True},
        }
    if wants_run_followup and "run_residual_followup" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["查看补测残差变化", "继续补测", "导出模型卡"],
        }
    if wants_residual_followup and "plan_residual_followup" not in called:
        return {"action": "call_tool", "tool": "plan_residual_followup", "arguments": {"budget": 4}}
    if wants_spice and "extract_spice_twin" in called:
        if wants_run_followup and "run_residual_followup" not in called:
            return {
                "action": "call_tool",
                "tool": "run_residual_followup",
                "arguments": {"mode": mode if mode in {"simulation", "hardware"} else "simulation", "budget": 3, "allow_hardware": False, "token_valid": True},
            }
        if wants_residual_followup and "plan_residual_followup" not in called:
            return {"action": "call_tool", "tool": "plan_residual_followup", "arguments": {"budget": 4}}
        return {
            "action": "final",
            "response": "",
            "next_actions": ["复制模型卡", "查看残差诊断", "继续补测"],
        }
    if "lookup_transistor" not in called:
        return {"action": "call_tool", "tool": "lookup_transistor", "arguments": {"model": model}}
    if "build_test_plan" not in called:
        return {
            "action": "call_tool",
            "tool": "build_test_plan",
            "arguments": {
                "model": model,
                "goal": "full" if wants_adaptive else _goal_from_text(text),
                "depth": "standard",
                "mode": mode if mode in {"simulation", "hardware"} else "simulation",
            },
        }
    if plan_only:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["运行仿真", "调整计划", "查看器件资料"],
        }
    if wants_execute and "evaluate_plan_safety" not in called:
        return {
            "action": "call_tool",
            "tool": "evaluate_plan_safety",
            "arguments": {"mode": "simulation", "allow_hardware": False, "token_valid": True},
        }
    if wants_execute and "run_simulation" not in called:
        return {"action": "call_tool", "tool": "run_simulation", "arguments": {}}
    if wants_execute and "diagnose_result" not in called:
        return {"action": "call_tool", "tool": "diagnose_result", "arguments": {"text": text}}
    return {
        "action": "final",
        "response": "",
        "next_actions": ["运行仿真", "调整计划", "查看器件资料"],
    }


def _tool_call_prompt_layers(
    *,
    text: str,
    mode: str,
    step_index: int,
    runtime: BJTToolRuntime,
    records: list[ToolCallRecord],
) -> PromptLayers:
    return PromptLayers(
        stable={
            "identity": "BJT 测试系统的 tool-calling agent",
            "protocol": [
                "像 Hermes Agent 一样通过工具推进任务：先看已有工具结果，再决定下一步调用一个工具，或给出最终回答。",
                "只输出 JSON 对象，不要输出 Markdown。",
                "不要输出隐藏推理链。",
            ],
            "safety_policy": [
                "硬件执行只能建议预检或确认；simulation 工具可直接执行，真实硬件工具必须遵守 allow_hardware/token_valid。",
                "如果用户只要求方案/计划/测试方案，不要运行仿真，也不要编造仿真结果。",
                "如果用户要求调整/细化/增加测试点，优先调用 propose_plan_update；等待用户确认后才调用 apply_plan_update。",
            ],
            "tool_policy": [
                "复杂任务优先调用 delegate_task 生成子任务图，再按子任务建议调用具体工具。",
                "如果还没有计划，通常先 lookup_transistor 或 build_test_plan。",
                "如果已有计划且用户要求仿真，可以 evaluate_plan_safety 后 run_simulation。",
                "危险或真实硬件工具应先用 dry_run=true 预演前置条件、安全合同和所需确认，再请求真实执行。",
            ],
            "response_schema": {
                "action": "call_tool or final",
                "tool": "tool name when action=call_tool",
                "arguments": "object arguments for the tool",
                "response": "Chinese final answer when action=final",
                "next_actions": "optional Chinese next action labels",
            },
        },
        context={
            "available_tools": [schema.to_llm_schema() for schema in runtime.schemas()],
            "current_plan": runtime.current_plan.to_dict() if runtime.current_plan else None,
            "pending_plan_update": runtime.pending_plan_update,
            "current_task_graph": runtime.task_graph.to_dict(),
            "next_tool_from_task_graph": runtime.task_graph.next_tool(),
        },
        volatile=make_volatile(
            user_message=text,
            requested_mode=mode,
            step_index=step_index,
            previous_tool_results=[record.to_dict() for record in records],
        ),
    )


def _required_task_graph_decision(
    text: str,
    mode: str,
    records: list[ToolCallRecord],
    task_graph: dict | None,
) -> dict | None:
    called = [record.name for record in records]
    wants_execute = any(word in text for word in ("执行", "仿真", "运行", "跑一下", "开始"))
    plan_only = _wants_plan_only(text)
    complex_task = wants_execute or any(word in text for word in ("完整", "全套", "然后", "并", "先", "再"))
    has_task_graph = bool((task_graph or {}).get("subtasks"))
    if complex_task and not has_task_graph and "delegate_task" not in called:
        return _delegate_task_decision(text, wants_execute=wants_execute and not plan_only)
    return None


def _required_plan_only_decision(
    text: str,
    mode: str,
    records: list[ToolCallRecord],
    decision: dict,
) -> dict | None:
    if not _wants_plan_only(text):
        return None
    unsafe_tools = {"evaluate_plan_safety", "preflight_plan", "run_simulation", "diagnose_result"}
    called = [record.name for record in records]
    if str(decision.get("tool") or "") == "delegate_task":
        arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        if arguments.get("task_type") == "full_test":
            return _delegate_task_decision(text, wants_execute=False)
    if "build_test_plan" in called and (
        decision.get("action") == "final" or str(decision.get("tool") or "") in unsafe_tools
    ):
        return {
            "action": "final",
            "response": "",
            "next_actions": ["运行仿真", "调整计划", "查看器件资料"],
        }
    if str(decision.get("tool") or "") in unsafe_tools:
        model = _model_from_text_or_records(text, records)
        if "lookup_transistor" not in called:
            return {"action": "call_tool", "tool": "lookup_transistor", "arguments": {"model": model}}
        return {
            "action": "call_tool",
            "tool": "build_test_plan",
            "arguments": {
                "model": model,
                "goal": _goal_from_text(text),
                "depth": "standard",
                "mode": mode if mode in {"simulation", "hardware"} else "simulation",
            },
        }
    return None


def _required_pending_plan_update_decision(
    text: str,
    records: list[ToolCallRecord],
    *,
    context: dict[str, Any] | None,
) -> dict | None:
    called = [record.name for record in records]
    if _pending_plan_update_from_context(context) and _is_affirmation(text) and "apply_plan_update" not in called:
        return {"action": "call_tool", "tool": "apply_plan_update", "arguments": {"confirmed": True}}
    if "apply_plan_update" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["运行仿真", "继续调整计划", "查看器件资料"],
        }
    return None


def _required_grid_refine_decision(
    text: str,
    records: list[ToolCallRecord],
    decision: dict,
    *,
    current_plan: TestPlan | None,
    context: dict[str, Any] | None,
) -> dict | None:
    if not current_plan or not _wants_grid_refinement(text, context):
        return None
    called = [record.name for record in records]
    if "propose_plan_update" in called:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["确认应用修改", "继续调整计划", "取消修改"],
        }
    if str(decision.get("tool") or "") == "propose_plan_update":
        return None
    unsafe_tools = {"delegate_task", "build_test_plan", "evaluate_plan_safety", "preflight_plan", "run_simulation", "diagnose_result", "apply_plan_update"}
    if decision.get("action") == "final" or str(decision.get("tool") or "") in unsafe_tools:
        return _propose_grid_update_decision()
    return None


def _propose_grid_update_decision() -> dict:
    return {
        "action": "call_tool",
        "tool": "propose_plan_update",
        "arguments": {
            "update_type": "grid_density",
            "vcc_step_v": 0.2,
            "vbb_step_v": 0.1,
            "rationale": "用户要求细化扫描步进，建议提高 Vcc/Vbb 网格密度；只生成待确认提案，不执行仿真。",
            "requires_confirmation": True,
        },
    }


def _delegate_task_decision(text: str, *, wants_execute: bool) -> dict:
    return {
        "action": "call_tool",
        "tool": "delegate_task",
        "arguments": {
            "task_type": "full_test" if wants_execute else "plan_build",
            "objective": text,
            "context_query": text,
        },
    }


def _wants_plan_only(text: str) -> bool:
    lowered = text.lower()
    asks_for_plan = any(word in text for word in ("方案", "计划", "测试方案", "测试计划", "怎么测", "如何测"))
    asks_for_execution = any(word in text for word in ("执行", "仿真", "运行", "跑一下", "开始", "测一下", "测一遍")) or any(
        word in lowered for word in ("simulate", "run", "execute")
    )
    return asks_for_plan and not asks_for_execution


def _wants_unknown_device_autonomy(text: str) -> bool:
    lowered = text.lower()
    has_unknown_device = any(word in text for word in ("未知三脚", "不知道型号", "未知型号", "三脚器件", "三端器件", "不知道是什么"))
    wants_autonomy = any(word in text for word in ("自己搞清楚", "自主", "端到端", "表征报告", "搞清楚它是什么", "判器件类型"))
    return (has_unknown_device and wants_autonomy) or any(
        phrase in lowered
        for phrase in (
            "unknown three-pin",
            "unknown 3-pin",
            "identify unknown device",
            "autonomous characterization",
        )
    )


def _wants_grid_refinement(text: str, context: dict[str, Any] | None = None) -> bool:
    lowered = text.lower()
    explicit = any(
        word in text
        for word in (
            "增多测试点",
            "增加测试点",
            "多加测试点",
            "细化步进",
            "细化步进点",
            "加密步进",
            "加密测试点",
            "加密扫描",
            "更多测试点",
            "步进更细",
            "点更密",
        )
    ) or any(word in lowered for word in ("more points", "finer step", "denser grid"))
    if explicit:
        return True
    if not _is_affirmation(text):
        return False
    previous = _latest_assistant_text(context)
    if not previous:
        return False
    has_refine_proposal = any(word in previous for word in ("细化", "加密", "增加测试点", "更新计划", "VCC 改为", "Vbb 改为", "0.2V", "0.1V"))
    return has_refine_proposal and "执行硬件" not in previous


def _is_affirmation(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"是", "确认", "可以", "好的", "好", "按这个", "就这样", "yes", "ok", "继续"}


def _latest_assistant_text(context: dict[str, Any] | None) -> str:
    if not isinstance(context, dict):
        return ""
    messages = context.get("messages")
    if not isinstance(messages, list):
        nested = context.get("conversation_state")
        messages = nested.get("messages") if isinstance(nested, dict) else []
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or item.get("text") or "")
        if role == "assistant" and content.strip():
            return content
    return ""


def _model_from_text_or_records(text: str, records: list[ToolCallRecord]) -> str:
    for record in records:
        profile = record.result.get("profile") if isinstance(record.result, dict) else None
        if isinstance(profile, dict) and profile.get("model"):
            return str(profile["model"])
        plan = record.result.get("plan") if isinstance(record.result, dict) else None
        if isinstance(plan, dict) and plan.get("model"):
            return str(plan["model"])
    return extract_model_guess(text)


def _decision_from_task_graph(
    text: str,
    mode: str,
    records: list[ToolCallRecord],
    task_graph: dict,
) -> dict | None:
    subtasks = task_graph.get("subtasks") if isinstance(task_graph, dict) else []
    if not isinstance(subtasks, list) or not subtasks:
        return None
    next_task = next(
        (
            item
            for item in subtasks
            if isinstance(item, dict) and item.get("status") in {"in_progress", "pending"} and item.get("suggested_tool")
        ),
        None,
    )
    if not next_task:
        return {
            "action": "final",
            "response": "",
            "next_actions": ["解释结果", "调整计划", "查看任务图"],
        }
    tool_name = str(next_task.get("suggested_tool") or "")
    decision_text = " ".join(item for item in [text, str(next_task.get("context_query") or "")] if item)
    return _decision_for_tool(tool_name, text=decision_text, mode=mode, records=records)


def _decision_for_tool(tool_name: str, *, text: str, mode: str, records: list[ToolCallRecord]) -> dict:
    model = _model_from_text_or_records(text, records)
    if tool_name == "lookup_transistor":
        return {"action": "call_tool", "tool": "lookup_transistor", "arguments": {"model": model}}
    if tool_name == "build_test_plan":
        return {
            "action": "call_tool",
            "tool": "build_test_plan",
            "arguments": {
                "model": model,
                "goal": _goal_from_text(text),
                "depth": "standard",
                "mode": mode if mode in {"simulation", "hardware"} else "simulation",
            },
        }
    if tool_name == "evaluate_plan_safety":
        return {
            "action": "call_tool",
            "tool": "evaluate_plan_safety",
            "arguments": {"mode": "simulation", "allow_hardware": False, "token_valid": True},
        }
    if tool_name == "run_simulation":
        return {"action": "call_tool", "tool": "run_simulation", "arguments": {}}
    if tool_name == "diagnose_result":
        return {"action": "call_tool", "tool": "diagnose_result", "arguments": {"text": text}}
    if tool_name == "session_search":
        return {"action": "call_tool", "tool": "session_search", "arguments": {"query": text, "limit": 5}}
    if tool_name == "memory":
        return {"action": "call_tool", "tool": "memory", "arguments": {"action": "read", "target": "project"}}
    return {"action": "call_tool", "tool": tool_name, "arguments": {}}


def _session_search_response(records: list[ToolCallRecord]) -> str:
    search = next((record for record in records if record.name == "session_search"), None)
    hits = (search.result.get("hits") if search and isinstance(search.result, dict) else []) or []
    if not hits:
        return "我没有在当前会话里找到相关计划、日志或结果。"
    lines = ["我在当前会话里找到这些相关内容："]
    for item in hits[:3]:
        lines.append("- {0}：{1}".format(item.get("title", item.get("kind", "记录")), item.get("text", "")))
    return "\n".join(lines)


def _goal_from_text(text: str) -> str:
    if "饱和" in text or "vce" in text.lower():
        return "vce_sat"
    if "曲线" in text or "curve" in text.lower():
        return "curves"
    if "beta" in text.lower() or "增益" in text:
        return "beta"
    return "auto"


def _task_graph_from_context(context: dict[str, Any]) -> dict | None:
    direct = context.get("task_graph")
    if isinstance(direct, dict):
        return direct
    nested = context.get("conversation_state")
    if isinstance(nested, dict) and isinstance(nested.get("task_graph"), dict):
        return nested.get("task_graph")
    return None


def _pending_plan_update_from_context(context: dict[str, Any] | None) -> dict | None:
    if not isinstance(context, dict):
        return None
    direct = context.get("pending_plan_update")
    if isinstance(direct, dict):
        return direct
    nested = context.get("conversation_state")
    if isinstance(nested, dict) and isinstance(nested.get("pending_plan_update"), dict):
        return nested.get("pending_plan_update")
    return None


def _pending_plan_update_response(update: dict[str, Any]) -> str:
    summary = update.get("summary") if isinstance(update.get("summary"), dict) else {}
    rationale = str(update.get("rationale") or "我生成了一个计划修改提案。")
    vcc_points = summary.get("vcc_points", "?")
    vbb_points = summary.get("vbb_points", "?")
    scan_points = summary.get("scan_points", "?")
    static_points = summary.get("static_points", "?")
    return (
        "{0}\n"
        "提案：Vcc {1} 点，Vbb {2} 点，共 {3} 个扫描组合；静态点 {4} 个。\n"
        "如果确认应用，回复“确认”或“是”；如果要调整，请直接说新的范围、步进或测试点。"
    ).format(rationale, vcc_points, vbb_points, scan_points, static_points)


def _plan_from_context(context: dict[str, Any]) -> TestPlan | None:
    raw = context.get("current_plan")
    if not isinstance(raw, dict):
        nested = context.get("conversation_state")
        if isinstance(nested, dict) and isinstance(nested.get("current_plan"), dict):
            raw = nested.get("current_plan")
    if not isinstance(raw, dict):
        return None
    try:
        return TestPlan(
            model=str(raw.get("model") or "UNKNOWN"),
            bjt_type=str(raw.get("bjt_type") or "NPN"),
            goal=raw.get("goal") if raw.get("goal") in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else "auto",
            depth=raw.get("depth") if raw.get("depth") in {"conservative", "standard", "deep"} else "standard",
            mode=str(raw.get("mode") or "simulation"),
            vcc_steps=[float(item) for item in raw.get("vcc_steps", [])],
            vbb_steps=[float(item) for item in raw.get("vbb_steps", [])],
            static_points=[dict(item) for item in raw.get("static_points", []) if isinstance(item, dict)],
            ic_limit_a=float(raw.get("ic_limit_a", 0.03)),
            power_limit_w=float(raw.get("power_limit_w", 0.25)),
            sample_count=int(raw.get("sample_count", 1)),
            scan_mode=str(raw.get("scan_mode") or "static"),
            steps=[str(item) for item in raw.get("steps", [])],
            safety_notes=[str(item) for item in raw.get("safety_notes", [])],
            profile=dict(raw.get("profile") or {}),
        )
    except (TypeError, ValueError):
        return None


def _parse_json_object(text: str) -> dict:
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("tool-calling agent did not return JSON")
    payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("tool-calling agent JSON must be an object")
    return payload


def _normalize_decision(decision: dict, schemas: list) -> dict:
    action = str(decision.get("action") or "").strip()
    if action == "final":
        return {
            "action": "final",
            "response": str(decision.get("response") or ""),
            "next_actions": decision.get("next_actions") if isinstance(decision.get("next_actions"), list) else [],
        }
    tool_name = str(decision.get("tool") or "").strip()
    allowed = {schema.name for schema in schemas}
    if tool_name not in allowed:
        raise ValueError("unknown tool requested: {0}".format(tool_name))
    return {
        "action": "call_tool",
        "tool": tool_name,
        "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {},
    }


def _default_next_actions(plan: dict | None, execution: dict | None) -> list[str]:
    if execution:
        return ["解释结果", "调整计划后重测", "导出执行数据"]
    if plan:
        return ["运行仿真", "调整计划", "请求硬件预检"]
    return ["提供晶体管型号", "选择测试目标"]


def _agent_state(plan: dict | None, execution: dict | None) -> str:
    if execution:
        return "execution_complete" if not execution.get("aborted") else "execution_aborted"
    if plan:
        return "plan_ready"
    return "idle"


def _merge_provider(primary: str, secondary: str) -> str:
    values = [
        part.strip()
        for value in (primary, secondary)
        for part in str(value or "").split(",")
        if part.strip() and part.strip() != "local"
    ]
    if not values:
        return primary or secondary or "local"
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def _merge_usage(primary: dict | None, secondary: dict | None) -> dict:
    merged: dict = dict(primary or {})
    for key, value in (secondary or {}).items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] += value
        elif key not in merged:
            merged[key] = value
    return merged
