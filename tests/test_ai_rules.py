from __future__ import annotations

from ai.diagnosis_engine import diagnose_observation, summarize_diagnosis
from ai.rules import diagnose_context, infer_rule_decision


def test_rule_understands_quick_screening() -> None:
    decision = infer_rule_decision("给我快速验一下这个 S8050，不要烧管")

    assert decision.goal == "screening"
    assert decision.depth == "conservative"


def test_rule_understands_batch_pass_fail() -> None:
    decision = infer_rule_decision("批量筛选 S8050，beta 低于 100 判不合格")

    assert decision.goal == "screening"


def test_rule_understands_vce_sat_and_limits() -> None:
    decision = infer_rule_decision("重点看饱和压降，Ic 不超过 10mA，功耗 80mW")

    assert decision.goal == "vce_sat"
    assert decision.ic_limit_a == 0.01
    assert decision.power_limit_w == 0.08


def test_rule_understands_curve_and_vcc_range() -> None:
    decision = infer_rule_decision("画 Ic-Vce 曲线，Vcc 最高 3V，加密到 12 个点")

    assert decision.goal == "curves"
    assert decision.vcc_max == 3.0
    assert decision.vbb_points == 12


def test_diagnosis_engine_returns_tags_without_action_labels() -> None:
    result = diagnose_observation(
        text="Vce 怎么都压不上去电流爆表",
        logs=[],
        measurements=[{"Ic": 0.03, "Vce": 0.1, "region": "saturation"}],
    )

    assert "overcurrent" in result.tags
    assert "short_circuit" in result.tags
    assert "clamp_current" not in result.tags


def test_diagnosis_engine_summary_explains_observation_only() -> None:
    result = diagnose_observation(
        text="三个脚两两量都不通",
        logs=[],
        measurements=[],
    )

    summary = summarize_diagnosis(result)

    assert "开路" in summary
    assert "建议下一步" not in summary


def test_diagnose_open_overcurrent_and_saturation() -> None:
    text = diagnose_context(
        "诊断一下",
        logs=["未检测到器件接入 (开路)", "Ic 过流"],
        measurements=[
            {"beta": 20.0, "region": "saturation"},
            {"beta": 22.0, "region": "saturation"},
        ],
    )

    assert "疑似开路" in text
    assert "过流保护" in text
    assert "多数点处于饱和区" in text
    assert "建议下一步" not in text
