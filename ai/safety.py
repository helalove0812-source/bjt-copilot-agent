from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ai.test_planner import TestPlan
from core.types import HwConfig


@dataclass(frozen=True)
class PlanPolicyResult:
    plan: TestPlan
    tags: list[str]
    changed: bool


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    status: Literal["allow", "deny", "require_confirm"]
    reasons: list[str]
    tags: list[str]
    blocked_reason: str = ""


def clamp_plan_to_policy(plan: TestPlan, cfg: HwConfig) -> PlanPolicyResult:
    ic_limit = min(float(plan.ic_limit_a), float(cfg.Ic_max_A))
    power_limit = min(float(plan.power_limit_w), float(cfg.Pmax_W))
    vcc_steps = [min(float(value), float(cfg.Vcc_max)) for value in plan.vcc_steps]
    static_points = [
        {
            "vcc": min(float(point["vcc"]), float(cfg.Vcc_max)),
            "vbb": float(point["vbb"]),
        }
        for point in plan.static_points
    ]

    changed = (
        ic_limit != plan.ic_limit_a
        or power_limit != plan.power_limit_w
        or vcc_steps != plan.vcc_steps
        or static_points != plan.static_points
    )

    tags: list[str] = []
    if changed:
        tags.append("clamped_to_hardware_max")
    if plan.profile.get("confidence") == "fallback":
        tags.append("unknown_model_fallback")

    return PlanPolicyResult(
        plan=replace(
            plan,
            ic_limit_a=ic_limit,
            power_limit_w=power_limit,
            vcc_steps=vcc_steps,
            static_points=static_points,
        ),
        tags=tags,
        changed=changed,
    )


def evaluate_execution_request(
    *,
    plan: TestPlan,
    mode: str,
    allow_hardware: bool,
    token_valid: bool,
) -> ExecutionPolicyDecision:
    tags: list[str] = []
    reasons: list[str] = []

    if plan.profile.get("confidence") == "fallback":
        tags.append("unknown_model_fallback")

    if plan.bjt_type != "NPN":
        return ExecutionPolicyDecision(
            status="deny",
            reasons=["当前自动执行路径只开放 NPN；PNP/未知型号先生成计划并等待专用流程。"],
            tags=tags + ["pnp_auto_execution_blocked"],
            blocked_reason="pnp_execution_blocked",
        )

    if mode != "hardware":
        return ExecutionPolicyDecision(status="allow", reasons=reasons, tags=tags)

    if not allow_hardware:
        return ExecutionPolicyDecision(
            status="deny",
            reasons=["硬件执行还需要调用方显式允许；我已保留当前计划，未打开真实输出。"],
            tags=tags + ["blocked_hardware_execution"],
            blocked_reason="preflight_blocked",
        )

    if not token_valid:
        return ExecutionPolicyDecision(
            status="require_confirm",
            reasons=["硬件执行需要显式确认。"],
            tags=tags + ["requires_hardware_confirmation"],
            blocked_reason="hardware_confirmation_required",
        )

    return ExecutionPolicyDecision(status="allow", reasons=reasons, tags=tags)
