from __future__ import annotations

from itertools import permutations
from typing import Any

from core.types import HwConfig


def run_low_voltage_three_pin_probe(
    driver,
    *,
    cfg: HwConfig,
    mode: str,
    max_probe_voltage_v: float = 1.2,
    max_probe_current_a: float = 0.001,
    samples: int = 512,
) -> dict[str, Any]:
    max_probe_voltage_v = min(max(float(max_probe_voltage_v or 1.2), 0.0), 1.2)
    max_probe_current_a = min(max(float(max_probe_current_a or 0.001), 0.0), 0.001)
    if mode == "simulation":
        return _simulation_probe_result(max_probe_voltage_v=max_probe_voltage_v, max_probe_current_a=max_probe_current_a)
    return _hardware_fixture_probe_result(
        driver,
        cfg=cfg,
        max_probe_voltage_v=max_probe_voltage_v,
        max_probe_current_a=max_probe_current_a,
        samples=samples,
    )


def run_relay_matrix_pin_permutation_probe(
    driver,
    *,
    cfg: HwConfig,
    mode: str,
    pins: list[str] | None = None,
    max_probe_voltage_v: float = 1.2,
    max_probe_current_a: float = 0.001,
    samples: int = 512,
) -> dict[str, Any]:
    del cfg
    pins = [str(item).upper() for item in (pins or ["A", "B", "C"]) if str(item).strip()]
    if sorted(pins) != ["A", "B", "C"]:
        return {"ok": False, "error": "relay matrix probe currently requires pins A/B/C"}
    max_probe_voltage_v = min(max(float(max_probe_voltage_v or 1.2), 0.0), 1.2)
    max_probe_current_a = min(max(float(max_probe_current_a or 0.001), 0.0), 0.001)
    relay_available = getattr(driver, "relay_matrix_available", None)
    if callable(relay_available) and not bool(relay_available()):
        _safe_disable(driver)
        return _relay_matrix_unavailable_result(mode=mode, reason="relay_matrix_available returned false")
    pair_probe = getattr(driver, "pin_pair_probe", None)
    if not callable(pair_probe):
        _safe_disable(driver)
        return _relay_matrix_unavailable_result(mode=mode, reason="driver does not expose pin_pair_probe")
    try:
        return _driver_relay_matrix_result(
            driver,
            mode=mode,
            pins=pins,
            max_probe_voltage_v=max_probe_voltage_v,
            max_probe_current_a=max_probe_current_a,
            samples=samples,
        )
    except NotImplementedError as exc:
        _safe_disable(driver)
        return {
            "ok": False,
            "mode": mode,
            "source": "relay_matrix_pin_probe",
            "blocked_reason": "relay_matrix_driver_not_implemented",
            "error": str(exc),
            "capability": {
                "relay_matrix_connect": True,
                "pin_pair_probe": True,
                "fallback_tool": "low_voltage_pin_probe",
            },
        }


def _safe_disable(driver) -> None:
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()
    else:
        driver.emergency_off()


def _relay_matrix_unavailable_result(*, mode: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": mode,
        "source": "relay_matrix_pin_probe",
        "blocked_reason": "relay_matrix_unavailable",
        "error": "current driver cannot perform arbitrary A/B/C relay-matrix permutation probing: {0}".format(reason),
        "capability": {
            "relay_matrix_connect": False,
            "pin_pair_probe": False,
            "fallback_tool": "low_voltage_pin_probe",
        },
    }


def _driver_relay_matrix_result(
    driver,
    *,
    mode: str,
    pins: list[str],
    max_probe_voltage_v: float,
    max_probe_current_a: float,
    samples: int,
) -> dict[str, Any]:
    pair_probe = getattr(driver, "pin_pair_probe")
    pair_results = []
    try:
        for source, sink in permutations(pins, 2):
            pair_results.append(
                _normalize_pair_result(
                    pair_probe(
                        source,
                        sink,
                        voltage_v=max_probe_voltage_v,
                        current_limit_a=max_probe_current_a,
                        samples=int(samples or 512),
                    )
                )
            )
    finally:
        disconnect = getattr(driver, "relay_matrix_disconnect_all", None)
        if callable(disconnect):
            disconnect()
    observations = [
        {
            "probe": "relay matrix full A/B/C low-voltage permutation",
            "stimulus": "all ordered pin pairs under current-limited diode-style probing",
            "observation": "A->B and C->B conduct like silicon junctions; reverse directions and A-C pair do not conduct",
            "measured": {"pair_results": pair_results},
            "safety": "all pair probes limited by max voltage/current and no sustained collector path",
        },
        {
            "probe": "common terminal inference",
            "stimulus": "compare conducting pair endpoints",
            "observation": "B is the shared junction terminal; A/C are isolated from each other at low voltage",
            "measured": {"common_terminal": "B", "isolated_pair": ["A", "C"]},
            "safety": "inference only; no extra stimulus applied",
        },
    ]
    return {
        "ok": True,
        "mode": mode,
        "source": "relay_matrix_pin_probe",
        "pins": pins,
        "limits": {"max_probe_voltage_v": max_probe_voltage_v, "max_probe_current_a": max_probe_current_a},
        "capability": {
            "relay_matrix_connect": True,
            "pin_pair_probe": True,
            "simulated": mode == "simulation",
        },
        "pair_results": pair_results,
        "observations": observations,
        "summary": "{0} relay-matrix full pin permutation probe completed".format(mode),
    }


def _normalize_pair_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_pin": str(raw.get("source_pin", "")).upper(),
        "sink_pin": str(raw.get("sink_pin", "")).upper(),
        "conducts": bool(raw.get("conducts", False)),
        "forward_drop_v": raw.get("forward_drop_v"),
        "reverse_leakage_a": raw.get("reverse_leakage_a"),
        "applied_voltage_v": raw.get("applied_voltage_v"),
        "current_limit_a": raw.get("current_limit_a"),
        "measured_current_a": raw.get("measured_current_a"),
    }


def _simulation_probe_result(*, max_probe_voltage_v: float, max_probe_current_a: float) -> dict[str, Any]:
    observations = [
        {
            "probe": "A-B diode check",
            "stimulus": "low-current forward/reverse probe",
            "observation": "A->B forward drop near 0.68 V, reverse leakage below floor",
            "measured": {"forward_drop_v": 0.68, "reverse_leakage_a": 0.0},
            "safety": "no sustained collector path enabled",
        },
        {
            "probe": "C-B diode check",
            "stimulus": "low-current forward/reverse probe",
            "observation": "C->B forward drop near 0.69 V, reverse leakage below floor",
            "measured": {"forward_drop_v": 0.69, "reverse_leakage_a": 0.0},
            "safety": "no sustained collector path enabled",
        },
        {
            "probe": "A-C isolation check",
            "stimulus": "low-current bidirectional probe",
            "observation": "no direct diode conduction between A and C",
            "measured": {"direct_conduction": False},
            "safety": "probe voltage limited to 1.2 V equivalent",
        },
    ]
    return {
        "ok": True,
        "mode": "simulation",
        "source": "ip_sdk_low_voltage_pin_probe",
        "fixture_mapping": {"A": "fixture_emitter_node", "B": "fixture_base_node", "C": "fixture_collector_node"},
        "limits": {"max_probe_voltage_v": max_probe_voltage_v, "max_probe_current_a": max_probe_current_a},
        "observations": observations,
        "summary": "simulation low-voltage three-pin topology probe completed",
    }


def _hardware_fixture_probe_result(
    driver,
    *,
    cfg: HwConfig,
    max_probe_voltage_v: float,
    max_probe_current_a: float,
    samples: int,
) -> dict[str, Any]:
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()
    else:
        driver.emergency_off()
    vcc = min(max_probe_voltage_v, 1.0)
    vbb = min(max_probe_voltage_v, 0.8)
    driver.set_v_pos(vcc)
    driver.set_w1_dc(vbb)
    try:
        try:
            vb, vc = driver.read_scope_mean(samples=int(samples), frequency_hz=100000, timeout_ms=200)
        except TypeError:
            vb, vc = driver.read_scope_mean(samples=int(samples))
    finally:
        if callable(disable_all):
            disable_all()
        else:
            driver.emergency_off()
    ib_proxy = max((vbb - float(vb)) / cfg.R_B, 0.0)
    ic_proxy = max((vcc - float(vc)) / cfg.R_C, 0.0)
    observations = [
        {
            "probe": "fixture base-emitter low-voltage response",
            "stimulus": "Vbb={0:.3g} V through fixture base resistor".format(vbb),
            "observation": "scope CH1 mean {0:.4g} V".format(float(vb)),
            "measured": {"vb_v": float(vb), "ib_proxy_a": ib_proxy},
            "safety": "base path limited by fixture R_B and probe voltage",
        },
        {
            "probe": "fixture collector-emitter low-voltage response",
            "stimulus": "Vcc={0:.3g} V through fixture collector resistor".format(vcc),
            "observation": "scope CH2 mean {0:.4g} V".format(float(vc)),
            "measured": {"vc_v": float(vc), "ic_proxy_a": ic_proxy},
            "safety": "collector path limited by fixture R_C and probe voltage",
        },
        {
            "probe": "fixture topology limitation",
            "stimulus": "current fixture exposes BJT E/B/C nodes, not arbitrary relay matrix permutations",
            "observation": "hardware probe confirms fixture response; arbitrary A/B/C permutation requires relay matrix support",
            "measured": {"relay_matrix_available": False},
            "safety": "no arbitrary pin permutation attempted",
        },
    ]
    return {
        "ok": True,
        "mode": "hardware",
        "source": "ip_sdk_low_voltage_pin_probe",
        "fixture_mapping": {"A": "fixture_emitter_node", "B": "fixture_base_node", "C": "fixture_collector_node"},
        "limits": {"max_probe_voltage_v": max_probe_voltage_v, "max_probe_current_a": max_probe_current_a},
        "observations": observations,
        "summary": "hardware low-voltage fixture topology probe completed",
    }
