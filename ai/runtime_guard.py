from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeAbortDecision:
    should_abort: bool
    reason: str
    tags: list[str]


def check_abort_after_point(*, plan, point: dict, history: list[dict]) -> RuntimeAbortDecision:
    ic = float(point.get("Ic", 0.0))
    vce = float(point.get("Vce", 0.0))

    if ic > float(plan.ic_limit_a):
        return RuntimeAbortDecision(
            should_abort=True,
            reason="当前 Ic 超过计划上限，已停止后续硬件测量。",
            tags=["runtime_ic_limit_exceeded"],
        )

    if ic * vce > float(plan.power_limit_w):
        return RuntimeAbortDecision(
            should_abort=True,
            reason="当前功耗超过计划上限，已停止后续硬件测量。",
            tags=["runtime_power_limit_exceeded"],
        )

    if history:
        last = history[-1]
        last_ic = float(last.get("Ic", 0.0))
        last_vce = float(last.get("Vce", 0.0))
        if ic - last_ic >= 0.002 and last_vce - vce >= 0.5:
            return RuntimeAbortDecision(
                should_abort=True,
                reason="检测到 Ic 上升且 Vce 下降的异常趋势，已停止后续硬件测量。",
                tags=["runtime_instability_trend"],
            )

    return RuntimeAbortDecision(should_abort=False, reason="", tags=[])
