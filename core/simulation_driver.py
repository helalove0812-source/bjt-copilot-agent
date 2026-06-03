from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class SimulationDriver:
    v_pos: float = 0.0
    w1: float = 0.0
    w2: float = 0.0
    connected: bool = False
    serial: str = "SIM-BJT-001"

    def connect(self) -> str:
        self.connected = True
        return self.serial

    def close(self) -> None:
        self.connected = False

    def set_v_pos(self, volts: float) -> None:
        self.v_pos = float(volts)

    def set_w1_dc(self, volts: float) -> None:
        self.w1 = float(volts)

    def set_w2_dc(self, volts: float) -> None:
        self.w2 = float(volts)

    def read_scope_mean(self, samples: int) -> Tuple[float, float]:
        _ = samples
        vb = _clamp(self.w1 - 1.32, 0.0, 0.82)
        vc = _clamp(self.v_pos - 0.56 - (vb * 0.08), 0.12, max(self.v_pos, 0.12))
        return vb, vc

    def emergency_off(self) -> None:
        self.v_pos = 0.0
        self.w1 = 0.0
        self.w2 = 0.0
