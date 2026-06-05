from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from typing import Any

from ai.conversation import AIConversationState, AIIntent
from ai.llm_client import LLMUnavailable, chat_text


@dataclass(frozen=True)
class AgentOrchestrationPlan:
    selected_tools: list[str] = field(default_factory=list)
    tool_sequence: list[str] = field(default_factory=list)
    evidence_summary: str = ""
    risk_notes: list[str] = field(default_factory=list)
    requires_hardware_confirmation: bool = False
    fallback_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "selected_tools": self.selected_tools,
            "tool_sequence": self.tool_sequence,
            "evidence_summary": self.evidence_summary,
            "risk_notes": self.risk_notes,
            "requires_hardware_confirmation": self.requires_hardware_confirmation,
            "fallback_reason": self.fallback_reason,
        }


def orchestrate_turn_with_llm(
    text: str,
    state: AIConversationState,
    *,
    intent: AIIntent,
    tools: Any,
    default_mode: str = "simulation",
) -> tuple[AgentOrchestrationPlan, bool, str, dict]:
    local_plan = _local_orchestration(intent)
    if os.getenv("BJT_AI_MODE", "local") != "cloud":
        return local_plan, False, "local", {}

    descriptors = [asdict(item) for item in tools.describe()]
    allowed_tools = {str(item.get("name")) for item in descriptors if item.get("name")}
    prompt = json.dumps(
        {
            "user_message": text,
            "default_mode": default_mode,
            "intent": _intent_to_mapping(intent),
            "context": _compact_context(state),
            "available_tools": descriptors,
            "schema": {
                "selected_tools": "ordered list of tool names from available_tools",
                "tool_sequence": "short observable step labels, no hidden reasoning",
                "evidence_summary": "one short Chinese sentence about context used",
                "risk_notes": "list of short Chinese safety/state notes",
                "requires_hardware_confirmation": "boolean",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    instructions = """你是 BJT 测试 Agent 的工具编排器。
你必须让 LLM 参与判断每一轮应该使用哪些工具，但不能绕过本地 SafetyGuard、硬件确认、限流和功耗边界。
只输出 JSON 对象，不要输出 Markdown，不要输出推理链。
selected_tools 只能来自 available_tools.name。
tool_sequence 写成可审计的外部步骤，例如“解析意图”“查资料”“生成计划”“安全检查”“执行/总结”，不要写内部思维。"""
    try:
        result = chat_text(system_text=instructions, user_text=prompt)
        data = _parse_json_object(result.text)
        plan = _plan_from_mapping(data, allowed_tools, local_plan)
        return plan, True, "{0}:{1}".format(result.provider, result.model), result.usage
    except (LLMUnavailable, ValueError, TypeError) as exc:
        fallback = AgentOrchestrationPlan(
            selected_tools=local_plan.selected_tools,
            tool_sequence=local_plan.tool_sequence,
            evidence_summary=local_plan.evidence_summary,
            risk_notes=local_plan.risk_notes,
            requires_hardware_confirmation=local_plan.requires_hardware_confirmation,
            fallback_reason=str(exc) or exc.__class__.__name__,
        )
        return fallback, False, "local", {}


def _local_orchestration(intent: AIIntent) -> AgentOrchestrationPlan:
    selected = ["interpret_intent"]
    sequence = ["解析意图"]
    risks: list[str] = []
    requires_confirmation = False

    if intent.action in {"create_plan", "modify_plan"}:
        selected.extend(["lookup_datasheet_profile", "apply_intent_to_plan", "summarize_plan"])
        sequence.extend(["补齐器件资料", "生成或调整计划", "总结计划"])
    elif intent.action == "execute_simulation":
        selected.extend(["execute_plan", "summarize_execution", "diagnose_tags", "recommend_actions"])
        sequence.extend(["执行仿真", "总结结果", "生成下一步动作"])
    elif intent.action == "execute_hardware":
        selected.extend(["evaluate_execution_request", "preflight_plan", "execute_plan", "summarize_execution"])
        sequence.extend(["硬件安全检查", "预检", "等待确认后执行", "总结结果"])
        risks.append("真实硬件执行必须经过本地确认令牌和 SafetyGuard。")
        requires_confirmation = True
    elif intent.action == "explain_result":
        selected.extend(["diagnose_context", "diagnose_tags", "recommend_actions"])
        sequence.extend(["分析上下文", "归类诊断标签", "生成建议动作"])
    elif intent.action in {"save_profile", "update_profile", "manage_profile_library"}:
        selected.extend(["lookup_transistor", "recommend_actions"])
        sequence.extend(["核对器件库状态", "生成后续动作"])
    else:
        selected.append("recommend_actions")
        sequence.append("回答并提示下一步")

    return AgentOrchestrationPlan(
        selected_tools=_dedupe(selected),
        tool_sequence=sequence,
        evidence_summary="根据本轮意图和当前会话状态选择工具路径。",
        risk_notes=risks,
        requires_hardware_confirmation=requires_confirmation,
    )


def _plan_from_mapping(data: dict, allowed_tools: set[str], fallback: AgentOrchestrationPlan) -> AgentOrchestrationPlan:
    selected_tools = [
        str(name)
        for name in data.get("selected_tools", [])
        if isinstance(name, str) and name in allowed_tools
    ]
    if "interpret_intent" in allowed_tools and "interpret_intent" not in selected_tools:
        selected_tools.insert(0, "interpret_intent")
    if not selected_tools:
        selected_tools = fallback.selected_tools
    tool_sequence = [str(item) for item in data.get("tool_sequence", []) if str(item).strip()]
    risk_notes = [str(item) for item in data.get("risk_notes", []) if str(item).strip()]
    return AgentOrchestrationPlan(
        selected_tools=_dedupe(selected_tools),
        tool_sequence=tool_sequence or fallback.tool_sequence,
        evidence_summary=str(data.get("evidence_summary") or fallback.evidence_summary),
        risk_notes=risk_notes,
        requires_hardware_confirmation=bool(
            data.get("requires_hardware_confirmation", fallback.requires_hardware_confirmation)
        ),
    )


def _compact_context(state: AIConversationState) -> dict:
    return {
        "has_current_plan": state.current_plan is not None,
        "current_plan": state.current_plan.to_dict() if state.current_plan else None,
        "has_current_execution": state.current_execution is not None,
        "current_summary": state.current_summary,
        "pending_profile_model": state.pending_profile_model,
        "pending_profile_fields": state.pending_profile_fields,
        "recent_messages": [
            {"role": item.role, "content": item.content}
            for item in state.messages[-4:]
        ],
    }


def _intent_to_mapping(intent: AIIntent) -> dict:
    return {
        "action": intent.action,
        "model": intent.model,
        "goal": intent.goal,
        "depth": intent.depth,
        "mode": intent.mode,
        "ic_limit_a": intent.ic_limit_a,
        "power_limit_w": intent.power_limit_w,
        "vcc_max": intent.vcc_max,
        "vbb_points": intent.vbb_points,
        "library_patch": intent.library_patch,
        "response": intent.response,
    }


def _parse_json_object(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM orchestration did not return a JSON object")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM orchestration JSON must be an object")
    return data


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out
