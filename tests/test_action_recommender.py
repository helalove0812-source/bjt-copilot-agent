from __future__ import annotations

from ai.action_recommender import recommend_actions


def test_recommend_actions_maps_diagnosis_tags_to_structured_items() -> None:
    items = recommend_actions(diagnosis_tags=["bce_reversed", "overcurrent"])

    assert [item["action"] for item in items] == [
        "check_wiring",
        "prompt_pinout_confirm",
        "clamp_current",
        "explain_limit",
    ]
    assert all("id" in item for item in items)
    assert all("label" in item for item in items)
    assert all("kind" in item for item in items)
    assert all("priority" in item for item in items)


def test_recommend_actions_maps_beta_unstable_to_measurement_followups() -> None:
    items = recommend_actions(diagnosis_tags=["beta_unstable"])

    assert [item["action"] for item in items] == ["increase_averaging", "check_wiring"]
