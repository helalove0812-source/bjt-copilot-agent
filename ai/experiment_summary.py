from __future__ import annotations

from typing import Any


def summarize_experiment_records(records: list[dict[str, Any]]) -> str:
    by_name = {str(item.get("name") or ""): item for item in records if isinstance(item, dict)}
    if not _has_experiment_record(by_name):
        return ""
    unknown = _result(by_name, "autonomous_unknown_device_report")
    if unknown:
        return _unknown_device_summary(unknown)
    lines: list[str] = []
    adaptive = _result(by_name, "run_adaptive_characterization")
    twin = _result(by_name, "extract_spice_twin")
    followup_plan = _result(by_name, "plan_residual_followup")
    followup_run = _result(by_name, "run_residual_followup")

    if adaptive:
        measurements = adaptive.get("measurements") or []
        belief = adaptive.get("belief") if isinstance(adaptive.get("belief"), dict) else {}
        uncertainty = belief.get("uncertainty") if isinstance(belief.get("uncertainty"), dict) else {}
        candidates = belief.get("next_measurement_candidates") if isinstance(belief.get("next_measurement_candidates"), list) else []
        aide_goal = adaptive.get("aide_goal") if isinstance(adaptive.get("aide_goal"), dict) else {}
        trace = adaptive.get("adaptive_trace") if isinstance(adaptive.get("adaptive_trace"), list) else []
        lines.append("自适应表征已完成：共测 {0} 个点。".format(len(measurements)))
        if aide_goal:
            lines.append(
                "AIDE 目标：{0}，按 {1} 这些 belief 投影降低不确定性。".format(
                    aide_goal.get("kind"),
                    ", ".join(str(item) for item in (aide_goal.get("projection_variables") or [])[:4]),
                )
            )
        if trace and isinstance(trace[0], dict):
            design = trace[0].get("active_inference_design") if isinstance(trace[0].get("active_inference_design"), dict) else {}
            summary = design.get("summary") if isinstance(design.get("summary"), dict) else {}
            if summary:
                lines.append(
                    "主动布点：第一批候选按 {0} 排序，预计信息增益合计 {1}，覆盖 {2}。".format(
                        summary.get("objective"),
                        _fmt(summary.get("total_expected_information_gain")),
                        ", ".join(str(item) for item in summary.get("covered_uncertainty_targets", [])),
                    )
                )
        if uncertainty:
            lines.append(
                "当前主要不确定性：beta={0}，饱和区={1}，Early effect={2}，overall={3}。".format(
                    _fmt(uncertainty.get("beta")),
                    _fmt(uncertainty.get("saturation_region")),
                    _fmt(uncertainty.get("early_voltage")),
                    _fmt(uncertainty.get("overall")),
                )
            )
        if candidates:
            first = candidates[0]
            lines.append("下一优先测点建议：Vcc={0} V, Vbb={1} V，用于 {2}。".format(first.get("vcc"), first.get("vbb"), first.get("objective")))

    if twin:
        spice = twin.get("spice_twin") if isinstance(twin.get("spice_twin"), dict) else {}
        if spice:
            lines.append(_spice_summary(spice))

    if followup_plan:
        plan = followup_plan.get("followup_plan") if isinstance(followup_plan.get("followup_plan"), dict) else {}
        candidates = plan.get("candidates") if isinstance(plan.get("candidates"), list) else []
        if candidates:
            objectives = ", ".join(dict.fromkeys(str(item.get("objective")) for item in candidates))
            lines.append("残差补测计划：生成 {0} 个候选点，目标包括 {1}。".format(len(candidates), objectives))

    if followup_run:
        measurements = followup_run.get("measurements") if isinstance(followup_run.get("measurements"), list) else []
        comparison = followup_run.get("residual_comparison") if isinstance(followup_run.get("residual_comparison"), dict) else {}
        lines.append("已执行残差补测：新增 {0} 个点。".format(len(measurements)))
        if comparison:
            lines.append(
                "模型残差变化：{0} -> {1}，delta={2}。".format(
                    _fmt(comparison.get("before_overall_mean_abs")),
                    _fmt(comparison.get("after_overall_mean_abs")),
                    _fmt(comparison.get("delta_overall_mean_abs")),
                )
            )
        spice = followup_run.get("spice_twin") if isinstance(followup_run.get("spice_twin"), dict) else {}
        if spice:
            lines.append(_spice_summary(spice, include_card=False))

    next_line = _next_action_line(twin, followup_plan, followup_run)
    if next_line:
        lines.append(next_line)
    model_card = _model_card_from_records(twin, followup_run)
    if model_card:
        lines.append("模型卡：\n```spice\n{0}\n```".format(model_card))
    return "\n".join(line for line in lines if line)


def _has_experiment_record(by_name: dict[str, dict[str, Any]]) -> bool:
    return any(
        name in by_name
        for name in (
            "run_adaptive_characterization",
            "extract_spice_twin",
            "plan_residual_followup",
            "run_residual_followup",
            "autonomous_unknown_device_report",
        )
    )


def _result(by_name: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    raw = by_name.get(name, {}).get("result")
    return raw if isinstance(raw, dict) and raw.get("ok", False) else {}


def _spice_summary(spice: dict[str, Any], *, include_card: bool = True) -> str:
    residuals = spice.get("residuals") if isinstance(spice.get("residuals"), dict) else {}
    diagnosis = spice.get("diagnosis") if isinstance(spice.get("diagnosis"), list) else []
    parts = [
        "SPICE 数字孪生已生成：{0}，confidence={1}，overall residual={2}。".format(
            spice.get("model_name", "DUT"),
            _fmt(spice.get("confidence")),
            _fmt(residuals.get("overall_mean_abs")),
        )
    ]
    if diagnosis:
        labels = ", ".join("{0}({1})".format(item.get("name"), item.get("severity")) for item in diagnosis[:3])
        parts.append("残差诊断集中在：{0}。".format(labels))
    return "".join(parts)


def _next_action_line(twin: dict[str, Any], followup_plan: dict[str, Any], followup_run: dict[str, Any]) -> str:
    if followup_run:
        return "建议下一步：查看补测后的模型卡；若残差仍集中在同一区域，再继续执行残差补测。"
    if followup_plan:
        return "建议下一步：确认是否执行这些补测点。"
    if twin:
        return "建议下一步：根据残差诊断生成补测计划，或直接导出模型卡。"
    return "建议下一步：生成 SPICE 数字孪生，或继续自适应补测。"


def _model_card_from_records(twin: dict[str, Any], followup_run: dict[str, Any]) -> str:
    spice = followup_run.get("spice_twin") if isinstance(followup_run.get("spice_twin"), dict) else {}
    if spice.get("model_card"):
        return str(spice["model_card"])
    spice = twin.get("spice_twin") if isinstance(twin.get("spice_twin"), dict) else {}
    return str(spice.get("model_card") or "")


def _unknown_device_summary(result: dict[str, Any]) -> str:
    report = result.get("unknown_device_report") if isinstance(result.get("unknown_device_report"), dict) else {}
    if not report:
        return str(result.get("response") or "")
    lines: list[str] = []
    if report.get("conclusion"):
        lines.append(str(report["conclusion"]))
    hypotheses = report.get("topology_hypotheses") if isinstance(report.get("topology_hypotheses"), list) else []
    if hypotheses:
        first = hypotheses[0]
        lines.append(
            "拓扑假设排序：{0}，confidence={1}，pinout={2}。".format(
                first.get("device_type"),
                _fmt(first.get("confidence")),
                _pinout_text(first.get("pinout") if isinstance(first.get("pinout"), dict) else {}),
            )
        )
    journal = report.get("decision_journal") if isinstance(report.get("decision_journal"), list) else []
    if journal:
        lines.append("判断过程：")
        for item in journal[:4]:
            lines.append(
                "- {0}：看到 {1}；判断 {2}；所以下一步 {3}。".format(
                    item.get("phase"),
                    item.get("observation"),
                    item.get("judgment"),
                    item.get("next_action") or "人工复核",
                )
            )
    suite = report.get("selected_suite") if isinstance(report.get("selected_suite"), dict) else {}
    if suite:
        lines.append("已选择表征套件：{0}；原因：{1}".format(suite.get("suite"), suite.get("reason")))
    program = report.get("measurement_program") if isinstance(report.get("measurement_program"), dict) else {}
    program_summary = program.get("summary") if isinstance(program.get("summary"), dict) else {}
    if program_summary:
        lines.append(
            "测量程序：由 {0} 个 typed primitives 组成，类型分布 {1}。".format(
                program_summary.get("primitive_count"),
                program_summary.get("kind_counts"),
            )
        )
    critic = report.get("critic_review") if isinstance(report.get("critic_review"), dict) else {}
    if critic:
        issues = critic.get("issues") if isinstance(critic.get("issues"), list) else []
        lines.append("critic 审查：status={0}，发现 {1} 个覆盖/风险问题。".format(critic.get("status"), len(issues)))
        if issues:
            lines.append("critic 最主要意见：{0}".format(issues[0].get("message")))
    refinement = report.get("program_refinement") if isinstance(report.get("program_refinement"), dict) else {}
    if refinement:
        applied = refinement.get("applied_suggestions") if isinstance(refinement.get("applied_suggestions"), list) else []
        added = refinement.get("added_primitives") if isinstance(refinement.get("added_primitives"), list) else []
        if applied or added:
            actions = ", ".join(str(item.get("action")) for item in applied)
            lines.append("program refine：已应用 {0}，新增 {1} 个 typed primitives。".format(actions or "critic suggestions", len(added)))
    optimization = report.get("program_optimization") if isinstance(report.get("program_optimization"), dict) else {}
    if optimization:
        lines.append(
            "program optimizer：重配置次数 {0} -> {1}，预计节省 {2}。".format(
                optimization.get("original_reconfiguration_count"),
                optimization.get("optimized_reconfiguration_count"),
                _fmt(optimization.get("estimated_runtime_reduction_fraction")),
            )
        )
    refined_execution = report.get("refined_program_execution") if isinstance(report.get("refined_program_execution"), dict) else {}
    if refined_execution:
        lines.append("refined program execution：已执行 {0} 个 critic 新增测点。".format(refined_execution.get("executed_primitive_count", 0)))
        comparison = refined_execution.get("residual_comparison") if isinstance(refined_execution.get("residual_comparison"), dict) else {}
        if comparison:
            lines.append(
                "refined 后残差变化：{0} -> {1}，delta={2}。".format(
                    _fmt(comparison.get("before_overall_mean_abs")),
                    _fmt(comparison.get("after_overall_mean_abs")),
                    _fmt(comparison.get("delta_overall_mean_abs")),
                )
            )
        pulse = refined_execution.get("pulse_diagnosis") if isinstance(refined_execution.get("pulse_diagnosis"), dict) else {}
        if pulse.get("ok"):
            lines.append(
                "pulse 诊断：{0}，confidence={1}；依据：{2}".format(
                    pulse.get("hypothesis"),
                    _fmt(pulse.get("confidence")),
                    pulse.get("evidence"),
                )
            )
    adaptive = report.get("adaptive_result") if isinstance(report.get("adaptive_result"), dict) else {}
    measurements = adaptive.get("measurements") if isinstance(adaptive.get("measurements"), list) else []
    aide_goal = adaptive.get("aide_goal") if isinstance(adaptive.get("aide_goal"), dict) else {}
    adaptive_trace = adaptive.get("adaptive_trace") if isinstance(adaptive.get("adaptive_trace"), list) else []
    if aide_goal:
        lines.append(
            "AIDE 目标：{0}，belief 投影={1}。".format(
                aide_goal.get("kind"),
                ", ".join(str(item) for item in (aide_goal.get("projection_variables") or [])[:4]),
            )
        )
    if adaptive_trace and isinstance(adaptive_trace[0], dict):
        design = adaptive_trace[0].get("active_inference_design") if isinstance(adaptive_trace[0].get("active_inference_design"), dict) else {}
        summary = design.get("summary") if isinstance(design.get("summary"), dict) else {}
        if summary:
            lines.append(
                "主动布点：首批选择 {0} 个点，预计信息增益 {1}，优先覆盖 {2}。".format(
                    summary.get("selected_count"),
                    _fmt(summary.get("total_expected_information_gain")),
                    ", ".join(str(item) for item in summary.get("covered_uncertainty_targets", [])),
                )
            )
    if measurements:
        lines.append("自适应测量：完成 {0} 个点。".format(len(measurements)))
    followup = report.get("residual_followup") if isinstance(report.get("residual_followup"), dict) else {}
    comparison = followup.get("residual_comparison") if isinstance(followup.get("residual_comparison"), dict) else {}
    if comparison:
        lines.append(
            "残差补测：overall residual {0} -> {1}，delta={2}。".format(
                _fmt(comparison.get("before_overall_mean_abs")),
                _fmt(comparison.get("after_overall_mean_abs")),
                _fmt(comparison.get("delta_overall_mean_abs")),
            )
        )
    twin = report.get("spice_twin") if isinstance(report.get("spice_twin"), dict) else {}
    if twin.get("model_card"):
        lines.append("模型卡：\n```spice\n{0}\n```".format(twin["model_card"]))
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []
    if recommendations:
        lines.append("建议下一步：{0}".format("；".join(str(item) for item in recommendations[:3])))
    return "\n".join(line for line in lines if line)


def _pinout_text(pinout: dict[str, Any]) -> str:
    if not pinout:
        return "n/a"
    return ", ".join("{0}={1}".format(pin, role) for pin, role in sorted(pinout.items()))


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return "{0:.4g}".format(value)
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "n/a"
    return str(value)
