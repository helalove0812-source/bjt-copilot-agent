from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ai.diagnosis_engine import diagnose_observation, summarize_diagnosis
from ai.test_planner import TestDepth, TestGoal


@dataclass(frozen=True)
class RuleDecision:
    goal: TestGoal | None = None
    depth: TestDepth | None = None
    ic_limit_a: float | None = None
    power_limit_w: float | None = None
    vcc_max: float | None = None
    vbb_points: int | None = None
    response: str = ""


def infer_rule_decision(text: str, context: dict[str, Any] | None = None) -> RuleDecision:
    lowered = text.lower()
    context = context or {}
    goal = _infer_goal(text, lowered)
    depth = _infer_depth(text, lowered, goal)
    ic_limit = _extract_current_limit_a(text)
    power_limit = _extract_power_limit_w(text)
    vcc_max = _extract_voltage_limit(text)
    vbb_points = _extract_point_count(text)
    response = _rule_response(goal, depth, ic_limit, power_limit, vcc_max, vbb_points, context)
    return RuleDecision(
        goal=goal,
        depth=depth,
        ic_limit_a=ic_limit,
        power_limit_w=power_limit,
        vcc_max=vcc_max,
        vbb_points=vbb_points,
        response=response,
    )


def extract_profile_fields(text: str) -> dict[str, float | str]:
    fields: dict[str, float | str] = {}
    upper = text.upper()

    if "NPN" in upper:
        fields["bjt_type"] = "NPN"
    elif "PNP" in upper:
        fields["bjt_type"] = "PNP"

    vceo = _extract_profile_vceo_max_v(text)
    if vceo is not None:
        fields["vceo_max_v"] = vceo

    ic_max = _extract_profile_ic_max_a(text)
    if ic_max is not None:
        fields["ic_max_a"] = ic_max

    p_tot = _extract_profile_p_tot_w(text)
    if p_tot is not None:
        fields["p_tot_w"] = p_tot

    return fields


def diagnose_tags(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> list[str]:
    return diagnose_observation(text, logs=logs, measurements=measurements).tags


def diagnose_context(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> str:
    return summarize_diagnosis(diagnose_observation(text, logs=logs, measurements=measurements))


def _infer_goal(text: str, lowered: str) -> TestGoal | None:
    if any(word in text for word in ("快速", "验管", "看看好坏", "先测一下")):
        return "screening"
    if any(word in text for word in ("批量", "分选", "筛选", "合格", "不合格")):
        return "screening"
    if any(word in text for word in ("饱和", "压降")) or "vce_sat" in lowered or "sat" in lowered:
        return "vce_sat"
    if any(word in text for word in ("曲线", "输出特性", "族线")) or "ic-vce" in lowered or "curve" in lowered:
        return "curves"
    if any(word in text for word in ("完整", "报告", "全套")) or "full" in lowered:
        return "full"
    if any(word in text for word in ("beta", "hfe", "放大倍数", "增益", "线性", "β")) or "beta" in lowered:
        return "beta"
    return None


def _infer_depth(text: str, lowered: str, goal: TestGoal | None = None) -> TestDepth | None:
    if any(word in text for word in ("失效分析", "线性度", "多扫几个 Ic", "多扫几个 Ib", "随 Ic", "随 电流", "坏了", "分析下", "加深", "深入一点")):
        return "deep"
    if any(word in text for word in ("接线", "引脚", "验证", "没丝印", "拆机件", "型号不确定", "国产管子")):
        return "conservative"
    if any(word in text for word in ("保守", "安全", "低压", "轻一点", "稳一点", "别烧", "不要烧", "别烧管", "不烧管", "快速", "快一点", "少测")) or "conservative" in lowered:
        return "conservative"
    if any(word in text for word in ("精细", "详细", "深入", "加密", "多测", "完整", "全套")) or "deep" in lowered:
        return "deep"
    if any(word in text for word in ("标准", "正常", "默认")):
        return "standard"
    if goal in ("screening", "wiring_check"):
        return "conservative"
    if goal in ("full", "beta_linearity", "failure_analysis"):
        return "deep"
    return "standard"


def _extract_current_limit_a(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ma|毫安)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r"(?:ic|电流).*?(?:不超过|最高|上限|限制|到)?\s*(\d+(?:\.\d+)?)\s*a", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_power_limit_w(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(mw|毫瓦)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r"(?:功耗|power).*?(?:不超过|最高|上限|限制|到)?\s*(\d+(?:\.\d+)?)\s*w", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_voltage_limit(text: str) -> float | None:
    match = re.search(r"(?:vcc|电压).*?(?:不超过|最高|上限|限制|到)\s*(\d+(?:\.\d+)?)\s*v?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"0\s*(?:到|-|~|～)\s*(\d+(?:\.\d+)?)\s*v", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_point_count(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:个)?(?:点|档|级)", text)
    if match:
        return max(2, min(int(match.group(1)), 32))
    if "加密" in text or "多测" in text:
        return 10
    if "快速" in text or "少测" in text:
        return 3
    return None


def _extract_profile_vceo_max_v(text: str) -> float | None:
    match = re.search(r"vceo\s*(\d+(?:\.\d+)?)\s*v", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*v", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_profile_ic_max_a(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ma|毫安)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*a", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_profile_p_tot_w(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(mw|毫瓦)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*w", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _rule_response(
    goal: TestGoal | None,
    depth: TestDepth | None,
    ic_limit: float | None,
    power_limit: float | None,
    vcc_max: float | None,
    vbb_points: int | None,
    context: dict[str, Any],
) -> str:
    parts: list[str] = []
    if goal:
        parts.append(f"目标切换为 {goal}")
    if depth:
        parts.append(f"深度设为 {depth}")
    if ic_limit is not None:
        parts.append(f"Ic 上限 {ic_limit * 1000:.1f} mA")
    if power_limit is not None:
        parts.append(f"功耗上限 {power_limit * 1000:.1f} mW")
    if vcc_max is not None:
        parts.append(f"Vcc 最高 {vcc_max:.2f} V")
    if vbb_points is not None:
        parts.append(f"Vbb 点数 {vbb_points}")
    if parts:
        return "已按本地规则理解：" + "，".join(parts) + "。"
    if context.get("has_plan"):
        return "我会基于当前计划继续处理。"
    return "已根据本地规则理解你的测试需求。"
