from __future__ import annotations

from statistics import median
from typing import Iterable

from core.types import StaticPoint


def beta_median(points: Iterable[StaticPoint]) -> float:
    active_betas = [point.beta for point in points if point.region == "active"]
    if not active_betas:
        return 0.0
    return float(median(active_betas))
