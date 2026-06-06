from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ai.test_planner import TestPlan, extract_model_guess


GoalKind = Literal["IDENTIFY", "CHARACTERIZE", "EXTRACT_MODEL", "DIAGNOSE", "SCREEN"]


@dataclass(frozen=True)
class ExperimentGoal:
    kind: GoalKind
    user_goal: str
    model_hint: str = "UNKNOWN"
    projection_variables: list[str] = field(default_factory=list)
    epsilon: dict[str, float] = field(default_factory=dict)
    deliverables: list[str] = field(default_factory=list)
    safety_constraints: dict[str, Any] = field(default_factory=dict)
    stop_when: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_experiment_goal(
    text: str,
    *,
    mode: str = "simulation",
    model_hint: str = "",
    plan: TestPlan | None = None,
) -> ExperimentGoal:
    user_goal = str(text or "").strip()
    lowered = user_goal.lower()
    model = model_hint or (plan.model if plan else "") or extract_model_guess(user_goal)

    if _looks_like_unknown_device_goal(user_goal, lowered):
        return ExperimentGoal(
            kind="IDENTIFY",
            user_goal=user_goal or "identify unknown three-pin DUT",
            model_hint=model or "UNKNOWN",
            projection_variables=[
                "device_type",
                "pinout_confidence",
                "topology_hypotheses",
                "spice_parameter_posterior",
                "anomaly_hypotheses",
            ],
            epsilon={"pinout_entropy": 0.25, "model_residual": 0.25},
            deliverables=["topology_report", "characterization_report", "spice_model_card", "residual_diagnosis"],
            safety_constraints=_safety_constraints(mode, plan),
            stop_when={"pinout_confidence_at_least": 0.8, "model_confidence_at_least": 0.6},
            rationale="用户给的是高层未知器件目标，先降低离散拓扑/类型不确定性，再转入模型表征。",
        )

    if _looks_like_diagnosis_goal(user_goal, lowered):
        return ExperimentGoal(
            kind="DIAGNOSE",
            user_goal=user_goal or "diagnose DUT anomaly",
            model_hint=model or "UNKNOWN",
            projection_variables=["anomaly_hypotheses", "residuals", "spice_parameter_posterior"],
            epsilon={"hypothesis_entropy": 0.2, "residual_delta": 0.05},
            deliverables=["differential_diagnosis", "evidence_chain", "targeted_followup_plan"],
            safety_constraints=_safety_constraints(mode, plan),
            stop_when={"dominant_hypothesis_confidence_at_least": 0.75},
            rationale="目标是解释异常，测量优先服务于区分假设，而不是盲目增加网格密度。",
        )

    if _looks_like_model_goal(user_goal, lowered, plan):
        return ExperimentGoal(
            kind="EXTRACT_MODEL",
            user_goal=user_goal or "extract SPICE compact model",
            model_hint=model or "UNKNOWN",
            projection_variables=[
                "spice_parameter_posterior",
                "beta_distribution",
                "vbe_model",
                "early_voltage_uncertainty",
                "saturation_region_uncertainty",
            ],
            epsilon={"overall_uncertainty": 0.25, "model_residual": 0.25},
            deliverables=["spice_model_card", "parameter_uncertainty", "residual_map"],
            safety_constraints=_safety_constraints(mode, plan),
            stop_when={"overall_uncertainty_at_most": 0.25, "model_confidence_at_least": 0.7},
            rationale="目标产物是可进入设计流程的 SPICE 模型，所以布点优先减少参数不可辨识性。",
        )

    if _looks_like_screen_goal(user_goal, lowered, plan):
        return ExperimentGoal(
            kind="SCREEN",
            user_goal=user_goal or "screen DUT against limits",
            model_hint=model or "UNKNOWN",
            projection_variables=["pass_fail_confidence", "beta_distribution", "saturation_region_uncertainty"],
            epsilon={"pass_fail_margin": 0.1},
            deliverables=["screening_result", "limit_margin", "evidence_chain"],
            safety_constraints=_safety_constraints(mode, plan),
            stop_when={"pass_fail_confidence_at_least": 0.9},
            rationale="目标是筛选而非完整建模，测量集中在判据边界附近。",
        )

    return ExperimentGoal(
        kind="CHARACTERIZE",
        user_goal=user_goal or "characterize BJT behavior",
        model_hint=model or "UNKNOWN",
        projection_variables=[
            "beta_distribution",
            "vbe_model",
            "early_voltage_uncertainty",
            "saturation_region_uncertainty",
            "spice_parameter_posterior",
        ],
        epsilon={"overall_uncertainty": 0.3, "beta_uncertainty": 0.25},
        deliverables=["characterization_summary", "candidate_next_measurements", "spice_model_card"],
        safety_constraints=_safety_constraints(mode, plan),
        stop_when={"overall_uncertainty_at_most": 0.3},
        rationale="目标是器件表征，测量按 belief 中仍高的不确定性自适应分配。",
    )


def goal_from_plan(plan: TestPlan | None, *, mode: str = "simulation", user_goal: str = "") -> ExperimentGoal:
    if plan is None:
        return compile_experiment_goal(user_goal or "characterize BJT behavior", mode=mode)
    goal_text = user_goal or "plan goal: {0} for {1}".format(plan.goal, plan.model)
    if plan.goal in {"full", "curves"}:
        goal_text = goal_text + " extract model"
    elif plan.goal == "screening":
        goal_text = goal_text + " screening"
    elif plan.goal == "vce_sat":
        goal_text = goal_text + " diagnose saturation"
    return compile_experiment_goal(goal_text, mode=mode, model_hint=plan.model, plan=plan)


def _looks_like_unknown_device_goal(text: str, lowered: str) -> bool:
    return any(word in text for word in ("未知三脚", "不知道型号", "未知型号", "三脚器件", "三端器件", "不知道是什么")) or any(
        phrase in lowered for phrase in ("unknown three-pin", "unknown 3-pin", "identify unknown device")
    )


def _looks_like_diagnosis_goal(text: str, lowered: str) -> bool:
    return any(word in text for word in ("诊断", "异常", "反常", "残差", "坏", "假货", "接触", "达林顿")) or any(
        word in lowered for word in ("diagnose", "residual", "anomaly", "failure")
    )


def _looks_like_model_goal(text: str, lowered: str, plan: TestPlan | None) -> bool:
    if plan and plan.goal in {"full", "curves"}:
        return True
    return any(word in text for word in ("模型", "数字孪生", "模型卡", "提取参数")) or any(
        word in lowered for word in ("spice", ".model", "digital twin", "model card")
    )


def _looks_like_screen_goal(text: str, lowered: str, plan: TestPlan | None) -> bool:
    if plan and plan.goal == "screening":
        return True
    return any(word in text for word in ("筛选", "分选", "良品", "是否合格")) or any(word in lowered for word in ("screen", "pass", "fail"))


def _safety_constraints(mode: str, plan: TestPlan | None) -> dict[str, Any]:
    return {
        "mode": mode if mode in {"simulation", "hardware"} else "simulation",
        "max_vcc_v": max(plan.vcc_steps) if plan and plan.vcc_steps else 5.0,
        "max_ic_a": plan.ic_limit_a if plan else 0.03,
        "max_power_w": plan.power_limit_w if plan else 0.25,
        "hardware_requires_confirmation": mode == "hardware",
    }
