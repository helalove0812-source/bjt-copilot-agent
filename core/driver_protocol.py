from typing import Any, Protocol, Tuple, runtime_checkable


@runtime_checkable
class DriverProtocol(Protocol):
    def connect(self) -> str:
        ...

    def close(self) -> None:
        ...

    def set_v_pos(self, volts: float) -> None:
        ...

    def set_w1_dc(self, volts: float) -> None:
        ...

    def set_w2_dc(self, volts: float) -> None:
        ...

    def read_scope_mean(self, samples: int) -> Tuple[float, float]:
        ...

    def emergency_off(self) -> None:
        ...

    def relay_matrix_available(self) -> bool:
        ...

    def relay_matrix_connect(self, source_pin: str, sink_pin: str) -> None:
        ...

    def relay_matrix_disconnect_all(self) -> None:
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
