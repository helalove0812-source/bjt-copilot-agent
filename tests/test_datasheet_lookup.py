from __future__ import annotations

import json

from ai.datasheet_lookup import DatasheetSearchResult, lookup_datasheet_profile
from ai.llm_client import LLMUnavailable


def test_lookup_datasheet_profile_extracts_profile_with_llm(monkeypatch) -> None:
    class FakeResult:
        provider = "deepseek"
        model = "deepseek-test"
        usage = {"total_tokens": 42}
        text = json.dumps(
            {
                "model": "C1815",
                "bjt_type": "NPN",
                "description": "Audio frequency amplifier transistor",
                "vceo_max_v": 50,
                "ic_max_a": 0.15,
                "p_tot_w": 0.4,
                "hfe_typical": [70, 700],
                "package": "TO-92",
                "pinout_hint": "Check ECB pinout by manufacturer.",
                "confidence": "high",
            }
        )

    monkeypatch.setattr("ai.datasheet_lookup.chat_text", lambda *args, **kwargs: FakeResult())

    result = lookup_datasheet_profile(
        "C1815",
        search_fn=lambda query, limit: [
            DatasheetSearchResult(
                title="2SC1815 Datasheet",
                url="https://example.test/c1815.pdf",
                snippet="NPN VCEO 50V Ic 150mA Ptot 400mW hFE 70-700 TO-92",
            )
        ],
    )

    assert result.ok is True
    assert result.used_llm_api is True
    assert result.llm_provider == "deepseek:deepseek-test"
    assert result.profile is not None
    assert result.profile.model == "C1815"
    assert result.profile.bjt_type == "NPN"
    assert result.profile.vceo_max_v == 50.0
    assert result.profile.ic_max_a == 0.15
    assert result.profile.p_tot_w == 0.4
    assert result.profile.confidence == "datasheet_lookup"


def test_lookup_datasheet_profile_falls_back_to_heuristic(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise LLMUnavailable("no key")

    monkeypatch.setattr("ai.datasheet_lookup.chat_text", unavailable)

    result = lookup_datasheet_profile(
        "C1815",
        search_fn=lambda query, limit: [
            DatasheetSearchResult(
                title="2SC1815 Datasheet NPN TO-92",
                url="https://example.test/c1815",
                snippet="VCEO 50V Collector Current Ic 150mA Power Dissipation 400mW hFE 70-700",
            )
        ],
    )

    assert result.ok is True
    assert result.used_llm_api is False
    assert result.confidence == "low"
    assert result.profile is not None
    assert result.profile.model == "C1815"
    assert result.profile.ic_max_a == 0.15
