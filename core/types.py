from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple


BJTType = Literal["NPN", "PNP", "UNKNOWN"]
Region = Literal["cutoff", "active", "saturation"]
DriverMode = Literal["hardware", "simulation"]


@dataclass
class HwConfig:
    R_B: float = 22e3
    R_C: float = 220.0
    Vbe_typ: float = 0.7
    Ic_max_A: float = 30e-3
    Pmax_W: float = 0.30
    Vcc_max: float = 5.0
    lin_ic_lo_A: float = 0.5e-3
    lin_ic_hi_A: float = 20e-3
    lin_vce_window: Tuple[float, float] = (2.0, 4.0)


@dataclass
class StaticPoint:
    Vbb: float
    Vcc: float
    Vb: float
    Vc: float
    Ib: float
    Ic: float
    Vbe: float
    Vce: float
    beta: float
    region: Region
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DeviceReport:
    bjt_type: BJTType
    serial: str
    dut_label: str
    beta_median: float
    beta_active_curve: List[StaticPoint]
    vce_sat: float
    Ic_at_sat: float
    output_curves: Dict[float, List[StaticPoint]]
    early_voltage: Optional[float]
    beta_linearity: Optional[object]
    hw_config: HwConfig
    started_at: datetime
    finished_at: datetime
    reference_point: Optional[StaticPoint] = None
