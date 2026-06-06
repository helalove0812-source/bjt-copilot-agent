from __future__ import annotations

from ai.dut_belief import update_belief_from_measurements
from ai.spice_twin import extract_spice_twin_from_belief, plan_residual_followup_measurements
from ai.test_planner import build_test_plan
from ai.tool_call_agent import ToolCallingAgent
from ai.tool_runtime import BJTToolRuntime


SAMPLE_POINTS = [
    {"Vcc": 3.0, "Vbb": 1.8, "Vbe": 0.66, "Vce": 2.6, "Ib": 52e-6, "Ic": 4.5e-3, "beta": 86.5, "region": "active"},
    {"Vcc": 4.5, "Vbb": 1.8, "Vbe": 0.66, "Vce": 4.0, "Ib": 52e-6, "Ic": 4.8e-3, "beta": 92.3, "region": "active"},
    {"Vcc": 3.0, "Vbb": 2.2, "Vbe": 0.69, "Vce": 2.3, "Ib": 68e-6, "Ic": 7.5e-3, "beta": 110.3, "region": "active"},
    {"Vcc": 0.5, "Vbb": 2.8, "Vbe": 0.73, "Vce": 0.18, "Ib": 94e-6, "Ic": 2.1e-3, "beta": 22.3, "region": "saturation"},
]


def test_extract_spice_twin_outputs_model_card_and_residuals() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    belief = update_belief_from_measurements(None, SAMPLE_POINTS, plan=plan)

    twin = extract_spice_twin_from_belief(belief)

    assert twin.model_name == "DUT_S8050"
    assert twin.model_card.startswith(".model DUT_S8050 NPN")
    assert "BF=" in twin.model_card
    assert "IS=" in twin.model_card
    assert twin.parameters["BF"] > 0
    assert twin.residuals["point_count"] == len(SAMPLE_POINTS)
    assert 0.0 <= twin.confidence <= 1.0


def test_tool_runtime_extracts_spice_twin_from_current_belief() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))
    runtime.dispatch("update_dut_belief", {"measurements": SAMPLE_POINTS})

    record = runtime.dispatch("extract_spice_twin", {"include_model_card": True})

    assert record.result["ok"] is True
    assert record.result["spice_twin"]["model_card"].startswith(".model DUT_S8050 NPN")
    assert record.result["spice_twin"]["residuals"]["normalized_current_residual"]
    assert record.result["postcondition_checks"][0]["status"] == "passed"


def test_residual_followup_plans_targeted_measurement_candidates() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    belief = update_belief_from_measurements(None, SAMPLE_POINTS, plan=plan)
    twin = extract_spice_twin_from_belief(belief)

    followup = plan_residual_followup_measurements(twin, belief, plan=plan, budget=3)

    assert followup["ok"] is True
    assert followup["followup_plan"]["candidates"]
    assert followup["followup_plan"]["summary"]["candidate_count"] <= 3
    assert all("safety" in item for item in followup["followup_plan"]["candidates"])


def test_tool_runtime_plans_residual_followup_from_current_belief() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))
    runtime.dispatch("update_dut_belief", {"measurements": SAMPLE_POINTS})

    record = runtime.dispatch("plan_residual_followup", {"budget": 3})

    assert record.result["ok"] is True
    assert record.result["followup_plan"]["candidates"]
    assert record.result["postcondition_checks"][0]["status"] == "passed"


def test_tool_runtime_runs_residual_followup_and_updates_twin() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))
    runtime.dispatch("run_adaptive_characterization", {"mode": "simulation", "iterations": 2, "batch_size": 2})
    before_count = len(runtime.current_belief.measured_points)

    record = runtime.dispatch("run_residual_followup", {"mode": "simulation", "budget": 2})

    assert record.result["ok"] is True
    assert record.result["measurements"]
    assert len(runtime.current_belief.measured_points) > before_count
    assert record.result["spice_twin"]["model_card"].startswith(".model DUT_S8050 NPN")
    assert record.result["residual_comparison"]["added_points"] > 0
    assert runtime.current_execution["residual_followup"] is True


def test_tool_runtime_extracts_spice_twin_after_adaptive_characterization() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))
    runtime.dispatch("run_adaptive_characterization", {"mode": "simulation", "iterations": 2, "batch_size": 2})

    record = runtime.dispatch("extract_spice_twin", {"include_model_card": True})

    assert record.result["ok"] is True
    assert "spice_twin" in record.result
    assert record.result["spice_twin"]["model_card"].startswith(".model DUT_S8050 NPN")


def test_tool_calling_agent_can_characterize_and_extract_spice_model(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    result = ToolCallingAgent().run_turn("表征 S8050 并生成 SPICE 数字孪生模型", mode="simulation")

    names = [item["name"] for item in result.tool_calls]
    assert names == [
        "delegate_task",
        "lookup_transistor",
        "build_test_plan",
        "run_adaptive_characterization",
        "extract_spice_twin",
    ]
    assert result.tool_calls[-1]["result"]["spice_twin"]["model_card"].startswith(".model DUT_S8050 NPN")
    assert "SPICE 数字孪生已生成" in result.response
    assert ".model DUT_S8050 NPN" in result.response


def test_tool_calling_agent_can_plan_residual_followup_after_spice_model(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    result = ToolCallingAgent().run_turn("表征 S8050 并生成 SPICE 数字孪生模型，然后根据残差给补测计划", mode="simulation")

    names = [item["name"] for item in result.tool_calls]
    assert names == [
        "delegate_task",
        "lookup_transistor",
        "build_test_plan",
        "run_adaptive_characterization",
        "extract_spice_twin",
        "plan_residual_followup",
    ]
    assert result.tool_calls[-1]["result"]["followup_plan"]["candidates"]
    assert "残差补测计划" in result.response


def test_tool_calling_agent_can_execute_residual_followup(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    result = ToolCallingAgent().run_turn("表征 S8050 并生成 SPICE 数字孪生模型，然后根据残差执行补测", mode="simulation")

    names = [item["name"] for item in result.tool_calls]
    assert names == [
        "delegate_task",
        "lookup_transistor",
        "build_test_plan",
        "run_adaptive_characterization",
        "extract_spice_twin",
        "run_residual_followup",
    ]
    assert result.tool_calls[-1]["result"]["measurements"]
    assert result.tool_calls[-1]["result"]["residual_comparison"]["added_points"] > 0
    assert "已执行残差补测" in result.response
    assert "模型残差变化" in result.response
