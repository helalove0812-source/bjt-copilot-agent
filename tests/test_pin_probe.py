from __future__ import annotations

from core.simulation_driver import SimulationDriver
from core.types import HwConfig
from measurement.pin_probe import run_relay_matrix_pin_permutation_probe


class NoRelayHardwareDriver(SimulationDriver):
    def relay_matrix_available(self) -> bool:
        return False


class FakeRelayHardwareDriver(SimulationDriver):
    def relay_matrix_available(self) -> bool:
        return True


def test_relay_matrix_probe_simulation_scans_ordered_pairs() -> None:
    result = run_relay_matrix_pin_permutation_probe(
        SimulationDriver(),
        cfg=HwConfig(),
        mode="simulation",
    )

    assert result["ok"] is True
    assert result["source"] == "relay_matrix_pin_probe"
    assert len(result["pair_results"]) == 6
    assert result["capability"]["relay_matrix_connect"] is True
    assert result["capability"]["pin_pair_probe"] is True
    assert {item["source_pin"] + item["sink_pin"] for item in result["pair_results"]} == {
        "AB",
        "AC",
        "BA",
        "BC",
        "CA",
        "CB",
    }


def test_relay_matrix_probe_reports_missing_hardware_capability() -> None:
    driver = NoRelayHardwareDriver()
    driver.connect()

    result = run_relay_matrix_pin_permutation_probe(
        driver,
        cfg=HwConfig(),
        mode="hardware",
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "relay_matrix_unavailable"
    assert result["capability"]["relay_matrix_connect"] is False


def test_relay_matrix_probe_hardware_driver_uses_pin_pair_probe() -> None:
    driver = FakeRelayHardwareDriver()
    driver.connect()

    result = run_relay_matrix_pin_permutation_probe(
        driver,
        cfg=HwConfig(),
        mode="hardware",
    )

    assert result["ok"] is True
    assert result["mode"] == "hardware"
    assert result["capability"]["simulated"] is False
    assert len(result["pair_results"]) == 6
    assert any(item["source_pin"] == "A" and item["sink_pin"] == "B" and item["conducts"] for item in result["pair_results"])
    assert driver.relay_source_pin is None
    assert driver.relay_sink_pin is None
