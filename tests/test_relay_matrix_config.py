from __future__ import annotations

import pytest

import app.services as services
from core.relay_matrix import RelayMatrixWrappedDriver


class BareHardwareDriver:
    def __init__(self) -> None:
        self.connected = False
        self.disabled = False

    def connect(self) -> str:
        self.connected = True
        return "BARE-HW"

    def close(self) -> None:
        self.connected = False

    def disable_all(self) -> None:
        self.disabled = True


def test_hardware_build_driver_defaults_to_unavailable_relay_matrix(monkeypatch) -> None:
    monkeypatch.delenv("BJT_RELAY_MATRIX_BACKEND", raising=False)
    monkeypatch.setattr(services, "PyRDDriver", BareHardwareDriver)

    driver = services.build_driver("hardware")

    assert isinstance(driver, RelayMatrixWrappedDriver)
    assert driver.relay_matrix_available() is False


def test_hardware_build_driver_can_enable_simulated_relay_matrix(monkeypatch) -> None:
    monkeypatch.setenv("BJT_RELAY_MATRIX_BACKEND", "simulated")
    monkeypatch.setattr(services, "PyRDDriver", BareHardwareDriver)

    driver = services.build_driver("hardware")
    result = driver.pin_pair_probe("C", "B", voltage_v=1.2, current_limit_a=0.001)

    assert isinstance(driver, RelayMatrixWrappedDriver)
    assert driver.relay_matrix_available() is True
    assert result["conducts"] is True
    assert result["forward_drop_v"] == 0.69


def test_hardware_build_driver_rejects_unknown_relay_backend(monkeypatch) -> None:
    monkeypatch.setenv("BJT_RELAY_MATRIX_BACKEND", "mystery")
    monkeypatch.setattr(services, "PyRDDriver", BareHardwareDriver)

    with pytest.raises(RuntimeError, match="BJT_RELAY_MATRIX_BACKEND"):
        services.build_driver("hardware")
