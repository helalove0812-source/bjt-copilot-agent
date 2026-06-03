from __future__ import annotations

from ai.action_taxonomy import action_item


_DIAGNOSIS_ACTIONS: dict[str, list[str]] = {
    "bce_reversed": ["check_wiring", "prompt_pinout_confirm"],
    "wrong_polarity": ["check_wiring", "prompt_pinout_confirm"],
    "overcurrent": ["clamp_current", "explain_limit"],
    "power_exceeded": ["clamp_power", "explain_limit"],
    "mostly_saturation": ["modify_plan", "suggest_next_step"],
    "mostly_cutoff": ["modify_plan", "suggest_next_step"],
    "low_beta": ["suggest_failure_analysis"],
    "beta_unstable": ["increase_averaging", "check_wiring"],
}


def recommend_actions(*, diagnosis_tags: list[str]) -> list[dict]:
    actions: list[str] = []
    for tag in diagnosis_tags:
        actions.extend(_DIAGNOSIS_ACTIONS.get(tag, []))
    return [action_item(action) for action in dict.fromkeys(actions)]
