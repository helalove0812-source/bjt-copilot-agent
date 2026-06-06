from __future__ import annotations

from ai.dut_belief import suggest_next_measurements_for_state, update_belief_from_measurements
from ai.test_planner import build_test_plan
from ai.tool_call_agent import ToolCallingAgent
from ai.tool_runtime import BJTToolRuntime


def test_dut_belief_updates_structured_uncertainty_and_candidates() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    belief = update_belief_from_measurements(
        None,
        [
            {"Vcc": 3.0, "Vbb": 2.0, "Vbe": 0.68, "Vce": 2.4, "Ib": 60e-6, "Ic": 3e-3, "beta": 50, "region": "active"},
            {"Vcc": 0.5, "Vbb": 2.8, "Vbe": 0.72, "Vce": 0.18, "Ib": 90e-6, "Ic": 2e-3, "beta": 22, "region": "saturation"},
        ],
        plan=plan,
    )

    assert belief.model == "S8050"
    assert belief.device_type == "NPN"
    assert belief.region_counts["active"] == 1
    assert belief.region_counts["saturation"] == 1
    assert belief.beta_distribution["count"] == 1
    assert belief.uncertainty["overall"] > 0
    assert belief.next_measurement_candidates


def test_dut_belief_suggests_unmeasured_informative_points() -> None:
    plan = build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation")
    belief = update_belief_from_measurements(
        None,
        [{"Vcc": 3.0, "Vbb": 2.0, "Vbe": 0.68, "Vce": 2.4, "Ib": 60e-6, "Ic": 3e-3, "beta": 50, "region": "active"}],
        plan=plan,
    )

    candidates = suggest_next_measurements_for_state(belief, plan=plan, budget=3)

    assert len(candidates) == 3
    assert all((candidate.vcc, candidate.vbb) != (3.0, 2.0) for candidate in candidates)
    assert any("uncertainty" in candidate.objective for candidate in candidates)


def test_tool_runtime_adaptive_characterization_runs_belief_loop() -> None:
    runtime = BJTToolRuntime(current_plan=build_test_plan(model="S8050", goal="full", depth="standard", mode="simulation"))

    record = runtime.dispatch("run_adaptive_characterization", {"mode": "simulation", "iterations": 2, "batch_size": 2})

    assert record.result["ok"] is True
    assert record.result["belief"]["measured_points"]
    assert record.result["adaptive_trace"]
    assert runtime.current_belief is not None
    assert runtime.current_execution is not None
    assert runtime.current_execution["adaptive"] is True
    assert "postcondition_checks" in record.result


def test_tool_calling_agent_can_enter_adaptive_characterization(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    result = ToolCallingAgent().run_turn("表征 S8050，用自适应方式研究这个管子", mode="simulation")

    names = [item["name"] for item in result.tool_calls]
    assert names == ["delegate_task", "lookup_transistor", "build_test_plan", "run_adaptive_characterization"]
    assert result.execution is not None
    assert result.execution["adaptive"] is True
