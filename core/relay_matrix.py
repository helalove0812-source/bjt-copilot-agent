from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RelayMatrixAdapter(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def connect_pair(self, source_pin: str, sink_pin: str) -> None:
        ...

    def disconnect_all(self) -> None:
        ...

    def pin_pair_probe(
        self,
        source_pin: str,
        sink_pin: str,
        *,
        voltage_v: float,
        current_limit_a: float,
        samples: int = 512,
    ) -> dict[str, Any]:
        ...


@dataclass
class NullRelayMatrixAdapter:
    name: str = "none"

    def available(self) -> bool:
        return False

    def connect_pair(self, source_pin: str, sink_pin: str) -> None:
        del source_pin, sink_pin
        raise NotImplementedError("未配置外部 relay matrix adapter")

    def disconnect_all(self) -> None:
        return

    def pin_pair_probe(
        self,
        source_pin: str,
        sink_pin: str,
        *,
        voltage_v: float,
        current_limit_a: float,
        samples: int = 512,
    ) -> dict[str, Any]:
        del source_pin, sink_pin, voltage_v, current_limit_a, samples
        raise NotImplementedError("未配置外部 relay matrix adapter")


@dataclass
class SimulatedRelayMatrixAdapter:
    name: str = "simulated_relay_matrix"
    connected_pair: tuple[str, str] | None = None

    def available(self) -> bool:
        return True

    def connect_pair(self, source_pin: str, sink_pin: str) -> None:
        source = _normalize_pin(source_pin)
        sink = _normalize_pin(sink_pin)
        if source == sink:
            raise ValueError("relay matrix requires two distinct pins")
        self.connected_pair = (source, sink)

    def disconnect_all(self) -> None:
        self.connected_pair = None

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
        source = _normalize_pin(source_pin)
        sink = _normalize_pin(sink_pin)
        voltage = _clamp(float(voltage_v), 0.0, 1.2)
        current_limit = _clamp(float(current_limit_a), 0.0, 0.001)
        self.connect_pair(source, sink)
        forward_drop = {("A", "B"): 0.68, ("C", "B"): 0.69}.get((source, sink))
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
            "adapter": self.name,
        }


@dataclass
class RelayMatrixWrappedDriver:
    base_driver: Any
    adapter: RelayMatrixAdapter

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_driver, name)

    def connect(self) -> str:
        return self.base_driver.connect()

    def close(self) -> None:
        self.relay_matrix_disconnect_all()
        self.base_driver.close()

    def emergency_off(self) -> None:
        emergency_off = getattr(self.base_driver, "emergency_off", None)
        if callable(emergency_off):
            emergency_off()
        self.relay_matrix_disconnect_all()

    def disable_all(self) -> None:
        disable_all = getattr(self.base_driver, "disable_all", None)
        if callable(disable_all):
            disable_all()
        else:
            self.emergency_off()
        self.relay_matrix_disconnect_all()

    def relay_matrix_available(self) -> bool:
        return bool(self.adapter.available())

    def relay_matrix_connect(self, source_pin: str, sink_pin: str) -> None:
        self.adapter.connect_pair(source_pin, sink_pin)

    def relay_matrix_disconnect_all(self) -> None:
        self.adapter.disconnect_all()

    def pin_pair_probe(
        self,
        source_pin: str,
        sink_pin: str,
        *,
        voltage_v: float,
        current_limit_a: float,
        samples: int = 512,
    ) -> dict[str, Any]:
        if not self.relay_matrix_available():
            raise NotImplementedError("relay matrix adapter is not available")
        return self.adapter.pin_pair_probe(
            source_pin,
            sink_pin,
            voltage_v=voltage_v,
            current_limit_a=current_limit_a,
            samples=samples,
        )


def _normalize_pin(value: str) -> str:
    pin = str(value).strip().upper()
    if pin not in {"A", "B", "C"}:
        raise ValueError("relay matrix adapter expects pins A/B/C")
    return pin


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
