from __future__ import annotations

AGENT_STATE_METADATA = {
    "idle": {"label": "空闲"},
    "plan_ready": {"label": "计划已就绪"},
    "simulation_ready": {"label": "仿真可执行"},
    "awaiting_profile_fields": {"label": "等待补全未知型号"},
    "awaiting_hardware_confirmation": {"label": "等待硬件确认"},
    "profile_library_ready": {"label": "器件库已就绪"},
    "executing": {"label": "执行中"},
    "aborted": {"label": "执行已中止"},
    "completed": {"label": "执行完成"},
}

EXECUTION_STATE_METADATA = {
    "not_started": {"label": "未开始"},
    "blocked": {"label": "已阻断"},
    "skipped": {"label": "已跳过"},
    "running": {"label": "执行中"},
    "aborted": {"label": "已中止"},
    "completed": {"label": "已完成"},
}

BLOCK_REASON_METADATA = {
    "unsafe_request": {"label": "危险请求", "kind": "safety"},
    "hardware_confirmation_required": {"label": "需要硬件确认", "kind": "safety"},
    "unknown_model_incomplete": {"label": "未知型号信息未补全", "kind": "input"},
    "pnp_execution_blocked": {"label": "PNP/未知型号禁止自动硬件执行", "kind": "safety"},
    "runtime_abort": {"label": "运行时安全中止", "kind": "safety"},
    "preflight_blocked": {"label": "预检阻止执行", "kind": "safety"},
}


def state_item(state: str, *, execution: bool = False, detail: str = "") -> dict:
    metadata = EXECUTION_STATE_METADATA if execution else AGENT_STATE_METADATA
    meta = metadata.get(state, {"label": state})
    return {"id": state, "label": meta["label"], "detail": detail}


def blocked_reason_item(reason: str, *, detail: str = "") -> dict:
    if not reason:
        return {}
    meta = BLOCK_REASON_METADATA.get(reason, {"label": reason, "kind": "other"})
    return {"id": reason, "label": meta["label"], "kind": meta["kind"], "detail": detail}


def pick_blocked_reason(
    *,
    pending_profile_model: str | None = None,
    execution: dict | None = None,
    policy_reason: str = "",
) -> str:
    if pending_profile_model:
        return "unknown_model_incomplete"
    if execution and execution.get("aborted"):
        return "runtime_abort"
    return policy_reason


def pick_execution_state(
    *,
    execution: dict | None = None,
    raw_agent_state: str = "",
    blocked_reason: str = "",
) -> str:
    if execution:
        if execution.get("aborted"):
            return "aborted"
        if execution.get("skipped"):
            return "skipped"
        return "completed"
    if raw_agent_state in {"execution_blocked", "preflight_blocked"} and blocked_reason:
        return "blocked"
    return "not_started"


def canonical_agent_state(
    *,
    raw_agent_state: str,
    execution_state: str = "not_started",
    pending_profile_model: str | None = None,
) -> str:
    if pending_profile_model:
        return "awaiting_profile_fields"
    if raw_agent_state == "awaiting_hardware_confirmation":
        return raw_agent_state
    if execution_state == "aborted" or raw_agent_state in {"execution_aborted", "execution_blocked", "preflight_blocked"}:
        return "aborted"
    if raw_agent_state in {"execution_complete", "plan_refined"}:
        return "completed"
    return raw_agent_state
