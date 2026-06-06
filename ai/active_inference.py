from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import fmean
from typing import Any

from ai.dut_belief import DUTBeliefState, MeasurementCandidate, suggest_next_measurements_for_state
from ai.experiment_goal import ExperimentGoal, goal_from_plan
from ai.test_planner import TestPlan


@dataclass(frozen=True)
class ActiveInferenceCandidate:
    vcc: float
    vbb: float
    objective: str
    uncertainty_target: str
    prior_uncertainty: float
    expected_uncertainty_after: float
    expected_information_gain: float
    estimated_cost: float
    utility: float
    safety_status: str
    safety_reasons: list[str] = field(default_factory=list)
    rationale: str = ""
    source_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchDesign:
    goal: ExperimentGoal
    selected: list[ActiveInferenceCandidate]
    rejected: list[ActiveInferenceCandidate]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "selected": [item.to_dict() for item in self.selected],
            "rejected": [item.to_dict() for item in self.rejected],
            "summary": dict(self.summary),
        }


def design_next_measurement_batch(
    belief: DUTBeliefState | None,
    *,
    goal: ExperimentGoal | None = None,
    plan: TestPlan | None = None,
    budget: int = 3,
    previous_measurement: dict[str, Any] | None = None,
) -> BatchDesign:
    budget = max(1, min(int(budget or 3), 12))
    active_goal = goal or goal_from_plan(plan)
    raw_candidates = suggest_next_measurements_for_state(
        belief,
        plan=plan,
        budget=max(budget * 4, 8),
    )
    scored = [
        _score_candidate(candidate, belief=belief, goal=active_goal, plan=plan, previous_measurement=previous_measurement)
        for candidate in raw_candidates
    ]
    allowed = sorted((item for item in scored if item.safety_status == "allow"), key=lambda item: item.utility, reverse=True)
    rejected = sorted((item for item in scored if item.safety_status != "allow"), key=lambda item: item.utility, reverse=True)
    selected = allowed[:budget]
    return BatchDesign(
        goal=active_goal,
        selected=selected,
        rejected=rejected,
        summary={
            "candidate_count": len(scored),
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "objective": "maximize_expected_information_gain_per_cost_under_safety_constraints",
            "total_expected_information_gain": round(sum(item.expected_information_gain for item in selected), 5),
            "mean_utility": round(fmean([item.utility for item in selected]), 5) if selected else 0.0,
            "covered_uncertainty_targets": list(dict.fromkeys(item.uncertainty_target for item in selected)),
            "safety_filter": "static_voltage_current_power_guard",
        },
    )


def _score_candidate(
    candidate: MeasurementCandidate,
    *,
    belief: DUTBeliefState | None,
    goal: ExperimentGoal,
    plan: TestPlan | None,
    previous_measurement: dict[str, Any] | None,
) -> ActiveInferenceCandidate:
    target = _target_from_objective(candidate.objective, goal)
    prior_uncertainty = _belief_uncertainty(belief, target)
    goal_bonus = 1.25 if target in set(goal.projection_variables) else 1.0
    source_score = max(0.05, min(float(candidate.score or 0.0), 1.5))
    reduction_fraction = max(0.05, min(0.72, 0.16 + source_score * 0.28))
    expected_information_gain = max(0.0, min(prior_uncertainty, prior_uncertainty * reduction_fraction * goal_bonus))
    expected_after = max(0.0, prior_uncertainty - expected_information_gain)
    safety_status, safety_reasons = _safety_for_candidate(candidate, belief=belief, plan=plan)
    cost = _measurement_cost(candidate, belief=belief, plan=plan, previous_measurement=previous_measurement)
    utility = expected_information_gain / max(cost, 1e-9)
    if safety_status != "allow":
        utility = 0.0
    return ActiveInferenceCandidate(
        vcc=round(float(candidate.vcc), 4),
        vbb=round(float(candidate.vbb), 4),
        objective=candidate.objective,
        uncertainty_target=target,
        prior_uncertainty=round(prior_uncertainty, 5),
        expected_uncertainty_after=round(expected_after, 5),
        expected_information_gain=round(expected_information_gain, 5),
        estimated_cost=round(cost, 5),
        utility=round(utility, 5),
        safety_status=safety_status,
        safety_reasons=safety_reasons,
        rationale=candidate.rationale,
        source_score=round(source_score, 5),
    )


def _target_from_objective(objective: str, goal: ExperimentGoal) -> str:
    lowered = objective.lower()
    if "saturation" in lowered or "sat" in lowered or "knee" in lowered:
        return "saturation_region_uncertainty"
    if "early" in lowered or "vaf" in lowered or "multi_vce" in lowered:
        return "early_voltage_uncertainty"
    if "beta" in lowered or "gain" in lowered:
        return "beta_distribution"
    if "vbe" in lowered or "low_current" in lowered:
        return "vbe_model"
    if "residual" in lowered or "spice" in lowered or goal.kind == "EXTRACT_MODEL":
        return "spice_parameter_posterior"
    if goal.kind == "IDENTIFY":
        return "pinout_confidence"
    return goal.projection_variables[0] if goal.projection_variables else "uncertainty"


def _belief_uncertainty(belief: DUTBeliefState | None, target: str) -> float:
    if belief is None:
        return 1.0
    if target == "pinout_confidence":
        return max(0.0, min(1.0, 1.0 - float(belief.pinout_confidence or 0.0)))
    if target == "spice_parameter_posterior":
        values = [
            float(item.get("uncertainty"))
            for item in (belief.spice_parameter_posterior or {}).values()
            if isinstance(item, dict) and isinstance(item.get("uncertainty"), (int, float))
        ]
        return max(0.05, min(1.0, fmean(values))) if values else float((belief.uncertainty or {}).get("overall") or 1.0)
    if target in {"beta_distribution", "beta"}:
        return float((belief.uncertainty or {}).get("beta") or 1.0)
    if target == "vbe_model":
        return float((belief.uncertainty or {}).get("vbe") or 1.0)
    if target == "saturation_region_uncertainty":
        return float((belief.uncertainty or {}).get("saturation_region") or belief.saturation_region_uncertainty or 1.0)
    if target == "early_voltage_uncertainty":
        return float((belief.uncertainty or {}).get("early_voltage") or belief.early_voltage_uncertainty or 1.0)
    return float((belief.uncertainty or {}).get("overall") or 1.0)


def _safety_for_candidate(
    candidate: MeasurementCandidate,
    *,
    belief: DUTBeliefState | None,
    plan: TestPlan | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    vcc = float(candidate.vcc)
    vbb = float(candidate.vbb)
    if vcc < 0.0 or vbb < 0.0:
        return "reject", ["negative voltage candidate"]
    if plan is None:
        if vcc <= 5.5 and vbb <= 3.5:
            return "allow", ["within default low-voltage BJT envelope"]
        return "reject", ["outside default low-voltage BJT envelope"]

    max_vcc = max(float(item) for item in plan.vcc_steps) if plan.vcc_steps else 5.0
    vbb_low = min(float(item) for item in plan.vbb_steps) if plan.vbb_steps else 0.0
    vbb_high = max(float(item) for item in plan.vbb_steps) if plan.vbb_steps else 3.3
    if vcc > max_vcc + 1e-9:
        reasons.append("vcc exceeds plan envelope")
    if vbb < vbb_low - 0.15 or vbb > vbb_high + 0.15:
        reasons.append("vbb outside plan drive envelope")

    estimated_ic = _estimate_candidate_ic(candidate, belief=belief, plan=plan)
    estimated_power = vcc * estimated_ic
    if estimated_ic > plan.ic_limit_a * 1.05:
        reasons.append("estimated collector current exceeds plan limit")
    if estimated_power > plan.power_limit_w * 1.05:
        reasons.append("estimated power exceeds plan limit")
    if reasons:
        return "reject", reasons
    return "allow", ["within plan voltage/current/power envelope"]


def _measurement_cost(
    candidate: MeasurementCandidate,
    *,
    belief: DUTBeliefState | None,
    plan: TestPlan | None,
    previous_measurement: dict[str, Any] | None,
) -> float:
    vcc = float(candidate.vcc)
    vbb = float(candidate.vbb)
    if previous_measurement:
        prev_vcc = float(previous_measurement.get("Vcc", previous_measurement.get("vcc", vcc)) or vcc)
        prev_vbb = float(previous_measurement.get("Vbb", previous_measurement.get("vbb", vbb)) or vbb)
    elif belief and belief.measured_points:
        last = belief.measured_points[-1]
        prev_vcc = float(last.get("Vcc", vcc) or vcc)
        prev_vbb = float(last.get("Vbb", vbb) or vbb)
    else:
        prev_vcc = vcc
        prev_vbb = vbb
    reconfiguration_cost = 0.08 * abs(vcc - prev_vcc) + 0.05 * abs(vbb - prev_vbb)
    current = _estimate_candidate_ic(candidate, belief=belief, plan=plan)
    thermal_cost = 0.0
    if plan:
        thermal_cost = min(1.0, (vcc * current) / max(plan.power_limit_w, 1e-9)) * 0.45
    objective_cost = 0.12 if "saturation" in candidate.objective else 0.0
    return 1.0 + reconfiguration_cost + thermal_cost + objective_cost


def _estimate_candidate_ic(
    candidate: MeasurementCandidate,
    *,
    belief: DUTBeliefState | None,
    plan: TestPlan | None,
) -> float:
    beta = 60.0
    if belief and isinstance((belief.beta_distribution or {}).get("mean"), (int, float)):
        beta = max(5.0, min(300.0, float((belief.beta_distribution or {}).get("mean"))))
    ib = max((float(candidate.vbb) - 0.68) / 22000.0, 0.0)
    estimated = beta * ib
    if plan:
        estimated = min(estimated, float(plan.ic_limit_a) * 0.95)
    return max(0.0, estimated)
