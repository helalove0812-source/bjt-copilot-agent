from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from core.types import StaticPoint


@dataclass
class BetaLinearity:
    eta: Optional[float]
    beta_max: float = 0.0
    beta_min: float = 0.0
    beta_avg: float = 0.0
    n: int = 0
    beta_vs_ic: List[Tuple[float, float]] = field(default_factory=list)
    reason: str = ""


def _beta_average(points: Iterable[StaticPoint]) -> float:
    total_beta = 0.0
    count = 0
    for point in points:
        total_beta += point.beta
        count += 1
    if count == 0:
        return 0.0
    return total_beta / count


def beta_linearity(
    points: Iterable[StaticPoint],
    ic_range: Tuple[float, float],
    vce_window: Tuple[float, float],
    min_points: int = 8,
) -> BetaLinearity:
    candidates = [
        point
        for point in points
        if point.region == "active"
        and ic_range[0] <= abs(point.Ic) <= ic_range[1]
        and vce_window[0] <= abs(point.Vce) <= vce_window[1]
    ]
    if len(candidates) < int(min_points):
        return BetaLinearity(
            eta=None,
            n=len(candidates),
            reason="有效点不足",
        )

    betas = [point.beta for point in candidates]
    beta_max = max(betas)
    beta_min = min(betas)
    beta_avg = _beta_average(candidates)
    eta = 0.0 if beta_avg <= 0.0 else (beta_max - beta_min) / beta_avg
    beta_vs_ic = [(abs(point.Ic), point.beta) for point in candidates]
    return BetaLinearity(
        eta=eta,
        beta_max=beta_max,
        beta_min=beta_min,
        beta_avg=beta_avg,
        n=len(candidates),
        beta_vs_ic=beta_vs_ic,
    )


def summarize_beta_linearity(
    points: Iterable[StaticPoint],
    cfg,
    min_points: int = 1,
) -> BetaLinearity:
    return beta_linearity(
        points,
        ic_range=(cfg.lin_ic_lo_A, cfg.lin_ic_hi_A),
        vce_window=cfg.lin_vce_window,
        min_points=min_points,
    )
