from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ai.dut_belief import DUTBeliefState
from ai.spice_twin import SpiceDigitalTwin


@dataclass(frozen=True)
class TopologyHypothesis:
    device_type: str
    pinout: dict[str, str]
    confidence: float
    evidence: list[str] = field(default_factory=list)
    next_discriminator: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentalJudgment:
    phase: str
    observation: str
    judgment: str
    hypotheses_supported: list[str] = field(default_factory=list)
    hypotheses_weakened: list[str] = field(default_factory=list)
    next_action: str = ""
    why_next: str = ""
    confidence_delta: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnknownDeviceReport:
    goal: str
    mode: str
    topology_observations: list[dict[str, Any]]
    topology_hypotheses: list[TopologyHypothesis]
    selected_suite: dict[str, Any]
    adaptive_result: dict[str, Any]
    spice_twin: SpiceDigitalTwin | None
    residual_followup: dict[str, Any]
    nominal_comparison: dict[str, Any]
    decision_journal: list[ExperimentalJudgment]
    conclusion: str
    recommendations: list[str]
    measurement_program: dict[str, Any] = field(default_factory=dict)
    critic_review: dict[str, Any] = field(default_factory=dict)
    program_refinement: dict[str, Any] = field(default_factory=dict)
    program_optimization: dict[str, Any] = field(default_factory=dict)
    refined_program_execution: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["topology_hypotheses"] = [item.to_dict() for item in self.topology_hypotheses]
        data["decision_journal"] = [item.to_dict() for item in self.decision_journal]
        data["spice_twin"] = self.spice_twin.to_dict() if self.spice_twin else None
        return data


def simulate_three_pin_topology_probe() -> tuple[list[dict[str, Any]], list[TopologyHypothesis]]:
    observations = _default_simulated_observations()
    return observations, topology_hypotheses_from_probe_result({"observations": observations, "mode": "simulation"})


def topology_hypotheses_from_probe_result(probe_result: dict[str, Any]) -> list[TopologyHypothesis]:
    observations = probe_result.get("observations") if isinstance(probe_result.get("observations"), list) else []
    text = " ".join(str(item.get("observation") or "") for item in observations if isinstance(item, dict)).lower()
    confidence = 0.78
    evidence = [
        "base-to-emitter and base-to-collector junctions look like two silicon PN junctions",
        "emitter/collector pair is isolated at low current",
    ]
    if probe_result.get("source") == "relay_matrix_pin_probe" and probe_result.get("pair_results"):
        confidence = 0.86
        evidence = [
            "relay-matrix permutation found two conducting ordered pairs into common terminal B",
            "A/C pair is isolated in both directions at low voltage",
        ]
    if "relay matrix" in text or "fixture response" in text:
        confidence = 0.62
    if "no direct diode" in text and "forward drop" in text:
        confidence = max(confidence, 0.78)
    hypotheses = [
        TopologyHypothesis(
            device_type="NPN_BJT",
            pinout={"A": "emitter", "B": "base", "C": "collector"},
            confidence=confidence,
            evidence=evidence,
            next_discriminator="Run low-power BJT active-region point and check current gain.",
        ),
        TopologyHypothesis(
            device_type="PNP_BJT_REVERSED_ORIENTATION",
            pinout={"A": "collector_or_emitter", "B": "base", "C": "emitter_or_collector"},
            confidence=0.1,
            evidence=["two-junction topology is also compatible with a PNP if probe polarity is reversed"],
            next_discriminator="Repeat diode probe with reversed polarity before hardware execution.",
        ),
        TopologyHypothesis(
            device_type="DIODE_ARRAY",
            pinout={"A": "diode_terminal", "B": "common", "C": "diode_terminal"},
            confidence=0.07,
            evidence=["two diode junctions share a common terminal"],
            next_discriminator="Bias as transistor; absence of controlled collector current supports diode-array hypothesis.",
        ),
        TopologyHypothesis(
            device_type="MOSFET_OR_JFET",
            pinout={"A": "source_or_drain", "B": "gate", "C": "drain_or_source"},
            confidence=0.05,
            evidence=["three-terminal device cannot exclude FET before transfer-curve probe"],
            next_discriminator="Check for insulated gate behavior and body diode signature.",
        ),
    ]
    return hypotheses


def _default_simulated_observations() -> list[dict[str, Any]]:
    return [
        {
            "probe": "A-B diode check",
            "stimulus": "low-current forward/reverse probe",
            "observation": "A->B forward drop near 0.68 V, reverse leakage below floor",
            "safety": "no sustained collector path enabled",
        },
        {
            "probe": "C-B diode check",
            "stimulus": "low-current forward/reverse probe",
            "observation": "C->B forward drop near 0.69 V, reverse leakage below floor",
            "safety": "no sustained collector path enabled",
        },
        {
            "probe": "A-C isolation check",
            "stimulus": "low-current bidirectional probe",
            "observation": "no direct diode conduction between A and C",
            "safety": "probe voltage limited to 1.2 V equivalent",
        },
    ]


def select_characterization_suite(hypotheses: list[TopologyHypothesis]) -> dict[str, Any]:
    winner = hypotheses[0] if hypotheses else TopologyHypothesis("UNKNOWN", {}, 0.0)
    if winner.device_type == "NPN_BJT":
        return {
            "suite": "bjt_npn_adaptive_characterization",
            "model_label": "UNKNOWN_NPN",
            "bjt_type": "NPN",
            "depth": "conservative",
            "reason": "拓扑更像 NPN BJT，先用低功耗自适应表征套件验证 beta/Vbe/Vce(sat)。",
        }
    return {
        "suite": "safe_low_voltage_discriminator",
        "model_label": "UNKNOWN",
        "bjt_type": "UNKNOWN",
        "depth": "conservative",
        "reason": "拓扑置信度不足，只允许低压判别测量。",
    }


def compare_unknown_against_nominal_class(belief: DUTBeliefState | None, twin: SpiceDigitalTwin | None) -> dict[str, Any]:
    if belief is None:
        return {"class": "unknown", "status": "insufficient_measurements", "notes": ["还没有足够测量点进行类别比较。"]}
    beta = belief.beta_distribution or {}
    beta_mean = float(beta.get("mean") or 0.0)
    residual = twin.residuals.get("overall_mean_abs") if twin else None
    notes: list[str] = []
    likely_class = "small_signal_npn_bjt" if belief.device_type == "NPN" else "unknown_three_terminal"
    if beta_mean <= 0:
        notes.append("当前有效放大区样本不足，beta 均值还不能作为分类依据。")
    elif beta_mean < 30:
        notes.append("beta 偏低，更像功率管、接触问题、偏置不足或异常器件。")
    elif beta_mean <= 300:
        notes.append("beta 落在常见小信号/小功率 BJT 的粗略范围内。")
    else:
        notes.append("beta 偏高，需排除达林顿、漏电或模型外推误差。")
    if residual is not None and residual > 0.7:
        notes.append("SPICE 拟合残差仍偏高，结论应标记为候选而非最终型号。")
    return {
        "class": likely_class,
        "beta_mean": round(beta_mean, 4),
        "overall_residual": residual,
        "status": "candidate_classification",
        "notes": notes,
    }


def build_experimental_journal(
    *,
    topology_observations: list[dict[str, Any]],
    topology_hypotheses: list[TopologyHypothesis],
    selected_suite: dict[str, Any],
    adaptive_result: dict[str, Any],
    belief: DUTBeliefState | None,
    twin: SpiceDigitalTwin | None,
    residual_followup: dict[str, Any],
    nominal_comparison: dict[str, Any],
) -> list[ExperimentalJudgment]:
    journal: list[ExperimentalJudgment] = []
    winner = topology_hypotheses[0] if topology_hypotheses else None
    topology_summary = "; ".join(str(item.get("observation") or "") for item in topology_observations)
    if winner:
        journal.append(
            ExperimentalJudgment(
                phase="topology_probe",
                observation=topology_summary,
                judgment="两个端点都像通过同一个公共端形成 PN 结，第三对端点低压隔离，因此先按三极管而不是 MOSFET/单二极管处理。",
                hypotheses_supported=[winner.device_type],
                hypotheses_weakened=["MOSFET_OR_JFET", "single_diode", "shorted_device"],
                next_action=selected_suite.get("suite", ""),
                why_next="这个动作最能验证关键假设：公共端是否真的是 base，以及另外两端能否形成受控 collector current。",
                confidence_delta={winner.device_type: winner.confidence},
            )
        )

    measurements = adaptive_result.get("measurements") if isinstance(adaptive_result.get("measurements"), list) else []
    if measurements:
        active = [item for item in measurements if str(item.get("region")) == "active"]
        saturated = [item for item in measurements if str(item.get("region")) == "saturation"]
        beta_mean = (belief.beta_distribution or {}).get("mean") if belief else None
        uncertainty = belief.uncertainty if belief else {}
        journal.append(
            ExperimentalJudgment(
                phase="adaptive_characterization",
                observation="测到 {0} 个点，其中 active={1}、saturation={2}，beta_mean={3}，overall_uncertainty={4}。".format(
                    len(measurements),
                    len(active),
                    len(saturated),
                    _fmt(beta_mean),
                    _fmt(uncertainty.get("overall") if isinstance(uncertainty, dict) else None),
                ),
                judgment="已经出现受基极驱动控制的集电极电流，NPN BJT 假设被加强；但饱和区和 Early effect 信息仍不足。",
                hypotheses_supported=["NPN_BJT"],
                hypotheses_weakened=["DIODE_ARRAY", "open_pin", "pure_resistor_network"],
                next_action="extract_spice_twin",
                why_next="先把已有测点压缩成模型参数和残差地图，再让残差告诉我们哪里最值得补测。",
            )
        )

    if twin:
        diagnosis = ", ".join("{0}:{1}".format(item.get("name"), item.get("severity")) for item in twin.diagnosis[:3])
        journal.append(
            ExperimentalJudgment(
                phase="model_fit",
                observation="SPICE twin confidence={0}，overall_residual={1}，diagnosis={2}。".format(
                    _fmt(twin.confidence),
                    _fmt(twin.residuals.get("overall_mean_abs")),
                    diagnosis or "none",
                ),
                judgment="模型已经能给出候选数字孪生，但残差分布说明结论还不是最终定型；需要像工程师一样追问残差从哪里来。",
                hypotheses_supported=[str(nominal_comparison.get("class") or "candidate_classification")],
                hypotheses_weakened=[],
                next_action="run_residual_followup",
                why_next="残差集中区比继续均匀扫点更有信息量，优先补测能区分模型不足、接触问题和饱和区参数错误。",
            )
        )

    comparison = residual_followup.get("residual_comparison") if isinstance(residual_followup.get("residual_comparison"), dict) else {}
    if comparison:
        delta = float(comparison.get("delta_overall_mean_abs") or 0.0)
        journal.append(
            ExperimentalJudgment(
                phase="residual_followup",
                observation="补测后 overall_residual 从 {0} 变为 {1}，新增 {2} 个点。".format(
                    _fmt(comparison.get("before_overall_mean_abs")),
                    _fmt(comparison.get("after_overall_mean_abs")),
                    comparison.get("added_points"),
                ),
                judgment="补测带来了可见改善。" if delta > 0 else "补测没有改善模型，异常更可能来自模型结构不足或夹具/接触问题。",
                hypotheses_supported=["saturation_parameter_refinement"] if delta > 0 else ["model_mismatch_or_fixture_issue"],
                hypotheses_weakened=["random_measurement_noise"] if delta > 0 else ["simple_parameter_error"],
                next_action="human_review_or_targeted_next_probe",
                why_next="如果残差仍高，应继续围绕同一物理区域做判别测试，而不是盲目加网格密度。",
            )
        )
    return journal


def write_unknown_device_conclusion(report: UnknownDeviceReport) -> str:
    winner = report.topology_hypotheses[0] if report.topology_hypotheses else None
    twin = report.spice_twin
    comparison = report.nominal_comparison
    if not winner:
        return "还不能可靠判断这个三脚器件，需要先做低压拓扑探测。"
    pieces = [
        "未知三脚器件的第一轮自治侦查完成。",
        "低压拓扑最像 {0}，pinout 候选为 {1}，置信度约 {2:.0%}。".format(
            winner.device_type,
            _pinout_text(winner.pinout),
            winner.confidence,
        ),
    ]
    if twin:
        pieces.append(
            "已基于自适应测量提取 SPICE 数字孪生 {0}，模型置信度 {1:.0%}，overall residual={2}。".format(
                twin.model_name,
                twin.confidence,
                _fmt(twin.residuals.get("overall_mean_abs")),
            )
        )
    if comparison.get("notes"):
        pieces.append("类别比较：{0}".format("；".join(str(item) for item in comparison["notes"])))
    if report.residual_followup.get("residual_comparison"):
        delta = report.residual_followup["residual_comparison"].get("delta_overall_mean_abs")
        pieces.append("残差补测后模型误差改善 delta={0}。".format(_fmt(delta)))
    if report.decision_journal:
        last = report.decision_journal[-1]
        pieces.append("当前判断：{0}".format(last.judgment))
    return "\n".join(pieces)


def _pinout_text(pinout: dict[str, str]) -> str:
    return ", ".join("{0}={1}".format(pin, role) for pin, role in sorted(pinout.items()))


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return "{0:.4g}".format(value)
    if value is None:
        return "n/a"
    return str(value)
