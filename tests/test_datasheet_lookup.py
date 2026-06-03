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


def test_lookup_datasheet_profile_merges_partial_llm_output_with_heuristic(monkeypatch) -> None:
    class FakeResult:
        provider = "deepseek"
        model = "deepseek-test"
        usage = {"total_tokens": 64}
        text = json.dumps(
            {
                "model": "C1815",
                "bjt_type": "NPN",
                "description": "Audio frequency amplifier transistor",
                "vceo_max_v": "50V",
                "ic_max_a": None,
                "p_tot_w": "400mW",
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
                title="2SC1815 Datasheet NPN TO-92",
                url="https://example.test/c1815",
                snippet="VCEO 50V Collector Current Ic 150mA Power Dissipation 400mW hFE 70-700 ECB pinout",
            )
        ],
    )

    assert result.ok is True
    assert result.used_llm_api is True
    assert result.profile is not None
    assert result.profile.vceo_max_v == 50.0
    assert result.profile.ic_max_a == 0.15
    assert result.profile.p_tot_w == 0.4
    assert "ECB" in result.profile.pinout_hint


def test_lookup_datasheet_profile_retries_with_expanded_results(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise LLMUnavailable("no key")

    calls: list[tuple[str, int]] = []

    def fake_search(query: str, limit: int) -> list[DatasheetSearchResult]:
        calls.append((query, limit))
        if limit <= 3:
            return [
                DatasheetSearchResult(
                    title="C1815 transistor overview",
                    url="https://example.test/1",
                    snippet="NPN transistor with VCEO 50V in TO-92 package",
                )
            ]
        if "power dissipation" in query:
            return [
                DatasheetSearchResult(
                    title="C1815 ratings and dissipation",
                    url="https://example.test/2",
                    snippet="Total Device Dissipation 400mW hFE 70-700",
                )
            ]
        return [
            DatasheetSearchResult(
                title="C1815 transistor overview",
                url="https://example.test/1",
                snippet="NPN transistor with VCEO 50V in TO-92 package",
            ),
            DatasheetSearchResult(
                title="C1815 current rating",
                url="https://example.test/3",
                snippet="Maximum Collector Current Ic 150mA",
            ),
        ]

    monkeypatch.setattr("ai.datasheet_lookup.chat_text", unavailable)

    result = lookup_datasheet_profile("C1815", limit=3, search_fn=fake_search)

    assert result.ok is True
    assert result.used_llm_api is False
    assert result.profile is not None
    assert result.profile.vceo_max_v == 50.0
    assert result.profile.ic_max_a == 0.15
    assert result.profile.p_tot_w == 0.4
    assert any(limit == 8 for _, limit in calls)
    assert any("power dissipation" in query for query, _ in calls)
    assert result.debug is not None
    assert result.debug["initial_result_count"] == 1
    assert result.debug["expanded_lookup_attempted"] is True
    assert result.debug["expanded_result_count"] >= 2
