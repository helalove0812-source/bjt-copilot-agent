from __future__ import annotations

from typing import Any


def diagnose_pulse_response(trace: list[dict[str, Any]]) -> dict[str, Any]:
    pulse_measurements = [
        item.get("measurement")
        for item in trace
        if isinstance(item, dict)
        and item.get("status") == "measured"
        and isinstance(item.get("primitive"), dict)
        and item["primitive"].get("kind") == "pulse"
        and isinstance(item.get("measurement"), dict)
    ]
    clean = [item for item in pulse_measurements if isinstance(item, dict) and item.get("pulse_width_us") is not None]
    if len(clean) < 2:
        return {
            "ok": False,
            "status": "insufficient_pulse_data",
            "hypothesis": "unknown",
            "confidence": 0.0,
            "evidence": "需要至少一个短脉冲和一个长脉冲测量。",
            "metrics": {},
        }
    ordered = sorted(clean, key=lambda item: int(item.get("pulse_width_us") or 0))
    short = ordered[0]
    long = ordered[-1]
    short_vce = float(short.get("Vce") or 0.0)
    long_vce = float(long.get("Vce") or 0.0)
    short_ic = float(short.get("Ic") or 0.0)
    long_ic = float(long.get("Ic") or 0.0)
    vce_delta = long_vce - short_vce
    vce_ratio = vce_delta / max(abs(short_vce), 1e-9)
    ic_ratio = (long_ic - short_ic) / max(abs(short_ic), 1e-9)
    if vce_ratio >= 0.02:
        hypothesis = "self_heating_or_thermal_saturation_drift"
        confidence = min(0.85, 0.45 + vce_ratio * 4.0)
        evidence = "长脉冲 Vce 相比短脉冲升高，说明热漂移/自热比纯静态串联电阻更可疑。"
    elif abs(vce_ratio) < 0.01 and abs(ic_ratio) < 0.03:
        hypothesis = "contact_or_package_series_resistance"
        confidence = 0.62
        evidence = "短/长脉冲差异很小，残差更像接触、封装电阻或模型参数不足。"
    else:
        hypothesis = "mixed_or_inconclusive_pulse_signature"
        confidence = 0.4
        evidence = "短/长脉冲差异存在但不够单一，需要更多脉宽或电流点。"
    return {
        "ok": True,
        "status": "diagnosed",
        "hypothesis": hypothesis,
        "confidence": round(confidence, 4),
        "evidence": evidence,
        "metrics": {
            "short_pulse_width_us": int(short.get("pulse_width_us") or 0),
            "long_pulse_width_us": int(long.get("pulse_width_us") or 0),
            "short_vce": round(short_vce, 6),
            "long_vce": round(long_vce, 6),
            "vce_delta": round(vce_delta, 6),
            "vce_delta_ratio": round(vce_ratio, 6),
            "ic_delta_ratio": round(ic_ratio, 6),
        },
    }


def pulse_diagnosis_to_hypothesis(diagnosis: dict[str, Any]) -> dict[str, Any] | None:
    if not diagnosis.get("ok"):
        return None
    return {
        "name": str(diagnosis.get("hypothesis") or "pulse_signature_unknown"),
        "confidence": float(diagnosis.get("confidence") or 0.0),
        "evidence": str(diagnosis.get("evidence") or ""),
        "source": "pulse_diagnosis",
        "metrics": diagnosis.get("metrics") if isinstance(diagnosis.get("metrics"), dict) else {},
    }
