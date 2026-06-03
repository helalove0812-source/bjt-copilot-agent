from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable, Mapping

from core.types import BJTType


@dataclass(frozen=True)
class TransistorProfile:
    model: str
    bjt_type: BJTType
    description: str
    vceo_max_v: float
    ic_max_a: float
    p_tot_w: float
    hfe_typical: tuple[int, int]
    package: str = ""
    pinout_hint: str = ""
    confidence: str = "catalog"


_PROFILES: dict[str, TransistorProfile] = {
    "S8050": TransistorProfile(
        model="S8050",
        bjt_type="NPN",
        description="小功率通用 NPN 三极管",
        vceo_max_v=25.0,
        ic_max_a=0.5,
        p_tot_w=0.625,
        hfe_typical=(85, 300),
        package="TO-92 / SOT-23 variants",
        pinout_hint="常见 TO-92 批次存在 E-B-C / E-C-B 差异，实测前核对丝印资料。",
    ),
    "S8550": TransistorProfile(
        model="S8550",
        bjt_type="PNP",
        description="小功率通用 PNP 三极管",
        vceo_max_v=25.0,
        ic_max_a=0.5,
        p_tot_w=0.625,
        hfe_typical=(85, 300),
        package="TO-92 / SOT-23 variants",
        pinout_hint="常见 TO-92 批次存在 E-B-C / E-C-B 差异，实测前核对丝印资料。",
    ),
    "2N3904": TransistorProfile(
        model="2N3904",
        bjt_type="NPN",
        description="通用小信号 NPN 三极管",
        vceo_max_v=40.0,
        ic_max_a=0.2,
        p_tot_w=0.625,
        hfe_typical=(100, 300),
        package="TO-92",
        pinout_hint="常见 TO-92 正面朝向时为 E-B-C，但不同厂商需核对。",
    ),
    "2N3906": TransistorProfile(
        model="2N3906",
        bjt_type="PNP",
        description="通用小信号 PNP 三极管",
        vceo_max_v=40.0,
        ic_max_a=0.2,
        p_tot_w=0.625,
        hfe_typical=(100, 300),
        package="TO-92",
        pinout_hint="常见 TO-92 正面朝向时为 E-B-C，但不同厂商需核对。",
    ),
    "2N2222": TransistorProfile(
        model="2N2222",
        bjt_type="NPN",
        description="通用开关/放大小信号 NPN 三极管",
        vceo_max_v=40.0,
        ic_max_a=0.6,
        p_tot_w=0.625,
        hfe_typical=(75, 300),
        package="TO-18 / TO-92 variants",
        pinout_hint="金属壳与塑封版本引脚可能不同，必须核对封装。",
    ),
    "BC547": TransistorProfile(
        model="BC547",
        bjt_type="NPN",
        description="低噪声通用小信号 NPN 三极管",
        vceo_max_v=45.0,
        ic_max_a=0.1,
        p_tot_w=0.5,
        hfe_typical=(110, 800),
        package="TO-92",
        pinout_hint="常见 TO-92 正面朝向时为 C-B-E。",
    ),
    "BC557": TransistorProfile(
        model="BC557",
        bjt_type="PNP",
        description="低噪声通用小信号 PNP 三极管",
        vceo_max_v=45.0,
        ic_max_a=0.1,
        p_tot_w=0.5,
        hfe_typical=(110, 800),
        package="TO-92",
        pinout_hint="常见 TO-92 正面朝向时为 C-B-E。",
    ),
    "S9013": TransistorProfile(
        model="S9013",
        bjt_type="NPN",
        description="通用小功率 NPN 三极管",
        vceo_max_v=25.0,
        ic_max_a=0.5,
        p_tot_w=0.625,
        hfe_typical=(64, 300),
        package="TO-92 / SOT-23 variants",
        pinout_hint="国产批次引脚差异较常见，建议先低压确认。",
    ),
    "S9014": TransistorProfile(
        model="S9014",
        bjt_type="NPN",
        description="低噪声小信号 NPN 三极管",
        vceo_max_v=45.0,
        ic_max_a=0.1,
        p_tot_w=0.45,
        hfe_typical=(60, 1000),
        package="TO-92 / SOT-23 variants",
        pinout_hint="国产批次引脚差异较常见，建议先低压确认。",
    ),
    "TIP41C": TransistorProfile(
        model="TIP41C",
        bjt_type="NPN",
        description="中功率 NPN 功率三极管",
        vceo_max_v=100.0,
        ic_max_a=6.0,
        p_tot_w=65.0,
        hfe_typical=(15, 75),
        package="TO-220",
        pinout_hint="常见 TO-220 正面朝向时为 B-C-E，散热片通常接 C。",
    ),
}


def normalize_model_name(model: str) -> str:
    return "".join(ch for ch in model.upper().strip() if ch.isalnum())


def _user_profile_store_path() -> Path:
    return Path(os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))


def lookup_transistor(model: str) -> TransistorProfile:
    from ai.user_profile_store import InvalidUserProfileStoreError, get_user_profile_record

    key = normalize_model_name(model)
    try:
        record = get_user_profile_record(_user_profile_store_path(), model)
    except InvalidUserProfileStoreError:
        record = None
    except RuntimeError:
        record = None
    if record and bool(record.get("enabled", True)):
        return TransistorProfile(
            model=str(record.get("model") or model.strip() or "UNKNOWN"),
            bjt_type=str(record.get("bjt_type") or "UNKNOWN"),
            description=str(record.get("description") or "用户确认沉淀的型号参数"),
            vceo_max_v=float(record.get("vceo_max_v") or 0.0),
            ic_max_a=float(record.get("ic_max_a") or 0.0),
            p_tot_w=float(record.get("p_tot_w") or 0.0),
            hfe_typical=tuple(record.get("hfe_typical") or [0, 0]),
            package=str(record.get("package") or ""),
            pinout_hint=str(record.get("pinout_hint") or ""),
            confidence=str(record.get("confidence") or "user_confirmed"),
        )
    if key in _PROFILES:
        return _PROFILES[key]
    return TransistorProfile(
        model=model.strip() or "UNKNOWN",
        bjt_type="UNKNOWN",
        description="未知 BJT 型号，使用低压保守探测方案",
        vceo_max_v=12.0,
        ic_max_a=0.02,
        p_tot_w=0.1,
        hfe_typical=(0, 0),
        pinout_hint="未知型号必须先确认 datasheet 和引脚，硬件模式只建议低压探测。",
        confidence="fallback",
    )


def build_profile_from_fields(model: str, fields: Mapping[str, float | str]) -> TransistorProfile:
    bjt_type = str(fields["bjt_type"]).upper()
    if bjt_type not in {"NPN", "PNP"}:
        raise ValueError("Unsupported BJT type for profile override")
    return TransistorProfile(
        model=model.strip() or "UNKNOWN",
        bjt_type=bjt_type,
        description="用户补充规格的临时 profile",
        vceo_max_v=float(fields["vceo_max_v"]),
        ic_max_a=float(fields["ic_max_a"]),
        p_tot_w=float(fields["p_tot_w"]),
        hfe_typical=(0, 0),
        confidence="user_supplied",
    )


def known_models() -> Iterable[str]:
    return sorted(_PROFILES)
