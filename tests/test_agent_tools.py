from __future__ import annotations

from dataclasses import replace

from ai.agent_orchestration import orchestrate_turn_with_llm
from ai.agent_step_review import AgentStepReview
from ai.agent import TestAgent
from ai.agent_tools import default_agent_tools
from ai.conversation import AIConversationState, AIIntent


def test_default_agent_tools_expose_clear_layers() -> None:
    tools = default_agent_tools()

    descriptors = tools.describe()
    names = {item.name for item in descriptors}
    layers = {item.layer for item in descriptors}

    assert {
        "orchestrate_turn",
        "review_step",
        "interpret_intent",
        "apply_intent_to_plan",
        "lookup_datasheet_profile",
        "evaluate_execution_request",
        "execute_plan",
        "diagnose_tags",
        "recommend_actions",
    }.issubset(names)
    assert {
        "orchestration",
        "cognition",
        "planning",
        "knowledge",
        "safety",
        "execution",
        "diagnosis",
        "actions",
    }.issubset(layers)


def test_agent_uses_injected_tool_registry_for_plan_summary(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    calls = {}
    tools = replace(
        default_agent_tools(),
        summarize_plan=lambda plan, text: (
            calls.setdefault("summary", f"{plan.model}:{text}"),
            False,
            "local",
            {},
        ),
    )

    result = TestAgent(tools=tools).run_turn("测 S8050 beta")

    assert calls["summary"] == "S8050:测 S8050 beta"
    assert result.response == "S8050:测 S8050 beta"


def test_local_orchestration_exposes_tool_path(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    tools = default_agent_tools()
    plan, used_ai, provider, usage = orchestrate_turn_with_llm(
        "开始硬件执行",
        AIConversationState(),
        intent=AIIntent(action="execute_hardware"),
        tools=tools,
        default_mode="hardware",
    )

    assert used_ai is False
    assert provider == "local"
    assert usage == {}
    assert "evaluate_execution_request" in plan.selected_tools
    assert plan.requires_hardware_confirmation is True


def test_agent_merges_llm_orchestration_trace(monkeypatch) -> None:
    class FakeResult:
        provider = "deepseek"
        model = "orchestrator-model"
        usage = {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
        text = """
        {
          "selected_tools": ["interpret_intent", "apply_intent_to_plan", "missing_tool", "summarize_plan"],
          "tool_sequence": ["解析意图", "生成计划", "总结计划"],
          "evidence_summary": "用户要求测试 S8050 beta。",
          "risk_notes": ["先仿真再硬件。"],
          "requires_hardware_confirmation": false
        }
        """

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.agent_orchestration.chat_text", lambda *args, **kwargs: FakeResult())
    tools = replace(
        default_agent_tools(),
        interpret_intent=lambda text, state, default_mode="simulation": (
            AIIntent(action="create_plan", model="S8050", goal="beta", mode=default_mode),
            False,
            "local",
            {},
            {"final_source": "test"},
        ),
        summarize_plan=lambda plan, text: ("计划摘要", False, "local", {}),
        review_step=lambda **kwargs: (
            AgentStepReview(step=kwargs["step"], observation="reviewed:" + kwargs["step"]),
            True,
            "deepseek:review-model",
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        ),
    )

    result = TestAgent(tools=tools).run_turn("测 S8050 beta")

    assert result.used_ai_api is True
    assert result.llm_provider == "deepseek:orchestrator-model,deepseek:review-model"
    assert result.llm_usage == {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9}
    assert result.orchestration["selected_tools"] == ["interpret_intent", "apply_intent_to_plan", "summarize_plan"]
    assert result.intent_debug["orchestration"]["evidence_summary"] == "用户要求测试 S8050 beta。"
    assert [item["step"] for item in result.orchestration["step_reviews"]] == ["intent", "planning", "next_actions"]
