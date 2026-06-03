from __future__ import annotations

from typing import Iterable, Tuple

from core.types import StaticPoint


def find_vce_sat_point(
    points: Iterable[StaticPoint], ic_floor_a: float
) -> Tuple[float, float]:
    candidates = [
        point for point in points if abs(point.Ic) >= float(ic_floor_a)
    ]
    if not candidates:
        raise ValueError("no saturation candidate meets current floor")

    best = min(candidates, key=lambda point: abs(point.Vce))
    return abs(best.Vce), abs(best.Ic)


def estimate_vce_sat(point: StaticPoint, ic_floor_a: float = 0.0) -> Tuple[float, float]:
    return find_vce_sat_point([point], ic_floor_a=ic_floor_a)
