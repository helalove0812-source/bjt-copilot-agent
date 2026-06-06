from __future__ import annotations

from ai.dut_belief import update_belief_from_measurements
from ai.measurement_program import (
    build_unknown_device_measurement_program,
    critique_measurement_program,
    optimize_measurement_program,
    refine_measurement_program_from_critique,
)
from ai.unknown_device import select_characterization_suite, simulate_three_pin_topology_probe


def test_unknown_device_measurement_program_is_typed_and_criticized() -> None:
    _observations, hypotheses = simulate_three_pin_topology_probe()
    suite = select_characterization_suite(hypotheses)
    adaptive = {
        "adaptive_trace": [
            {
                "candidates": [
                    {"vcc": 1.5, "vbb": 2.0, "objective": "seed_nominal_active", "rationale": "nominal active point"},
                    {"vcc": 0.5, "vbb": 2.2, "objective": "reduce_saturation_boundary_uncertainty", "rationale": "find knee"},
                ]
            }
        ],
        "measurements": [
            {"Vcc": 1.5, "Vbb": 2.0, "Vbe": 0.68, "Vce": 0.9, "Ib": 60e-6, "Ic": 2.7e-3, "beta": 45, "region": "active"},
        ],
    }
    followup = {"followup_plan": {"candidates": [{"vcc": 0.8, "vbb": 1.95, "objective": "vce_sat_vs_ic"}]}}

    program = build_unknown_device_measurement_program(
        goal="identify unknown device",
        topology_hypotheses=hypotheses,
        selected_suite=suite,
        adaptive_result=adaptive,
        residual_followup=followup,
    )
    belief = update_belief_from_measurements(None, adaptive["measurements"], model="UNKNOWN_NPN")
    critique = critique_measurement_program(program, belief=belief, topology_hypotheses=hypotheses)
    refinement = refine_measurement_program_from_critique(program, critique, belief=belief)
    optimization = optimize_measurement_program(refinement.refined_program)

    assert program.primitives[0].objective == "identify_topology_and_candidate_pinout"
    assert {item.kind for item in program.primitives} == {"measure", "analyze"}
    assert critique.status == "warn"
    assert any(item["area"] == "coverage" for item in critique.issues)
    assert any(item.name == "critic_same_base_drive_vce_sweep" and item.kind == "sweep" for item in refinement.added_primitives)
    assert any(item.name == "critic_short_long_pulse_vce_sat_check" and item.kind == "pulse" for item in refinement.added_primitives)
    assert len(refinement.refined_program.primitives) > len(program.primitives)
    assert "sweep" in {item.kind for item in refinement.refined_program.primitives}
    assert "pulse" in {item.kind for item in refinement.refined_program.primitives}
    assert optimization.optimized_reconfiguration_count <= optimization.original_reconfiguration_count
