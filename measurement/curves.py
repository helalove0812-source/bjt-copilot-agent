from __future__ import annotations

from typing import Dict, Iterable, List

from core.types import StaticPoint


def group_points_by_ib(points: Iterable[StaticPoint]) -> Dict[float, List[StaticPoint]]:
    curves = {}
    for point in points:
        key = float(point.Ib)
        curves.setdefault(key, []).append(point)
    return curves


def build_minimal_output_curves(point: StaticPoint) -> Dict[float, List[StaticPoint]]:
    return group_points_by_ib([point])
