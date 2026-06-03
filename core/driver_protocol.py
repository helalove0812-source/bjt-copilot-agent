from typing import Protocol, Tuple, runtime_checkable


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
