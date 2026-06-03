from pathlib import Path

from app.runtime import Runtime
from core import HwConfig, StaticPoint
from utils.config_loader import AppConfig, load_app_config


def test_load_app_config_reads_yaml(tmp_path: Path):
    cfg = tmp_path / "default.yaml"
    cfg.write_text(
        """
driver_mode: simulation
rb_ohm: 22000.0
rc_ohm: 220.0
ic_max_a: 0.03
pmax_w: 0.3
vcc_max: 5.0
lin_ic_lo_a: 0.0005
lin_ic_hi_a: 0.02
lin_vce_lo_v: 2.0
lin_vce_hi_v: 4.0
sample_count: 2048
settle_ms: 20
""".strip()
    )

    result = load_app_config(cfg)

    assert isinstance(result, AppConfig)
    assert result.driver_mode == "simulation"
    assert result.rb_ohm == 22000.0
    assert result.lin_vce_window == (2.0, 4.0)


def test_static_point_region_and_signs_are_explicit():
    cfg = HwConfig(R_B=22_000.0, R_C=220.0)
    point = StaticPoint(
        Vbb=1.5,
        Vcc=5.0,
        Vb=0.68,
        Vc=2.93,
        Ib=37.2e-6,
        Ic=9.41e-3,
        Vbe=0.68,
        Vce=2.93,
        beta=253.0,
        region="active",
    )

    assert cfg.R_B == 22_000.0
    assert point.region == "active"
    assert point.beta > 200


def test_runtime_requires_hw_config_and_driver_contract(fake_driver):
    runtime = Runtime(
        config=HwConfig(),
        driver=fake_driver,
        serial="SIM-BJT-001",
    )

    assert runtime.config.R_C == 220.0
    assert runtime.driver.connect() == "SIM-BJT-001"
    assert runtime.serial.startswith("SIM-")
