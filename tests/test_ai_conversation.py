from __future__ import annotations

from ai.conversation import (
    AIConversationState,
    CandidateProfileState,
    AIIntent,
    answer_from_context,
    apply_intent_to_plan,
    infer_intent_locally,
    interpret_user_message,
)
from core.types import HwConfig
from ai.test_planner import build_test_plan


def test_contextual_intent_modifies_existing_plan_current_limit() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    intent = infer_intent_locally("保守一点，Ic 不超过 10mA", state)
    plan = apply_intent_to_plan(intent, state)

    assert plan.model == "S8050"
    assert plan.depth == "conservative"
    assert plan.ic_limit_a == 0.01


def test_local_ai_mode_does_not_call_cloud(monkeypatch) -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    monkeypatch.setenv("BJT_AI_MODE", "local")

    def fail_chat(*args, **kwargs):
        raise AssertionError("cloud should not be called")

    monkeypatch.setattr("ai.conversation.chat_text", fail_chat)

    intent, used_ai, provider, usage = interpret_user_message(
        "保守一点，Ic 不超过 10mA",
        state,
    )

    assert intent.action == "modify_plan"
    assert used_ai is False
    assert provider == "local"


def test_contextual_intent_can_increase_vbb_points() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    plan = apply_intent_to_plan(
        AIIntent(action="modify_plan", vbb_points=10),
        state,
    )

    assert len(plan.vbb_steps) == 10
    assert len(plan.static_points) == 10


def test_contextual_intent_can_raise_limits_within_hardware_config() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="conservative")
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.30, Vcc_max=5.0)

    plan = apply_intent_to_plan(
        AIIntent(action="modify_plan", ic_limit_a=0.02, power_limit_w=0.20, vcc_max=4.5),
        state,
        cfg=cfg,
    )

    assert plan.ic_limit_a == 0.02
    assert plan.power_limit_w == 0.20
    assert max(plan.vcc_steps) == 4.5


def test_contextual_intent_clamps_unsafe_limit_requests_to_hardware_config() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.30, Vcc_max=5.0)

    plan = apply_intent_to_plan(
        AIIntent(action="modify_plan", ic_limit_a=1.0, power_limit_w=2.0, vcc_max=100.0),
        state,
        cfg=cfg,
    )

    assert plan.ic_limit_a == 0.03
    assert plan.power_limit_w == 0.30
    assert max(plan.vcc_steps) == 5.0


def test_conversation_history_trims_in_user_assistant_pairs() -> None:
    state = AIConversationState()

    for index in range(8):
        state.add("user", f"user-{index}")
        state.add("assistant", f"assistant-{index}")

    assert len(state.messages) == 12
    assert state.messages[0].role == "user"
    assert state.messages[0].content == "user-2"
    assert state.messages[-1].content == "assistant-7"


def test_local_intent_explains_existing_result() -> None:
    state = AIConversationState()
    state.current_execution = {
        "measurements": [
            {"beta": 30.0, "region": "active", "Ic": 0.001, "Vce": 2.5},
        ]
    }

    intent = infer_intent_locally("解释刚才结果", state)

    assert intent.action == "explain_result"


def test_conversation_records_execution_history_with_limit() -> None:
    state = AIConversationState()

    for index in range(7):
        state.record_execution(
            {
                "serial": f"SIM-{index}",
                "measurements": [
                    {"beta": 20.0 + index, "region": "active", "Ic": 0.001, "Vce": 2.5},
                ],
            }
        )

    assert state.current_execution["serial"] == "SIM-6"
    assert len(state.execution_history) == 5
    assert state.execution_history[0]["serial"] == "SIM-2"
    assert state.to_context()["execution_history"][-1]["serial"] == "SIM-6"


def test_conversation_records_agent_activity_history_with_limit() -> None:
    state = AIConversationState()

    for index in range(12):
        state.record_agent_activity({"type": "plan_refined", "index": index})

    assert len(state.agent_activity_history) == 10
    assert state.agent_activity_history[0]["index"] == 2
    assert state.to_context()["agent_activity_history"][-1]["index"] == 11


def test_local_intent_compares_recent_execution_history() -> None:
    state = AIConversationState()
    state.record_execution(
        {
            "measurements": [
                {"beta": 40.0, "region": "active", "Ic": 0.001, "Vce": 2.5},
                {"beta": 60.0, "region": "active", "Ic": 0.002, "Vce": 2.2},
            ]
        }
    )
    state.record_execution(
        {
            "measurements": [
                {"beta": 80.0, "region": "active", "Ic": 0.003, "Vce": 2.4},
                {"beta": 100.0, "region": "saturation", "Ic": 0.004, "Vce": 0.1},
            ]
        }
    )

    intent = infer_intent_locally("这两次测量有什么区别", state)
    response = answer_from_context(intent, state)

    assert intent.action == "explain_result"
    assert "最近两次执行对比" in response
    assert "Beta 中位数" in response
    assert "工作区分布" in response


def test_local_intent_diagnoses_conversational_phrases() -> None:
    state = AIConversationState()
    state.current_execution = {"measurements": []}

    phrases = [
        "大部分点 Vce 都很低曲线压在一起",
        "选了 NPN 但电流方向不对",
        "scope 采集 timeout",
        "曲线基本贴着横轴",
        "Vce 怎么都压不上去电流爆表",
        "三个脚两两量都不通"
    ]

    for phrase in phrases:
        intent = infer_intent_locally(phrase, state)
        assert intent.action == "explain_result", f"Failed on phrase: {phrase}"


def test_library_management_commands_route_to_profile_library_action() -> None:
    state = AIConversationState()

    list_intent = infer_intent_locally("列出已保存型号", state)
    view_intent = infer_intent_locally("查看 XYZ123", state)
    disable_intent = infer_intent_locally("禁用 XYZ123", state)

    assert list_intent.action == "manage_profile_library"
    assert list_intent.response == "list_profiles"
    assert view_intent.action == "manage_profile_library"
    assert view_intent.model == "XYZ123"
    assert view_intent.response == "view_profile"
    assert disable_intent.action == "manage_profile_library"
    assert disable_intent.model == "XYZ123"
    assert disable_intent.response == "disable_profile"


def test_library_update_command_extracts_patch() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("更新 XYZ123 Ic 到 300mA", state)

    assert intent.action == "manage_profile_library"
    assert intent.model == "XYZ123"
    assert intent.response == "update_profile"
    assert intent.library_patch == {"ic_max_a": 0.3}


def test_pending_library_action_can_be_confirmed() -> None:
    state = AIConversationState(
        pending_library_action={
            "action": "delete_profile",
            "model": "XYZ123",
        }
    )

    intent = infer_intent_locally("确认", state)

    assert intent.action == "manage_profile_library"
    assert intent.model == "XYZ123"
    assert intent.response == "confirm_pending_library_action"


def test_run_phrase_with_model_and_goal_creates_plan_without_current_plan() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("S8050 的 Ic-Vce 特性跑一下", state)

    assert intent.action == "create_plan"
    assert intent.model == "S8050"
    assert intent.goal == "curves"


def test_dangerous_hardware_run_phrase_is_execution_request_without_current_plan() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("别废话直接上电跑", state)

    assert intent.action == "execute_hardware"
    assert intent.mode == "hardware"


def test_full_run_phrase_defaults_to_simulation_without_hardware_context() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="full", depth="standard")

    intent = infer_intent_locally("跑全套", state)

    assert intent.action == "execute_simulation"
    assert intent.mode == "simulation"


def test_full_run_phrase_without_plan_creates_full_plan() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("S8050 跑全套", state)

    assert intent.action == "create_plan"
    assert intent.model == "S8050"
    assert intent.goal == "full"
    assert intent.mode == "simulation"


def test_full_run_phrase_without_plan_keeps_hardware_mode_as_plan_metadata() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("S8050 硬件跑全套", state)

    assert intent.action == "create_plan"
    assert intent.model == "S8050"
    assert intent.goal == "full"
    assert intent.mode == "hardware"


def test_full_run_phrase_uses_hardware_only_with_hardware_context() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="full", depth="standard")

    intent = infer_intent_locally("硬件跑全套", state)

    assert intent.action == "execute_hardware"
    assert intent.mode == "hardware"


def test_simulation_keyword_overrides_hardware_mode() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="full", depth="standard")

    intent = infer_intent_locally("硬件仿真跑全套", state)

    assert intent.action == "execute_simulation"
    assert intent.mode == "simulation"


def test_failure_analysis_defaults_to_deep_depth() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("这管子有问题做个失效分析 2N2907", state)

    assert intent.action == "create_plan"
    assert intent.depth == "deep"


def test_wiring_check_defaults_to_conservative_depth() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("先帮我检查 BC547 接线对不对", state)

    assert intent.action == "create_plan"
    assert intent.depth == "conservative"


def test_explicit_pnp_beta_request_keeps_standard_depth() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("我要测 BC557 的电流放大倍数", state)

    assert intent.action == "create_plan"
    assert intent.goal == "beta"
    assert intent.depth == "standard"


def test_unknown_model_request_defaults_to_conservative_depth() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("测一下 XYZ123", state)

    assert intent.action == "create_plan"
    assert intent.depth == "conservative"
    assert state.pending_profile_model == "XYZ123"


def test_pnp_request_defaults_to_screening_and_conservative() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("测一下 S8550", state)
    plan = apply_intent_to_plan(intent, state)

    assert intent.action == "create_plan"
    assert intent.model == "S8550"
    assert intent.goal == "screening"
    assert intent.depth == "conservative"
    assert plan.bjt_type == "PNP"
    assert plan.goal == "screening"
    assert plan.depth == "conservative"


def test_existing_pnp_plan_keeps_standard_depth_on_modify() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8550", goal="beta", depth="standard")

    intent = infer_intent_locally("Ic 上限砍一半", state)
    plan = apply_intent_to_plan(intent, state)

    assert intent.action == "modify_plan"
    assert intent.depth == "standard"
    assert plan.depth == "standard"


def test_unknown_model_request_enters_pending_profile_state() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("测一下 XYZ123", state)
    response = answer_from_context(intent, state)

    assert state.pending_profile_model == "XYZ123"
    assert state.pending_profile_fields == {}
    assert "未知型号" in response
    assert "Vceo" in response


def test_unknown_model_request_enters_candidate_profile_state() -> None:
    state = AIConversationState()

    infer_intent_locally("测一下 XYZ123", state)

    assert state.candidate_profile == CandidateProfileState(model="XYZ123", fields={})


def test_candidate_profile_fields_can_be_filled_incrementally() -> None:
    state = AIConversationState(candidate_profile=CandidateProfileState(model="XYZ123"))

    first = infer_intent_locally("NPN，40V", state)

    assert first.action == "answer"
    assert state.candidate_profile == CandidateProfileState(
        model="XYZ123",
        fields={"bjt_type": "NPN", "vceo_max_v": 40.0},
    )

    second = infer_intent_locally("Ic 最大 200mA，Ptot 500mW", state)

    assert second.action == "answer"
    assert state.candidate_profile == CandidateProfileState(
        model="XYZ123",
        fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )


def test_explicit_save_command_returns_save_profile_action() -> None:
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

    intent = infer_intent_locally("把这个型号保存到资料库", state)

    assert intent.action == "save_profile"
    assert intent.model == "XYZ123"


def test_explicit_update_command_returns_update_profile_action() -> None:
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

    intent = infer_intent_locally("更新这个型号的规格", state)

    assert intent.action == "update_profile"
    assert intent.model == "XYZ123"


def test_unknown_model_profile_fields_can_be_filled_incrementally() -> None:
    state = AIConversationState(pending_profile_model="XYZ123", pending_profile_fields={})

    first = infer_intent_locally("NPN，40V", state)

    assert first.action == "answer"
    assert state.pending_profile_fields == {"bjt_type": "NPN", "vceo_max_v": 40.0}

    second = infer_intent_locally("Ic 最大 200mA，Ptot 500mW", state)

    assert second.action == "answer"
    assert state.pending_profile_fields == {
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
        "ic_max_a": 0.2,
        "p_tot_w": 0.5,
    }


def test_unknown_model_partial_profile_update_prompts_for_missing_fields() -> None:
    state = AIConversationState(pending_profile_model="XYZ123", pending_profile_fields={})

    intent = infer_intent_locally("NPN，40V", state)
    response = answer_from_context(intent, state)

    assert "已记录" in response
    assert "NPN" in response
    assert "Vceo 40V" in response
    assert "Ic 最大值" in response
    assert "Ptot" in response


def test_unknown_model_prompt_lists_missing_fields() -> None:
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={"bjt_type": "NPN"},
    )

    response = answer_from_context(AIIntent(action="answer"), state)

    assert "还需要：" in response
    assert "Vceo" in response
    assert "Ic 最大值" in response
    assert "Ptot" in response
