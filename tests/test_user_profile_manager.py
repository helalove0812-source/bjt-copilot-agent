from __future__ import annotations

from pathlib import Path

import pytest

from ai.transistor_db import lookup_transistor
from ai.user_profile_store import (
    create_user_profile,
    delete_user_profile,
    get_user_profile_record,
    list_user_profiles,
    search_user_profiles,
    toggle_user_profile_enabled,
    update_user_profile_record,
)


def _payload(model: str = "XYZ123", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
        "ic_max_a": 0.2,
        "p_tot_w": 0.5,
        "enabled": True,
        "source": "user_confirmed",
        "notes": "",
    }
    payload.update(overrides)
    return payload


def test_list_user_profiles_returns_metadata_and_enabled_flag(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload())

    items = list_user_profiles(store)

    assert len(items) == 1
    assert items[0]["model"] == "XYZ123"
    assert items[0]["enabled"] is True
    assert items[0]["source"] == "user_confirmed"


def test_search_user_profiles_filters_by_model_fragment(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload(model="XYZ123"))
    create_user_profile(store, _payload(model="ABC999", bjt_type="PNP"))

    items = search_user_profiles(store, "xyz")

    assert [item["model"] for item in items] == ["XYZ123"]


def test_toggle_user_profile_enabled_changes_runtime_flag(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload())

    record = toggle_user_profile_enabled(store, "XYZ123", enabled=False)

    assert record["enabled"] is False
    assert get_user_profile_record(store, "XYZ123")["enabled"] is False


def test_update_user_profile_record_requires_confirmation_for_critical_changes(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload())

    result = update_user_profile_record(
        store,
        "XYZ123",
        {"ic_max_a": 0.3},
        require_confirmation=False,
    )

    assert result["status"] == "confirmation_required"
    assert result["critical_changes"] == [
        {"field": "ic_max_a", "old": 0.2, "new": 0.3}
    ]


def test_update_user_profile_record_applies_confirmed_critical_changes(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload())

    result = update_user_profile_record(
        store,
        "XYZ123",
        {"ic_max_a": 0.3},
        require_confirmation=True,
    )

    assert result["status"] == "updated"
    assert result["record"]["ic_max_a"] == 0.3


def test_delete_user_profile_removes_existing_record(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload())

    delete_user_profile(store, "XYZ123")

    assert list_user_profiles(store) == []


def test_lookup_transistor_ignores_disabled_user_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, _payload(enabled=False))
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))

    profile = lookup_transistor("XYZ123")

    assert profile.confidence == "fallback"
