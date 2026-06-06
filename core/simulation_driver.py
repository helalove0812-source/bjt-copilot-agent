from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class SimulationDriver:
    v_pos: float = 0.0
    w1: float = 0.0
    w2: float = 0.0
    connected: bool = False
    serial: str = "SIM-BJT-001"
    relay_source_pin: str | None = None
    relay_sink_pin: str | None = None

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
        self.relay_matrix_disconnect_all()

    def relay_matrix_available(self) -> bool:
        return True

    def relay_matrix_connect(self, source_pin: str, sink_pin: str) -> None:
        source = str(source_pin).upper()
        sink = str(sink_pin).upper()
        if source == sink or source not in {"A", "B", "C"} or sink not in {"A", "B", "C"}:
            raise ValueError("simulation relay matrix expects two distinct pins from A/B/C")
        self.relay_source_pin = source
        self.relay_sink_pin = sink

    def relay_matrix_disconnect_all(self) -> None:
        self.relay_source_pin = None
        self.relay_sink_pin = None

    def pin_pair_probe(
        self,
        source_pin: str,
        sink_pin: str,
        *,
        voltage_v: float,
        current_limit_a: float,
        samples: int = 512,
    ) -> dict[str, Any]:
        del samples
        source = str(source_pin).upper()
        sink = str(sink_pin).upper()
        voltage = _clamp(float(voltage_v), 0.0, 1.2)
        current_limit = _clamp(float(current_limit_a), 0.0, 0.001)
        self.relay_matrix_connect(source, sink)
        diode_map = {
            ("A", "B"): 0.68,
            ("C", "B"): 0.69,
        }
        forward_drop = diode_map.get((source, sink))
        conducts = forward_drop is not None and voltage >= forward_drop
        return {
            "source_pin": source,
            "sink_pin": sink,
            "conducts": bool(conducts),
            "forward_drop_v": forward_drop if conducts else None,
            "reverse_leakage_a": None if conducts else 0.0,
            "applied_voltage_v": voltage,
            "current_limit_a": current_limit,
            "measured_current_a": min(current_limit, 0.00062) if conducts else 0.0,
        }
