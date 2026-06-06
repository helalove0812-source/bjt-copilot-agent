from __future__ import annotations

from ai.active_inference import design_next_measurement_batch
from ai.dut_belief import update_belief_from_measurements
from ai.experiment_goal import compile_experiment_goal
from ai.test_planner import build_test_plan
from ai.tool_runtime import BJTToolRuntime


def test_compile_experiment_goal_turns_unknown_device_request_into_identify_goal() -> None:
    goal = compile_experiment_goal("这有个不知道型号的三脚器件，自己搞清楚它是什么，并给我一份表征报告")

    assert goal.kind == "IDENTIFY"
    assert "pinout_confidence" in goal.projection_variables
    assert "spice_model_card" in goal.deliverables
    assert goal.safety_constraints["max_vcc_v"] == 5.0


def test_active_inference_batch_scores_information_gain_cost_and_safety() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    belief = update_belief_from_measurements(
        None,
        [{"Vcc": 3.0, "Vbb": 2.0, "Vbe": 0.68, "Vce": 2.4, "Ib": 60e-6, "Ic": 3e-3, "beta": 50, "region": "active"}],
        plan=plan,
    )
    goal = compile_experiment_goal("表征 S8050 并提取 SPICE 模型", plan=plan)

    design = design_next_measurement_batch(belief, goal=goal, plan=plan, budget=3)

    assert design.goal.kind == "EXTRACT_MODEL"
    assert design.selected
    assert all(item.safety_status == "allow" for item in design.selected)
    assert all(item.expected_information_gain > 0 for item in design.selected)
    assert design.summary["objective"] == "maximize_expected_information_gain_per_cost_under_safety_constraints"
    assert design.summary["covered_uncertainty_targets"]


def test_runtime_design_next_batch_tool_records_provenance() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    runtime = BJTToolRuntime(current_plan=plan)
    runtime.dispatch(
        "update_dut_belief",
        {
            "measurements": [
                {"Vcc": 3.0, "Vbb": 2.0, "Vbe": 0.68, "Vce": 2.4, "Ib": 60e-6, "Ic": 3e-3, "beta": 50, "region": "active"}
            ]
        },
    )

    record = runtime.dispatch("design_next_batch", {"goal": "继续表征并提取模型", "budget": 2})
    provenance = runtime.dispatch("read_experiment_provenance", {"limit": 20})

    assert record.result["ok"] is True
    assert record.result["batch_design"]["summary"]["selected_count"] == 2
    assert record.result["postcondition_checks"][0]["status"] == "passed"
    assert any("batch_designed" in line for line in provenance.result["notebook"])


def test_adaptive_characterization_uses_active_inference_trace() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))

    record = runtime.dispatch("run_adaptive_characterization", {"mode": "simulation", "iterations": 1, "batch_size": 2})

    assert record.result["ok"] is True
    assert record.result["aide_goal"]["kind"] in {"CHARACTERIZE", "EXTRACT_MODEL"}
    assert record.result["adaptive_trace"][0]["active_inference_design"]["summary"]["selected_count"] == 2
    assert record.result["provenance"]["event_count"] > 0
