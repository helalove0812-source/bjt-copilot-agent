from __future__ import annotations

from datetime import datetime, timedelta

import ai.agent as agent_module

from ai.agent import TestAgent
from ai.conversation import AIConversationState
from ai.safety import ExecutionPolicyDecision, evaluate_execution_request
from ai.test_planner import build_test_plan
from core.types import HwConfig


def test_unknown_model_uses_fallback_profile() -> None:
    plan = build_test_plan(model="XYZ123", goal="auto", depth="standard")

    assert plan.profile["confidence"] == "fallback"


def test_pnp_plan_is_not_for_auto_hardware_execution() -> None:
    plan = build_test_plan(model="S8550", goal="beta", depth="standard")

    assert plan.bjt_type == "PNP"
    assert any("PNP" in note for note in plan.safety_notes)


def test_pnp_plan_contains_guidance_notes() -> None:
    plan = build_test_plan(model="S8550", goal="screening", depth="conservative")

    notes = "\n".join(plan.safety_notes)
    assert "自动执行" in notes
    assert "NPN" in notes
    assert "datasheet" in notes or "引脚" in notes
    assert "低压" in notes


def test_pnp_plan_remains_blocked_for_auto_hardware_execution() -> None:
    plan = build_test_plan(
        model="S8550",
        goal="screening",
        depth="conservative",
        mode="hardware",
    )

    decision = evaluate_execution_request(
        plan=plan,
        mode="hardware",
        allow_hardware=True,
        token_valid=True,
    )

    assert decision.status == "deny"
    assert "pnp_auto_execution_blocked" in decision.tags


def test_hardware_execution_requires_confirmation_token(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)
    calls: list[dict] = []

    def fake_evaluate_execution_request(*, plan, mode, allow_hardware, token_valid):
        calls.append(
            {
                "plan": plan,
                "mode": mode,
                "allow_hardware": allow_hardware,
                "token_valid": token_valid,
            }
        )
        return ExecutionPolicyDecision(
            status="require_confirm",
            reasons=["need confirmation"],
            tags=["requires_hardware_confirmation"],
        )

    monkeypatch.setattr(agent_module, "evaluate_execution_request", fake_evaluate_execution_request)

    result = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)

    assert calls == [
        {
            "plan": state.current_plan,
            "mode": "hardware",
            "allow_hardware": True,
            "token_valid": False,
        }
    ]
    assert result.hardware_confirmation_required is True
    assert result.execution is None
    assert result.hardware_confirmation_token


def test_expired_hardware_confirmation_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    first = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)
    agent._hardware_confirmation["expires_at"] = datetime.now() - timedelta(seconds=1)

    second = agent.run_turn(
        "开始执行硬件测试",
        default_mode="hardware",
        allow_hardware=True,
        hardware_confirmation_token=first.hardware_confirmation_token,
    )

    assert second.hardware_confirmation_required is True
    assert second.execution is None


def test_plan_limits_are_clamped_to_hw_config() -> None:
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.30, Vcc_max=5.0)
    plan = build_test_plan(model="S8050", goal="full", depth="deep", cfg=cfg)

    assert plan.ic_limit_a <= cfg.Ic_max_A
    assert plan.power_limit_w <= cfg.Pmax_W
    assert max(plan.vcc_steps) <= cfg.Vcc_max
    assert all(point["vcc"] <= cfg.Vcc_max for point in plan.static_points)
