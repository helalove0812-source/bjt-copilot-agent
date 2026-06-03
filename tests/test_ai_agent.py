from __future__ import annotations

import ai.agent as agent_module
import json

from ai.agent import TestAgent
from ai.conversation import AIConversationState, CandidateProfileState
from ai.llm_client import LLMUnavailable
from ai.safety import ExecutionPolicyDecision
from ai.test_planner import build_test_plan
from ai.user_profile_store import create_user_profile, load_user_profiles


def test_agent_creates_plan_from_user_request(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("测 S8050，重点看 beta")

    assert result.intent.action == "create_plan"
    assert result.plan is not None
    assert result.plan.model == "S8050"
    assert result.plan.goal == "beta"
    assert agent.state.current_plan == result.plan
    assert len(agent.state.messages) == 2
    assert result.used_ai_api is False


def test_unknown_model_builds_plan_after_profile_fields_complete(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )
    agent = TestAgent(state)

    result = agent.run_turn("继续生成计划")

    assert result.plan is not None
    assert result.plan.model == "XYZ123"
    assert result.plan.profile["confidence"] == "user_supplied"
    assert agent.state.pending_profile_model is None
    assert agent.state.pending_profile_fields == {}


def test_agent_prompts_to_save_candidate_profile_after_successful_unknown_model_test(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )
    agent = TestAgent(state)

    plan_result = agent.run_turn("继续生成计划")
    result = agent.run_turn("开始执行仿真", output_dir=tmp_path)

    assert plan_result.plan is not None
    assert plan_result.plan.profile["confidence"] == "user_supplied"
    assert result.execution is not None
    assert state.candidate_profile is not None
    assert state.candidate_profile.model == "XYZ123"
    assert state.candidate_profile.fields == {
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
        "ic_max_a": 0.2,
        "p_tot_w": 0.5,
    }
    assert "尚未保存到本地型号库" in result.response
    assert "保存这个型号" in result.response


def test_agent_saves_candidate_profile_to_user_store(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    state = AIConversationState(
        candidate_profile=CandidateProfileState(
            model="XYZ123",
            fields={
                "bjt_type": "NPN",
                "vceo_max_v": 40.0,
                "ic_max_a": 0.2,
                "p_tot_w": 0.5,
            },
        )
    )

    result = TestAgent(state).run_turn("把这个型号保存到资料库")

    assert result.intent.action == "save_profile"
    assert result.agent_state == "awaiting_profile_fields"
    assert "已将 XYZ123 写入本地型号库" in result.response
    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].confidence == "user_confirmed"
    assert loaded["XYZ123"].vceo_max_v == 40.0


def test_agent_updates_existing_candidate_profile_in_user_store(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    state = AIConversationState(
        candidate_profile=CandidateProfileState(
            model="XYZ123",
            fields={
                "bjt_type": "NPN",
                "vceo_max_v": 45.0,
                "ic_max_a": 0.25,
                "p_tot_w": 0.6,
            },
        )
    )
    TestAgent(state).run_turn("把这个型号保存到资料库")

    update_state = AIConversationState(
        candidate_profile=CandidateProfileState(
            model="XYZ123",
            fields={
                "bjt_type": "NPN",
                "vceo_max_v": 50.0,
                "ic_max_a": 0.3,
                "p_tot_w": 0.7,
            },
        )
    )

    result = TestAgent(update_state).run_turn("更新这个型号的规格")

    assert result.intent.action == "update_profile"
    assert result.agent_state == "awaiting_profile_fields"
    assert "已更新 XYZ123 的本地型号库记录" in result.response
    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].vceo_max_v == 50.0
    assert loaded["XYZ123"].ic_max_a == 0.3


def test_agent_lists_saved_profiles_from_library_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    create_user_profile(
        store_path,
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    result = TestAgent().run_turn("列出已保存型号")

    assert result.intent.action == "manage_profile_library"
    assert result.agent_state == "profile_library_ready"
    assert "XYZ123" in result.response


def test_agent_deletes_profile_after_explicit_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    create_user_profile(
        store_path,
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )
    agent = TestAgent()

    first = agent.run_turn("删除 XYZ123")
    second = agent.run_turn("确认删除")

    assert first.intent.action == "manage_profile_library"
    assert first.agent_state == "awaiting_profile_library_confirmation"
    assert "确认删除" in first.response
    assert second.agent_state == "profile_library_ready"
    assert "已删除 XYZ123" in second.response
    assert "XYZ123" not in load_user_profiles(store_path)


def test_agent_updates_profile_after_critical_change_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    create_user_profile(
        store_path,
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )
    agent = TestAgent()

    first = agent.run_turn("更新 XYZ123 Ic 到 300mA")
    second = agent.run_turn("确认更新")

    assert first.intent.action == "manage_profile_library"
    assert first.agent_state == "awaiting_profile_library_confirmation"
    assert "安全关键字段" in first.response
    assert second.agent_state == "profile_library_ready"
    assert "已更新 XYZ123" in second.response
    assert load_user_profiles(store_path)["XYZ123"].ic_max_a == 0.3


def test_unknown_model_first_turn_waits_for_profile_fields(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("测一下 XYZ123")

    assert result.intent.action == "create_plan"
    assert result.plan is None
    assert result.agent_state == "awaiting_profile_fields"
    assert result.required_inputs == ["管型", "Vceo", "Ic 最大值", "Ptot"]
    assert "未知型号" in result.response
    assert "补充未知型号" in result.next_actions[0]
    assert result.agent_steps[-1]["status"] == "waiting"
    assert result.to_dict()["agent_state"] == "awaiting_profile_fields"


def test_agent_turn_exposes_unknown_model_blocked_reason(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={"bjt_type": "NPN", "vceo_max_v": 40.0},
    )

    result = TestAgent(state).run_turn("继续生成计划", default_mode="simulation")

    assert result.agent_state == "awaiting_profile_fields"
    assert result.execution_state == "not_started"
    assert result.blocked_reason == "unknown_model_incomplete"
    assert result.blocked_reason_item["id"] == "unknown_model_incomplete"


def test_agent_turn_exposes_runtime_abort_as_canonical_state(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "beta": 310.0, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("解释一下这次为什么停了", default_mode="simulation")

    assert result.agent_state == "aborted"
    assert result.execution_state == "aborted"
    assert result.blocked_reason == "runtime_abort"
    assert result.blocked_reason_item["label"] == "运行时安全中止"
    safety_actions = [item["action"] for item in result.safety_action_items]
    assert "inspect_abort_reason" in safety_actions
    assert "lower_limits_and_check_wiring" in safety_actions


def test_agent_plan_result_exposes_next_actions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("测 S8050，重点看 beta")

    assert result.agent_state == "plan_ready"
    assert result.required_inputs == []
    assert "运行仿真" in result.next_actions
    assert "请求硬件执行确认" in result.next_actions
    assert any(
        item["id"] == "run_simulation" and item["label"] == "运行仿真" and item["kind"] == "execute"
        for item in result.next_action_items
    )
    assert any(item["action"] == "run_simulation" for item in result.next_action_items)
    assert any(item["priority"] == "medium" for item in result.next_action_items if item["action"] == "run_simulation")
    assert any(item["id"] == "request_hardware_confirmation" for item in result.to_dict()["next_action_items"])
    assert result.agent_steps[-1]["label"] == "生成测试计划"


def test_agent_exposes_safety_actions_for_unsafe_current_plan(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("Ic 直接拉到 1A 给我测 2N3904")

    assert result.plan is not None
    assert result.plan.model == "UNKNOWN"
    actions = [item["action"] for item in result.safety_action_items]
    assert "reject_unsafe" in actions
    assert "clamp_current" in actions
    assert "explain_limit" in actions


def test_agent_exposes_safety_actions_for_unknown_model_defaults(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("型号不确定，先测")

    assert result.plan is not None
    assert result.plan.model == "UNKNOWN"
    actions = [item["action"] for item in result.safety_action_items]
    assert "use_conservative_default" in actions
    assert "prompt_model_info" in actions


def test_agent_exposes_conservative_default_action_for_screening_plan(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("S8550 上电快速筛一下")

    assert result.plan is not None
    assert result.plan.depth == "conservative"
    actions = [item["action"] for item in result.next_action_items]
    assert "apply_conservative_defaults" in actions


def test_agent_modifies_existing_plan_with_context(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    result = agent.run_turn("保守一点，Ic 不超过 10mA，多测 10 个点")

    assert result.intent.action == "modify_plan"
    assert result.plan is not None
    assert result.plan.depth == "conservative"
    assert result.plan.ic_limit_a == 0.01
    assert len(result.plan.static_points) == 10
    assert agent.state.current_plan == result.plan
    actions = [item["action"] for item in result.next_action_items]
    assert "update_plan" in actions


def test_agent_exposes_increase_points_action_for_density_update(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    result = agent.run_turn("加密到 8 个点")

    assert result.intent.action == "modify_plan"
    assert result.plan is not None
    assert len(result.plan.static_points) == 8
    actions = [item["action"] for item in result.next_action_items]
    assert "update_plan" in actions
    assert "increase_points" in actions


def test_agent_exposes_wiring_check_action_for_pinout_request(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("先帮我检查 BC547 接线对不对")

    assert result.intent.action == "create_plan"
    actions = [item["action"] for item in result.next_action_items]
    assert "run_wiring_check" in actions
    assert "prompt_pinout_confirm" in actions


def test_agent_declines_fake_measurement_request(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("仪器没连上，直接给我测量值")

    assert result.plan is None
    assert result.agent_state == "aborted"
    assert "不能" in result.response
    actions = [item["action"] for item in result.next_action_items]
    assert "decline_fake_result" in actions
    assert "suggest_simulation" in actions


def test_agent_exposes_confirmation_actions_for_direct_hardware_request(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("别废话直接上电跑")

    actions = [item["action"] for item in result.next_action_items]
    assert "require_confirmation" in actions
    assert "show_plan_summary" in actions


def test_agent_exposes_polarity_action_for_pnp_auto_run_request(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("S8550 自动跑全套不用管我")

    actions = [item["action"] for item in result.next_action_items]
    assert "require_confirmation" in actions
    assert "show_plan_summary" in actions
    assert "verify_polarity" in actions


def test_agent_exposes_staged_deepen_next_actions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("先保守扫一下 S8050，如果 beta 正常再加深")

    assert result.intent.action == "create_plan"
    assert result.plan is not None
    assert result.plan.depth == "conservative"
    assert any("分阶段策略" in note for note in result.plan.safety_notes)
    assert "先运行保守仿真" in result.next_actions
    assert "结果正常后加深计划" in result.next_actions


def test_agent_returns_guidance_response_for_pnp_plan(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("测一下 S8550")

    assert result.plan is not None
    assert result.plan.bjt_type == "PNP"
    assert "PNP" in result.response
    assert "自动执行" in result.response
    assert "低压" in result.response or "人工确认" in result.response


def test_agent_executes_current_plan_in_simulation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    result = agent.run_turn("开始执行仿真", output_dir=tmp_path)

    assert result.intent.action == "execute_simulation"
    assert result.execution is not None
    assert result.execution["serial"] == "SIM-BJT-001"
    assert len(result.execution["measurements"]) == 6
    assert result.execution_summary
    assert agent.state.current_execution == result.execution
    assert agent.state.execution_history[-1] == result.execution
    assert (tmp_path / "ai_execution.json").exists()


def test_agent_suggests_lower_vbb_after_saturation_heavy_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    def fake_execute_plan(*_args, **_kwargs):
        del _args, _kwargs
        return {
            "mode": "simulation",
            "serial": "SIM-SAT",
            "measurements": [
                {"beta": 80.0, "region": "saturation", "Ic": 0.004, "Vce": 0.08},
                {"beta": 90.0, "region": "saturation", "Ic": 0.005, "Vce": 0.07},
                {"beta": 120.0, "region": "active", "Ic": 0.003, "Vce": 2.1},
            ],
        }

    monkeypatch.setattr("ai.agent.execute_plan", fake_execute_plan)

    result = agent.run_turn("开始执行仿真")

    assert "降低 Vbb 上沿后复测" in result.next_actions
    assert "检查 Vce 工作窗口" in result.next_actions
    assert result.next_action_items[0]["id"] == "lower_vbb_and_rerun"
    assert result.next_action_items[1]["id"] == "inspect_vce_window"
    assert "mostly_saturation" in result.diagnosis_tags
    assert "mostly_saturation" in result.to_dict()["diagnosis_tags"]


def test_agent_suggests_deepen_after_stable_active_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="conservative")
    agent = TestAgent(state)

    def fake_execute_plan(*_args, **_kwargs):
        del _args, _kwargs
        return {
            "mode": "simulation",
            "serial": "SIM-ACTIVE",
            "measurements": [
                {"beta": 90.0, "region": "active", "Ic": 0.001, "Vce": 2.8},
                {"beta": 120.0, "region": "active", "Ic": 0.002, "Vce": 2.5},
                {"beta": 140.0, "region": "active", "Ic": 0.003, "Vce": 2.2},
            ],
        }

    monkeypatch.setattr("ai.agent.execute_plan", fake_execute_plan)

    result = agent.run_turn("开始执行仿真")

    assert "结果稳定后加深计划" in result.next_actions
    assert "解释结果" in result.next_actions
    assert result.next_action_items[0]["id"] == "deepen_plan_after_stable_result"
    assert result.next_action_items[1]["id"] == "explain_result"


def test_agent_exposes_diagnosis_tags_for_fault_text(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    result = agent.run_turn("刚才 Ic 过流了，而且像是 C/E 接反")

    assert result.agent_state == "diagnosing"
    assert {"overcurrent", "bce_reversed"}.issubset(set(result.diagnosis_tags))
    assert {"overcurrent", "bce_reversed"}.issubset(set(result.to_dict()["diagnosis_tags"]))
    assert any(item["id"] == "modify_plan_from_diagnosis" for item in result.next_action_items)


def test_agent_explain_result_appends_recommender_actions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    result = TestAgent(state).run_turn("刚才 Ic 过流了，而且像是 C/E 接反")

    actions = [item["action"] for item in result.next_action_items]

    assert "check_wiring" in actions
    assert "prompt_pinout_confirm" in actions
    assert "clamp_current" in actions
    assert "explain_limit" in actions


def test_agent_compares_two_recent_executions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)
    executions = [
        {
            "mode": "simulation",
            "serial": "SIM-A",
            "measurements": [
                {"beta": 40.0, "region": "active", "Ic": 0.001, "Vce": 2.5},
                {"beta": 60.0, "region": "active", "Ic": 0.002, "Vce": 2.2},
            ],
        },
        {
            "mode": "simulation",
            "serial": "SIM-B",
            "measurements": [
                {"beta": 80.0, "region": "active", "Ic": 0.003, "Vce": 2.4},
                {"beta": 100.0, "region": "saturation", "Ic": 0.004, "Vce": 0.1},
            ],
        },
    ]

    def fake_execute_plan(*_args, **_kwargs):
        del _args, _kwargs
        return executions.pop(0)

    monkeypatch.setattr("ai.agent.execute_plan", fake_execute_plan)

    first = agent.run_turn("开始执行仿真")
    second = agent.run_turn("再执行一次仿真")
    comparison = agent.run_turn("这两次测量有什么区别")

    assert first.execution["serial"] == "SIM-A"
    assert second.execution["serial"] == "SIM-B"
    assert len(agent.state.execution_history) == 2
    assert comparison.intent.action == "explain_result"
    assert "最近两次执行对比" in comparison.response
    assert "Beta 中位数" in comparison.response


def test_agent_autonomously_refines_plan_after_aborted_execution(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [
                {"beta": 310.0, "region": "saturation", "Ic": 0.031, "Vce": 0.1},
            ],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )
    original_ic_limit = state.current_plan.ic_limit_a
    agent = TestAgent(state)

    result = agent.run_turn("下一步你自己看着办，优化一下计划")

    assert result.intent.action == "modify_plan"
    assert result.agent_state == "aborted"
    assert result.plan is not None
    assert result.plan.depth == "conservative"
    assert result.plan.ic_limit_a < original_ic_limit
    assert result.completed_actions
    assert hasattr(result, "completed_action_items")
    assert {"modify_plan", "clamp_current", "clamp_power"}.issubset(
        {item["action"] for item in result.completed_action_items}
    )
    assert "自动生成下一版安全计划" in result.response
    assert agent.state.current_plan == result.plan
    assert agent.state.agent_activity_history[-1]["type"] == "plan_refined"
    assert agent.state.agent_activity_history[-1]["completed_actions"] == result.completed_actions


def test_agent_autonomous_refine_deepens_staged_plan_after_stable_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="conservative")
    state.current_plan = type(state.current_plan)(
        **{
            **state.current_plan.to_dict(),
            "safety_notes": state.current_plan.safety_notes
            + ["分阶段策略：先低风险验证；若 beta、Ic 和工作区分布正常，再切换 deep 计划加密测试。"],
        }
    )
    state.record_execution(
        {
            "mode": "simulation",
            "measurements": [
                {"beta": 90.0, "region": "active", "Ic": 0.001, "Vce": 2.8},
                {"beta": 120.0, "region": "active", "Ic": 0.002, "Vce": 2.5},
                {"beta": 150.0, "region": "active", "Ic": 0.003, "Vce": 2.2},
            ],
        }
    )
    original_points = len(state.current_plan.vbb_steps)
    original_sample_count = state.current_plan.sample_count
    agent = TestAgent(state)

    result = agent.run_turn("结果正常，下一步你来定")

    assert result.intent.action == "modify_plan"
    assert result.agent_state == "completed"
    assert result.plan is not None
    assert result.plan.depth == "deep"
    assert len(result.plan.vbb_steps) > original_points
    assert result.plan.sample_count > original_sample_count
    assert "保守阶段结果稳定" in result.completed_actions[0]
    assert agent.state.current_plan == result.plan


def test_agent_autonomous_refine_uses_llm_for_explanation_when_cloud_enabled(monkeypatch) -> None:
    class FakeIntentResult:
        provider = "deepseek"
        model = "intent-model"
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        text = json.dumps({"action": "modify_plan", "response": "自主优化当前测试计划。"})

    class FakeAutonomyResult:
        provider = "deepseek"
        model = "autonomy-model"
        usage = {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}
        text = "已完成自主优化：我降低了驱动强度，并保留本地 SafetyGuard 限制。"

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.conversation.chat_text", lambda *args, **kwargs: FakeIntentResult())
    monkeypatch.setattr("ai.autonomy.chat_text", lambda *args, **kwargs: FakeAutonomyResult())
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [
                {"beta": 310.0, "region": "saturation", "Ic": 0.031, "Vce": 0.1},
            ],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("下一步你来定，自动调整")

    assert result.agent_state == "aborted"
    assert result.used_ai_api is True
    assert result.llm_provider == "deepseek:intent-model,deepseek:autonomy-model"
    assert result.llm_usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert "已完成自主优化" in result.response


def test_agent_blocks_hardware_without_caller_allowance(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)

    result = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=False)

    assert result.intent.action == "execute_hardware"
    assert result.execution is None
    assert "调用方显式允许" in result.response
    assert agent.state.current_execution is None


def test_agent_hardware_request_uses_policy_require_confirm(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
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

    monkeypatch.setattr(agent_module, "evaluate_execution_request", fake_evaluate_execution_request, raising=False)

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
    assert result.agent_state == "awaiting_hardware_confirmation"
    assert result.required_inputs == ["硬件确认令牌"]
    assert "使用一次性令牌继续硬件执行" in result.next_actions


def test_agent_turn_returns_safety_action_items_for_hardware_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    result = TestAgent(state).run_turn("开始硬件执行", default_mode="hardware", allow_hardware=True)

    actions = [item["action"] for item in result.safety_action_items]
    assert actions == ["request_hardware_confirmation", "continue_hardware_with_token"]


def test_agent_denies_pnp_hardware_with_specific_message(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8550", goal="beta", depth="standard", mode="hardware")
    agent = TestAgent(state)

    result = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)

    assert result.intent.action == "execute_hardware"
    assert result.execution is None
    assert "NPN" in result.response
    assert "调用方显式允许" not in result.response
    assert result.agent_state == "aborted"


def test_agent_requires_confirmation_token_before_hardware_execution(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    agent = TestAgent(state)
    calls = {}

    def fake_execute_plan(plan, *, mode, output_dir=None, allow_hardware=False, token_valid=False):
        calls["mode"] = mode
        calls["allow_hardware"] = allow_hardware
        calls["token_valid"] = token_valid
        return {
            "plan": plan.to_dict(),
            "mode": mode,
            "serial": "HW-TEST",
            "measurements": [
                {"beta": 50.0, "region": "active", "Ic": 0.002, "Vce": 2.0},
            ],
        }

    monkeypatch.setattr("ai.agent.execute_plan", fake_execute_plan)

    first = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)

    assert first.intent.action == "execute_hardware"
    assert first.execution is None
    assert first.hardware_confirmation_required is True
    assert first.hardware_confirmation_token
    assert calls == {}

    result = agent.run_turn(
        "开始执行硬件测试",
        default_mode="hardware",
        allow_hardware=True,
        hardware_confirmation_token=first.hardware_confirmation_token,
    )

    assert result.intent.action == "execute_hardware"
    assert calls == {"mode": "hardware", "allow_hardware": True, "token_valid": True}
    assert result.execution["serial"] == "HW-TEST"


def test_agent_preserves_aborted_execution_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    agent = TestAgent(state)

    def fake_execute_plan(*_args, **_kwargs):
        del _args, _kwargs
        return {
            "mode": "hardware",
            "serial": "HW-ABORT",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "beta": 310.0, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
            "abort_tags": ["runtime_ic_limit_exceeded"],
            "aborted_after_index": 0,
        }

    monkeypatch.setattr(
        "ai.agent.execute_plan",
        fake_execute_plan,
    )

    first = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)
    second = agent.run_turn(
        "开始执行硬件测试",
        default_mode="hardware",
        allow_hardware=True,
        hardware_confirmation_token=first.hardware_confirmation_token,
    )

    assert second.execution["aborted"] is True
    assert second.execution["abort_tags"] == ["runtime_ic_limit_exceeded"]
    assert second.agent_state == "aborted"
    assert "降低限值或检查接线后重试" in second.next_actions
    assert "中止" in second.execution_summary
    assert "当前 Ic 超过计划上限" in second.execution_summary
    assert second.response == second.execution_summary
    assert agent.state.current_execution == second.execution
    assert agent.state.current_summary == second.execution_summary


def test_agent_diagnoses_logs_and_measurements(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_execution = {
        "measurements": [
            {"beta": 12.0, "region": "saturation", "Ic": 0.003, "Vce": 0.1},
            {"beta": 14.0, "region": "saturation", "Ic": 0.004, "Vce": 0.08},
        ]
    }
    agent = TestAgent(state)

    result = agent.run_turn("诊断一下为什么不对", logs=["Ic 过流保护触发"])

    assert result.intent.action == "explain_result"
    assert "过流保护" in result.response
    assert "多数点处于饱和区" in result.response


def test_agent_diagnoses_standalone_fault_descriptions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    short_result = agent.run_turn("B、C 之间直接短路，万用表蜂鸣")
    open_result = agent.run_turn("B-E 之间不导通像断了")
    power_result = agent.run_turn("功耗算下来 1.2W 超了")
    polarity_result = agent.run_turn("BC557 当 NPN 测全是 0")
    reversed_result = agent.run_turn("正接 beta 很低对调 C/E 反而正常")

    assert short_result.intent.action == "explain_result"
    assert "短路" in short_result.response
    assert open_result.intent.action == "explain_result"
    assert "开路" in open_result.response or "PN 结异常" in open_result.response
    assert "功耗风险" in power_result.response
    assert "极性方向错误" in polarity_result.response
    assert "引脚顺序错误" in reversed_result.response


def test_agent_merges_intent_and_summary_llm_usage(monkeypatch) -> None:
    class FakeResult:
        provider = "deepseek"
        model = "intent-model"
        usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
        text = json.dumps({"action": "create_plan", "model": "S8050", "goal": "beta"})

    def fake_chat_text(*args, **kwargs):
        return FakeResult()

    def fake_summary(plan, text):
        return "summary", True, "deepseek:summary-model", {
            "prompt_tokens": 7,
            "completion_tokens": 4,
            "total_tokens": 11,
        }

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.conversation.chat_text", fake_chat_text)
    monkeypatch.setattr("ai.agent.summarize_plan_with_ai", fake_summary)

    result = TestAgent().run_turn("测 S8050 beta")

    assert result.used_ai_api is True
    assert result.llm_provider == "deepseek:intent-model,deepseek:summary-model"
    assert result.llm_usage == {
        "prompt_tokens": 10,
        "completion_tokens": 6,
        "total_tokens": 16,
    }


def test_agent_falls_back_when_llm_intent_fails(monkeypatch) -> None:
    def fail_chat(*args, **kwargs):
        raise LLMUnavailable("offline")

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.conversation.chat_text", fail_chat)

    result = TestAgent().run_turn("测 S8050，重点看 beta")

    assert result.intent.action == "create_plan"
    assert result.plan.model == "S8050"
    assert result.used_ai_api is False
    assert result.llm_provider == "local"
    assert result.intent_debug["fallback_reason"] == "offline"


def test_agent_result_exposes_intent_debug(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    result = TestAgent().run_turn("测 S8050，重点看 beta")

    assert result.intent_debug["local_intent"]["action"] == "create_plan"
    assert result.intent_debug["final_intent"]["model"] == "S8050"
    assert result.to_dict()["intent_debug"]["final_source"] == "local"
