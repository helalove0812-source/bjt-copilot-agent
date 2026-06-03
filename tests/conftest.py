import pytest


class FakeDriver:
    def connect(self):
        return "SIM-BJT-001"

    def close(self):
        return None

    def set_v_pos(self, volts):
        return None

    def set_w1_dc(self, volts):
        return None

    def set_w2_dc(self, volts):
        return None

    def read_scope_mean(self, samples, frequency_hz=100000, timeout_ms=200):
        return (0.68, 2.93)

    def emergency_off(self):
        return None


@pytest.fixture
def fake_driver():
    return FakeDriver()
