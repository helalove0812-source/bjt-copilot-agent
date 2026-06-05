from __future__ import annotations

import json
import os
from statistics import median

from ai.llm_client import LLMUnavailable, chat_text
from ai.test_planner import TestPlan


_INSTRUCTIONS = """你是一个 BJT 自动化测试系统助手。
根据输入的测试计划，用中文简洁说明型号资料依据、测试意图、扫描范围、关键安全限制和预期输出。
如果 safe_plan.profile 中有型号资料，必须明确提到 Vceo、Ic 最大值、Ptot、hFE 典型范围和引脚/封装提醒。
只有当 safe_plan.profile.confidence 为 datasheet_lookup 时，才可以说“根据联网 datasheet 搜索结果”；否则不要声称已经联网搜索，只能说“根据当前型号资料/本地资料库/已提供资料”。
如果 user_request 表示“放宽限制/不要太保守/安全限制不要那么死”，且 safe_plan 已给出更高的 Ic、功耗或扫描范围，应说明“已在 SafetyGuard 允许范围内适度放宽到这些数值”；不要说“不会放宽”或“不能放宽”。
不要要求绕过本地 SafetyGuard，不要建议超过计划中的电流、功耗、电压限制。"""


def summarize_plan_with_ai(plan: TestPlan, user_text: str) -> tuple[str, bool, str, dict]:
    if os.getenv("BJT_AI_MODE", "local") != "cloud":
        return local_plan_summary(plan), False, "local", {}

    prompt = json.dumps(
        {
            "user_request": user_text,
            "safe_plan": plan.to_dict(),
        },
        ensure_ascii=False,
        indent=2,
    )
    try:
        result = chat_text(system_text=_INSTRUCTIONS, user_text=prompt)
        provider_label = "{0}:{1}".format(result.provider, result.model)
        return result.text, True, provider_label, result.usage
    except LLMUnavailable:
        return local_plan_summary(plan), False, "local", {}


def local_plan_summary(plan: TestPlan) -> str:
    summary = (
        "已生成 {model} 的 {goal} 测试计划：管型 {bjt_type}，模式 {mode}，"
        "Vcc 扫描 {vcc_start:.2f}-{vcc_stop:.2f} V，Vbb 扫描 {vbb_start:.2f}-{vbb_stop:.2f} V，"
        "Vcc {vcc_count} 点，Vbb {vbb_count} 点，共 {scan_count} 个扫描组合，"
        "电流限制 {ic_ma:.1f} mA，功耗限制 {power_mw:.0f} mW。"
    ).format(
        model=plan.model,
        goal=plan.goal,
        bjt_type=plan.bjt_type,
        mode=plan.mode,
        vcc_start=min(plan.vcc_steps),
        vcc_stop=max(plan.vcc_steps),
        vbb_start=min(plan.vbb_steps),
        vbb_stop=max(plan.vbb_steps),
        vcc_count=len(plan.vcc_steps),
        vbb_count=len(plan.vbb_steps),
        scan_count=len(plan.vcc_steps) * len(plan.vbb_steps),
        ic_ma=plan.ic_limit_a * 1000.0,
        power_mw=plan.power_limit_w * 1000.0,
    )
    profile = plan.profile or {}
    if profile:
        hfe = profile.get("hfe_typical") or []
        hfe_text = "{0}-{1}".format(hfe[0], hfe[1]) if isinstance(hfe, (list, tuple)) and len(hfe) >= 2 else "未知"
        summary += (
            "\n资料依据：{description}；Vceo {vceo:g} V，Ic 最大 {ic_ma:g} mA，"
            "Ptot {power_mw:g} mW，hFE 典型 {hfe}。引脚/封装提醒：{pinout}"
        ).format(
            description=str(profile.get("description") or "当前型号资料"),
            vceo=float(profile.get("vceo_max_v") or 0.0),
            ic_ma=float(profile.get("ic_max_a") or 0.0) * 1000.0,
            power_mw=float(profile.get("p_tot_w") or 0.0) * 1000.0,
            hfe=hfe_text,
            pinout=str(profile.get("pinout_hint") or ""),
        )
    return summary


def summarize_execution_with_ai(result: dict) -> tuple[str, bool, str, dict]:
    stats = build_execution_stats(result)
    if os.getenv("BJT_AI_MODE", "local") != "cloud":
        return local_execution_summary(stats), False, "local", {}

    prompt = json.dumps(
        {
            "execution": result,
            "stats": stats,
        },
        ensure_ascii=False,
        indent=2,
    )
    instructions = """你是 BJT 测试结果分析助手。
根据 execution 和 stats，用中文简洁总结测试结果、beta 范围、工作区分布、异常迹象和下一步建议。
如果 execution.aborted 为 true，必须明确说明执行已中止、触发原因，以及当前保留的测量点信息。
不要声称做了未出现在 execution 中的测试。"""
    try:
        llm_result = chat_text(system_text=instructions, user_text=prompt)
        provider_label = "{0}:{1}".format(llm_result.provider, llm_result.model)
        return llm_result.text, True, provider_label, llm_result.usage
    except LLMUnavailable:
        return local_execution_summary(stats), False, "local", {}


def build_execution_stats(result: dict) -> dict:
    measurements = result.get("measurements") or []
    beta_values = [float(point["beta"]) for point in measurements if point.get("beta") is not None]
    active_betas = [
        float(point["beta"])
        for point in measurements
        if point.get("region") == "active" and point.get("beta") is not None
    ]
    region_counts: dict[str, int] = {}
    for point in measurements:
        region = str(point.get("region", "unknown"))
        region_counts[region] = region_counts.get(region, 0) + 1

    stats = {
        "point_count": len(measurements),
        "aborted": bool(result.get("aborted")),
        "abort_reason": str(result.get("abort_reason", "")),
        "abort_tags": list(result.get("abort_tags") or []),
        "aborted_after_index": result.get("aborted_after_index"),
        "region_counts": region_counts,
        "beta_min": min(beta_values) if beta_values else None,
        "beta_max": max(beta_values) if beta_values else None,
        "beta_median": median(beta_values) if beta_values else None,
        "active_beta_median": median(active_betas) if active_betas else None,
        "ic_max_a": max((float(point["Ic"]) for point in measurements), default=None),
        "vce_min_v": min((float(point["Vce"]) for point in measurements), default=None),
    }
    return stats


def local_execution_summary(stats: dict) -> str:
    if stats["point_count"] == 0 and stats.get("aborted"):
        reason = stats.get("abort_reason") or "触发了运行时安全判据。"
        return "执行已因安全判据中止。{0}".format(reason)
    if stats["point_count"] == 0:
        return "测试未产生测量点。"
    lines = [
        "测试完成：共 {0} 个测量点。".format(stats["point_count"]),
        "工作区分布：{0}。".format(
            ", ".join("{0}={1}".format(key, value) for key, value in stats["region_counts"].items())
        ),
    ]
    if stats.get("aborted"):
        reason = stats.get("abort_reason") or "触发了运行时安全判据。"
        lines[0] = "执行已因安全判据中止：{0}".format(reason)
        lines.insert(1, "已保留 {0} 个测量点。".format(stats["point_count"]))
    if stats["beta_min"] is not None:
        lines.append(
            "Beta 范围 {0:.1f} - {1:.1f}，中位数 {2:.1f}。".format(
                stats["beta_min"],
                stats["beta_max"],
                stats["beta_median"],
            )
        )
    if stats["active_beta_median"] is not None:
        lines.append("Active 区 beta 中位数约 {0:.1f}。".format(stats["active_beta_median"]))
    if stats["ic_max_a"] is not None:
        lines.append("最大 Ic 约 {0:.2f} mA。".format(stats["ic_max_a"] * 1000.0))
    if stats.get("aborted"):
        lines.append("建议先排查中止原因并复核安全限值，再决定是否继续硬件测试。")
    else:
        lines.append("建议结合曲线检查 cutoff 到 active 的过渡区，必要时加密 Vbb 扫描。")
    return "\n".join(lines)
