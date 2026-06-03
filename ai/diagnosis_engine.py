from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiagnosisResult:
    tags: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)


def diagnose_observation(
    text: str,
    *,
    logs: list[str] | None = None,
    measurements: list[dict] | None = None,
) -> DiagnosisResult:
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
        tags.add("overcurrent")
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

    hints = _build_hints(lowered, joined_logs, measurements, tags)
    return DiagnosisResult(tags=sorted(tags), hints=hints)


def summarize_diagnosis(result: DiagnosisResult) -> str:
    if result.hints:
        return "诊断观察：\n" + "\n".join(f"- {hint}" for hint in result.hints)
    if result.tags:
        return "诊断观察：\n- 已识别标签：" + "、".join(result.tags)
    return "诊断观察：\n- 当前未识别到明确异常标签。"


def _build_hints(
    lowered: str,
    joined_logs: str,
    measurements: list[dict[str, Any]],
    tags: set[str],
) -> list[str]:
    hints: list[str] = []

    if "device_not_found" in tags:
        hints.append("设备枚举或 SDK 层异常，表现为未找到雨骤设备或 pyRD 初始化失败。")
    if "open_circuit" in tags and ("开路" in joined_logs or "未检测到器件" in joined_logs):
        hints.append("疑似开路，表现为未检测到器件接入或夹具未形成有效导通。")
    elif "open_circuit" in tags:
        hints.append("疑似开路或 PN 结异常。")
    if "short_circuit" in tags:
        hints.append("疑似短路或夹具接线错误。")
    if "wrong_polarity" in tags:
        hints.append("疑似管型或极性方向错误。")
    if "bce_reversed" in tags:
        hints.append("疑似 C/E 或 B/C/E 引脚顺序错误。")
    if "overcurrent" in tags:
        hints.append("过流保护触发。")
    if "power_exceeded" in tags:
        hints.append("功耗风险：功耗超过当前安全窗口。")
    if "scope_timeout" in tags:
        hints.append("采样超时。")

    if measurements:
        if "low_beta" in tags:
            hints.append("Beta 明显偏低。")
        if "mostly_saturation" in tags:
            hints.append("多数点处于饱和区。")
        if "mostly_cutoff" in tags:
            hints.append("多数点处于截止区。")
        if "beta_unstable" in tags:
            hints.append("Beta 波动较大。")

    return hints


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
