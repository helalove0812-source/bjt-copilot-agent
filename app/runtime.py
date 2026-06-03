from __future__ import annotations

from dataclasses import dataclass

from core.driver_protocol import DriverProtocol
from core.types import HwConfig


@dataclass
class Runtime:
    config: HwConfig
    driver: DriverProtocol
    serial: str
