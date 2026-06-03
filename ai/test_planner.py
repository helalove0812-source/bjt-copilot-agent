from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from core.types import HwConfig

from ai.transistor_db import TransistorProfile, lookup_transistor


TestDepth = Literal["conservative", "standard", "deep"]
TestGoal = Literal["auto", "beta", "vce_sat", "curves", "screening", "full"]


@dataclass(frozen=True)
class TestPlan:
    __test__ = False

    model: str
    bjt_type: str
    goal: TestGoal
    depth: TestDepth
    mode: str
    vcc_steps: list[float]
    vbb_steps: list[float]
    static_points: list[dict[str, float]]
    ic_limit_a: float
    power_limit_w: float
    sample_count: int
    scan_mode: str
    steps: list[str]
    safety_notes: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_steps(values: list[float]) -> list[float]:
    return [round(value, 3) for value in values]


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [round(start, 3)]
    step = (stop - start) / float(count - 1)
    return _round_steps([start + i * step for i in range(count)])


def infer_goal(text: str) -> TestGoal:
    lowered = text.lower()
    if any(word in lowered for word in ("饱和", "vce_sat", "sat")):
        return "vce_sat"
    if any(word in lowered for word in ("曲线", "curve", "ic-vce", "扫描")):
        return "curves"
    if any(word in lowered for word in ("筛选", "分选", "pass", "fail", "良品")):
        return "screening"
    if any(word in lowered for word in ("完整", "报告", "full")):
        return "full"
    if any(word in lowered for word in ("beta", "hfe", "放大倍数", "增益", "β")):
        return "beta"
    return "auto"


def infer_depth(text: str) -> TestDepth:
    lowered = text.lower()
    if any(word in lowered for word in ("深入", "详细", "精细", "deep", "加深", "加密", "多测", "完整", "全套")):
        return "deep"
    if any(word in lowered for word in ("保守", "安全", "低压", "conservative", "轻一点", "稳一点", "别烧", "不要烧", "快速", "快一点", "少测")):
        return "conservative"
    return "standard"


def extract_model_guess(text: str) -> str:
    tokens = []
    for raw in text.replace(",", " ").replace("，", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in "-_")
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            tokens.append(token)
    return tokens[0] if tokens else "UNKNOWN"


def _base_limits(profile: TransistorProfile, cfg: HwConfig, depth: TestDepth) -> tuple[float, float, float]:
    if depth == "conservative":
        current_fraction = 0.03
        power_fraction = 0.08
        vcc_fraction = 0.12
    elif depth == "deep":
        current_fraction = 0.12
        power_fraction = 0.22
        vcc_fraction = 0.24
    else:
        current_fraction = 0.06
        power_fraction = 0.14
        vcc_fraction = 0.18

    ic_limit = min(cfg.Ic_max_A, max(0.003, profile.ic_max_a * current_fraction))
    power_limit = min(cfg.Pmax_W, max(0.03, profile.p_tot_w * power_fraction))
    vcc_stop = min(cfg.Vcc_max, max(1.5, profile.vceo_max_v * vcc_fraction))
    return ic_limit, power_limit, vcc_stop


def _vbb_range(profile: TransistorProfile, depth: TestDepth) -> tuple[float, float, int]:
    if profile.bjt_type == "PNP":
        # The present hardware path is NPN-first; keep PNP plans conservative until PNP flows exist.
        return 0.0, 0.0, 1
    if depth == "conservative":
        return 1.0, 2.2, 4
    if depth == "deep":
        return 0.9, 3.2, 8
    return 1.0, 2.8, 6


def clamp_plan_to_policy(plan: TestPlan, cfg: HwConfig):
    from ai.safety import clamp_plan_to_policy as apply_policy_clamp

    return apply_policy_clamp(plan, cfg)


def build_test_plan(
    *,
    model: str,
    goal: TestGoal = "auto",
    depth: TestDepth = "standard",
    mode: str = "simulation",
    cfg: HwConfig | None = None,
    scan_mode: str | None = None,
    bjt_type: str | None = None,
    profile_override: TransistorProfile | None = None,
) -> TestPlan:
    cfg = cfg or HwConfig()
    profile = profile_override or lookup_transistor(model)
    if bjt_type in {"NPN", "PNP"}:
        profile = replace(profile, bjt_type=bjt_type)
    if profile.bjt_type == "PNP" and goal == "auto" and depth == "standard":
        if goal == "auto":
            goal = "screening"
        if depth == "standard":
            depth = "conservative"
    ic_limit, power_limit, vcc_stop = _base_limits(profile, cfg, depth)

    vcc_count = {"conservative": 6, "standard": 9, "deep": 13}[depth]
    vcc_steps = _linspace(0.0, vcc_stop, vcc_count)
    vbb_start, vbb_stop, vbb_count = _vbb_range(profile, depth)
    vbb_steps = _linspace(vbb_start, vbb_stop, vbb_count)

    if goal == "beta":
        static_points = [{"vcc": min(3.0, vcc_stop), "vbb": value} for value in vbb_steps]
        computed_scan_mode = "software"
    elif goal == "vce_sat":
        static_points = [{"vcc": min(2.0, vcc_stop), "vbb": value} for value in vbb_steps[-3:]]
        computed_scan_mode = "software"
        vcc_steps = _linspace(0.0, min(1.2, vcc_stop), max(7, vcc_count))
    elif goal in {"curves", "full", "screening", "auto"}:
        static_points = [{"vcc": min(3.0, vcc_stop), "vbb": 2.0 if profile.bjt_type != "PNP" else 0.0}]
        computed_scan_mode = "software"
    else:
        static_points = [{"vcc": min(3.0, vcc_stop), "vbb": 2.0}]
        computed_scan_mode = "software"
    selected_scan_mode = scan_mode or computed_scan_mode

    safety_notes = [
        "硬件测试前先执行低压自检和管型识别。",
        "任何测量点超过电流或功耗限制时立即关断输出。",
        "大模型只能生成计划，实际输出仍由本地 SafetyGuard 和驱动层控制。",
    ]
    if mode == "hardware":
        safety_notes.append("hardware 模式需要用户确认后执行。")
    if profile.bjt_type == "PNP":
        safety_notes.extend(
            [
                "当前自动执行路径只开放 NPN，PNP 计划仅用于引导和人工低压确认。",
                "PNP 的偏置和接线方向与 NPN 不同，继续前必须核对 datasheet 与 E/B/C 引脚。",
                "建议先从低压、低电流、人工确认路径开始，不要直接自动上电。",
            ]
        )
    if profile.confidence == "fallback":
        safety_notes.append("未知型号使用保守兜底参数；接硬件前请补充 datasheet 额定值。")

    steps = [
        "读取型号资料并选择保守额定值。",
        "执行设备自检，确认输出可关断、示波器可读数。",
        "低压识别管型并检查开路/短路/疑似接反。",
        "按计划执行静态点或曲线扫描。",
        "汇总 beta、Vce(sat)、工作区间和异常点。",
    ]

    plan = TestPlan(
        model=profile.model,
        bjt_type=profile.bjt_type,
        goal=goal,
        depth=depth,
        mode=mode,
        vcc_steps=vcc_steps,
        vbb_steps=vbb_steps,
        static_points=[{"vcc": round(p["vcc"], 3), "vbb": round(p["vbb"], 3)} for p in static_points],
        ic_limit_a=round(_clamp(ic_limit, 0.0, cfg.Ic_max_A), 6),
        power_limit_w=round(_clamp(power_limit, 0.0, cfg.Pmax_W), 6),
        sample_count=2048,
        scan_mode=selected_scan_mode,
        steps=steps,
        safety_notes=safety_notes,
        profile=asdict(profile),
    )
    return clamp_plan_to_policy(plan, cfg).plan


def plan_from_text(
    text: str,
    *,
    mode: str = "simulation",
    cfg: HwConfig | None = None,
    goal: TestGoal | None = None,
    depth: TestDepth | None = None,
    scan_mode: str | None = None,
    bjt_type: str | None = None,
) -> TestPlan:
    return build_test_plan(
        model=extract_model_guess(text),
        goal=goal or infer_goal(text),
        depth=depth or infer_depth(text),
        mode=mode,
        cfg=cfg,
        scan_mode=scan_mode,
        bjt_type=bjt_type,
    )
