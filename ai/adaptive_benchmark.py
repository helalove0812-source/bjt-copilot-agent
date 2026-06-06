from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai.spice_twin import extract_spice_twin_from_belief
from ai.test_planner import TestPlan, build_test_plan
from ai.tool_runtime import BJTToolRuntime


@dataclass(frozen=True)
class CharacterizationBenchmark:
    model: str
    adaptive: dict[str, Any]
    fixed_grid: dict[str, Any]
    comparison: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def benchmark_adaptive_vs_fixed(
    *,
    model: str = "S8050",
    goal: str = "full",
    depth: str = "standard",
    adaptive_iterations: int = 3,
    adaptive_batch_size: int = 2,
) -> CharacterizationBenchmark:
    plan = build_test_plan(model=model, goal=goal, depth=depth, mode="simulation")
    adaptive = _run_adaptive(plan, iterations=adaptive_iterations, batch_size=adaptive_batch_size)
    fixed = _run_fixed_grid(plan, point_budget=max(1, adaptive["point_count"]))
    fixed_match = _find_fixed_budget_to_match(plan, adaptive.get("residual_overall_mean_abs"), start_budget=max(1, adaptive["point_count"]))
    return CharacterizationBenchmark(
        model=plan.model,
        adaptive=adaptive,
        fixed_grid=fixed,
        comparison=_compare_runs(adaptive, fixed, fixed_match),
    )


def _run_adaptive(plan: TestPlan, *, iterations: int, batch_size: int) -> dict[str, Any]:
    runtime = BJTToolRuntime(current_plan=plan)
    result = runtime.dispatch(
        "run_adaptive_characterization",
        {"mode": "simulation", "iterations": iterations, "batch_size": batch_size},
    ).result
    twin = runtime.dispatch("extract_spice_twin", {"include_model_card": True}).result["spice_twin"]
    return _run_summary(
        label="adaptive",
        measurements=list(result.get("measurements") or []),
        twin=twin,
        trace=list(result.get("adaptive_trace") or []),
    )


def _run_fixed_grid(plan: TestPlan, *, point_budget: int) -> dict[str, Any]:
    runtime = BJTToolRuntime(current_plan=plan)
    measurements: list[dict[str, Any]] = []
    for point in _fixed_grid_points(plan, point_budget):
        result = runtime.dispatch("run_static_point", {"mode": "simulation", "vcc": point["vcc"], "vbb": point["vbb"]}).result
        if result.get("ok") and isinstance(result.get("measurement"), dict):
            measurements.append(result["measurement"])
    runtime.dispatch("update_dut_belief", {"measurements": measurements, "reset": True})
    twin = runtime.dispatch("extract_spice_twin", {"include_model_card": True}).result["spice_twin"]
    return _run_summary(label="fixed_grid", measurements=measurements, twin=twin, trace=[])


def _fixed_grid_points(plan: TestPlan, point_budget: int) -> list[dict[str, float]]:
    grid = [{"vcc": float(vcc), "vbb": float(vbb)} for vbb in plan.vbb_steps for vcc in plan.vcc_steps]
    if not grid:
        return [{"vcc": 3.0, "vbb": 2.0}]
    budget = max(1, min(int(point_budget), len(grid)))
    if budget == 1:
        return [grid[len(grid) // 2]]
    step = (len(grid) - 1) / float(budget - 1)
    indices = sorted({round(index * step) for index in range(budget)})
    return [grid[int(index)] for index in indices[:budget]]


def _find_fixed_budget_to_match(
    plan: TestPlan,
    target_residual: Any,
    *,
    start_budget: int,
) -> dict[str, Any]:
    max_budget = max(1, len(plan.vcc_steps) * len(plan.vbb_steps))
    if not isinstance(target_residual, (int, float)):
        return {
            "matched": False,
            "target_residual": target_residual,
            "fixed_points_to_match": None,
            "max_fixed_points": max_budget,
            "best_fixed_residual": None,
        }
    best: dict[str, Any] | None = None
    budgets = _budget_search_points(start_budget, max_budget)
    for budget in budgets:
        run = _run_fixed_grid(plan, point_budget=budget)
        residual = run.get("residual_overall_mean_abs")
        if best is None or _residual_is_better(residual, best.get("residual_overall_mean_abs")):
            best = run
        if isinstance(residual, (int, float)) and float(residual) <= float(target_residual):
            return {
                "matched": True,
                "target_residual": target_residual,
                "fixed_points_to_match": run["point_count"],
                "max_fixed_points": max_budget,
                "best_fixed_residual": residual,
            }
    return {
        "matched": False,
        "target_residual": target_residual,
        "fixed_points_to_match": None,
        "max_fixed_points": max_budget,
        "best_fixed_residual": best.get("residual_overall_mean_abs") if best else None,
    }


def _budget_search_points(start_budget: int, max_budget: int) -> list[int]:
    start = max(1, min(int(start_budget), int(max_budget)))
    values = {start, max_budget}
    current = start
    while current < max_budget:
        current = min(max_budget, max(current + 1, int(round(current * 1.5))))
        values.add(current)
    return sorted(values)


def _residual_is_better(candidate: Any, incumbent: Any) -> bool:
    if not isinstance(candidate, (int, float)):
        return False
    if not isinstance(incumbent, (int, float)):
        return True
    return float(candidate) < float(incumbent)


def _run_summary(
    *,
    label: str,
    measurements: list[dict[str, Any]],
    twin: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    residual = twin.get("residuals", {})
    regions: dict[str, int] = {}
    for point in measurements:
        region = str(point.get("region") or "unknown")
        regions[region] = regions.get(region, 0) + 1
    return {
        "label": label,
        "point_count": len(measurements),
        "regions": regions,
        "residual_overall_mean_abs": residual.get("overall_mean_abs"),
        "twin_confidence": twin.get("confidence"),
        "diagnosis": twin.get("diagnosis", []),
        "suggested_followups": twin.get("suggested_followups", []),
        "model_card": twin.get("model_card", ""),
        "trace": trace,
    }


def _compare_runs(adaptive: dict[str, Any], fixed: dict[str, Any], fixed_match: dict[str, Any]) -> dict[str, Any]:
    adaptive_residual = adaptive.get("residual_overall_mean_abs")
    fixed_residual = fixed.get("residual_overall_mean_abs")
    residual_delta = None
    residual_ratio = None
    if isinstance(adaptive_residual, (int, float)) and isinstance(fixed_residual, (int, float)):
        residual_delta = round(float(fixed_residual) - float(adaptive_residual), 6)
        residual_ratio = round(float(adaptive_residual) / max(float(fixed_residual), 1e-12), 6)
    confidence_delta = None
    if isinstance(adaptive.get("twin_confidence"), (int, float)) and isinstance(fixed.get("twin_confidence"), (int, float)):
        confidence_delta = round(float(adaptive["twin_confidence"]) - float(fixed["twin_confidence"]), 6)
    fixed_points_to_match = fixed_match.get("fixed_points_to_match")
    point_reduction_fraction = None
    if isinstance(fixed_points_to_match, int) and fixed_points_to_match > 0 and isinstance(adaptive.get("point_count"), int):
        point_reduction_fraction = round(1.0 - (int(adaptive["point_count"]) / float(fixed_points_to_match)), 6)
    lower_bound_reduction = None
    if fixed_match.get("matched") is False and isinstance(fixed_match.get("max_fixed_points"), int) and isinstance(adaptive.get("point_count"), int):
        lower_bound_reduction = round(1.0 - (int(adaptive["point_count"]) / float(fixed_match["max_fixed_points"])), 6)
    adaptive_beats_full_fixed = False
    if fixed_match.get("matched") is False and isinstance(adaptive_residual, (int, float)) and isinstance(fixed_match.get("best_fixed_residual"), (int, float)):
        adaptive_beats_full_fixed = float(adaptive_residual) < float(fixed_match["best_fixed_residual"])
    return {
        "same_point_budget": adaptive.get("point_count") == fixed.get("point_count"),
        "point_budget": adaptive.get("point_count"),
        "residual_delta_fixed_minus_adaptive": residual_delta,
        "adaptive_residual_ratio": residual_ratio,
        "confidence_delta_adaptive_minus_fixed": confidence_delta,
        "fixed_grid_match": fixed_match,
        "point_reduction_fraction_vs_fixed_match": point_reduction_fraction,
        "lower_bound_point_reduction_fraction": lower_bound_reduction,
        "adaptive_beats_full_fixed_grid": adaptive_beats_full_fixed,
        "adaptive_region_coverage": adaptive.get("regions", {}),
        "fixed_region_coverage": fixed.get("regions", {}),
    }
