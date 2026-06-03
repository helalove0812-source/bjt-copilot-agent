from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


DriverMode = Literal["hardware", "simulation"]


@dataclass
class AppConfig:
    driver_mode: DriverMode
    rb_ohm: float
    rc_ohm: float
    ic_max_a: float
    pmax_w: float
    vcc_max: float
    lin_ic_lo_a: float
    lin_ic_hi_a: float
    lin_vce_window: tuple[float, float]
    sample_count: int
    settle_ms: int


def load_app_config(path: str | Path) -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        driver_mode=data["driver_mode"],
        rb_ohm=float(data["rb_ohm"]),
        rc_ohm=float(data["rc_ohm"]),
        ic_max_a=float(data["ic_max_a"]),
        pmax_w=float(data["pmax_w"]),
        vcc_max=float(data["vcc_max"]),
        lin_ic_lo_a=float(data["lin_ic_lo_a"]),
        lin_ic_hi_a=float(data["lin_ic_hi_a"]),
        lin_vce_window=(float(data["lin_vce_lo_v"]), float(data["lin_vce_hi_v"])),
        sample_count=int(data["sample_count"]),
        settle_ms=int(data["settle_ms"]),
    )
