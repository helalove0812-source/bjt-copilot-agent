from __future__ import annotations

from dataclasses import replace

import ai.test_planner as test_planner_module
from ai.test_planner import TestPlan, build_test_plan
from core.types import HwConfig

from ai.safety import PlanPolicyResult, clamp_plan_to_policy, evaluate_execution_request


def make_plan(**overrides) -> TestPlan:
    base = TestPlan(
        model="S8050",
        bjt_type="NPN",
        goal="beta",
        depth="standard",
        mode="simulation",
        vcc_steps=[0.0, 1.0, 6.0],
        vbb_steps=[1.0, 2.0],
        static_points=[{"vcc": 3.0, "vbb": 2.0}],
        ic_limit_a=0.2,
        power_limit_w=0.8,
        sample_count=2048,
        scan_mode="software",
        steps=["x"],
        safety_notes=[],
        profile={"confidence": "catalog"},
    )
    return base.__class__(**{**base.to_dict(), **overrides})


def test_clamp_plan_to_policy_caps_plan_limits() -> None:
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.3, Vcc_max=5.0)
    plan = make_plan()

    result = clamp_plan_to_policy(plan, cfg)

    assert result.changed is True
    assert result.plan.ic_limit_a == 0.03
    assert result.plan.power_limit_w == 0.3
    assert max(result.plan.vcc_steps) == 5.0
    assert "clamped_to_hardware_max" in result.tags


def test_build_test_plan_uses_policy_clamp(monkeypatch) -> None:
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.3, Vcc_max=5.0)
    calls: list[tuple[TestPlan, HwConfig]] = []

    def fake_clamp(plan: TestPlan, cfg_arg: HwConfig) -> PlanPolicyResult:
        calls.append((plan, cfg_arg))
        return PlanPolicyResult(
            plan=replace(
                plan,
                ic_limit_a=0.012345,
                power_limit_w=0.06789,
                vcc_steps=[0.0, 1.234],
            ),
            tags=["fake_policy"],
            changed=True,
        )

    monkeypatch.setattr(test_planner_module, "clamp_plan_to_policy", fake_clamp, raising=False)

    plan = build_test_plan(model="S8050", goal="full", depth="deep", cfg=cfg)

    assert calls and calls[0][1] is cfg
    assert plan.ic_limit_a == 0.012345
    assert plan.power_limit_w == 0.06789
    assert plan.vcc_steps == [0.0, 1.234]


def test_evaluate_execution_request_requires_confirm_for_hardware_without_token() -> None:
    decision = evaluate_execution_request(
        plan=make_plan(mode="hardware"),
        mode="hardware",
        allow_hardware=True,
        token_valid=False,
    )

    assert decision.status == "require_confirm"
    assert "显式确认" in decision.reasons[0]
    assert "requires_hardware_confirmation" in decision.tags


def test_evaluate_execution_request_denies_non_npn_hardware_execution() -> None:
    decision = evaluate_execution_request(
        plan=make_plan(bjt_type="PNP", mode="hardware"),
        mode="hardware",
        allow_hardware=True,
        token_valid=True,
    )

    assert decision.status == "deny"
    assert "pnp_auto_execution_blocked" in decision.tags


def test_evaluate_execution_request_prioritizes_non_npn_block_over_hardware_allowance() -> None:
    decision = evaluate_execution_request(
        plan=make_plan(bjt_type="PNP", mode="hardware"),
        mode="hardware",
        allow_hardware=False,
        token_valid=False,
    )

    assert decision.status == "deny"
    assert "pnp_auto_execution_blocked" in decision.tags
    assert "NPN" in decision.reasons[0]
