from __future__ import annotations

from ai.assistant import local_plan_summary, summarize_plan_with_ai
from ai.test_planner import build_test_plan


def test_local_plan_summary_includes_profile_basis() -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    summary = local_plan_summary(plan)

    assert "资料依据" in summary
    assert "Vceo" in summary
    assert "Ic 最大" in summary
    assert "Ptot" in summary
    assert "hFE" in summary
    assert "引脚" in summary


def test_cloud_plan_summary_prompt_allows_guarded_relaxation(monkeypatch) -> None:
    captured = {}

    class FakeResult:
        provider = "deepseek"
        model = "chat-model"
        usage = {}
        text = "已在 SafetyGuard 允许范围内适度放宽。"

    def fake_chat(*, system_text: str, user_text: str):
        captured["system_text"] = system_text
        captured["user_text"] = user_text
        return FakeResult()

    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.setattr("ai.assistant.chat_text", fake_chat)
    plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    text, used_ai, provider, _usage = summarize_plan_with_ai(plan, "安全限制不要那么死")

    assert used_ai is True
    assert provider == "deepseek:chat-model"
    assert text == "已在 SafetyGuard 允许范围内适度放宽。"
    assert "适度放宽" in captured["system_text"]
    assert "不要说“不会放宽”" in captured["system_text"]
    assert "安全限制不要那么死" in captured["user_text"]
