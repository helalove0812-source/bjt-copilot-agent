from __future__ import annotations

from ai.experiment_summary import summarize_experiment_records
from ai.tool_call_agent import ToolCallingAgent


def test_experiment_summary_includes_model_card_and_residual_change(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    result = ToolCallingAgent().run_turn("表征 S8050 并生成 SPICE 数字孪生模型，然后根据残差执行补测", mode="simulation")

    assert "自适应表征已完成" in result.response
    assert "SPICE 数字孪生已生成" in result.response
    assert "已执行残差补测" in result.response
    assert "模型残差变化" in result.response
    assert "```spice" in result.response
    assert ".model DUT_S8050 NPN" in result.response


def test_experiment_summary_returns_empty_for_non_experiment_records() -> None:
    text = summarize_experiment_records(
        [
            {
                "name": "lookup_transistor",
                "arguments": {"model": "S8050"},
                "result": {"ok": True, "profile": {"model": "S8050"}},
            }
        ]
    )

    assert text == ""
