# Hardware Bring-Up Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-first real-hardware bring-up path for `Raindrop Model S`, including self-test, scope readiness polling, deterministic shutdown, and minimal NPN static measurement.

**Architecture:** Strengthen `core/pyrd_driver.py` into a real bring-up driver, keep measurement math pure in `measurement/static.py`, and expose hardware-first services through `app/services.py` plus focused CLI commands. The GUI remains untouched unless it needs to consume already-validated services later.

**Tech Stack:** Python 3.9, pyRD, pytest, argparse

---

## File Map

### Core Hardware Layer

- Modify: `core/pyrd_driver.py`
- Modify: `core/psu.py`
- Modify: `core/awg.py`
- Modify: `core/scope.py`
- Modify: `core/safety.py`

### Measurement Layer

- Modify: `measurement/static.py`
- Modify: `measurement/detector.py`

### App Layer

- Modify: `app/services.py`
- Modify: `app/orchestrator.py`

### CLI And Docs

- Modify: `cli.py`
- Modify: `README.md`

### Tests

- Modify: `tests/test_detector_logic.py`
- Modify: `tests/test_static_math.py`
- Modify: `tests/test_safety.py`
- Modify: `tests/test_cli_smoke.py`
- Modify: `tests/conftest.py`

---

### Task 1: Harden `PyRDDriver` For Real Bring-Up

**Files:**
- Modify: `core/pyrd_driver.py`
- Modify: `tests/test_detector_logic.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing driver sequencing test**

```python
from core.pyrd_driver import PyRDDriver


class FakeRD:
    def __init__(self):
        self.devicelist = [(b"SERIAL-001", b"Model S")]
        self.analoginstatus = 0
        self.aidatach1 = [0.12, 0.14, 0.16]
        self.aidatach2 = [1.10, 1.20, 1.30]
        self.calls = []

    def DeviceEnumLists(self):
        self.calls.append(("DeviceEnumLists",))

    def DeviceOpen(self, index):
        self.calls.append(("DeviceOpen", index))
        return 0

    def DeviceClose(self):
        self.calls.append(("DeviceClose",))
        return 0

    def AnalogInCHEnable(self, ch, enabled):
        self.calls.append(("AnalogInCHEnable", ch, enabled))

    def AnalogInCHRangeSet(self, ch, value):
        self.calls.append(("AnalogInCHRangeSet", ch, value))

    def AnalogInFrequencySet(self, value):
        self.calls.append(("AnalogInFrequencySet", value))

    def AnalogInBufferSizeSet(self, value):
        self.calls.append(("AnalogInBufferSizeSet", value))

    def AnalogInRun(self, enabled):
        self.calls.append(("AnalogInRun", enabled))

    def AnalogInStatus(self):
        self.calls.append(("AnalogInStatus",))
        self.analoginstatus = 2

    def AnalogInRead(self, count, ch):
        self.calls.append(("AnalogInRead", count, ch))

    def AnalogOutConfigure(self, ch, enabled):
        self.calls.append(("AnalogOutConfigure", ch, enabled))

    def AnalogIOChannelEnableSet(self, ch, enabled):
        self.calls.append(("AnalogIOChannelEnableSet", ch, enabled))


def test_pyrd_driver_reads_scope_with_polling(monkeypatch):
    fake_rd = FakeRD()

    def fake_factory():
        return fake_rd

    monkeypatch.setattr("core.pyrd_driver._build_rd", fake_factory)

    driver = PyRDDriver()
    assert driver.connect() == "SERIAL-001"

    vb, vc = driver.read_scope_mean(samples=3, frequency_hz=100000, timeout_ms=100)

    assert round(vb, 2) == 0.14
    assert round(vc, 2) == 1.20
    assert ("AnalogInStatus",) in fake_rd.calls
    assert ("AnalogInRun", False) in fake_rd.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_detector_logic.py -k pyrd_driver_reads_scope_with_polling -v`

Expected: FAIL because `read_scope_mean(..., frequency_hz, timeout_ms)` and `_build_rd()` do not exist yet

- [ ] **Step 3: Implement the minimal real bring-up driver changes**

```python
# core/pyrd_driver.py
from __future__ import annotations

import time
from statistics import fmean

from core.device import ensure_sdk_path


def _build_rd():
    ensure_sdk_path()
    from pyRD import RD

    return RD()


class PyRDDriver:
    def __init__(self) -> None:
        self.rd = None

    def connect(self) -> str:
        rd = _build_rd()
        rd.DeviceEnumLists()
        if not rd.devicelist:
            raise RuntimeError("未找到雨骤设备")
        status = rd.DeviceOpen(0)
        if status != 0:
            raise RuntimeError("打开雨骤设备失败")
        self.rd = rd
        serial = rd.devicelist[0][0]
        return serial.decode("utf-8") if isinstance(serial, bytes) else str(serial)

    def read_scope_mean(self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200) -> tuple[float, float]:
        rd = self._require_connected()
        rd.AnalogInCHEnable(0, True)
        rd.AnalogInCHRangeSet(0, 5)
        rd.AnalogInCHEnable(1, True)
        rd.AnalogInCHRangeSet(1, 5)
        rd.AnalogInFrequencySet(int(frequency_hz))
        rd.AnalogInBufferSizeSet(int(samples))
        rd.AnalogInRun(True)
        deadline = time.time() + (timeout_ms / 1000.0)
        try:
            while time.time() < deadline:
                rd.AnalogInStatus()
                if getattr(rd, "analoginstatus", None) == 2:
                    rd.AnalogInRead(int(samples), 0)
                    rd.AnalogInRead(int(samples), 1)
                    return fmean(list(rd.aidatach1)[:samples]), fmean(list(rd.aidatach2)[:samples])
                time.sleep(0.01)
        finally:
            rd.AnalogInRun(False)
        raise TimeoutError("示波器采样超时")

    def disable_psu(self) -> None:
        rd = self._require_connected()
        rd.AnalogIOChannelEnableSet(0, False)
        rd.AnalogIOChannelEnableSet(1, False)

    def disable_awg(self) -> None:
        rd = self._require_connected()
        rd.AnalogOutConfigure(0, False)
        rd.AnalogOutConfigure(1, False)

    def disable_all(self) -> None:
        self.disable_awg()
        self.disable_psu()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_detector_logic.py -k pyrd_driver_reads_scope_with_polling -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/pyrd_driver.py tests/test_detector_logic.py tests/conftest.py
git commit -m "feat: harden pyrd driver for hardware bring-up"
```

---

### Task 2: Add Hardware Self-Test Service

**Files:**
- Modify: `app/services.py`
- Modify: `app/orchestrator.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing self-test service test**

```python
from core.types import HwConfig
from app.services import run_hardware_selftest


class FakeDriver:
    def __init__(self):
        self.events = []

    def connect(self):
        self.events.append("connect")
        return "SERIAL-001"

    def close(self):
        self.events.append("close")

    def set_v_pos(self, volts):
        self.events.append(("v_pos", volts))

    def set_w1_dc(self, volts):
        self.events.append(("w1", volts))

    def set_w2_dc(self, volts):
        self.events.append(("w2", volts))

    def read_scope_mean(self, samples, frequency_hz=100000, timeout_ms=200):
        self.events.append(("scope", samples, frequency_hz, timeout_ms))
        return 0.11, 1.22

    def disable_all(self):
        self.events.append("disable_all")

    def device_info(self):
        return {"model": "Model S", "serial": "SERIAL-001"}


def test_run_hardware_selftest_orders_outputs_and_shutdown(monkeypatch):
    fake = FakeDriver()

    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    result = run_hardware_selftest("hardware", HwConfig())

    assert result["serial"] == "SERIAL-001"
    assert result["scope_mean"] == {"ch1": 0.11, "ch2": 1.22}
    assert fake.events[0] == "connect"
    assert fake.events[-2] == "disable_all"
    assert fake.events[-1] == "close"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_smoke.py -k run_hardware_selftest_orders_outputs_and_shutdown -v`

Expected: FAIL because `run_hardware_selftest()` does not exist yet

- [ ] **Step 3: Implement the minimal self-test service**

```python
# app/services.py
def run_hardware_selftest(mode, cfg):
    runtime = build_runtime(mode, cfg)
    try:
        runtime.driver.disable_all()
        runtime.driver.set_v_pos(1.0)
        runtime.driver.disable_all()
        runtime.driver.set_w1_dc(1.0)
        runtime.driver.disable_all()
        runtime.driver.set_w2_dc(1.0)
        vb, vc = runtime.driver.read_scope_mean(samples=2048, frequency_hz=100000, timeout_ms=200)
        info = runtime.driver.device_info()
        return {
            "serial": runtime.serial,
            "device_info": info,
            "scope_mean": {"ch1": vb, "ch2": vc},
        }
    finally:
        runtime.driver.disable_all()
        runtime.driver.close()
```

```python
# app/orchestrator.py
def selftest(self, mode, cfg):
    return run_hardware_selftest(mode, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_smoke.py -k run_hardware_selftest_orders_outputs_and_shutdown -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services.py app/orchestrator.py tests/test_cli_smoke.py
git commit -m "feat: add hardware selftest service"
```

---

### Task 3: Expose `selftest` And `scope-check` In CLI

**Files:**
- Modify: `cli.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing CLI self-test smoke test**

```python
import subprocess
import sys


def test_cli_selftest_simulation_smoke():
    proc = subprocess.run(
        [sys.executable, "cli.py", "selftest", "--mode", "simulation"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "scope_mean" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_smoke.py -k cli_selftest_simulation_smoke -v`

Expected: FAIL because `selftest` command is not registered yet

- [ ] **Step 3: Implement the CLI commands**

```python
# cli.py
import argparse
import json

from app.orchestrator import AppOrchestrator
from core.types import HwConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["detect", "selftest", "scope-check", "npn-static"])
    parser.add_argument("--mode", choices=["hardware", "simulation"], default="hardware")
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--freq", type=int, default=100000)
    parser.add_argument("--vcc", type=float, default=3.0)
    parser.add_argument("--vbb", type=float, default=2.0)
    args = parser.parse_args()

    orchestrator = AppOrchestrator()
    cfg = HwConfig()

    if args.command == "selftest":
        print(json.dumps(orchestrator.selftest(args.mode, cfg), ensure_ascii=False))
        return 0
    if args.command == "scope-check":
        print(json.dumps(orchestrator.scope_check(args.mode, cfg, args.samples, args.freq), ensure_ascii=False))
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_smoke.py -k cli_selftest_simulation_smoke -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli_smoke.py
git commit -m "feat: add cli selftest and scope-check commands"
```

---

### Task 4: Add Real Scope-Check And Timeout Paths

**Files:**
- Modify: `app/services.py`
- Modify: `tests/test_detector_logic.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing timeout test**

```python
import pytest

from core.pyrd_driver import PyRDDriver


class NeverReadyRD:
    def __init__(self):
        self.devicelist = [(b"SERIAL-001", b"Model S")]
        self.analoginstatus = 0

    def DeviceEnumLists(self): ...
    def DeviceOpen(self, index): return 0
    def DeviceClose(self): return 0
    def AnalogInCHEnable(self, ch, enabled): ...
    def AnalogInCHRangeSet(self, ch, value): ...
    def AnalogInFrequencySet(self, value): ...
    def AnalogInBufferSizeSet(self, value): ...
    def AnalogInRun(self, enabled): ...
    def AnalogInStatus(self): self.analoginstatus = 1


def test_pyrd_driver_raises_timeout_when_scope_never_ready(monkeypatch):
    monkeypatch.setattr("core.pyrd_driver._build_rd", lambda: NeverReadyRD())
    driver = PyRDDriver()
    driver.connect()

    with pytest.raises(TimeoutError):
        driver.read_scope_mean(samples=128, frequency_hz=100000, timeout_ms=20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_detector_logic.py -k scope_never_ready -v`

Expected: FAIL because timeout path is not fully exercised or not yet exposed cleanly

- [ ] **Step 3: Implement scope-check service and timeout-safe reporting**

```python
# app/services.py
def run_scope_check(mode, cfg, samples, frequency_hz):
    runtime = build_runtime(mode, cfg)
    try:
        runtime.driver.disable_all()
        vb, vc = runtime.driver.read_scope_mean(samples=samples, frequency_hz=frequency_hz, timeout_ms=200)
        return {
            "serial": runtime.serial,
            "samples": int(samples),
            "frequency_hz": int(frequency_hz),
            "mean": {"ch1": vb, "ch2": vc},
        }
    finally:
        runtime.driver.disable_all()
        runtime.driver.close()
```

```python
# app/orchestrator.py
def scope_check(self, mode, cfg, samples, frequency_hz):
    return run_scope_check(mode, cfg, samples, frequency_hz)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_detector_logic.py -k scope_never_ready -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services.py app/orchestrator.py tests/test_detector_logic.py tests/test_cli_smoke.py
git commit -m "feat: add scope-check flow and timeout handling"
```

---

### Task 5: Implement Minimal NPN Static Bring-Up

**Files:**
- Modify: `measurement/static.py`
- Modify: `app/services.py`
- Modify: `cli.py`
- Modify: `tests/test_static_math.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing NPN bring-up test**

```python
from core.types import HwConfig
from app.services import run_npn_static_bringup


class FakeDriver:
    def __init__(self):
        self.events = []

    def connect(self):
        self.events.append("connect")
        return "SERIAL-001"

    def close(self):
        self.events.append("close")

    def disable_all(self):
        self.events.append("disable_all")

    def set_v_pos(self, volts):
        self.events.append(("v_pos", volts))

    def set_w1_dc(self, volts):
        self.events.append(("w1", volts))

    def read_scope_mean(self, samples, frequency_hz=100000, timeout_ms=200):
        self.events.append(("scope", samples, frequency_hz, timeout_ms))
        return 0.68, 2.90


def test_run_npn_static_bringup_returns_static_point(monkeypatch):
    fake = FakeDriver()
    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    point = run_npn_static_bringup("hardware", HwConfig(), vcc=3.0, vbb=2.0)

    assert round(point.Vbe, 2) == 0.68
    assert round(point.Vce, 2) == 2.90
    assert fake.events[-2] == "disable_all"
    assert fake.events[-1] == "close"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_smoke.py -k run_npn_static_bringup_returns_static_point -v`

Expected: FAIL because `run_npn_static_bringup()` does not exist yet

- [ ] **Step 3: Implement minimal real NPN bring-up**

```python
# measurement/static.py
def measure_static_point(driver, bjt_type, cfg, Vbb, Vcc, samples=2048, frequency_hz=100000, timeout_ms=200):
    driver.disable_all()
    driver.set_v_pos(float(Vcc))
    driver.set_w1_dc(float(Vbb))
    vb, vc = driver.read_scope_mean(samples=samples, frequency_hz=frequency_hz, timeout_ms=timeout_ms)
    point = build_static_point(
        bjt_type=bjt_type,
        R_B=cfg.R_B,
        R_C=cfg.R_C,
        Vbb=float(Vbb),
        Vcc=float(Vcc),
        Vb=vb,
        Vc=vc,
    )
    return point
```

```python
# app/services.py
def run_npn_static_bringup(mode, cfg, vcc, vbb):
    runtime = build_runtime(mode, cfg)
    try:
        point = measure_static_point(runtime.driver, "NPN", runtime.config, Vbb=vbb, Vcc=vcc)
        return point
    finally:
        runtime.driver.disable_all()
        runtime.driver.close()
```

```python
# cli.py
if args.command == "npn-static":
    point = orchestrator.npn_static(args.mode, cfg, args.vcc, args.vbb)
    print(json.dumps({"Vbe": point.Vbe, "Vce": point.Vce, "Ib": point.Ib, "Ic": point.Ic, "beta": point.beta}, ensure_ascii=False))
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_smoke.py -k run_npn_static_bringup_returns_static_point -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add measurement/static.py app/services.py cli.py tests/test_static_math.py tests/test_cli_smoke.py
git commit -m "feat: add npn static hardware bring-up flow"
```

---

### Task 6: Add Deterministic Shutdown Logging And Bench README

**Files:**
- Modify: `core/safety.py`
- Modify: `README.md`
- Modify: `tests/test_safety.py`

- [ ] **Step 1: Write the failing shutdown metadata test**

```python
from core.safety import SafetyGuard
from core.types import HwConfig, StaticPoint


class StubDriver:
    def __init__(self):
        self.off_called = False

    def emergency_off(self):
        self.off_called = True


def test_safety_guard_records_abort_reason():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Ic_max_A=0.01), driver, command_name="npn-static")
    point = StaticPoint(2.0, 3.0, 0.7, 0.1, 10e-6, 20e-3, 0.7, 0.1, 2000, "active")

    try:
        guard.check(point)
    except Exception:
        pass

    assert guard.last_abort_reason == "Ic 过流"
    assert guard.last_abort_context["command"] == "npn-static"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_safety.py -k records_abort_reason -v`

Expected: FAIL because `last_abort_reason` and `last_abort_context` do not exist yet

- [ ] **Step 3: Implement minimal abort metadata and README runbook**

```python
# core/safety.py
class SafetyGuard:
    def __init__(self, cfg, driver, command_name="unknown"):
        self.cfg = cfg
        self.driver = driver
        self.command_name = command_name
        self.last_abort_reason = ""
        self.last_abort_context = {}

    def _abort(self, reason):
        self.last_abort_reason = reason
        self.last_abort_context = {"command": self.command_name, "reason": reason}
        self.driver.emergency_off()
        raise SafetyAbort(reason)
```

```md
## Hardware Bring-Up

### 1. Self-Test

```bash
python3 cli.py selftest --mode hardware
```

Expected:
- device opens
- V+, W1, W2 are toggled
- CH1/CH2 mean values are printed
- outputs are disabled before exit

### 2. Scope Check

```bash
python3 cli.py scope-check --mode hardware --samples 2048 --freq 100000
```

### 3. NPN Static Bring-Up

```bash
python3 cli.py npn-static --mode hardware --vcc 3.0 --vbb 2.0
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_safety.py -k records_abort_reason -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/safety.py README.md tests/test_safety.py
git commit -m "docs: add hardware bring-up runbook"
```

---

## Self-Review

### Spec Coverage

- real hardware driver strengthening: Task 1
- hardware self-test: Task 2 and Task 3
- scope polling and timeout handling: Task 1 and Task 4
- NPN minimal real measurement: Task 5
- deterministic shutdown and logging: Task 6
- README bench workflow: Task 6

### Placeholder Scan

- no `TODO` or `TBD` placeholders remain
- every task names exact files
- every task includes specific tests, commands, and minimal code

### Type Consistency

- `run_hardware_selftest`, `run_scope_check`, and `run_npn_static_bringup` are introduced before CLI references them
- `read_scope_mean(samples, frequency_hz, timeout_ms)` is used consistently across driver and services
- `build_static_point()` stays pure and `measure_static_point()` stays sequencing-oriented
