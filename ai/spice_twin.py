from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from statistics import fmean
from typing import Any

from ai.dut_belief import DUTBeliefState
from ai.test_planner import TestPlan


@dataclass(frozen=True)
class SpiceDigitalTwin:
    model_name: str
    device_type: str
    parameters: dict[str, float]
    model_card: str
    residuals: dict[str, Any]
    diagnosis: list[dict[str, Any]] = field(default_factory=list)
    suggested_followups: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_spice_twin_from_belief(belief: DUTBeliefState) -> SpiceDigitalTwin:
    points = [_normalize_point(item) for item in belief.measured_points]
    active = [item for item in points if item["region"] == "active" and item["Ic"] > 0 and item["Ib"] > 0]
    saturated = [item for item in points if item["region"] == "saturation" and item["Ic"] > 0]
    beta_values = [item["Ic"] / max(item["Ib"], 1e-12) for item in active]
    bf = _safe_mean(beta_values, default=50.0)
    nf = _fit_nf(active)
    is_value = _fit_is(active, nf)
    vaf = _fit_vaf(active)
    ikf = _fit_ikf(active, bf)
    rc = _fit_series_resistance(saturated, "collector")
    re = _fit_series_resistance(saturated, "emitter")
    rb = _fit_rb(active)
    params = {
        "IS": is_value,
        "BF": bf,
        "NF": nf,
        "VAF": vaf,
        "IKF": ikf,
        "ISE": max(is_value * 10.0, 1e-15),
        "NE": max(nf * 1.8, 1.5),
        "RB": rb,
        "RC": rc,
        "RE": re,
    }
    residuals = _residual_map(points, params)
    diagnosis = _diagnose_residuals(residuals)
    followups = _suggest_followups(diagnosis, residuals)
    confidence = _confidence(active, saturated, residuals)
    model_name = _spice_model_name(belief.model)
    return SpiceDigitalTwin(
        model_name=model_name,
        device_type=belief.device_type if belief.device_type in {"NPN", "PNP"} else "NPN",
        parameters={key: _rounded_param(value) for key, value in params.items()},
        model_card=_model_card(model_name, belief.device_type if belief.device_type in {"NPN", "PNP"} else "NPN", params),
        residuals=residuals,
        diagnosis=diagnosis,
        suggested_followups=followups,
        confidence=confidence,
    )


def plan_residual_followup_measurements(
    twin: SpiceDigitalTwin | dict[str, Any],
    belief: DUTBeliefState,
    *,
    plan: TestPlan | None = None,
    budget: int = 4,
) -> dict[str, Any]:
    twin_data = twin.to_dict() if isinstance(twin, SpiceDigitalTwin) else dict(twin)
    diagnosis = list(twin_data.get("diagnosis") or [])
    residuals = dict(twin_data.get("residuals") or {})
    measured = [_normalize_point(item) for item in belief.measured_points]
    candidates: list[dict[str, Any]] = []
    for item in diagnosis:
        name = str(item.get("name") or "")
        candidates.extend(_followup_candidates_for_diagnosis(name, measured, plan))
    if not candidates and (residuals.get("overall_mean_abs") or 0.0) > 0.25:
        candidates.extend(_nominal_confirmation_candidates(measured, plan))
    if not candidates:
        candidates.extend(_coverage_followup_candidates(measured, plan))
    candidates = _dedupe_followup_candidates(candidates, measured)
    candidates = _safety_filter_candidates(candidates, plan)
    if not candidates:
        recovery = _coverage_followup_candidates(measured, plan) + _neighboring_unmeasured_candidates(measured, plan)
        candidates = _safety_filter_candidates(_dedupe_followup_candidates(recovery, measured), plan)
    candidates = sorted(candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True)[: max(1, min(int(budget or 4), 12))]
    return {
        "ok": True,
        "followup_plan": {
            "source": "residual_guided_diagnosis",
            "residuals": residuals,
            "diagnosis": diagnosis,
            "candidates": candidates,
            "summary": _followup_summary(candidates, diagnosis),
        },
    }


def _normalize_point(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "Vbb": float(item.get("Vbb", item.get("vbb", 0.0)) or 0.0),
        "Vcc": float(item.get("Vcc", item.get("vcc", 0.0)) or 0.0),
        "Vbe": float(item.get("Vbe", item.get("vbe", 0.0)) or 0.0),
        "Vce": float(item.get("Vce", item.get("vce", 0.0)) or 0.0),
        "Ib": float(item.get("Ib", item.get("ib", 0.0)) or 0.0),
        "Ic": float(item.get("Ic", item.get("ic", 0.0)) or 0.0),
        "beta": float(item.get("beta", 0.0) or 0.0),
        "region": str(item.get("region") or "cutoff"),
    }


def _followup_candidates_for_diagnosis(
    name: str,
    measured: list[dict[str, Any]],
    plan: TestPlan | None,
) -> list[dict[str, Any]]:
    max_vcc = _plan_max_vcc(plan)
    vbb_low, vbb_high = _plan_vbb_bounds(plan)
    nominal_vbb = _nominal_vbb(measured, vbb_low, vbb_high)
    high_vbb = vbb_high
    if name == "saturation_residual":
        return [
            _candidate(0.25, high_vbb, "vce_sat_vs_ic", 0.96, "饱和区残差大，补测低 VCE/高基极驱动以分离 RC/RE/contact。", max_vcc, vbb_low, vbb_high),
            _candidate(0.5, high_vbb, "vce_sat_vs_ic", 0.94, "用第二个 VCE(sat) 点估计饱和区斜率。", max_vcc, vbb_low, vbb_high),
            _candidate(0.8, high_vbb - 0.25, "vce_sat_vs_ic", 0.88, "改变基极驱动，观察饱和残差是否随 IC 系统变化。", max_vcc, vbb_low, vbb_high),
        ]
    if name == "high_current_residual":
        return [
            _candidate(min(3.0, max_vcc), high_vbb, "high_current_rolloff", 0.92, "高电流残差大，补测强驱动点以区分 IKF/高注入效应。", max_vcc, vbb_low, vbb_high),
            _candidate(min(4.5, max_vcc), high_vbb, "high_current_rolloff", 0.86, "提高 VCE 检查高电流残差是否来自 Early/self-heating。", max_vcc, vbb_low, vbb_high),
        ]
    if name == "early_effect_residual":
        return [
            _candidate(1.2, nominal_vbb, "same_ib_multi_vce", 0.9, "Early effect 残差大，补同一基极驱动低 VCE 点。", max_vcc, vbb_low, vbb_high),
            _candidate(min(3.0, max_vcc), nominal_vbb, "same_ib_multi_vce", 0.88, "Early effect 残差大，补同一基极驱动中 VCE 点。", max_vcc, vbb_low, vbb_high),
            _candidate(max_vcc, nominal_vbb, "same_ib_multi_vce", 0.86, "Early effect 残差大，补同一基极驱动高 VCE 点。", max_vcc, vbb_low, vbb_high),
        ]
    if name == "low_current_residual":
        return [
            _candidate(min(3.0, max_vcc), vbb_low, "low_current_floor_check", 0.9, "低电流残差大，补测低基极驱动以检查 IS/NF/测量底噪。", max_vcc, vbb_low, vbb_high),
            _candidate(min(4.5, max_vcc), vbb_low, "low_current_floor_check", 0.82, "低电流残差大，改变 VCE 检查漏电/输出电导贡献。", max_vcc, vbb_low, vbb_high),
        ]
    return []


def _nominal_confirmation_candidates(measured: list[dict[str, Any]], plan: TestPlan | None) -> list[dict[str, Any]]:
    max_vcc = _plan_max_vcc(plan)
    vbb_low, vbb_high = _plan_vbb_bounds(plan)
    return [
        _candidate(min(3.0, max_vcc), _nominal_vbb(measured, vbb_low, vbb_high), "confirm_model_residual", 0.62, "整体残差偏高，补测名义放大区点确认模型。", max_vcc, vbb_low, vbb_high)
    ]


def _coverage_followup_candidates(measured: list[dict[str, Any]], plan: TestPlan | None) -> list[dict[str, Any]]:
    max_vcc = _plan_max_vcc(plan)
    vbb_low, vbb_high = _plan_vbb_bounds(plan)
    return [
        _candidate(min(0.8, max_vcc), vbb_high, "improve_saturation_coverage", 0.55, "补充饱和边界覆盖。", max_vcc, vbb_low, vbb_high),
        _candidate(max_vcc, _nominal_vbb(measured, vbb_low, vbb_high), "improve_early_effect_coverage", 0.52, "补充高 VCE 放大区覆盖。", max_vcc, vbb_low, vbb_high),
    ]


def _neighboring_unmeasured_candidates(measured: list[dict[str, Any]], plan: TestPlan | None) -> list[dict[str, Any]]:
    max_vcc = _plan_max_vcc(plan)
    vbb_low, vbb_high = _plan_vbb_bounds(plan)
    nominal = _nominal_vbb(measured, vbb_low, vbb_high)
    anchors = [item for item in measured if item.get("region") in {"active", "saturation"}]
    if not anchors:
        return []
    latest = anchors[-1]
    vcc = float(latest.get("Vcc") or max_vcc)
    candidates = [
        _candidate(max(0.0, vcc - 0.3), nominal, "dedupe_recovery_lower_vce", 0.58, "原残差候选已被测过，改测邻近低 VCE 点观察残差梯度。", max_vcc, vbb_low, vbb_high),
        _candidate(min(max_vcc, vcc + 0.3), nominal, "dedupe_recovery_higher_vce", 0.56, "原残差候选已被测过，改测邻近高 VCE 点观察残差梯度。", max_vcc, vbb_low, vbb_high),
        _candidate(vcc, min(vbb_high, nominal + 0.15), "dedupe_recovery_higher_drive", 0.54, "原残差候选已被测过，改测邻近基极驱动点区分局部模型误差。", max_vcc, vbb_low, vbb_high),
    ]
    return candidates


def _candidate(
    vcc: float,
    vbb: float,
    objective: str,
    score: float,
    rationale: str,
    max_vcc: float,
    vbb_low: float,
    vbb_high: float,
) -> dict[str, Any]:
    return {
        "vcc": round(max(0.0, min(float(vcc), max_vcc)), 3),
        "vbb": round(max(vbb_low, min(float(vbb), vbb_high)), 3),
        "objective": objective,
        "score": round(float(score), 4),
        "rationale": rationale,
    }


def _dedupe_followup_candidates(candidates: list[dict[str, Any]], measured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    measured_keys = {(round(float(item["Vcc"]), 3), round(float(item["Vbb"]), 3)) for item in measured}
    seen: set[tuple[float, float]] = set()
    result = []
    for item in candidates:
        key = (round(float(item["vcc"]), 3), round(float(item["vbb"]), 3))
        if key in measured_keys or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _safety_filter_candidates(candidates: list[dict[str, Any]], plan: TestPlan | None) -> list[dict[str, Any]]:
    if plan is None:
        return candidates
    filtered = []
    for item in candidates:
        if float(item["vcc"]) <= max(plan.vcc_steps or [5.0]) + 1e-9:
            filtered.append({**item, "safety": {"status": "candidate_within_plan_voltage_window"}})
    return filtered


def _followup_summary(candidates: list[dict[str, Any]], diagnosis: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(candidates),
        "diagnosis_count": len(diagnosis),
        "objectives": list(dict.fromkeys(str(item.get("objective")) for item in candidates)),
    }


def _safe_mean(values: list[float], *, default: float) -> float:
    clean = [float(value) for value in values if math.isfinite(float(value)) and float(value) > 0]
    return fmean(clean) if clean else default


def _fit_nf(active: list[dict[str, float | str]]) -> float:
    usable = [item for item in active if float(item["Ic"]) > 0 and float(item["Vbe"]) > 0.1]
    if len(usable) < 2:
        return 1.0
    lo = min(usable, key=lambda item: float(item["Ic"]))
    hi = max(usable, key=lambda item: float(item["Ic"]))
    dv = float(hi["Vbe"]) - float(lo["Vbe"])
    ratio = max(float(hi["Ic"]) / max(float(lo["Ic"]), 1e-15), 1.0001)
    if abs(dv) < 1e-6:
        return 1.0
    nf = dv / (0.02585 * math.log(ratio))
    return max(0.7, min(2.5, nf))


def _plan_max_vcc(plan: TestPlan | None) -> float:
    if plan and plan.vcc_steps:
        return max(float(item) for item in plan.vcc_steps)
    return 5.0


def _plan_vbb_bounds(plan: TestPlan | None) -> tuple[float, float]:
    if plan and plan.vbb_steps:
        return min(float(item) for item in plan.vbb_steps), max(float(item) for item in plan.vbb_steps)
    return 0.9, 3.2


def _nominal_vbb(measured: list[dict[str, Any]], vbb_low: float, vbb_high: float) -> float:
    active = [float(item["Vbb"]) for item in measured if item.get("region") == "active"]
    if active:
        return sorted(active, key=lambda value: active.count(value), reverse=True)[0]
    return max(vbb_low, min(2.0, vbb_high))


def _fit_is(active: list[dict[str, float | str]], nf: float) -> float:
    estimates = []
    for item in active:
        ic = float(item["Ic"])
        vbe = float(item["Vbe"])
        if ic <= 0 or vbe <= 0:
            continue
        estimates.append(ic / max(math.exp(vbe / (nf * 0.02585)) - 1.0, 1e-30))
    return max(min(_safe_mean(estimates, default=1e-14), 1e-8), 1e-20)


def _fit_vaf(active: list[dict[str, float | str]]) -> float:
    if len(active) < 3:
        return 80.0
    groups: dict[float, list[dict[str, float | str]]] = {}
    for item in active:
        groups.setdefault(round(float(item["Vbb"]), 2), []).append(item)
    best_span = 0.0
    best_vaf = 80.0
    for group in groups.values():
        if len(group) < 2:
            continue
        sorted_group = sorted(group, key=lambda item: float(item["Vce"]))
        lo = sorted_group[0]
        hi = sorted_group[-1]
        span = float(hi["Vce"]) - float(lo["Vce"])
        if span <= best_span or float(hi["Ic"]) <= float(lo["Ic"]):
            continue
        slope = (float(hi["Ic"]) - float(lo["Ic"])) / max(span, 1e-9)
        if slope <= 0:
            continue
        intercept_current = fmean([float(lo["Ic"]), float(hi["Ic"])])
        best_vaf = max(10.0, min(500.0, intercept_current / slope))
        best_span = span
    return best_vaf


def _fit_ikf(active: list[dict[str, float | str]], bf: float) -> float:
    if len(active) < 3:
        return 0.1
    sorted_points = sorted(active, key=lambda item: float(item["Ic"]))
    peak_beta = max(float(item["Ic"]) / max(float(item["Ib"]), 1e-12) for item in sorted_points)
    for item in reversed(sorted_points):
        beta = float(item["Ic"]) / max(float(item["Ib"]), 1e-12)
        if beta < peak_beta * 0.75 and float(item["Ic"]) > 0:
            return max(float(item["Ic"]), 1e-4)
    return max(max(float(item["Ic"]) for item in sorted_points) * 3.0, bf * 1e-4)


def _fit_series_resistance(saturated: list[dict[str, float | str]], kind: str) -> float:
    if not saturated:
        return 1.0 if kind == "collector" else 0.5
    estimates = []
    for item in saturated:
        ic = float(item["Ic"])
        vce = abs(float(item["Vce"]))
        if ic <= 0:
            continue
        estimates.append(max(vce - 0.08, 0.0) / ic)
    default = 1.0 if kind == "collector" else 0.5
    return max(0.05, min(_safe_mean(estimates, default=default) * (0.7 if kind == "collector" else 0.3), 50.0))


def _fit_rb(active: list[dict[str, float | str]]) -> float:
    if not active:
        return 10.0
    ib_values = [float(item["Ib"]) for item in active if float(item["Ib"]) > 0]
    if not ib_values:
        return 10.0
    return max(1.0, min(100.0, 0.002 / max(fmean(ib_values), 1e-9)))


def _residual_map(points: list[dict[str, Any]], params: dict[str, float]) -> dict[str, Any]:
    buckets: dict[str, list[float]] = {
        "low_current": [],
        "active_beta": [],
        "high_current": [],
        "saturation": [],
        "early_effect": [],
    }
    for item in points:
        predicted_ic = _predict_ic(item, params)
        actual_ic = float(item["Ic"])
        residual = actual_ic - predicted_ic
        normalized = max(-10.0, min(10.0, residual / max(abs(actual_ic), 1e-9)))
        if item["region"] == "saturation":
            buckets["saturation"].append(normalized)
        elif actual_ic < 1e-3:
            buckets["low_current"].append(normalized)
        elif actual_ic > float(params["IKF"]):
            buckets["high_current"].append(normalized)
        else:
            buckets["active_beta"].append(normalized)
        if item["region"] == "active" and abs(float(item["Vce"])) > 1.0:
            buckets["early_effect"].append(normalized)
    summary = {
        key: {
            "count": len(values),
            "mean_abs": round(fmean([abs(value) for value in values]), 5) if values else None,
            "max_abs": round(max([abs(value) for value in values]), 5) if values else None,
        }
        for key, values in buckets.items()
    }
    all_values = [abs(value) for values in buckets.values() for value in values]
    return {
        "normalized_current_residual": summary,
        "overall_mean_abs": round(fmean(all_values), 5) if all_values else None,
        "point_count": len(points),
    }


def _predict_ic(item: dict[str, Any], params: dict[str, float]) -> float:
    vbe = float(item["Vbe"])
    vce = max(float(item["Vce"]), 0.0)
    ib = max(float(item["Ib"]), 0.0)
    diode_ic = params["IS"] * (math.exp(max(vbe, 0.0) / (params["NF"] * 0.02585)) - 1.0)
    beta_ic = params["BF"] * ib
    early = 1.0 + max(vce, 0.0) / max(params["VAF"], 1e-9)
    predicted = max(min(diode_ic, beta_ic * 2.0), beta_ic * 0.4) * early
    if item["region"] == "saturation":
        return min(predicted, max(vce / max(params["RC"] + params["RE"], 1e-9), 0.0))
    if predicted > params["IKF"]:
        predicted = params["IKF"] + (predicted - params["IKF"]) * 0.55
    return max(predicted, 0.0)


def _diagnose_residuals(residuals: dict[str, Any]) -> list[dict[str, Any]]:
    diagnosis: list[dict[str, Any]] = []
    bucket = residuals.get("normalized_current_residual", {})
    mapping = {
        "low_current": ("low_current_residual", "leakage / IS / NF / measurement floor"),
        "high_current": ("high_current_residual", "IKF / self-heating / high-injection effect"),
        "saturation": ("saturation_residual", "RC / RE / contact / package resistance"),
        "early_effect": ("early_effect_residual", "VAF / output conductance mismatch"),
    }
    for key, (name, physical_hint) in mapping.items():
        value = bucket.get(key, {}).get("mean_abs") if isinstance(bucket.get(key), dict) else None
        if isinstance(value, (int, float)) and value > 0.35:
            diagnosis.append(
                {
                    "name": name,
                    "severity": "high" if value > 0.75 else "medium",
                    "mean_abs_residual": value,
                    "physical_hint": physical_hint,
                }
            )
    return diagnosis


def _suggest_followups(diagnosis: list[dict[str, Any]], residuals: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    names = {item["name"] for item in diagnosis}
    if "saturation_residual" in names:
        suggestions.append({"objective": "vce_sat_vs_ic", "rationale": "饱和区残差集中，补测 VCE(sat) vs IC 以区分串联电阻/接触问题。"})
    if "high_current_residual" in names:
        suggestions.append({"objective": "pulse_width_sweep", "rationale": "高电流残差较大，补测不同 pulse width 以区分自热与高注入效应。"})
    if "early_effect_residual" in names:
        suggestions.append({"objective": "same_ib_multi_vce", "rationale": "Early effect 残差较大，补测同一基极驱动下多组 VCE。"})
    if "low_current_residual" in names:
        suggestions.append({"objective": "low_current_floor_check", "rationale": "低电流残差较大，补测漏电/测量底噪。"})
    if not suggestions and (residuals.get("overall_mean_abs") or 0) > 0.25:
        suggestions.append({"objective": "confirm_nominal_active_point", "rationale": "整体残差仍偏高，补测名义放大区工作点确认模型。"})
    return suggestions


def _confidence(active: list[dict[str, float | str]], saturated: list[dict[str, float | str]], residuals: dict[str, Any]) -> float:
    point_score = min(1.0, (len(active) + len(saturated)) / 10.0)
    region_score = 0.25 + (0.35 if active else 0.0) + (0.25 if saturated else 0.0)
    residual = residuals.get("overall_mean_abs")
    residual_score = 0.2 if residual is None else max(0.0, 0.4 - min(float(residual), 1.0) * 0.4)
    return round(max(0.0, min(1.0, point_score * 0.35 + region_score * 0.35 + residual_score)), 3)


def _model_card(model_name: str, device_type: str, params: dict[str, float]) -> str:
    ordered = ["IS", "BF", "NF", "VAF", "IKF", "ISE", "NE", "RB", "RC", "RE"]
    body = "\n+ ".join("{0}={1}".format(name, _format_spice_value(params[name])) for name in ordered)
    return ".model {0} {1} (\n+ {2}\n)".format(model_name, device_type, body)


def _spice_model_name(model: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(model or "DUT"))
    return "DUT_{0}".format(clean.upper() or "UNKNOWN")


def _format_spice_value(value: float) -> str:
    if abs(value) < 1e-3 or abs(value) >= 1e4:
        return "{:.4e}".format(value)
    return "{:.5g}".format(value)


def _rounded_param(value: float) -> float:
    if abs(value) < 1e-3:
        return float("{:.6e}".format(value))
    return round(float(value), 6)
