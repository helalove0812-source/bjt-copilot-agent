from __future__ import annotations

from ai.tool_call_agent import ToolCallingAgent
from ai.tool_runtime import BJTToolRuntime


def test_runtime_generates_autonomous_unknown_device_report() -> None:
    runtime = BJTToolRuntime()

    record = runtime.dispatch(
        "autonomous_unknown_device_report",
        {
            "mode": "simulation",
            "goal": "这有个不知道型号的三脚器件，自己搞清楚它是什么，并给我一份表征报告",
            "characterization_iterations": 2,
            "batch_size": 2,
            "followup_budget": 2,
        },
    )

    assert record.result["ok"] is True
    report = record.result["unknown_device_report"]
    assert report["topology_hypotheses"][0]["device_type"] == "NPN_BJT"
    assert record.result["topology_probe"]["probe_result"]["source"] == "relay_matrix_pin_probe"
    assert report["topology_hypotheses"][0]["confidence"] >= 0.85
    assert report["selected_suite"]["suite"] == "bjt_npn_adaptive_characterization"
    assert report["spice_twin"]["model_card"].startswith(".model DUT_UNKNOWN_NPN NPN")
    assert report["residual_followup"]["residual_comparison"]["added_points"] > 0
    assert "未知三脚器件的第一轮自治侦查完成" in report["conclusion"]
    assert [item["phase"] for item in report["decision_journal"]] == [
        "topology_probe",
        "adaptive_characterization",
        "model_fit",
        "residual_followup",
    ]
    assert "NPN_BJT" in report["decision_journal"][0]["hypotheses_supported"]
    assert report["decision_journal"][1]["why_next"]
    assert report["measurement_program"]["summary"]["primitive_count"] >= 4
    assert report["critic_review"]["status"] in {"pass", "warn", "revise"}
    assert report["program_refinement"]["applied_suggestions"]
    assert any(item["name"] == "critic_same_base_drive_vce_sweep" and item["kind"] == "sweep" for item in report["program_refinement"]["added_primitives"])
    assert any(item["name"] == "critic_short_long_pulse_vce_sat_check" and item["kind"] == "pulse" for item in report["program_refinement"]["added_primitives"])
    assert report["program_optimization"]["optimized_reconfiguration_count"] <= report["program_optimization"]["original_reconfiguration_count"]
    assert report["refined_program_execution"]["executed_primitive_count"] > 0
    assert report["refined_program_execution"]["executed_point_count"] > report["refined_program_execution"]["executed_primitive_count"]
    assert report["refined_program_execution"]["residual_comparison"]["added_points"] > 0
    assert any(item.get("pulse_width_us") for item in report["refined_program_execution"]["trace"] if item["status"] == "measured")
    assert report["refined_program_execution"]["pulse_diagnosis"]["hypothesis"] == "self_heating_or_thermal_saturation_drift"
    assert any(item["source"] == "pulse_diagnosis" for item in report["refined_program_execution"]["belief"]["anomaly_hypotheses"])


def test_tool_calling_agent_runs_unknown_device_demo_from_high_level_goal() -> None:
    result = ToolCallingAgent(max_steps=3).run_turn(
        "这有个不知道型号的三脚器件，你自己搞清楚它是什么，并给我一份表征报告",
        mode="simulation",
    )

    assert [item["name"] for item in result.tool_calls] == ["autonomous_unknown_device_report"]
    assert "拓扑假设排序" in result.response
    assert "判断过程" in result.response
    assert "测量程序" in result.response
    assert "critic 审查" in result.response
    assert "program refine" in result.response
    assert "program optimizer" in result.response
    assert "refined program execution" in result.response
    assert "pulse 诊断" in result.response
    assert "看到" in result.response
    assert "模型卡" in result.response
    assert ".model DUT_UNKNOWN_NPN NPN" in result.response
