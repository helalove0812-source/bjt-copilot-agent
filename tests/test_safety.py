import pytest

from core.safety import SafetyAbort, SafetyGuard
from core.types import HwConfig, StaticPoint


class StubDriver:
    def __init__(self):
        self.off_called = False

    def emergency_off(self):
        self.off_called = True


def make_point(**overrides):
    payload = {
        "Vbb": 1.0,
        "Vcc": 5.0,
        "Vb": 0.7,
        "Vc": 2.0,
        "Ib": 10e-6,
        "Ic": 5e-3,
        "Vbe": 0.7,
        "Vce": 2.0,
        "beta": 500.0,
        "region": "active",
    }
    payload.update(overrides)
    return StaticPoint(**payload)


def test_safety_guard_aborts_on_overcurrent():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Ic_max_A=0.01), driver)
    point = make_point(Ic=20e-3)

    with pytest.raises(SafetyAbort, match="Ic"):
        guard.check(point)

    assert driver.off_called is True


def test_safety_guard_aborts_on_overpower():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Pmax_W=0.01), driver)
    point = make_point(Ic=5e-3, Vce=4.0)

    with pytest.raises(SafetyAbort, match="功耗"):
        guard.check(point)

    assert driver.off_called is True


def test_safety_guard_aborts_on_invalid_measurement_state():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Vcc_max=5.0), driver)
    point = make_point(Vce=6.0)

    with pytest.raises(SafetyAbort, match="测量状态"):
        guard.check(point)

    assert driver.off_called is True


def test_safety_guard_aborts_when_stop_is_requested():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(), driver)

    guard.request_stop()

    with pytest.raises(SafetyAbort, match="用户停止"):
        guard.check(make_point())

    assert driver.off_called is True


def test_safety_guard_records_abort_reason():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Ic_max_A=0.01), driver, command_name="npn-static")
    point = make_point(Ic=20e-3)

    with pytest.raises(SafetyAbort, match="Ic"):
        guard.check(point)

    assert guard.last_abort_reason == "Ic 过流"
    assert guard.last_abort_context["command"] == "npn-static"
