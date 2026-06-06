from __future__ import annotations

import pytest

from core.relay_matrix import NullRelayMatrixAdapter, RelayMatrixWrappedDriver, SimulatedRelayMatrixAdapter
from core.simulation_driver import SimulationDriver


def test_relay_matrix_wrapper_delegates_base_driver_outputs() -> None:
    base = SimulationDriver()
    wrapped = RelayMatrixWrappedDriver(base, SimulatedRelayMatrixAdapter())

    assert wrapped.connect() == "SIM-BJT-001"
    wrapped.set_v_pos(1.25)
    wrapped.set_w1_dc(0.8)

    assert base.v_pos == 1.25
    assert base.w1 == 0.8


def test_relay_matrix_wrapper_uses_adapter_for_pair_probe() -> None:
    adapter = SimulatedRelayMatrixAdapter()
    wrapped = RelayMatrixWrappedDriver(SimulationDriver(), adapter)

    result = wrapped.pin_pair_probe("A", "B", voltage_v=1.2, current_limit_a=0.001)

    assert result["conducts"] is True
    assert result["forward_drop_v"] == 0.68
    assert result["adapter"] == "simulated_relay_matrix"
    assert adapter.connected_pair == ("A", "B")


def test_relay_matrix_wrapper_disconnects_adapter_on_disable() -> None:
    adapter = SimulatedRelayMatrixAdapter()
    wrapped = RelayMatrixWrappedDriver(SimulationDriver(), adapter)
    wrapped.pin_pair_probe("A", "B", voltage_v=1.2, current_limit_a=0.001)

    wrapped.disable_all()

    assert adapter.connected_pair is None


def test_null_relay_matrix_adapter_reports_unavailable() -> None:
    wrapped = RelayMatrixWrappedDriver(SimulationDriver(), NullRelayMatrixAdapter())

    assert wrapped.relay_matrix_available() is False
    with pytest.raises(NotImplementedError):
        wrapped.pin_pair_probe("A", "B", voltage_v=1.2, current_limit_a=0.001)
