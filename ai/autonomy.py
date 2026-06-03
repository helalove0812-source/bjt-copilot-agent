from __future__ import annotations

from dataclasses import dataclass
import json
import os

from core.types import HwConfig

from ai.assistant import build_execution_stats
from ai.llm_client import LLMUnavailable, chat_text
from ai.safety import clamp_plan_to_policy
from ai.test_planner import TestPlan


@dataclass(frozen=True)
class AutonomousWorkResult:
    plan: TestPlan
    response: str
    completed_actions: list[str]
    used_ai_api: bool = False
    llm_provider: str = "local"
    llm_usage: dict | None = None


def refine_plan_after_execution(
    plan: TestPlan,
    execution: dict,
    *,
    user_text: str = "",
    cfg: HwConfig | None = None,
) -> AutonomousWorkResult:
    stats = build_execution_stats(execution)
    data = plan.to_dict()
    completed_actions: list[str] = []

    if stats.get("aborted"):
        _scale_limits(data, current_scale=0.6, power_scale=0.7, vcc_scale=0.8)
        data["depth"] = "conservative"
        completed_actions.append("检测到运行时中止，已自动降低 Ic、功耗和 Vcc 上限。")
    elif _mostly_saturation(stats):
        _scale_vbb(data, stop_scale=0.88)
        _scale_limits(data, current_scale=0.8, power_scale=0.9, vcc_scale=1.0)
        completed_actions.append("检测到饱和点偏多，已收窄 Vbb 上沿并降低驱动强度。")
    elif _needs_more_resolution(stats):
        _increase_vbb_resolution(data)
        data["depth"] = "deep"
        completed_actions.append("有效 active 点偏少，已加密 Vbb 扫描并切换为 deep 深度。")
    elif _is_staged_strategy(plan) and _stable_active_result(stats):
        _increase_vbb_resolution(data)
        data["depth"] = "deep"
        data["sample_count"] = min(max(int(data["sample_count"]), 2048) * 2, 8192)
        completed_actions.append("保守阶段结果稳定，已切换为 deep 深度并加密 Vbb 扫描。")
    else:
        data["sample_count"] = min(max(int(data["sample_count"]), 2048) * 2, 8192)
        completed_actions.append("结果较稳定，已提高采样数以改善统计质量。")

    refined = _plan_from_data(data)
    refined = clamp_plan_to_policy(refined, cfg or HwConfig()).plan
    response, used_ai, provider, usage = _summarize_autonomous_work(
        original_plan=plan,
        refined_plan=refined,
        execution=execution,
        stats=stats,
        completed_actions=completed_actions,
        user_text=user_text,
    )
    return AutonomousWorkResult(
        plan=refined,
        response=response,
        completed_actions=completed_actions,
        used_ai_api=used_ai,
        llm_provider=provider,
        llm_usage=usage,
    )


def _mostly_saturation(stats: dict) -> bool:
    counts = stats.get("region_counts") or {}
    saturation = int(counts.get("saturation", 0))
    active = int(counts.get("active", 0))
    return saturation >= 2 and saturation >= active


def _needs_more_resolution(stats: dict) -> bool:
    counts = stats.get("region_counts") or {}
    point_count = int(stats.get("point_count") or 0)
    active = int(counts.get("active", 0))
    return point_count > 0 and active < 2


def _is_staged_strategy(plan: TestPlan) -> bool:
    return any("分阶段策略" in note for note in plan.safety_notes)


def _stable_active_result(stats: dict) -> bool:
    counts = stats.get("region_counts") or {}
    active = int(counts.get("active", 0))
    saturation = int(counts.get("saturation", 0))
    cutoff = int(counts.get("cutoff", 0))
    return active >= 2 and saturation == 0 and cutoff == 0 and not stats.get("aborted")


def _scale_limits(data: dict, *, current_scale: float, power_scale: float, vcc_scale: float) -> None:
    data["ic_limit_a"] = round(max(0.001, float(data["ic_limit_a"]) * current_scale), 6)
    data["power_limit_w"] = round(max(0.005, float(data["power_limit_w"]) * power_scale), 6)
    if data["vcc_steps"]:
        stop = max(data["vcc_steps"])
        limit = round(max(0.5, stop * vcc_scale), 3)
        data["vcc_steps"] = [value for value in data["vcc_steps"] if value <= limit]
        if not data["vcc_steps"] or data["vcc_steps"][-1] < limit:
            data["vcc_steps"].append(limit)
        for point in data["static_points"]:
            point["vcc"] = min(float(point["vcc"]), limit)


def _scale_vbb(data: dict, *, stop_scale: float) -> None:
    if not data["vbb_steps"]:
        return
    start = min(data["vbb_steps"])
    stop = max(data["vbb_steps"])
    new_stop = round(max(start, stop * stop_scale), 3)
    count = len(data["vbb_steps"])
    if count <= 1:
        data["vbb_steps"] = [new_stop]
    else:
        step = (new_stop - start) / float(count - 1)
        data["vbb_steps"] = [round(start + index * step, 3) for index in range(count)]
    if data["goal"] == "beta":
        vcc = data["static_points"][0]["vcc"] if data["static_points"] else 3.0
        data["static_points"] = [{"vcc": vcc, "vbb": value} for value in data["vbb_steps"]]


def _increase_vbb_resolution(data: dict) -> None:
    if not data["vbb_steps"]:
        return
    count = min(max(len(data["vbb_steps"]) + 2, 6), 14)
    start = min(data["vbb_steps"])
    stop = max(data["vbb_steps"])
    step = (stop - start) / float(count - 1) if count > 1 else 0.0
    data["vbb_steps"] = [round(start + index * step, 3) for index in range(count)]
    if data["goal"] == "beta":
        vcc = data["static_points"][0]["vcc"] if data["static_points"] else 3.0
        data["static_points"] = [{"vcc": vcc, "vbb": value} for value in data["vbb_steps"]]


def _plan_from_data(data: dict) -> TestPlan:
    return TestPlan(
        model=data["model"],
        bjt_type=data["bjt_type"],
        goal=data["goal"],
        depth=data["depth"],
        mode=data["mode"],
        vcc_steps=data["vcc_steps"],
        vbb_steps=data["vbb_steps"],
        static_points=data["static_points"],
        ic_limit_a=data["ic_limit_a"],
        power_limit_w=data["power_limit_w"],
        sample_count=data["sample_count"],
        scan_mode=data["scan_mode"],
        steps=data["steps"],
        safety_notes=data["safety_notes"],
        profile=data["profile"],
    )


def _summarize_autonomous_work(
    *,
    original_plan: TestPlan,
    refined_plan: TestPlan,
    execution: dict,
    stats: dict,
    completed_actions: list[str],
    user_text: str,
) -> tuple[str, bool, str, dict]:
    if os.getenv("BJT_AI_MODE", "local") != "cloud":
        return _local_autonomous_summary(refined_plan, completed_actions), False, "local", {}

    prompt = json.dumps(
        {
            "user_text": user_text,
            "completed_actions": completed_actions,
            "execution_stats": stats,
            "original_plan": original_plan.to_dict(),
            "refined_plan": refined_plan.to_dict(),
            "execution_aborted": bool(execution.get("aborted")),
        },
        ensure_ascii=False,
        indent=2,
    )
    instructions = """你是 BJT 测试 Agent 的自主工作说明器。
本地规则已经完成了安全计划调整，你只能解释已完成的调整、原因和下一步建议。
不要声称已经打开硬件输出，不要建议绕过 SafetyGuard，不要新增超过 refined_plan 的电压、电流或功耗。"""
    try:
        result = chat_text(system_text=instructions, user_text=prompt)
        return result.text, True, "{0}:{1}".format(result.provider, result.model), result.usage
    except LLMUnavailable:
        return _local_autonomous_summary(refined_plan, completed_actions), False, "local", {}


def _local_autonomous_summary(plan: TestPlan, completed_actions: list[str]) -> str:
    return (
        "我已根据最近一次执行结果自动生成下一版安全计划。\n"
        "{actions}\n"
        "新计划：depth={depth}，Vbb 点数 {vbb_points}，Ic 上限 {ic_ma:.1f} mA，"
        "功耗上限 {power_mw:.0f} mW，采样数 {sample_count}。"
    ).format(
        actions="\n".join("- " + action for action in completed_actions),
        depth=plan.depth,
        vbb_points=len(plan.vbb_steps),
        ic_ma=plan.ic_limit_a * 1000.0,
        power_mw=plan.power_limit_w * 1000.0,
        sample_count=plan.sample_count,
    )
