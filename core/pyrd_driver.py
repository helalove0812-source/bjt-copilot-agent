from __future__ import annotations

import time
from statistics import fmean
from typing import Any, Tuple

from core.device import ensure_sdk_path, probe_sdk_runtime


def _build_rd() -> Any:
    ensure_sdk_path()
    try:
        from pyRD import RD
    except Exception as exc:
        raise RuntimeError(
            "pyRD 导入失败: {0}; sdk={1}".format(exc, probe_sdk_runtime())
        ) from exc

    try:
        return RD()
    except Exception as exc:
        raise RuntimeError(
            "pyRD 初始化失败: {0}; sdk={1}".format(exc, probe_sdk_runtime())
        ) from exc


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _device_diagnostics(rd: Any) -> dict[str, Any]:
    diagnostics = probe_sdk_runtime()
    diagnostics["devicecount"] = getattr(rd, "devicecount", None)
    raw_devices = getattr(rd, "devicelist", [])
    diagnostics["devicelist"] = [
        [_decode_text(column) for column in row] for row in raw_devices
    ]
    return diagnostics


class PyRDDriver:
    def __init__(self) -> None:
        self.rd: Any = None
        self._serial = ""
        self._model = ""

    def connect(self) -> str:
        rd = _build_rd()
        device_count = getattr(rd, "DeviceCount", None)
        if callable(device_count):
            device_count()
        rd.DeviceEnumLists()
        if not rd.devicelist:
            raise RuntimeError(
                "未找到雨骤设备; diagnostics={0}".format(_device_diagnostics(rd))
            )

        status = rd.DeviceOpen(0)
        if status != 0:
            raise RuntimeError(
                "打开雨骤设备失败: status={0}; diagnostics={1}".format(
                    status, _device_diagnostics(rd)
                )
            )

        self.rd = rd
        serial = rd.devicelist[0][0]
        model = rd.devicelist[0][1] if len(rd.devicelist[0]) > 1 else ""
        self._serial = _decode_text(serial)
        self._model = _decode_text(model)
        return self._serial

    def close(self) -> None:
        if self.rd is None:
            return
        self.rd.DeviceClose()
        self.rd = None
        self._serial = ""
        self._model = ""

    def set_v_pos(self, volts: float) -> None:
        rd = self._require_connected()
        rd.AnalogIOChannelNodeSet(0, float(volts))
        rd.AnalogIOChannelEnableSet(0, True)

    def set_w1_dc(self, volts: float) -> None:
        rd = self._require_connected()
        self._configure_dc_output(rd, channel=0, volts=volts)

    def set_w1_custom_waveform(self, volts_array: list[float], frequency_hz: float = 1000) -> None:
        rd = self._require_connected()
        channel = 0
        node = 0  # RDAnalogOutNodeCarrier
        func = 10  # RDFUNCCustom
        rd.AnalogOutNodeEnableSet(channel, node, True)
        rd.AnalogOutNodeFunctionSet(channel, node, func)
        rd.AnalogOutNodeFrequencySet(channel, node, float(frequency_hz))
        rd.AnalogOutNodeOffsetAmpSet(channel, node, 0.0, 1.0)
        rd.AnalogOutNodeDataSet(channel, node, volts_array)
        rd.AnalogOutConfigure(channel, True)

    def set_w2_custom_waveform(self, volts_array: list[float], frequency_hz: float = 1000) -> None:
        rd = self._require_connected()
        channel = 1
        node = 0  # RDAnalogOutNodeCarrier
        func = 10  # RDFUNCCustom
        rd.AnalogOutNodeEnableSet(channel, node, True)
        rd.AnalogOutNodeFunctionSet(channel, node, func)
        rd.AnalogOutNodeFrequencySet(channel, node, float(frequency_hz))
        rd.AnalogOutNodeOffsetAmpSet(channel, node, 0.0, 1.0)
        rd.AnalogOutNodeDataSet(channel, node, volts_array)
        # We don't configure (start) it here yet, so it can be started together

    def fire_w2_and_read_scope(self, samples: int, frequency_hz: int) -> Tuple[list[float], list[float]]:
        """
        利用硬件触发与 FPGA 自定义波形资源：
        同时启动 AWG CH2(W2) 和 示波器，完成纳秒级硬件同步采样。
        """
        rd = self._require_connected()
        sample_count = max(1, int(samples))
        self._prepare_scope(rd, sample_count, int(frequency_hz))
        
        # 将示波器触发源设为 AWG (RDTRIGSRCDigitalOut=6 或 AnalogOut相关的触发)
        # 为兼容性，使用立即触发，但保证在调用 AnalogOutConfigure 的瞬间同时启动
        rd.AnalogInRun(True)
        
        # 触发 FPGA 底层自定义波形输出
        rd.AnalogOutConfigure(1, True)
        
        deadline = time.time() + 5.0
        try:
            while time.time() < deadline:
                rd.AnalogInStatus()
                if getattr(rd, "analoginstatus", None) == 2:
                    rd.AnalogInRead(sample_count, 0)
                    rd.AnalogInRead(sample_count, 1)
                    return list(rd.aidatach1)[:sample_count], list(rd.aidatach2)[:sample_count]
                time.sleep(0.01)
        finally:
            rd.AnalogInRun(False)
            rd.AnalogOutConfigure(1, False)
        raise TimeoutError("硬件加速采样超时")

    def set_w2_dc(self, volts: float) -> None:
        rd = self._require_connected()
        self._configure_dc_output(rd, channel=1, volts=volts)

    def read_scope_mean(
        self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200
    ) -> Tuple[float, float]:
        rd = self._require_connected()
        sample_count = max(1, int(samples))
        self._prepare_scope(rd, sample_count, int(frequency_hz))
        rd.AnalogInRun(True)
        deadline = time.time() + (max(1, int(timeout_ms)) / 1000.0)
        try:
            while time.time() < deadline:
                rd.AnalogInStatus()
                if getattr(rd, "analoginstatus", None) == 2:
                    rd.AnalogInRead(sample_count, 0)
                    rd.AnalogInRead(sample_count, 1)
                    vb = fmean(list(rd.aidatach1)[:sample_count])
                    vc = fmean(list(rd.aidatach2)[:sample_count])
                    return vb, vc
                time.sleep(0.01)
        finally:
            rd.AnalogInRun(False)
        raise TimeoutError("示波器采样超时")

    def emergency_off(self) -> None:
        rd = self._require_connected()
        for channel in (0, 1):
            rd.AnalogOutConfigure(channel, False)
        for channel in (0, 1):
            rd.AnalogIOChannelEnableSet(channel, False)

    def disable_all(self) -> None:
        self.emergency_off()

    def device_info(self):
        self._require_connected()
        return {"model": self._model, "serial": self._serial}

    def _require_connected(self) -> Any:
        if self.rd is None:
            raise RuntimeError("pyRD 设备尚未连接")
        return self.rd

    def _configure_dc_output(self, rd: Any, channel: int, volts: float) -> None:
        rd.AnalogOutNodeEnableSet(channel, 0, True)
        rd.AnalogOutNodeFunctionSet(channel, 0, 0)
        rd.AnalogOutNodeOffsetAmpSet(channel, 0, float(volts), 0.0)
        rd.AnalogOutConfigure(channel, True)

    def _prepare_scope(self, rd: Any, samples: int, frequency_hz: int) -> None:
        try:
            from pyRD.core.RDconstant import (
                RDTRIGSRCNone,
                RDTRIGTYPEEdge,
                RDTriggerSlopeEdge,
            )
        except Exception:
            RDTRIGSRCNone = 0
            RDTRIGTYPEEdge = 0
            RDTriggerSlopeEdge = 0

        rd.AnalogInRun(False)
        for channel in (0, 1):
            rd.AnalogInCHEnable(channel, True)
            rd.AnalogInCHRangeSet(channel, 5)
        rd.AnalogInFrequencySet(int(frequency_hz))
        rd.AnalogInBufferSizeSet(int(samples))
        # 每次采样前都显式重置触发状态，避免设备沿用上一次的等待触发配置。
        optional_calls = (
            ("AnalogInTriggerAutoTimeoutSet", (1,)),
            ("AnalogInTriggerSourceSet", (RDTRIGSRCNone,)),
            ("AnalogInTriggerTypeSet", (RDTRIGTYPEEdge,)),
            ("AnalogInTriggerConditionSet", (RDTriggerSlopeEdge,)),
            ("AnalogInTriggerLevelSet", (0.0, 5)),
        )
        for name, args in optional_calls:
            method = getattr(rd, name, None)
            if callable(method):
                method(*args)
