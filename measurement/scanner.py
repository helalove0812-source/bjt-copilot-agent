from __future__ import annotations

import time
import numpy as np

from core.types import HwConfig, StaticPoint
from measurement.static import build_static_point


def _extract_hardware_step_means(
    vb_array: list[float],
    vc_array: list[float],
    *,
    vcc_steps: list[float],
    repeats: int,
) -> list[tuple[float, float, float]]:
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    total_plateaus = len(vcc_steps) * repeats
    if total_plateaus <= 0:
        return []
    plateau_len = min(len(vb_array), len(vc_array)) // total_plateaus
    if plateau_len <= 0:
        raise ValueError("insufficient samples for hardware plateau extraction")

    step_means = []
    settle_offset = max(1, plateau_len // 2)
    for step_index, vcc in enumerate(vcc_steps):
        vb_plateaus = []
        vc_plateaus = []
        for repeat_index in range(repeats):
            plateau_index = step_index * repeats + repeat_index
            start_idx = plateau_index * plateau_len + settle_offset
            end_idx = (plateau_index + 1) * plateau_len
            if end_idx <= start_idx:
                continue
            vb_plateaus.append(float(np.mean(vb_array[start_idx:end_idx])))
            vc_plateaus.append(float(np.mean(vc_array[start_idx:end_idx])))
        if vb_plateaus and vc_plateaus:
            step_means.append((vcc, float(np.mean(vb_plateaus)), float(np.mean(vc_plateaus))))
    return step_means


def scan_curves_software(driver, bjt_type: str, cfg: HwConfig, vbb_steps: list[float], vcc_steps: list[float]) -> list[StaticPoint]:
    """
    软件轮询模式：
    CPU 依次下发指令控制电压，每次 sleep 等待稳定后调用示波器读取。
    速度较慢，受 USB 延迟限制。
    """
    points = []
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()

    for vbb in vbb_steps:
        driver.set_w1_dc(vbb)
        # 每切换基极电压，稍微多等一会儿让电路稳定
        time.sleep(0.05)
        for vcc in vcc_steps:
            driver.set_v_pos(vcc)
            time.sleep(0.02)
            
            # 使用普通的 scope 读取，带超时
            try:
                vb, vc = driver.read_scope_mean(
                    samples=256,
                    frequency_hz=100000,
                    timeout_ms=100,
                )
            except TypeError:
                vb, vc = driver.read_scope_mean(samples=256)
                
            point = build_static_point(
                bjt_type=bjt_type,
                R_B=cfg.R_B,
                R_C=cfg.R_C,
                Vbb=vbb,
                Vcc=vcc,
                Vb=float(vb),
                Vc=float(vc),
            )
            points.append(point)
            
    if callable(disable_all):
        disable_all()
    return points


def scan_curves_hardware(driver, bjt_type: str, cfg: HwConfig, vbb_steps: list[float], vcc_steps: list[float]) -> list[StaticPoint]:
    """
    硬件加速模式：
    使用自定义 IP，将 Vcc 阶梯波一次性下发到 FPGA，并通过硬件触发同步读取。
    实现超高速、无热漂移扫描。
    """
    points = []
    disable_all = getattr(driver, "disable_all", None)
    if callable(disable_all):
        disable_all()

    # 针对每一个固定的 Vbb (基极电流台阶)，用硬件打出一条 Vcc (集电极电压) 扫描曲线
    for vbb in vbb_steps:
        driver.set_w1_dc(vbb)
        time.sleep(0.05)
        
        # 构造阶梯波（每个台阶维持一定时间，这里通过重复点来实现）
        # 假设 AWG 输出率 1000Hz (即每个点 1ms)。
        repeats = 5
        waveform = []
        for vcc in vcc_steps:
            waveform.extend([vcc] * repeats)
            
        awg_freq = 1000.0
        
        # 示波器采样率需要和 AWG 匹配。
        scope_freq = 100000
        total_time = len(waveform) / awg_freq
        scope_samples = int(total_time * scope_freq)
        
        # 将阶梯波装载到 AWG CH2 (W2) 的 BRAM 中，这里需要把 W2 接到集电极
        driver.set_w2_custom_waveform(waveform, awg_freq)
        
        # 同时启动 AWG 和 Scope，实现硬件同步采样
        try:
            vb_array, vc_array = driver.fire_w2_and_read_scope(
                samples=scope_samples,
                frequency_hz=scope_freq
            )
        except Exception as e:
            # 如果硬件加速异常，或者设备不支持，记录异常但不直接崩溃
            raise RuntimeError(f"硬件加速扫描失败: {e}")
            
        # 采样数组实际对应 len(vcc_steps) * repeats 个平台。
        # 这里先按平台切开，再把同一个 Vcc 的 repeats 个平台求平均。
        for vcc, vb, vc in _extract_hardware_step_means(
            vb_array,
            vc_array,
            vcc_steps=vcc_steps,
            repeats=repeats,
        ):
            point = build_static_point(
                bjt_type=bjt_type,
                R_B=cfg.R_B,
                R_C=cfg.R_C,
                Vbb=vbb,
                Vcc=vcc,
                Vb=float(vb),
                Vc=float(vc),
            )
            points.append(point)

    if callable(disable_all):
        disable_all()
    return points
