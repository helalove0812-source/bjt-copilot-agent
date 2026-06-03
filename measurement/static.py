from __future__ import annotations

from core.safety import SafetyGuard
from core.types import HwConfig, StaticPoint


def _classify_region(vbe: float, vce: float) -> str:
    if abs(vbe) < 0.5:
        return "cutoff"
    if abs(vce) < 0.3:
        return "saturation"
    return "active"


def _safe_beta(ib: float, ic: float) -> float:
    if ib <= 1e-12 or ic <= 0.0:
        return 0.0
    return ic / ib


def build_static_point(
    *,
    bjt_type: str,
    R_B: float,
    R_C: float,
    Vbb: float,
    Vcc: float,
    Vb: float,
    Vc: float
) -> StaticPoint:
    if bjt_type == "NPN":
        ib = max((Vbb - Vb) / R_B, 0.0)
        ic = max((Vcc - Vc) / R_C, 0.0)
        vbe = Vb
        vce = Vc
    elif bjt_type == "PNP":
        ib = max((Vb - Vbb) / R_B, 0.0)
        ic = max(Vc / R_C, 0.0)
        vbe = Vb - Vcc
        vce = Vc - Vcc
    else:
        raise ValueError("unsupported bjt_type")

    beta = _safe_beta(ib, ic)
    region = _classify_region(vbe, vce)
    return StaticPoint(
        Vbb=Vbb,
        Vcc=Vcc,
        Vb=Vb,
        Vc=Vc,
        Ib=ib,
        Ic=ic,
        Vbe=vbe,
        Vce=vce,
        beta=beta,
        region=region,
    )


def measure_static_point(
    driver,
    *,
    bjt_type: str,
    cfg: HwConfig,
    Vbb: float,
    Vcc: float,
    samples: int = 2048,
    frequency_hz: int = 100000,
    timeout_ms: int = 200,
) -> StaticPoint:
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()
    driver.set_v_pos(Vcc)
    driver.set_w1_dc(Vbb)
    try:
        vb, vc = driver.read_scope_mean(
            samples=int(samples),
            frequency_hz=int(frequency_hz),
            timeout_ms=int(timeout_ms),
        )
    except TypeError:
        vb, vc = driver.read_scope_mean(samples=int(samples))
    point = build_static_point(
        bjt_type=bjt_type,
        R_B=cfg.R_B,
        R_C=cfg.R_C,
        Vbb=Vbb,
        Vcc=Vcc,
        Vb=float(vb),
        Vc=float(vc),
    )
    return SafetyGuard(cfg, driver).check(point)
