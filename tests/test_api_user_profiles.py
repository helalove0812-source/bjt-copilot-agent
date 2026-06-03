from __future__ import annotations

import json
import os
from pathlib import Path

import api_server


class FakeHandler:
    def __init__(self, payload: dict | None = None, *, path: str = "/api/user-profiles") -> None:
        self.payload = payload or {}
        self.path = path
        self.sent_status: int | None = None
        self.sent_payload: dict | None = None

    def _read_payload(self) -> dict:
        return dict(self.payload)

    def _send_json(self, status: int, payload: dict) -> None:
        self.sent_status = status
        self.sent_payload = json.loads(json.dumps(payload, ensure_ascii=False))

    def _user_profile_store_path(self) -> Path:
        return Path(os.environ["BJT_USER_PROFILE_STORE"])


def _call(handler_method: str, payload: dict | None = None, *, path: str = "/api/user-profiles") -> tuple[int, dict]:
    handler = FakeHandler(payload, path=path)
    getattr(api_server.ApiHandler, handler_method)(handler)
    assert handler.sent_status is not None
    assert handler.sent_payload is not None
    return handler.sent_status, handler.sent_payload


def test_list_user_profiles_returns_saved_items(monkeypatch, tmp_path) -> None:
    store = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))
    _call(
        "_handle_user_profiles_create",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    status, result = _call("_handle_user_profiles_list")

    assert status == 200
    assert result["ok"] is True
    assert result["items"][0]["model"] == "XYZ123"


def test_create_user_profile_returns_created_record(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))

    status, result = _call(
        "_handle_user_profiles_create",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    assert status == 200
    assert result["ok"] is True
    assert result["record"]["model"] == "XYZ123"
    assert result["record"]["enabled"] is True


def test_update_user_profile_requires_confirmation_for_critical_change(monkeypatch, tmp_path) -> None:
    store = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))
    _call(
        "_handle_user_profiles_create",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    status, result = _call(
        "_handle_user_profiles_update",
        {"model": "XYZ123", "patch": {"ic_max_a": 0.3}, "confirm_critical": False},
    )

    assert status == 200
    assert result["ok"] is True
    assert result["status"] == "confirmation_required"
    assert result["critical_changes"] == [
        {"field": "ic_max_a", "old": 0.2, "new": 0.3}
    ]


def test_toggle_user_profile_enabled_updates_enabled_flag(monkeypatch, tmp_path) -> None:
    store = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))
    _call(
        "_handle_user_profiles_create",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    status, result = _call(
        "_handle_user_profiles_toggle_enabled",
        {"model": "XYZ123", "enabled": False},
    )

    assert status == 200
    assert result["ok"] is True
    assert result["record"]["enabled"] is False


def test_delete_user_profile_removes_record(monkeypatch, tmp_path) -> None:
    store = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))
    _call(
        "_handle_user_profiles_create",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    status, result = _call("_handle_user_profiles_delete", {"model": "XYZ123"})

    assert status == 200
    assert result["ok"] is True
    assert result["deleted"] == "XYZ123"

    status, result = _call("_handle_user_profiles_list")
    assert status == 200
    assert result["items"] == []
