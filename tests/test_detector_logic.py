from __future__ import annotations

from pathlib import Path

import pytest

from core.pyrd_driver import PyRDDriver
from core.simulation_driver import SimulationDriver
from core.types import StaticPoint
from measurement.curves import group_points_by_ib
from measurement.detector import detect_bjt_type
from measurement.vce_sat import find_vce_sat_point


class StubDetectDriver:
    def __init__(self, vb: float, vc: float) -> None:
        self.vb = vb
        self.vc = vc
        self.v_pos_calls = []
        self.w1_calls = []
        self.emergency_off_called = False

    def set_v_pos(self, volts: float) -> None:
        self.v_pos_calls.append(volts)

    def set_w1_dc(self, volts: float) -> None:
        self.w1_calls.append(volts)

    def read_scope_mean(
        self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200
    ):
        return self.vb, self.vc

    def emergency_off(self) -> None:
        self.emergency_off_called = True


def test_simulation_driver_returns_stable_scope_means():
    driver = SimulationDriver()
    serial = driver.connect()

    driver.set_v_pos(3.0)
    driver.set_w1_dc(2.0)
    vb, vc = driver.read_scope_mean(samples=256)

    assert serial.startswith("SIM-")
    assert 0.5 < vb < 0.9
    assert 0.0 < vc < 3.1


def test_detect_bjt_type_returns_npn_and_resets_outputs():
    driver = StubDetectDriver(vb=0.68, vc=1.10)

    result = detect_bjt_type(driver, R_B=22_000.0, R_C=220.0)

    assert result == "NPN"
    assert driver.v_pos_calls == [3.0]
    assert driver.w1_calls == [2.0]
    assert driver.emergency_off_called is True


def test_detect_bjt_type_returns_suspected_pnp_for_reverse_bias_signature():
    driver = StubDetectDriver(vb=1.78, vc=2.86)

    result = detect_bjt_type(driver, R_B=22_000.0, R_C=220.0)

    assert result == "SUSPECTED_PNP"
    assert driver.emergency_off_called is True


def test_detect_bjt_type_returns_unknown_when_signal_is_unclear():
    driver = StubDetectDriver(vb=1.25, vc=1.90)

    result = detect_bjt_type(driver, R_B=22_000.0, R_C=220.0)

    assert result == "UNKNOWN"
    assert driver.emergency_off_called is True


def test_find_vce_sat_point_prefers_lowest_vce_over_current_floor():
    points = [
        StaticPoint(0, 5, 0.7, 0.40, 20e-6, 8e-3, 0.7, 0.40, 400.0, "active"),
        StaticPoint(0, 5, 0.7, 0.22, 22e-6, 10e-3, 0.7, 0.22, 454.5, "saturation"),
        StaticPoint(0, 5, 0.7, 0.18, 25e-6, 12e-3, 0.7, 0.18, 480.0, "saturation"),
    ]

    vce_sat, ic_at_sat = find_vce_sat_point(points, ic_floor_a=9e-3)

    assert round(vce_sat, 3) == 0.180
    assert round(ic_at_sat, 3) == 0.012


def test_group_points_by_ib_preserves_curve_membership():
    points = [
        StaticPoint(0, 5, 0.7, 3.8, 10e-6, 4e-3, 0.7, 3.8, 400.0, "active"),
        StaticPoint(0, 5, 0.7, 3.5, 10e-6, 5e-3, 0.7, 3.5, 500.0, "active"),
        StaticPoint(0, 5, 0.7, 3.2, 15e-6, 7e-3, 0.7, 3.2, 466.7, "active"),
    ]

    curves = group_points_by_ib(points)

    assert sorted(curves.keys()) == [10e-6, 15e-6]
    assert len(curves[10e-6]) == 2
    assert curves[15e-6][0].Ic == 7e-3


def test_pyrd_driver_connect_bootstraps_sdk_path_and_opens_first_device(
    tmp_path: Path, monkeypatch
):
    sdk_src = tmp_path / "sdk"
    py_rd_pkg = sdk_src / "pyRD"
    py_rd_pkg.mkdir(parents=True)
    (py_rd_pkg / "__init__.py").write_text(
        "\n".join(
            [
                "class RD:",
                "    def __init__(self):",
                "        self.devicelist = []",
                "        self.opened_index = None",
                "        self.closed = False",
                "",
                "    def DeviceEnumLists(self):",
                "        self.devicelist = [(b'SIM-SN-001', b'RainDrop Mock')]",
                "",
                "    def DeviceOpen(self, index):",
                "        self.opened_index = index",
                "        return 0",
                "",
                "    def DeviceClose(self):",
                "        self.closed = True",
                "        return 0",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("core.device.SDK_SRC", sdk_src)

    driver = PyRDDriver()

    serial = driver.connect()

    assert serial == "SIM-SN-001"
    assert driver.rd is not None
    assert driver.rd.opened_index == 0


class FakeRD:
    def __init__(self) -> None:
        self.devicelist = [(b"SERIAL-001", b"Model S")]
        self.analoginstatus = 0
        self.aidatach1 = [0.12, 0.14, 0.16]
        self.aidatach2 = [1.10, 1.20, 1.30]
        self.calls = []

    def DeviceEnumLists(self):
        self.calls.append(("DeviceEnumLists",))

    def DeviceOpen(self, index):
        self.calls.append(("DeviceOpen", index))
        return 0

    def DeviceClose(self):
        self.calls.append(("DeviceClose",))
        return 0

    def AnalogInCHEnable(self, ch, enabled):
        self.calls.append(("AnalogInCHEnable", ch, enabled))

    def AnalogInCHRangeSet(self, ch, value):
        self.calls.append(("AnalogInCHRangeSet", ch, value))

    def AnalogInFrequencySet(self, value):
        self.calls.append(("AnalogInFrequencySet", value))

    def AnalogInBufferSizeSet(self, value):
        self.calls.append(("AnalogInBufferSizeSet", value))

    def AnalogInRun(self, enabled):
        self.calls.append(("AnalogInRun", enabled))

    def AnalogInStatus(self):
        self.calls.append(("AnalogInStatus",))
        self.analoginstatus = 2

    def AnalogInRead(self, count, ch):
        self.calls.append(("AnalogInRead", count, ch))

    def AnalogOutConfigure(self, ch, enabled):
        self.calls.append(("AnalogOutConfigure", ch, enabled))

    def AnalogIOChannelEnableSet(self, ch, enabled):
        self.calls.append(("AnalogIOChannelEnableSet", ch, enabled))


class NeverReadyRD:
    def __init__(self) -> None:
        self.devicelist = [(b"SERIAL-001", b"Model S")]
        self.analoginstatus = 0
        self.calls = []

    def DeviceEnumLists(self):
        self.calls.append(("DeviceEnumLists",))

    def DeviceOpen(self, index):
        self.calls.append(("DeviceOpen", index))
        return 0

    def DeviceClose(self):
        self.calls.append(("DeviceClose",))
        return 0

    def AnalogInCHEnable(self, ch, enabled):
        self.calls.append(("AnalogInCHEnable", ch, enabled))

    def AnalogInCHRangeSet(self, ch, value):
        self.calls.append(("AnalogInCHRangeSet", ch, value))

    def AnalogInFrequencySet(self, value):
        self.calls.append(("AnalogInFrequencySet", value))

    def AnalogInBufferSizeSet(self, value):
        self.calls.append(("AnalogInBufferSizeSet", value))

    def AnalogInRun(self, enabled):
        self.calls.append(("AnalogInRun", enabled))

    def AnalogInStatus(self):
        self.calls.append(("AnalogInStatus",))
        self.analoginstatus = 1


def test_pyrd_driver_reads_scope_with_polling(monkeypatch):
    fake_rd = FakeRD()

    def fake_factory():
        return fake_rd

    monkeypatch.setattr("core.pyrd_driver._build_rd", fake_factory)

    driver = PyRDDriver()
    assert driver.connect() == "SERIAL-001"

    vb, vc = driver.read_scope_mean(samples=3, frequency_hz=100000, timeout_ms=100)

    assert round(vb, 2) == 0.14
    assert round(vc, 2) == 1.20
    assert ("AnalogInStatus",) in fake_rd.calls
    assert ("AnalogInRun", False) in fake_rd.calls


def test_pyrd_driver_raises_timeout_when_scope_never_ready(monkeypatch):
    never_ready = NeverReadyRD()

    monkeypatch.setattr("core.pyrd_driver._build_rd", lambda: never_ready)
    driver = PyRDDriver()
    assert driver.connect() == "SERIAL-001"

    with pytest.raises(TimeoutError, match="示波器采样超时"):
        driver.read_scope_mean(samples=128, frequency_hz=100000, timeout_ms=20)

    assert ("AnalogInRun", True) in never_ready.calls
    assert ("AnalogInRun", False) in never_ready.calls
