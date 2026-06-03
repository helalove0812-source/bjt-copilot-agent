from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services import (
    run_detect,
    run_full_suite,
    run_hardware_selftest,
    run_npn_static_bringup,
    run_scope_check,
)
from core.types import DriverMode, HwConfig


@dataclass
class AppOrchestrator:
    config: HwConfig

    def detect(self, mode: DriverMode):
        return run_detect(mode, self.config)

    def selftest(self, mode: DriverMode):
        return run_hardware_selftest(mode, self.config)

    def scope_check(self, mode: DriverMode, samples: int, frequency_hz: int):
        return run_scope_check(mode, self.config, samples, frequency_hz)

    def npn_static(self, mode: DriverMode, vcc: float, vbb: float):
        return run_npn_static_bringup(mode, self.config, vcc, vbb)

    def scan_curves(self, mode: DriverMode, scan_mode: str):
        from app.services import run_scan_curves
        return run_scan_curves(mode, self.config, scan_mode)

    def full_run(self, mode: DriverMode, dut_label: str, output_dir: Path):
        return run_full_suite(
            mode=mode,
            dut_label=dut_label,
            output_dir=output_dir,
            cfg=self.config,
        )
