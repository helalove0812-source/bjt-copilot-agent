from __future__ import annotations

from math import isfinite
from typing import Any

from core.types import HwConfig, StaticPoint


class SafetyAbort(RuntimeError):
    pass


class SafetyGuard:
    def __init__(self, cfg: HwConfig, driver: Any, command_name: str = "unknown") -> None:
        self.cfg = cfg
        self.driver = driver
        self.command_name = command_name
        self.last_abort_reason = ""
        self.last_abort_context = {}
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _abort(self, reason: str) -> None:
        self.last_abort_reason = reason
        self.last_abort_context = {
            "command": self.command_name,
            "reason": reason,
        }
        self.driver.emergency_off()
        raise SafetyAbort(reason)

    def check(self, point: StaticPoint) -> StaticPoint:
        if self._stop_requested:
            self._abort("用户停止")

        values = (point.Ib, point.Ic, point.Vbe, point.Vce)
        if not all(isfinite(value) for value in values):
            self._abort("测量状态无效")

        if abs(point.Vb) < 0.1 and abs(point.Vc) < 0.1:
            if abs(point.Vbb) > 0.5 or abs(point.Vcc) > 0.5:
                self._abort("测量点电压接近0V (请检查夹具线缆是否连接或器件是否短路)")

        if abs(point.Vb - point.Vbb) < 0.1 and abs(point.Vc - point.Vcc) < 0.1:
            if abs(point.Vbb) > 0.5 or abs(point.Vcc) > 0.5:
                self._abort("未检测到器件接入 (开路)")

        if abs(point.Vce) > self.cfg.Vcc_max:
            self._abort("测量状态异常")

        if abs(point.Ic) > self.cfg.Ic_max_A:
            self._abort("Ic 过流")

        if abs(point.Vce * point.Ic) > self.cfg.Pmax_W:
            self._abort("功耗超限")

        return point
