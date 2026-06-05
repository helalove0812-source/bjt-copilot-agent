from __future__ import annotations

import json

from ai.conversation import AIConversationState, interpret_user_message_with_debug
from ai.prompt_layers import PromptLayers, make_volatile
from ai.test_planner import build_test_plan
from ai.tool_call_agent import ToolCallingAgent


def test_prompt_layers_render_stable_in_system_and_dynamic_layers_in_user() -> None:
    layers = PromptLayers(
        stable={"identity": "stable role"},
        context={"file": "context.json"},
        volatile=make_volatile(user_message="测试 S8050"),
    )

    system_text = layers.system_text()
    user_payload = json.loads(layers.user_text())

    assert system_text.startswith("<stable>")
    assert "stable role" in system_text
    assert user_payload["prompt_layers"]["context"] == {"file": "context.json"}
    assert user_payload["prompt_layers"]["volatile"]["user_message"] == "测试 S8050"
    assert "timestamp_utc" in user_payload["prompt_layers"]["volatile"]


def test_conversation_cloud_intent_uses_layered_prompt(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResult:
        provider = "deepseek"
        model = "intent-model"
        usage = {"total_tokens": 3}
        text = '{"action":"create_plan","model":"S8050","goal":"beta","depth":"standard","response":"创建计划。"}'

    def fake_chat_text(*, system_text: str, user_text: str, **_kwargs):
        captured["system_text"] = system_text
        captured["user_text"] = user_text
        return FakeResult()

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.conversation.chat_text", fake_chat_text)

    intent, used_ai, provider, usage, _debug = interpret_user_message_with_debug(
        "给我 S8050 的测试方案",
        AIConversationState(),
    )

    user_payload = json.loads(captured["user_text"])
    assert intent.action == "create_plan"
    assert used_ai is True
    assert provider == "deepseek:intent-model"
    assert usage["total_tokens"] == 3
    assert captured["system_text"].startswith("<stable>")
    assert "上下文意图解析器" in captured["system_text"]
    assert user_payload["prompt_layers"]["context"]["default_mode"] == "simulation"
    assert user_payload["prompt_layers"]["volatile"]["user_message"] == "给我 S8050 的测试方案"


def test_tool_call_agent_cloud_decision_uses_layered_prompt(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResult:
        provider = "deepseek"
        model = "tool-model"
        usage = {"total_tokens": 5}
        text = '{"action":"final","response":"好的。","next_actions":[]}'

    def fake_chat_text(*, system_text: str, user_text: str, **_kwargs):
        captured["system_text"] = system_text
        captured["user_text"] = user_text
        return FakeResult()

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.tool_call_agent.chat_text", fake_chat_text)
    plan = build_test_plan(model="S8050", goal="full", depth="deep", mode="simulation")

    result = ToolCallingAgent(context={"current_plan": plan.to_dict()}).run_turn("下一步怎么做", mode="simulation")

    user_payload = json.loads(captured["user_text"])
    assert result.response == "好的。"
    assert result.used_ai_api is True
    assert captured["system_text"].startswith("<stable>")
    assert "tool-calling agent" in captured["system_text"]
    assert user_payload["prompt_layers"]["context"]["current_plan"]["model"] == "S8050"
    assert user_payload["prompt_layers"]["context"]["available_tools"]
    assert user_payload["prompt_layers"]["volatile"]["user_message"] == "下一步怎么做"
