from pathlib import Path

import pytest

from ai.transistor_db import TransistorProfile, lookup_transistor
from ai.user_profile_store import (
    DuplicateUserProfileError,
    InvalidUserProfileStoreError,
    load_user_profiles,
    save_user_profile,
    update_user_profile,
)


def _profile(model: str = "XYZ123", *, vceo_max_v: float = 40.0) -> TransistorProfile:
    return TransistorProfile(
        model=model,
        bjt_type="NPN",
        description="用户确认沉淀的型号参数",
        vceo_max_v=vceo_max_v,
        ic_max_a=0.2,
        p_tot_w=0.5,
        hfe_typical=(0, 0),
        confidence="user_confirmed",
    )


def test_load_user_profiles_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_user_profiles(tmp_path / "missing.json") == {}


def test_save_user_profile_persists_profile(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"

    save_user_profile(store_path, _profile())

    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].confidence == "user_confirmed"
    assert loaded["XYZ123"].bjt_type == "NPN"


def test_save_user_profile_rejects_duplicate_without_update(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(store_path, _profile())

    with pytest.raises(DuplicateUserProfileError):
        save_user_profile(store_path, _profile())


def test_update_user_profile_overwrites_existing_entry(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(store_path, _profile())

    update_user_profile(store_path, _profile(vceo_max_v=45.0))

    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].vceo_max_v == 45.0


def test_load_user_profiles_raises_clear_error_for_invalid_json(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    store_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(InvalidUserProfileStoreError, match="profiles.json"):
        load_user_profiles(store_path)


def test_lookup_transistor_prefers_user_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(store_path, _profile(vceo_max_v=55.0))
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))

    profile = lookup_transistor("XYZ123")

    assert profile.confidence == "user_confirmed"
    assert profile.vceo_max_v == 55.0
