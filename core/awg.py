from __future__ import annotations

from core.driver_protocol import DriverProtocol


class AWG:
    def __init__(self, driver: DriverProtocol) -> None:
        self.driver = driver

    def set_dc(self, channel: int, volts: float) -> None:
        if channel == 1:
            self.driver.set_w1_dc(volts)
            return
        if channel == 2:
            self.driver.set_w2_dc(volts)
            return
        raise ValueError("channel must be 1 or 2")

    def off(self) -> None:
        self.driver.set_w1_dc(0.0)
        self.driver.set_w2_dc(0.0)
