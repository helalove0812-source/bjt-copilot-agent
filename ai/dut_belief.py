from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import fmean, pstdev
from typing import Any

from ai.test_planner import TestPlan


@dataclass(frozen=True)
class MeasurementCandidate:
    vcc: float
    vbb: float
    objective: str
    score: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DUTBeliefState:
    model: str = "UNKNOWN"
    device_type: str = "UNKNOWN"
    pinout_confidence: float = 0.0
    measured_points: list[dict[str, Any]] = field(default_factory=list)
    region_counts: dict[str, int] = field(default_factory=dict)
    beta_distribution: dict[str, float | int | None] = field(default_factory=dict)
    vbe_model: dict[str, float | int | None] = field(default_factory=dict)
    saturation_region_uncertainty: float = 1.0
    early_voltage_uncertainty: float = 1.0
    spice_parameter_posterior: dict[str, dict[str, float | None]] = field(default_factory=dict)
    anomaly_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: dict[str, float] = field(default_factory=dict)
    next_measurement_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def update_belief_from_measurements(
    belief: DUTBeliefState | None,
    measurements: list[dict[str, Any]],
    *,
    plan: TestPlan | None = None,
    model: str | None = None,
) -> DUTBeliefState:
    existing = belief.measured_points if belief else []
    merged = _dedupe_points(existing + [_normalize_point(item) for item in measurements])
    model_name = model or (plan.model if plan else None) or (belief.model if belief else "UNKNOWN")
    device_type = _infer_device_type(merged, plan=plan, fallback=belief.device_type if belief else "UNKNOWN")
    region_counts = _region_counts(merged)
    active_points = [item for item in merged if item.get("region") == "active" and float(item.get("beta") or 0.0) > 0.0]
    saturated_points = [item for item in merged if item.get("region") == "saturation"]
    beta_distribution = _beta_distribution(active_points)
    vbe_model = _vbe_model(active_points)
    saturation_uncertainty = _saturation_uncertainty(saturated_points, merged)
    early_uncertainty = _early_voltage_uncertainty(active_points)
    anomaly_hypotheses = _anomaly_hypotheses(merged, beta_distribution, vbe_model)
    uncertainty = {
        "beta": _beta_uncertainty(beta_distribution),
        "vbe": _vbe_uncertainty(vbe_model),
        "saturation_region": saturation_uncertainty,
        "early_voltage": early_uncertainty,
        "overall": round(
            fmean(
                [
                    _beta_uncertainty(beta_distribution),
                    _vbe_uncertainty(vbe_model),
                    saturation_uncertainty,
                    early_uncertainty,
                ]
            ),
            4,
        ),
    }
    next_candidates = suggest_next_measurements_for_state(
        DUTBeliefState(
            model=model_name,
            device_type=device_type,
            pinout_confidence=_pinout_confidence(merged, device_type),
            measured_points=merged,
            region_counts=region_counts,
            beta_distribution=beta_distribution,
            vbe_model=vbe_model,
            saturation_region_uncertainty=saturation_uncertainty,
            early_voltage_uncertainty=early_uncertainty,
            spice_parameter_posterior=_spice_posterior(beta_distribution, vbe_model, early_uncertainty),
            anomaly_hypotheses=anomaly_hypotheses,
            uncertainty=uncertainty,
        ),
        plan=plan,
        budget=5,
    )
    return DUTBeliefState(
        model=model_name,
        device_type=device_type,
        pinout_confidence=_pinout_confidence(merged, device_type),
        measured_points=merged,
        region_counts=region_counts,
        beta_distribution=beta_distribution,
        vbe_model=vbe_model,
        saturation_region_uncertainty=saturation_uncertainty,
        early_voltage_uncertainty=early_uncertainty,
        spice_parameter_posterior=_spice_posterior(beta_distribution, vbe_model, early_uncertainty),
        anomaly_hypotheses=anomaly_hypotheses,
        uncertainty=uncertainty,
        next_measurement_candidates=[item.to_dict() for item in next_candidates],
    )


def suggest_next_measurements_for_state(
    belief: DUTBeliefState | None,
    *,
    plan: TestPlan | None = None,
    budget: int = 3,
) -> list[MeasurementCandidate]:
    budget = max(1, min(int(budget or 3), 10))
    measured = belief.measured_points if belief else []
    max_vcc = _plan_max_vcc(plan)
    vbb_low, vbb_high = _plan_vbb_bounds(plan)
    candidates: list[MeasurementCandidate] = []

    if not measured:
        seeds = [
            (min(3.0, max_vcc), _clamp(1.0, vbb_low, vbb_high), "seed_cutoff_or_low_drive", 0.82),
            (min(3.0, max_vcc), _clamp(2.0, vbb_low, vbb_high), "seed_nominal_active", 0.95),
            (min(1.0, max_vcc), _clamp(2.8, vbb_low, vbb_high), "seed_saturation_boundary", 0.9),
            (min(5.0, max_vcc), _clamp(2.0, vbb_low, vbb_high), "seed_early_effect", 0.72),
        ]
        return _dedupe_candidates(
            [
                MeasurementCandidate(
                    vcc=round(vcc, 3),
                    vbb=round(vbb, 3),
                    objective=objective,
                    score=score,
                    rationale="建立初始 DUT belief：覆盖低驱动、典型放大区、饱和边界和 VCE 依赖。",
                )
                for vcc, vbb, objective, score in seeds
            ],
            measured,
        )[:budget]

    uncertainty = belief.uncertainty if belief else {}
    if uncertainty.get("saturation_region", 1.0) >= 0.45:
        for vcc in (0.25, 0.5, 0.8, 1.2):
            candidates.append(
                MeasurementCandidate(
                    vcc=round(min(vcc, max_vcc), 3),
                    vbb=round(_clamp(vbb_high, vbb_low, vbb_high), 3),
                    objective="reduce_saturation_boundary_uncertainty",
                    score=0.9 + uncertainty.get("saturation_region", 1.0) * 0.2,
                    rationale="当前饱和区边界不确定，低 Vcc + 高 Vbb 测点更容易定位 VCE(sat) knee。",
                )
            )
    if uncertainty.get("beta", 1.0) >= 0.25:
        mid_vbb = (vbb_low + vbb_high) / 2.0
        for vbb in (mid_vbb - 0.25, mid_vbb, mid_vbb + 0.25):
            candidates.append(
                MeasurementCandidate(
                    vcc=round(min(3.0, max_vcc), 3),
                    vbb=round(_clamp(vbb, vbb_low, vbb_high), 3),
                    objective="reduce_beta_distribution_uncertainty",
                    score=0.78 + uncertainty.get("beta", 1.0) * 0.25,
                    rationale="当前 beta 分布样本不足或离散度较高，补充典型 VCE 下不同基极驱动点。",
                )
            )
    if uncertainty.get("early_voltage", 1.0) >= 0.4:
        nominal_vbb = _most_common_active_vbb(measured) or _clamp(2.0, vbb_low, vbb_high)
        for vcc in (1.5, 3.0, max_vcc):
            candidates.append(
                MeasurementCandidate(
                    vcc=round(min(vcc, max_vcc), 3),
                    vbb=round(nominal_vbb, 3),
                    objective="reduce_early_voltage_uncertainty",
                    score=0.74 + uncertainty.get("early_voltage", 1.0) * 0.2,
                    rationale="当前放大区 VCE 跨度不足，补充同一驱动下不同 Vcc 点以估计输出电导/Early effect。",
                )
            )
    if not candidates:
        candidates.append(
            MeasurementCandidate(
                vcc=round(min(3.0, max_vcc), 3),
                vbb=round(_clamp(2.0, vbb_low, vbb_high), 3),
                objective="confirm_model_residual",
                score=0.5,
                rationale="主要不确定性已下降，补充名义工作点用于确认模型残差。",
            )
        )
    return _dedupe_candidates(sorted(candidates, key=lambda item: item.score, reverse=True), measured)[:budget]


def _normalize_point(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "Vbb": round(float(item.get("Vbb", item.get("vbb", 0.0)) or 0.0), 4),
        "Vcc": round(float(item.get("Vcc", item.get("vcc", 0.0)) or 0.0), 4),
        "Vbe": round(float(item.get("Vbe", item.get("vbe", 0.0)) or 0.0), 6),
        "Vce": round(float(item.get("Vce", item.get("vce", 0.0)) or 0.0), 6),
        "Ib": float(item.get("Ib", item.get("ib", 0.0)) or 0.0),
        "Ic": float(item.get("Ic", item.get("ic", 0.0)) or 0.0),
        "beta": round(float(item.get("beta", 0.0) or 0.0), 4),
        "region": str(item.get("region") or "cutoff"),
    }


def _dedupe_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[float, float], dict[str, Any]] = {}
    for item in points:
        merged[(round(float(item["Vcc"]), 3), round(float(item["Vbb"]), 3))] = item
    return list(merged.values())


def _region_counts(points: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"cutoff": 0, "active": 0, "saturation": 0}
    for item in points:
        region = str(item.get("region") or "cutoff")
        counts[region] = counts.get(region, 0) + 1
    return counts


def _beta_distribution(points: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [float(item.get("beta") or 0.0) for item in points if float(item.get("beta") or 0.0) > 0.0]
    if not values:
        return {"count": 0, "mean": None, "std": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(fmean(values), 4),
        "std": round(pstdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _vbe_model(points: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [float(item.get("Vbe") or 0.0) for item in points if abs(float(item.get("Vbe") or 0.0)) > 0.1]
    if not values:
        return {"count": 0, "mean_v": None, "std_v": None}
    return {"count": len(values), "mean_v": round(fmean(values), 5), "std_v": round(pstdev(values), 5) if len(values) > 1 else 0.0}


def _saturation_uncertainty(saturated_points: list[dict[str, Any]], all_points: list[dict[str, Any]]) -> float:
    if not all_points:
        return 1.0
    if not saturated_points:
        return 0.85
    if len(saturated_points) < 3:
        return 0.55
    return 0.25


def _early_voltage_uncertainty(active_points: list[dict[str, Any]]) -> float:
    if len(active_points) < 3:
        return 0.85
    span = max(float(item["Vce"]) for item in active_points) - min(float(item["Vce"]) for item in active_points)
    if span < 0.7:
        return 0.75
    if span < 1.5:
        return 0.45
    return 0.25


def _beta_uncertainty(distribution: dict[str, float | int | None]) -> float:
    count = int(distribution.get("count") or 0)
    mean = distribution.get("mean")
    std = distribution.get("std")
    if count < 2 or not isinstance(mean, (int, float)) or mean <= 0:
        return 0.9
    relative = float(std or 0.0) / max(float(mean), 1e-9)
    return round(max(0.1, min(0.9, relative + 1.0 / (count + 1))), 4)


def _vbe_uncertainty(model: dict[str, float | int | None]) -> float:
    count = int(model.get("count") or 0)
    if count < 2:
        return 0.75
    std = float(model.get("std_v") or 0.0)
    return round(max(0.1, min(0.75, std / 0.08 + 1.0 / (count + 2))), 4)


def _spice_posterior(
    beta_distribution: dict[str, float | int | None],
    vbe_model: dict[str, float | int | None],
    early_uncertainty: float,
) -> dict[str, dict[str, float | None]]:
    beta = beta_distribution.get("mean")
    vbe = vbe_model.get("mean_v")
    return {
        "BF": {"mean": float(beta) if isinstance(beta, (int, float)) else None, "uncertainty": _beta_uncertainty(beta_distribution)},
        "VJE_proxy": {"mean": float(vbe) if isinstance(vbe, (int, float)) else None, "uncertainty": _vbe_uncertainty(vbe_model)},
        "VAF": {"mean": None, "uncertainty": early_uncertainty},
    }


def _anomaly_hypotheses(
    points: list[dict[str, Any]],
    beta_distribution: dict[str, float | int | None],
    vbe_model: dict[str, float | int | None],
) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    beta_mean = beta_distribution.get("mean")
    vbe_mean = vbe_model.get("mean_v")
    if isinstance(beta_mean, (int, float)) and beta_mean < 50 and len(points) >= 2:
        hypotheses.append({"name": "low_beta_or_wrong_bias", "confidence": 0.45, "evidence": "active-region beta mean is below 50"})
    if isinstance(vbe_mean, (int, float)) and vbe_mean > 0.9:
        hypotheses.append({"name": "darlington_or_pinout_issue", "confidence": 0.55, "evidence": "VBE mean is unusually high"})
    if points and all(float(item.get("Ic") or 0.0) <= 1e-9 for item in points):
        hypotheses.append({"name": "open_circuit_or_wrong_pinout", "confidence": 0.65, "evidence": "all measured collector currents are near zero"})
    return hypotheses


def _infer_device_type(points: list[dict[str, Any]], *, plan: TestPlan | None, fallback: str) -> str:
    if plan and plan.bjt_type in {"NPN", "PNP"}:
        return plan.bjt_type
    if any(float(item.get("Ic") or 0.0) > 0 for item in points):
        return "NPN"
    return fallback or "UNKNOWN"


def _pinout_confidence(points: list[dict[str, Any]], device_type: str) -> float:
    if device_type not in {"NPN", "PNP"}:
        return 0.1
    active_or_sat = sum(1 for item in points if item.get("region") in {"active", "saturation"})
    return round(min(0.95, 0.35 + active_or_sat * 0.15), 3)


def _plan_max_vcc(plan: TestPlan | None) -> float:
    if plan and plan.vcc_steps:
        return max(float(item) for item in plan.vcc_steps)
    return 5.0


def _plan_vbb_bounds(plan: TestPlan | None) -> tuple[float, float]:
    if plan and plan.vbb_steps:
        return min(float(item) for item in plan.vbb_steps), max(float(item) for item in plan.vbb_steps)
    return 0.9, 3.2


def _most_common_active_vbb(points: list[dict[str, Any]]) -> float | None:
    active = [float(item["Vbb"]) for item in points if item.get("region") == "active"]
    if not active:
        return None
    return sorted(active, key=lambda value: active.count(value), reverse=True)[0]


def _dedupe_candidates(candidates: list[MeasurementCandidate], measured: list[dict[str, Any]]) -> list[MeasurementCandidate]:
    measured_keys = {(round(float(item["Vcc"]), 3), round(float(item["Vbb"]), 3)) for item in measured}
    result: list[MeasurementCandidate] = []
    seen: set[tuple[float, float]] = set()
    for item in candidates:
        key = (round(float(item.vcc), 3), round(float(item.vbb), 3))
        if key in measured_keys or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
