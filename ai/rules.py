from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

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
    joined_logs = "\n".join(logs or [])
    lowered = (text + "\n" + joined_logs).lower()
    measurements = measurements or []
    tags: set[str] = set()

    if "未找到雨骤设备" in joined_logs or "pyrd" in lowered or "deviceenum" in lowered:
        tags.add("device_not_found")
    if "开路" in joined_logs or "未检测到器件" in joined_logs:
        tags.add("open_circuit")
    if "短路" in lowered or "蜂鸣" in lowered or "接近0v" in lowered:
        tags.add("short_circuit")
    if "不导通" in lowered or "断了" in lowered or "都不通" in lowered:
        tags.add("open_circuit")
    if (
        "当 npn" in lowered
        or "当 pnp" in lowered
        or "全是 0" in lowered
        or "全是0" in lowered
        or "方向不对" in lowered
        or "极性" in lowered and "反" in lowered
        or "电流方向不对" in lowered
    ):
        tags.add("wrong_polarity")
    if "对调" in lowered or "接反" in lowered or "引脚顺序" in lowered or "脚位" in lowered:
        tags.add("bce_reversed")
    if "过流" in joined_logs or "ic 过流" in lowered or "over-current" in lowered or "overcurrent" in lowered:
        tags.add("overcurrent")
    if "功耗" in lowered or "power" in lowered or "pd 超过" in lowered or "太大功耗" in lowered:
        tags.add("power_exceeded")
    if "超时" in joined_logs or "timeout" in lowered:
        tags.add("scope_timeout")
    if "短了" in lowered or "短接" in lowered or "电流爆表" in lowered:
        tags.add("short_circuit")
    if any(word in lowered for word in ("饱和", "vce 很低", "压在一起")):
        tags.add("mostly_saturation")
        tags.add("saturation_suspected")
    if any(word in lowered for word in ("beta 低", "beta 很低", "hfe 偏低", "hfe 异常低", "低一大截", "不达标")) or (
        "beta 只有" in lowered and "手册说" in lowered
    ):
        tags.add("low_beta")
    if any(word in lowered for word in ("没电流", "没反应", "一直是 0", "一直是0")):
        tags.add("open_circuit")
    if any(word in lowered for word in ("接近 0", "接近0", "截止", "贴着横轴", "没导通")):
        tags.add("mostly_cutoff")

    if measurements:
        betas = [_safe_float(point.get("beta")) for point in measurements]
        betas = [value for value in betas if value is not None]
        regions: dict[str, int] = {}
        for point in measurements:
            region = str(point.get("region", "unknown"))
            regions[region] = regions.get(region, 0) + 1
        if betas and max(betas) < 30:
            tags.add("low_beta")
        if regions.get("saturation", 0) >= max(1, len(measurements) // 2):
            tags.add("mostly_saturation")
            tags.add("saturation_suspected")
        if regions.get("cutoff", 0) >= max(1, len(measurements) // 2):
            tags.add("mostly_cutoff")
        if _beta_spread_large(betas):
            tags.add("beta_unstable")

    return sorted(tags)


def diagnose_context(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> str:
    joined_logs = "\n".join(logs or [])
    lowered = (text + "\n" + joined_logs).lower()
    measurements = measurements or []
    tags = set(diagnose_tags(text, logs=logs, measurements=measurements))
    hints: list[str] = []

    if "device_not_found" in tags:
        hints.append("设备枚举/SDK 层异常：检查 Model S 连接、USB 权限、pyRD SDK 路径和驱动库。")
    if "open_circuit" in tags and ("开路" in joined_logs or "未检测到器件" in joined_logs):
        hints.append("疑似开路：检查三极管是否插入、夹具接触、Rb/Rc 支路和 E/B/C 引脚顺序。")
    if "short_circuit" in tags:
        hints.append("疑似短路或夹具接线错误：断开输出后检查 B/E/C 到地阻抗。")
    if "open_circuit" in tags and ("不导通" in lowered or "断了" in lowered or "都不通" in lowered):
        hints.append("疑似开路或 PN 结异常：断开输出后用万用表二极管档复核 B-E、B-C 结，并检查夹具接触。")
    if "wrong_polarity" in tags:
        hints.append("疑似管型或极性方向错误：PNP/NPN 偏置方向不同，请先核对 datasheet、夹具方向和 E/B/C 引脚。")
    if "bce_reversed" in tags:
        hints.append("疑似 C/E 或 B/C/E 引脚顺序错误：停止自动输出后核对封装脚位，必要时低压重新识别。")
    if "overcurrent" in tags:
        hints.append("过流保护触发：降低 Vbb 或 Vcc，提高限流电阻，先使用保守计划复测。")
    if "power_exceeded" in tags:
        hints.append("功耗风险：缩小 Vcc 范围，并降低 Ic 上限。")
    if "scope_timeout" in tags:
        hints.append("采样超时：检查示波器通道使能、采样率/点数和触发配置。")

    if measurements:
        if "low_beta" in tags:
            hints.append("Beta 明显偏低：可能是器件型号不符、进入饱和区、基极电流过大或引脚接错。")
        if "mostly_saturation" in tags:
            hints.append("多数点处于饱和区：降低 Vbb 或提高 Vce 工作窗口后再评估 beta。")
        if "mostly_cutoff" in tags:
            hints.append("多数点处于截止区：提高 Vbb 起点，或检查基极支路连接。")
        if "beta_unstable" in tags:
            hints.append("Beta 波动较大：建议在 active 区加密 Vbb 点，并避开饱和/截止点。")

    if not hints:
        hints.append("当前上下文没有明显故障特征。建议先用保守计划跑静态点或仿真，积累测量点后再诊断。")
    return "诊断建议：\n" + "\n".join(f"- {hint}" for hint in hints)


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


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _beta_spread_large(betas: list[float]) -> bool:
    if len(betas) < 3:
        return False
    avg = sum(betas) / len(betas)
    return avg > 0 and (max(betas) - min(betas)) / avg > 0.6
