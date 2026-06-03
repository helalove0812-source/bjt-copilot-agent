from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from ai.transistor_db import TransistorProfile, normalize_model_name


class InvalidUserProfileStoreError(RuntimeError):
    pass


class DuplicateUserProfileError(RuntimeError):
    pass


class UserProfileNotFoundError(RuntimeError):
    pass


CRITICAL_PROFILE_FIELDS = {"bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"}


def _profile_from_mapping(data: Mapping[str, object]) -> TransistorProfile:
    hfe_typical = data.get("hfe_typical", [0, 0])
    if not isinstance(hfe_typical, (list, tuple)) or len(hfe_typical) != 2:
        hfe_typical = [0, 0]

    return TransistorProfile(
        model=str(data["model"]),
        bjt_type=str(data["bjt_type"]).upper(),
        description=str(data.get("description", "用户确认沉淀的型号参数")),
        vceo_max_v=float(data["vceo_max_v"]),
        ic_max_a=float(data["ic_max_a"]),
        p_tot_w=float(data["p_tot_w"]),
        hfe_typical=(int(hfe_typical[0]), int(hfe_typical[1])),
        package=str(data.get("package", "")),
        pinout_hint=str(data.get("pinout_hint", "")),
        confidence=str(data.get("confidence", "user_confirmed")),
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_raw_profiles(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidUserProfileStoreError(f"invalid user profile store: {path}") from exc

    if not isinstance(payload, dict):
        raise InvalidUserProfileStoreError(f"invalid user profile store: {path}")

    profiles: dict[str, dict[str, object]] = {}
    for model, raw_profile in payload.items():
        if not isinstance(raw_profile, Mapping):
            continue
        key = normalize_model_name(str(model))
        record = dict(raw_profile)
        record.setdefault("model", str(model))
        record.setdefault("enabled", True)
        record.setdefault("notes", "")
        record.setdefault("source", "user_confirmed")
        record.setdefault("confirmed_by_user", True)
        record.setdefault("created_at", _timestamp())
        record.setdefault("updated_at", record["created_at"])
        profiles[key] = record
    return profiles


def load_user_profiles(path: Path) -> dict[str, TransistorProfile]:
    return {
        key: _profile_from_mapping(record)
        for key, record in _load_raw_profiles(path).items()
    }


def _write_raw_profiles(path: Path, profiles: Mapping[str, Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    for key, record in profiles.items():
        payload[key] = dict(record)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def save_user_profile(path: Path, profile: TransistorProfile) -> None:
    profiles = _load_raw_profiles(path)
    key = normalize_model_name(profile.model)
    if key in profiles:
        raise DuplicateUserProfileError(profile.model)
    record = asdict(profile)
    record["hfe_typical"] = list(profile.hfe_typical)
    record.setdefault("enabled", True)
    record.setdefault("notes", "")
    record.setdefault("source", "user_confirmed")
    record.setdefault("confirmed_by_user", True)
    record.setdefault("created_at", _timestamp())
    record.setdefault("updated_at", record["created_at"])
    profiles[key] = record
    _write_raw_profiles(path, profiles)


def update_user_profile(path: Path, profile: TransistorProfile) -> None:
    profiles = _load_raw_profiles(path)
    key = normalize_model_name(profile.model)
    record = asdict(profile)
    record["hfe_typical"] = list(profile.hfe_typical)
    existing = profiles.get(key, {})
    record["enabled"] = bool(existing.get("enabled", True))
    record["notes"] = str(existing.get("notes", ""))
    record["source"] = str(existing.get("source", "manual_edit"))
    record["confirmed_by_user"] = bool(existing.get("confirmed_by_user", True))
    record["created_at"] = str(existing.get("created_at", _timestamp()))
    record["updated_at"] = _timestamp()
    profiles[key] = record
    _write_raw_profiles(path, profiles)


def _validate_payload(payload: Mapping[str, object], *, model_override: str | None = None) -> dict[str, object]:
    model = str(model_override or payload.get("model") or "").strip()
    if not model:
        raise ValueError("model is required")
    bjt_type = str(payload.get("bjt_type") or "").upper()
    if bjt_type not in {"NPN", "PNP"}:
        raise ValueError("bjt_type must be NPN or PNP")
    vceo_max_v = float(payload.get("vceo_max_v") or 0.0)
    ic_max_a = float(payload.get("ic_max_a") or 0.0)
    p_tot_w = float(payload.get("p_tot_w") or 0.0)
    if vceo_max_v <= 0 or ic_max_a <= 0 or p_tot_w <= 0:
        raise ValueError("rating fields must be positive")
    return {
        "model": model,
        "bjt_type": bjt_type,
        "vceo_max_v": vceo_max_v,
        "ic_max_a": ic_max_a,
        "p_tot_w": p_tot_w,
        "package": str(payload.get("package") or ""),
        "pinout_hint": str(payload.get("pinout_hint") or ""),
        "description": str(payload.get("description") or "用户确认沉淀的型号参数"),
        "hfe_typical": list(payload.get("hfe_typical") or [0, 0]),
        "confidence": str(payload.get("confidence") or "user_confirmed"),
        "source": str(payload.get("source") or "user_confirmed"),
        "notes": str(payload.get("notes") or ""),
        "enabled": bool(payload.get("enabled", True)),
        "confirmed_by_user": bool(payload.get("confirmed_by_user", True)),
    }


def list_user_profiles(path: Path, *, enabled_only: bool = False) -> list[dict[str, object]]:
    items = []
    for record in _load_raw_profiles(path).values():
        if enabled_only and not bool(record.get("enabled", True)):
            continue
        items.append(dict(record))
    return sorted(items, key=lambda item: str(item.get("model", "")))


def search_user_profiles(path: Path, query: str, *, enabled_only: bool = False) -> list[dict[str, object]]:
    needle = normalize_model_name(query)
    if not needle:
        return list_user_profiles(path, enabled_only=enabled_only)
    return [
        item
        for item in list_user_profiles(path, enabled_only=enabled_only)
        if needle in normalize_model_name(str(item.get("model", "")))
    ]


def get_user_profile_record(path: Path, model: str) -> dict[str, object]:
    key = normalize_model_name(model)
    profiles = _load_raw_profiles(path)
    if key not in profiles:
        raise UserProfileNotFoundError(model)
    return dict(profiles[key])


def create_user_profile(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    record = _validate_payload(payload)
    profiles = _load_raw_profiles(path)
    key = normalize_model_name(str(record["model"]))
    if key in profiles:
        raise DuplicateUserProfileError(str(record["model"]))
    now = _timestamp()
    record["created_at"] = now
    record["updated_at"] = now
    profiles[key] = record
    _write_raw_profiles(path, profiles)
    return dict(record)


def update_user_profile_record(
    path: Path,
    model: str,
    payload: Mapping[str, object],
    *,
    require_confirmation: bool,
) -> dict[str, object]:
    key = normalize_model_name(model)
    profiles = _load_raw_profiles(path)
    if key not in profiles:
        raise UserProfileNotFoundError(model)
    current = dict(profiles[key])
    merged = dict(current)
    merged.update(dict(payload))
    record = _validate_payload(merged, model_override=str(current.get("model", model)))
    record["created_at"] = str(current.get("created_at", _timestamp()))
    record["updated_at"] = _timestamp()
    critical_changes = []
    for field in sorted(CRITICAL_PROFILE_FIELDS):
        old = current.get(field)
        new = record.get(field)
        if old != new:
            critical_changes.append({"field": field, "old": old, "new": new})
    if critical_changes and not require_confirmation:
        return {
            "status": "confirmation_required",
            "record": dict(record),
            "critical_changes": critical_changes,
        }
    profiles[key] = record
    _write_raw_profiles(path, profiles)
    return {
        "status": "updated",
        "record": dict(record),
        "critical_changes": critical_changes,
    }


def delete_user_profile(path: Path, model: str) -> None:
    key = normalize_model_name(model)
    profiles = _load_raw_profiles(path)
    if key not in profiles:
        raise UserProfileNotFoundError(model)
    del profiles[key]
    _write_raw_profiles(path, profiles)


def toggle_user_profile_enabled(path: Path, model: str, *, enabled: bool) -> dict[str, object]:
    key = normalize_model_name(model)
    profiles = _load_raw_profiles(path)
    if key not in profiles:
        raise UserProfileNotFoundError(model)
    record = dict(profiles[key])
    record["enabled"] = enabled
    record["updated_at"] = _timestamp()
    profiles[key] = record
    _write_raw_profiles(path, profiles)
    return dict(record)
