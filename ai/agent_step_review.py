from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from ai.conversation import AIConversationState, AIIntent
from ai.llm_client import LLMUnavailable, chat_text


@dataclass(frozen=True)
class AgentStepReview:
    step: str
    observation: str = ""
    risk_notes: list[str] | None = None
    suggested_tools: list[str] | None = None
    fallback_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "observation": self.observation,
            "risk_notes": self.risk_notes or [],
            "suggested_tools": self.suggested_tools or [],
            "fallback_reason": self.fallback_reason,
        }


def review_agent_step_with_llm(
    *,
    step: str,
    user_text: str,
    state: AIConversationState,
    intent: AIIntent,
    summary: str,
    data: dict | None = None,
    available_tools: list[str] | None = None,
) -> tuple[AgentStepReview, bool, str, dict]:
    if os.getenv("BJT_AI_MODE", "local") != "cloud":
        return AgentStepReview(step=step, observation=summary), False, "local", {}

    prompt = json.dumps(
        {
            "step": step,
            "user_message": user_text,
            "intent": _intent_to_mapping(intent),
            "summary": summary,
            "data": data or {},
            "context": {
                "has_current_plan": state.current_plan is not None,
                "has_current_execution": state.current_execution is not None,
                "pending_profile_model": state.pending_profile_model,
            },
            "available_tools": available_tools or [],
            "schema": {
                "observation": "short Chinese external observation, no hidden reasoning",
                "risk_notes": "short Chinese safety/state notes",
                "suggested_tools": "optional tool names for the next visible step",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    instructions = """你是 BJT 测试 Agent 的环节复核器。
你参与每个关键环节，但只能输出可审计的外部观察、风险备注和下一步工具建议。
不要输出推理链，不要覆盖本地 SafetyGuard，不要要求超过器件或硬件限值。
只输出 JSON 对象，不要输出 Markdown。"""
    try:
        result = chat_text(system_text=instructions, user_text=prompt, timeout_s=12)
        payload = _parse_json_object(result.text)
        review = AgentStepReview(
            step=step,
            observation=str(payload.get("observation") or summary),
            risk_notes=[str(item) for item in payload.get("risk_notes", []) if str(item).strip()],
            suggested_tools=[
                str(item)
                for item in payload.get("suggested_tools", [])
                if str(item).strip() and (not available_tools or str(item) in available_tools)
            ],
        )
        return review, True, "{0}:{1}".format(result.provider, result.model), result.usage
    except (LLMUnavailable, ValueError, TypeError) as exc:
        return AgentStepReview(
            step=step,
            observation=summary,
            fallback_reason=str(exc) or exc.__class__.__name__,
        ), False, "local", {}


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
        "response": intent.response,
    }


def _parse_json_object(text: str) -> dict:
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM step review did not return a JSON object")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM step review JSON must be an object")
    return data
