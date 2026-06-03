from __future__ import annotations

from ai.test_planner import TestPlan

from ai.runtime_guard import RuntimeAbortDecision, check_abort_after_point


def make_plan() -> TestPlan:
    return TestPlan(
        model="S8050",
        bjt_type="NPN",
        goal="beta",
        depth="standard",
        mode="hardware",
        vcc_steps=[0.0, 1.0, 2.0],
        vbb_steps=[1.0, 2.0],
        static_points=[{"vcc": 1.0, "vbb": 1.0}],
        ic_limit_a=0.03,
        power_limit_w=0.3,
        sample_count=2048,
        scan_mode="software",
        steps=["x"],
        safety_notes=[],
        profile={"confidence": "catalog"},
    )


def test_runtime_guard_aborts_when_ic_exceeds_limit() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.031, "Vce": 2.0},
        history=[],
    )

    assert decision.should_abort is True
    assert "runtime_ic_limit_exceeded" in decision.tags


def test_runtime_guard_aborts_when_power_exceeds_limit() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.02, "Vce": 20.0},
        history=[],
    )

    assert decision.should_abort is True
    assert "runtime_power_limit_exceeded" in decision.tags


def test_runtime_guard_aborts_on_two_point_instability_trend() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.0065, "Vce": 1.0},
        history=[{"Ic": 0.004, "Vce": 1.7}],
    )

    assert decision.should_abort is True
    assert "runtime_instability_trend" in decision.tags


def test_runtime_guard_allows_normal_point() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.005, "Vce": 2.4},
        history=[{"Ic": 0.004, "Vce": 2.5}],
    )

    assert decision == RuntimeAbortDecision(should_abort=False, reason="", tags=[])
