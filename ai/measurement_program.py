from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ai.dut_belief import DUTBeliefState
from ai.unknown_device import TopologyHypothesis


PrimitiveKind = Literal["source", "measure", "sweep", "pulse", "analyze"]


@dataclass(frozen=True)
class MeasurementPrimitive:
    kind: PrimitiveKind
    name: str
    args: dict[str, Any]
    objective: str
    expected_observation: str = ""
    safety: dict[str, Any] = field(default_factory=dict)
    belief_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeasurementProgram:
    name: str
    primitives: list[MeasurementPrimitive]
    goal: str
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goal": self.goal,
            "assumptions": list(self.assumptions),
            "primitives": [item.to_dict() for item in self.primitives],
            "summary": summarize_program(self),
        }


@dataclass(frozen=True)
class ProgramCritique:
    status: str
    issues: list[dict[str, Any]]
    suggestions: list[dict[str, Any]]
    coverage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgramOptimization:
    strategy: str
    original_reconfiguration_count: int
    optimized_reconfiguration_count: int
    estimated_runtime_reduction_fraction: float
    optimized_order: list[MeasurementPrimitive]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "original_reconfiguration_count": self.original_reconfiguration_count,
            "optimized_reconfiguration_count": self.optimized_reconfiguration_count,
            "estimated_runtime_reduction_fraction": self.estimated_runtime_reduction_fraction,
            "optimized_order": [item.to_dict() for item in self.optimized_order],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ProgramRefinement:
    source_status: str
    applied_suggestions: list[dict[str, Any]]
    added_primitives: list[MeasurementPrimitive]
    refined_program: MeasurementProgram

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_status": self.source_status,
            "applied_suggestions": list(self.applied_suggestions),
            "added_primitives": [item.to_dict() for item in self.added_primitives],
            "refined_program": self.refined_program.to_dict(),
        }


def build_unknown_device_measurement_program(
    *,
    goal: str,
    topology_hypotheses: list[TopologyHypothesis],
    selected_suite: dict[str, Any],
    adaptive_result: dict[str, Any],
    residual_followup: dict[str, Any],
) -> MeasurementProgram:
    winner = topology_hypotheses[0] if topology_hypotheses else None
    primitives: list[MeasurementPrimitive] = [
        MeasurementPrimitive(
            kind="measure",
            name="probe_shared_pn_junctions",
            args={"pins": ["A", "B", "C"], "max_probe_voltage_v": 1.2, "max_probe_current_a": 0.001},
            objective="identify_topology_and_candidate_pinout",
            expected_observation="two silicon-like junctions sharing one terminal and no A-C short",
            safety={"max_voltage_v": 1.2, "max_current_a": 0.001, "sustained_output": False},
            belief_targets=["device_type", "pinout_confidence"],
        )
    ]
    if winner and winner.device_type == "NPN_BJT":
        primitives.append(
            MeasurementPrimitive(
                kind="measure",
                name="confirm_controlled_collector_current",
                args={"vcc": 1.5, "vbb": 2.0, "mode": "static_point"},
                objective="test_bjt_action_not_diode_array",
                expected_observation="collector current increases under base drive",
                safety={"max_voltage_v": 1.5, "max_current_a": 0.003},
                belief_targets=["device_type", "beta_distribution", "vbe_model"],
            )
        )

    for item in _adaptive_candidates(adaptive_result):
        primitives.append(
            MeasurementPrimitive(
                kind="measure",
                name="adaptive_static_point",
                args={"vcc": item.get("vcc"), "vbb": item.get("vbb"), "mode": "static_point"},
                objective=str(item.get("objective") or "reduce_uncertainty"),
                expected_observation=str(item.get("rationale") or "measurement reduces DUT belief uncertainty"),
                safety={"max_voltage_v": 5.5, "max_current_a": 0.03},
                belief_targets=[_target_from_objective(str(item.get("objective") or ""))],
            )
        )

    for item in _followup_candidates(residual_followup):
        primitives.append(
            MeasurementPrimitive(
                kind="measure",
                name="residual_guided_static_point",
                args={"vcc": item.get("vcc"), "vbb": item.get("vbb"), "mode": "static_point"},
                objective=str(item.get("objective") or "explain_model_residual"),
                expected_observation=str(item.get("rationale") or "candidate distinguishes residual hypotheses"),
                safety={"max_voltage_v": 5.5, "max_current_a": 0.03},
                belief_targets=["anomaly_hypotheses", "spice_parameter_posterior"],
            )
        )

    primitives.append(
        MeasurementPrimitive(
            kind="analyze",
            name="fit_spice_twin_and_residual_map",
            args={"model_family": selected_suite.get("bjt_type", "UNKNOWN"), "emit_model_card": True},
            objective="turn_measurements_into_design_asset",
            expected_observation="SPICE model parameters plus residual diagnosis",
            safety={"touches_hardware": False},
            belief_targets=["spice_parameter_posterior", "anomaly_hypotheses"],
        )
    )
    return MeasurementProgram(
        name="unknown_three_pin_autonomous_program",
        primitives=_dedupe_primitives(primitives),
        goal=goal,
        assumptions=[
            "程序先在仿真/低压路径验证，再允许硬件执行。",
            "候选 pinout 是 belief，不是正式库事实。",
            "每个测量点都必须经过 safety guard 过滤。",
        ],
    )


def critique_measurement_program(
    program: MeasurementProgram,
    *,
    belief: DUTBeliefState | None,
    topology_hypotheses: list[TopologyHypothesis],
) -> ProgramCritique:
    issues: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    objectives = {item.objective for item in program.primitives}
    targets = {target for item in program.primitives for target in item.belief_targets}
    coverage = {
        "primitive_count": len(program.primitives),
        "objectives": sorted(objectives),
        "belief_targets": sorted(targets),
        "has_topology_probe": "identify_topology_and_candidate_pinout" in objectives,
        "has_residual_followup": any("residual" in item.objective for item in program.primitives),
        "has_model_fit": any(item.name == "fit_spice_twin_and_residual_map" for item in program.primitives),
    }
    if not topology_hypotheses or topology_hypotheses[0].confidence < 0.7:
        issues.append(
            {
                "severity": "high",
                "area": "topology",
                "message": "拓扑置信度不足，不应直接进入高功率表征。",
            }
        )
        suggestions.append({"action": "add_reverse_polarity_probe", "reason": "区分 NPN/PNP 和双二极管公共端。"})
    if belief and belief.early_voltage_uncertainty > 0.7:
        issues.append(
            {
                "severity": "medium",
                "area": "coverage",
                "message": "Early effect 不确定性仍高，VCE 跨度覆盖不足。",
            }
        )
        suggestions.append({"action": "add_same_base_drive_multi_vce_points", "reason": "估计输出电导和 VAF。"})
    if belief and belief.saturation_region_uncertainty > 0.5:
        issues.append(
            {
                "severity": "medium",
                "area": "coverage",
                "message": "饱和边界不确定性仍高，knee 区域点数不足。",
            }
        )
        suggestions.append({"action": "add_low_vcc_high_base_drive_points", "reason": "定位 VCE(sat) knee。"})
        suggestions.append({"action": "add_short_long_pulse_comparison", "reason": "饱和边界未收敛时，用短/长脉冲提前区分热漂移、接触电阻和模型不足。"})
    if "vce_sat_vs_ic" in objectives or "explain_model_residual" in objectives:
        issues.append(
            {
                "severity": "medium",
                "area": "diagnosis",
                "message": "饱和/高电流残差需要区分模型参数、热效应和接触/封装电阻。",
            }
        )
        suggestions.append({"action": "add_short_long_pulse_comparison", "reason": "用短/长脉冲比较区分热效应与静态串联电阻。"})
    if not coverage["has_model_fit"]:
        issues.append({"severity": "high", "area": "deliverable", "message": "缺少模型拟合步骤，无法输出设计自动化资产。"})
    status = "revise" if any(item["severity"] == "high" for item in issues) else ("warn" if issues else "pass")
    return ProgramCritique(status=status, issues=issues, suggestions=suggestions, coverage=coverage)


def refine_measurement_program_from_critique(
    program: MeasurementProgram,
    critique: ProgramCritique,
    *,
    belief: DUTBeliefState | None,
) -> ProgramRefinement:
    added: list[MeasurementPrimitive] = []
    applied: list[dict[str, Any]] = []
    for suggestion in critique.suggestions:
        action = str(suggestion.get("action") or "")
        if action == "add_same_base_drive_multi_vce_points":
            primitives = _early_effect_refinement_primitives(belief)
        elif action == "add_low_vcc_high_base_drive_points":
            primitives = _saturation_refinement_primitives(belief)
        elif action == "add_reverse_polarity_probe":
            primitives = _reverse_polarity_probe_primitives()
        elif action == "add_short_long_pulse_comparison":
            primitives = _pulse_comparison_primitives(belief)
        else:
            primitives = []
        if not primitives:
            continue
        added.extend(primitives)
        applied.append(
            {
                "action": action,
                "reason": suggestion.get("reason", ""),
                "added_primitive_count": len(primitives),
            }
        )
    refined = MeasurementProgram(
        name=program.name + "_refined" if added else program.name,
        primitives=_dedupe_primitives(program.primitives + added),
        goal=program.goal,
        assumptions=program.assumptions
        + (["critic suggestions were materialized into typed primitives before optimization."] if added else []),
    )
    return ProgramRefinement(
        source_status=critique.status,
        applied_suggestions=applied,
        added_primitives=added,
        refined_program=refined,
    )


def optimize_measurement_program(program: MeasurementProgram) -> ProgramOptimization:
    original = _reconfiguration_count(program.primitives)
    optimized = sorted(program.primitives, key=_optimization_key)
    optimized_count = _reconfiguration_count(optimized)
    reduction = 0.0
    if original > 0:
        reduction = round(max(0.0, (original - optimized_count) / original), 4)
    return ProgramOptimization(
        strategy="group_by_primitive_kind_then_voltage_window",
        original_reconfiguration_count=original,
        optimized_reconfiguration_count=optimized_count,
        estimated_runtime_reduction_fraction=reduction,
        optimized_order=optimized,
        notes=[
            "拓扑探测保持在最前面。",
            "静态点按 Vcc/Vbb 窗口分组，减少源量程和输出状态切换。",
            "分析步骤放在测量完成后执行。",
        ],
    )


def summarize_program(program: MeasurementProgram) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in program.primitives:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {"primitive_count": len(program.primitives), "kind_counts": counts}


def _adaptive_candidates(adaptive_result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for step in adaptive_result.get("adaptive_trace") or []:
        if isinstance(step, dict):
            for item in step.get("candidates") or []:
                if isinstance(item, dict):
                    candidates.append(item)
    return candidates


def _followup_candidates(residual_followup: dict[str, Any]) -> list[dict[str, Any]]:
    plan = residual_followup.get("followup_plan") if isinstance(residual_followup.get("followup_plan"), dict) else {}
    return [item for item in plan.get("candidates") or [] if isinstance(item, dict)]


def _target_from_objective(objective: str) -> str:
    if "saturation" in objective:
        return "saturation_region_uncertainty"
    if "early" in objective:
        return "early_voltage_uncertainty"
    if "beta" in objective:
        return "beta_distribution"
    return "uncertainty"


def _early_effect_refinement_primitives(belief: DUTBeliefState | None) -> list[MeasurementPrimitive]:
    vbb = _nominal_active_vbb(belief)
    return [
        MeasurementPrimitive(
            kind="sweep",
            name="critic_same_base_drive_vce_sweep",
            args={"vcc_values": [1.0, 2.0, 3.0], "vbb": vbb, "mode": "static_point_sweep"},
            objective="reduce_early_voltage_uncertainty",
            expected_observation="same base drive at multiple VCE points estimates output conductance / VAF",
            safety={"max_voltage_v": 5.5, "max_current_a": 0.03},
            belief_targets=["early_voltage_uncertainty", "spice_parameter_posterior"],
        )
    ]


def _saturation_refinement_primitives(belief: DUTBeliefState | None) -> list[MeasurementPrimitive]:
    vbb = max(_nominal_active_vbb(belief), 2.1)
    return [
        MeasurementPrimitive(
            kind="measure",
            name="critic_low_vcc_high_base_drive",
            args={"vcc": vcc, "vbb": round(vbb, 3), "mode": "static_point"},
            objective="reduce_saturation_boundary_uncertainty",
            expected_observation="low VCC with strong base drive locates VCE(sat) knee",
            safety={"max_voltage_v": 1.5, "max_current_a": 0.03},
            belief_targets=["saturation_region_uncertainty", "spice_parameter_posterior"],
        )
        for vcc in (0.2, 0.4, 0.7)
    ]


def _reverse_polarity_probe_primitives() -> list[MeasurementPrimitive]:
    return [
        MeasurementPrimitive(
            kind="measure",
            name="critic_reverse_polarity_pn_probe",
            args={"pins": ["A", "B", "C"], "max_probe_voltage_v": 1.2, "reverse_polarity": True},
            objective="discriminate_npn_pnp_or_diode_array",
            expected_observation="reverse polarity separates NPN/PNP common-base diode signatures",
            safety={"max_voltage_v": 1.2, "max_current_a": 0.001, "sustained_output": False},
            belief_targets=["device_type", "pinout_confidence"],
        )
    ]


def _pulse_comparison_primitives(belief: DUTBeliefState | None) -> list[MeasurementPrimitive]:
    vbb = max(_nominal_active_vbb(belief), 2.1)
    return [
        MeasurementPrimitive(
            kind="pulse",
            name="critic_short_long_pulse_vce_sat_check",
            args={
                "vcc": 0.8,
                "vbb": round(vbb, 3),
                "pulse_width_us_values": [100, 5000],
                "duty_cycle": 0.05,
                "mode": "static_point_pulse_pair",
            },
            objective="separate_self_heating_from_contact_resistance",
            expected_observation="long-pulse VCE/Ic drift relative to short pulse suggests self-heating; similar readings suggest contact/model issue",
            safety={"max_voltage_v": 1.0, "max_current_a": 0.03, "max_duty_cycle": 0.05},
            belief_targets=["anomaly_hypotheses", "spice_parameter_posterior"],
        )
    ]


def _nominal_active_vbb(belief: DUTBeliefState | None) -> float:
    if belief:
        active = [item for item in belief.measured_points if item.get("region") == "active"]
        if active:
            return round(float(active[-1].get("Vbb") or 2.0), 3)
    return 2.0


def _dedupe_primitives(primitives: list[MeasurementPrimitive]) -> list[MeasurementPrimitive]:
    seen: set[tuple[str, str, float | None, float | None]] = set()
    result: list[MeasurementPrimitive] = []
    for item in primitives:
        key = (
            item.name,
            item.objective,
            _maybe_float(item.args.get("vcc")),
            _maybe_float(item.args.get("vbb")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _optimization_key(item: MeasurementPrimitive) -> tuple[int, float, float, str]:
    phase_rank = {"measure": 0, "source": 1, "sweep": 2, "pulse": 3, "analyze": 4}
    if item.objective == "identify_topology_and_candidate_pinout":
        return (-1, 0.0, 0.0, item.name)
    return (
        phase_rank.get(item.kind, 9),
        _maybe_float(item.args.get("vcc")) or 0.0,
        _maybe_float(item.args.get("vbb")) or 0.0,
        item.name,
    )


def _reconfiguration_count(primitives: list[MeasurementPrimitive]) -> int:
    previous: tuple[str, int, int] | None = None
    count = 0
    for item in primitives:
        state = (item.kind, _voltage_bucket(item.args.get("vcc")), _voltage_bucket(item.args.get("vbb")))
        if previous is not None and state != previous:
            count += 1
        previous = state
    return count


def _voltage_bucket(value: Any) -> int:
    number = _maybe_float(value)
    if number is None:
        return -1
    return int(number / 0.5)


def _maybe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None
