from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from analysis.data_processor import beta_median
from analysis.exporters import write_summary_json
from analysis.report import build_artifact_manifest, build_report_summary
from app.runtime import Runtime
from core.pyrd_driver import PyRDDriver
from core.relay_matrix import NullRelayMatrixAdapter, RelayMatrixWrappedDriver, SimulatedRelayMatrixAdapter
from core.simulation_driver import SimulationDriver
from core.types import DeviceReport, DriverMode, HwConfig
from measurement.curves import group_points_by_ib
from measurement.detector import detect_bjt_type
from measurement.linearity import summarize_beta_linearity
from measurement.pin_probe import run_low_voltage_three_pin_probe, run_relay_matrix_pin_permutation_probe
from measurement.static import measure_static_point
from measurement.vce_sat import estimate_vce_sat
from measurement.scanner import scan_curves_software, scan_curves_hardware


def build_driver(mode: DriverMode):
    if mode == "simulation":
        return SimulationDriver()
    return _with_optional_relay_matrix(PyRDDriver())


def _with_optional_relay_matrix(driver):
    backend = os.getenv("BJT_RELAY_MATRIX_BACKEND", "").strip().lower()
    if backend in {"simulated", "simulation", "mock"}:
        return RelayMatrixWrappedDriver(driver, SimulatedRelayMatrixAdapter())
    if backend in {"none", ""}:
        return RelayMatrixWrappedDriver(driver, NullRelayMatrixAdapter())
    raise RuntimeError(
        "未知 BJT_RELAY_MATRIX_BACKEND={0}; 当前支持 none/simulated".format(backend)
    )


def build_runtime(mode: DriverMode, cfg: HwConfig) -> Runtime:
    driver = build_driver(mode)
    serial = driver.connect()
    return Runtime(config=cfg, driver=driver, serial=serial)


def run_detect(mode: DriverMode, cfg: HwConfig):
    runtime = build_runtime(mode, cfg)
    try:
        result = detect_bjt_type(runtime.driver, runtime.config.R_B, runtime.config.R_C)
        return runtime.serial, result
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def _disable_outputs(driver) -> None:
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()
        return

    emergency_off = getattr(driver, "emergency_off", None)
    if callable(emergency_off):
        emergency_off()


def _read_scope_mean(driver, *, samples: int, frequency_hz: int, timeout_ms: int):
    try:
        return driver.read_scope_mean(
            samples=samples,
            frequency_hz=frequency_hz,
            timeout_ms=timeout_ms,
        )
    except TypeError:
        return driver.read_scope_mean(samples)


def _read_device_info(driver, serial: str):
    device_info = getattr(driver, "device_info", None)
    if callable(device_info):
        return device_info()
    return {"serial": serial}


def run_hardware_selftest(mode: DriverMode, cfg: HwConfig):
    runtime = build_runtime(mode, cfg)
    try:
        _disable_outputs(runtime.driver)
        runtime.driver.set_v_pos(1.0)
        _disable_outputs(runtime.driver)
        runtime.driver.set_w1_dc(1.0)
        _disable_outputs(runtime.driver)
        runtime.driver.set_w2_dc(1.0)
        vb, vc = _read_scope_mean(
            runtime.driver,
            samples=2048,
            frequency_hz=100000,
            timeout_ms=200,
        )
        return {
            "serial": runtime.serial,
            "device_info": _read_device_info(runtime.driver, runtime.serial),
            "scope_mean": {"ch1": vb, "ch2": vc},
        }
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def run_scope_check(mode: DriverMode, cfg: HwConfig, samples: int, frequency_hz: int):
    runtime = build_runtime(mode, cfg)
    try:
        _disable_outputs(runtime.driver)
        vb, vc = _read_scope_mean(
            runtime.driver,
            samples=int(samples),
            frequency_hz=int(frequency_hz),
            timeout_ms=200,
        )
        return {
            "serial": runtime.serial,
            "samples": int(samples),
            "frequency_hz": int(frequency_hz),
            "mean": {"ch1": vb, "ch2": vc},
        }
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def run_low_voltage_pin_probe(
    mode: DriverMode,
    cfg: HwConfig,
    *,
    max_probe_voltage_v: float = 1.2,
    max_probe_current_a: float = 0.001,
    samples: int = 512,
):
    runtime = build_runtime(mode, cfg)
    try:
        return {
            "serial": runtime.serial,
            "device_info": _read_device_info(runtime.driver, runtime.serial),
            **run_low_voltage_three_pin_probe(
                runtime.driver,
                cfg=runtime.config,
                mode=mode,
                max_probe_voltage_v=max_probe_voltage_v,
                max_probe_current_a=max_probe_current_a,
                samples=samples,
            ),
        }
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def run_relay_matrix_pin_probe(
    mode: DriverMode,
    cfg: HwConfig,
    *,
    pins: list[str] | None = None,
    max_probe_voltage_v: float = 1.2,
    max_probe_current_a: float = 0.001,
    samples: int = 512,
):
    runtime = build_runtime(mode, cfg)
    try:
        result = run_relay_matrix_pin_permutation_probe(
            runtime.driver,
            cfg=runtime.config,
            mode=mode,
            pins=pins,
            max_probe_voltage_v=max_probe_voltage_v,
            max_probe_current_a=max_probe_current_a,
            samples=samples,
        )
        return {
            "serial": runtime.serial,
            "device_info": _read_device_info(runtime.driver, runtime.serial),
            **result,
        }
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def run_npn_static_bringup(mode: DriverMode, cfg: HwConfig, vcc: float, vbb: float):
    runtime = build_runtime(mode, cfg)
    try:
        bjt_type = detect_bjt_type(runtime.driver, runtime.config.R_B, runtime.config.R_C)
        if bjt_type != "NPN":
            raise RuntimeError("检测结果不是明确 NPN，停止静态点测试。")
        return measure_static_point(
            runtime.driver,
            bjt_type="NPN",
            cfg=runtime.config,
            Vbb=float(vbb),
            Vcc=float(vcc),
        )
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()


def run_scan_curves(mode: DriverMode, cfg: HwConfig, scan_mode: str = "software"):
    runtime = build_runtime(mode, cfg)
    try:
        bjt_type = detect_bjt_type(runtime.driver, runtime.config.R_B, runtime.config.R_C)
        if bjt_type != "NPN":
            raise RuntimeError("检测结果不是明确 NPN，停止曲线扫描。")
            
        vbb_steps = [1.0, 1.5, 2.0, 2.5, 3.0]
        vcc_steps = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        
        if scan_mode == "hardware":
            points = scan_curves_hardware(
                runtime.driver, 
                bjt_type, 
                runtime.config, 
                vbb_steps, 
                vcc_steps
            )
        else:
            points = scan_curves_software(
                runtime.driver, 
                bjt_type, 
                runtime.config, 
                vbb_steps, 
                vcc_steps
            )
            
        return points
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()

def run_full_suite(
    *,
    mode: DriverMode,
    dut_label: str,
    output_dir: Path,
    cfg: HwConfig,
    scan_mode: str = "software",
):
    runtime = build_runtime(mode, cfg)
    started_at = datetime.now()
    try:
        bjt_type = detect_bjt_type(runtime.driver, runtime.config.R_B, runtime.config.R_C)
        if bjt_type != "NPN":
            raise RuntimeError("检测结果不是明确 NPN，停止完整测试。")
        point = measure_static_point(
            runtime.driver,
            bjt_type=bjt_type,
            cfg=runtime.config,
            Vbb=2.0,
            Vcc=3.0,
        )
        vbb_steps = [1.0, 1.5, 2.0, 2.5, 3.0]
        vcc_steps = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        if scan_mode == "hardware":
            output_curve_points = scan_curves_hardware(
                runtime.driver,
                bjt_type,
                runtime.config,
                vbb_steps,
                vcc_steps,
            )
        else:
            output_curve_points = scan_curves_software(
                runtime.driver,
                bjt_type,
                runtime.config,
                vbb_steps,
                vcc_steps,
            )
        beta_curve = [curve_point for curve_point in output_curve_points if curve_point.region == "active"] or [point]
        output_curves = group_points_by_ib(output_curve_points)
        vce_sat, ic_at_sat = estimate_vce_sat(point, ic_floor_a=0.0)
        linearity = summarize_beta_linearity(beta_curve, runtime.config, min_points=1)
        report = DeviceReport(
            bjt_type=bjt_type,
            serial=runtime.serial,
            dut_label=dut_label,
            beta_median=beta_median(beta_curve),
            beta_active_curve=beta_curve,
            vce_sat=vce_sat,
            Ic_at_sat=ic_at_sat,
            output_curves=output_curves,
            early_voltage=None,
            beta_linearity=linearity,
            hw_config=runtime.config,
            started_at=started_at,
            finished_at=datetime.now(),
            reference_point=point,
        )
        write_summary_json(report, output_dir)
        build_report_summary(report, build_artifact_manifest(output_dir))
        return report
    finally:
        _disable_outputs(runtime.driver)
        runtime.driver.close()
