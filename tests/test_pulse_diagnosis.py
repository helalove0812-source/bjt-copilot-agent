from __future__ import annotations

from ai.pulse_diagnosis import diagnose_pulse_response, pulse_diagnosis_to_hypothesis


def test_pulse_diagnosis_detects_self_heating_signature() -> None:
    primitive = {"kind": "pulse", "name": "critic_short_long_pulse_vce_sat_check"}
    trace = [
        {"status": "measured", "primitive": primitive, "measurement": {"pulse_width_us": 100, "Vce": 0.2, "Ic": 0.01}},
        {"status": "measured", "primitive": primitive, "measurement": {"pulse_width_us": 5000, "Vce": 0.21, "Ic": 0.01}},
    ]

    diagnosis = diagnose_pulse_response(trace)
    hypothesis = pulse_diagnosis_to_hypothesis(diagnosis)

    assert diagnosis["ok"] is True
    assert diagnosis["hypothesis"] == "self_heating_or_thermal_saturation_drift"
    assert diagnosis["metrics"]["vce_delta"] > 0
    assert hypothesis
    assert hypothesis["source"] == "pulse_diagnosis"
