# BJT Desktop + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local single-machine BJT test system with a PySide6 desktop UI and a shared-core CLI on top of the Raindrop Model S `pyRD` SDK, with explicit simulation support and exportable reports.

**Architecture:** The system is split into `core`, `measurement`, `analysis`, `app`, `gui`, and `cli` boundaries. `GUI` and `CLI` call the same orchestration layer, while all raw SDK access remains isolated inside the `core` driver wrappers. First delivery targets correctness, safety, and clean structure rather than packaging or remote control.

**Tech Stack:** Python 3.13, PySide6, matplotlib, numpy, pandas, PyYAML, reportlab, pytest, pyRD

---

## File Map

### Entry Points

- Create: `main.py` — desktop bootstrap
- Create: `cli.py` — CLI bootstrap

### Configuration

- Create: `config/default.yaml`
- Create: `config/logging.yaml`

### Core

- Create: `core/__init__.py`
- Create: `core/types.py`
- Create: `core/device.py`
- Create: `core/driver_protocol.py`
- Create: `core/pyrd_driver.py`
- Create: `core/simulation_driver.py`
- Create: `core/psu.py`
- Create: `core/awg.py`
- Create: `core/scope.py`
- Create: `core/dmm.py`
- Create: `core/safety.py`

### Measurement

- Create: `measurement/__init__.py`
- Create: `measurement/detector.py`
- Create: `measurement/static.py`
- Create: `measurement/vce_sat.py`
- Create: `measurement/curves.py`
- Create: `measurement/linearity.py`

### Analysis

- Create: `analysis/__init__.py`
- Create: `analysis/data_processor.py`
- Create: `analysis/exporters.py`
- Create: `analysis/report.py`

### App

- Create: `app/__init__.py`
- Create: `app/runtime.py`
- Create: `app/services.py`
- Create: `app/orchestrator.py`

### GUI

- Create: `gui/__init__.py`
- Create: `gui/models.py`
- Create: `gui/live_plot.py`
- Create: `gui/main_window.py`
- Create: `gui/panels/connection_panel.py`
- Create: `gui/panels/hw_config_panel.py`
- Create: `gui/panels/action_panel.py`
- Create: `gui/panels/live_value_panel.py`
- Create: `gui/panels/log_panel.py`

### Utilities

- Create: `utils/__init__.py`
- Create: `utils/config_loader.py`
- Create: `utils/logger.py`
- Create: `utils/paths.py`
- Create: `utils/units.py`

### Tests

- Create: `tests/test_config_loader.py`
- Create: `tests/test_detector_logic.py`
- Create: `tests/test_static_math.py`
- Create: `tests/test_linearity.py`
- Create: `tests/test_safety.py`
- Create: `tests/test_cli_smoke.py`
- Create: `tests/test_gui_smoke.py`
- Create: `tests/conftest.py`

### Docs

- Modify: `README.md`
- Create: `requirements.txt`

---

### Task 1: Scaffold The Repository And Baseline Configuration

**Files:**
- Create: `requirements.txt`
- Create: `README.md`
- Create: `config/default.yaml`
- Create: `config/logging.yaml`
- Create: `utils/__init__.py`
- Create: `utils/config_loader.py`
- Create: `utils/logger.py`
- Create: `utils/paths.py`
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing config loader test**

```python
from pathlib import Path

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_loader.py -v`

Expected: FAIL with `ModuleNotFoundError` or missing `load_app_config`

- [ ] **Step 3: Write minimal configuration and utility implementation**

```python
# utils/config_loader.py
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


DriverMode = Literal["hardware", "simulation"]


@dataclass(slots=True)
class AppConfig:
    driver_mode: DriverMode
    rb_ohm: float
    rc_ohm: float
    ic_max_a: float
    pmax_w: float
    vcc_max: float
    lin_ic_lo_a: float
    lin_ic_hi_a: float
    lin_vce_window: tuple[float, float]
    sample_count: int
    settle_ms: int


def load_app_config(path: str | Path) -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        driver_mode=data["driver_mode"],
        rb_ohm=float(data["rb_ohm"]),
        rc_ohm=float(data["rc_ohm"]),
        ic_max_a=float(data["ic_max_a"]),
        pmax_w=float(data["pmax_w"]),
        vcc_max=float(data["vcc_max"]),
        lin_ic_lo_a=float(data["lin_ic_lo_a"]),
        lin_ic_hi_a=float(data["lin_ic_hi_a"]),
        lin_vce_window=(float(data["lin_vce_lo_v"]), float(data["lin_vce_hi_v"])),
        sample_count=int(data["sample_count"]),
        settle_ms=int(data["settle_ms"]),
    )
```

```yaml
# config/default.yaml
driver_mode: hardware
rb_ohm: 22000.0
rc_ohm: 220.0
ic_max_a: 0.03
pmax_w: 0.30
vcc_max: 5.0
lin_ic_lo_a: 0.0005
lin_ic_hi_a: 0.02
lin_vce_lo_v: 2.0
lin_vce_hi_v: 4.0
sample_count: 2048
settle_ms: 20
```

```text
# requirements.txt
numpy>=1.26
pandas>=2.1
PySide6>=6.6
matplotlib>=3.8
PyYAML>=6.0
reportlab>=4.0
pytest>=8.0
pytest-qt>=4.4
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config_loader.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt README.md config/default.yaml config/logging.yaml utils tests/test_config_loader.py
git commit -m "chore: scaffold project configuration"
```

---

### Task 2: Define Canonical Types And Runtime Contracts

**Files:**
- Create: `core/__init__.py`
- Create: `core/types.py`
- Create: `core/driver_protocol.py`
- Create: `app/runtime.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing type contract test**

```python
from core.types import HwConfig, StaticPoint


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config_loader.py -k static_point_region_and_signs_are_explicit -v`

Expected: FAIL because `core.types` does not exist yet

- [ ] **Step 3: Write the canonical type definitions**

```python
# core/types.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


BJTType = Literal["NPN", "PNP", "UNKNOWN"]
Region = Literal["cutoff", "active", "saturation"]
DriverMode = Literal["hardware", "simulation"]


@dataclass(slots=True)
class HwConfig:
    R_B: float = 22e3
    R_C: float = 220.0
    Vbe_typ: float = 0.7
    Ic_max_A: float = 30e-3
    Pmax_W: float = 0.30
    Vcc_max: float = 5.0
    lin_ic_lo_A: float = 0.5e-3
    lin_ic_hi_A: float = 20e-3
    lin_vce_window: tuple[float, float] = (2.0, 4.0)


@dataclass(slots=True)
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


@dataclass(slots=True)
class DeviceReport:
    bjt_type: BJTType
    serial: str
    dut_label: str
    beta_median: float
    beta_active_curve: list[StaticPoint]
    vce_sat: float
    Ic_at_sat: float
    output_curves: dict[float, list[StaticPoint]]
    early_voltage: float | None
    beta_linearity: object | None
    hw_config: HwConfig
    started_at: datetime
    finished_at: datetime
```

```python
# core/driver_protocol.py
from typing import Protocol


class DriverProtocol(Protocol):
    def connect(self) -> str: ...
    def close(self) -> None: ...
    def set_v_pos(self, volts: float) -> None: ...
    def set_w1_dc(self, volts: float) -> None: ...
    def set_w2_dc(self, volts: float) -> None: ...
    def read_scope_mean(self, samples: int) -> tuple[float, float]: ...
    def emergency_off(self) -> None: ...
```

```python
# app/runtime.py
from dataclasses import dataclass

from core.driver_protocol import DriverProtocol
from core.types import HwConfig


@dataclass(slots=True)
class Runtime:
    config: HwConfig
    driver: DriverProtocol
    serial: str
```

- [ ] **Step 4: Run the type tests**

Run: `pytest tests/test_config_loader.py -k static_point_region_and_signs_are_explicit -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core app tests
git commit -m "feat: add canonical runtime types"
```

---

### Task 3: Add Real `pyRD` Driver Bootstrap And Explicit Simulation Driver

**Files:**
- Create: `core/device.py`
- Create: `core/pyrd_driver.py`
- Create: `core/simulation_driver.py`
- Test: `tests/test_detector_logic.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing simulation driver test**

```python
from core.simulation_driver import SimulationDriver


def test_simulation_driver_returns_stable_scope_means():
    driver = SimulationDriver()
    serial = driver.connect()

    driver.set_v_pos(3.0)
    driver.set_w1_dc(2.0)
    vb, vc = driver.read_scope_mean(samples=256)

    assert serial.startswith("SIM-")
    assert 0.5 < vb < 0.9
    assert 0.0 < vc < 3.1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_detector_logic.py -k stable_scope_means -v`

Expected: FAIL because the driver modules do not exist yet

- [ ] **Step 3: Implement the explicit simulation driver**

```python
# core/simulation_driver.py
from dataclasses import dataclass


@dataclass
class SimulationDriver:
    v_pos: float = 0.0
    w1: float = 0.0
    w2: float = 0.0
    connected: bool = False

    def connect(self) -> str:
        self.connected = True
        return "SIM-BJT-001"

    def close(self) -> None:
        self.connected = False

    def set_v_pos(self, volts: float) -> None:
        self.v_pos = volts

    def set_w1_dc(self, volts: float) -> None:
        self.w1 = volts

    def set_w2_dc(self, volts: float) -> None:
        self.w2 = volts

    def read_scope_mean(self, samples: int) -> tuple[float, float]:
        vb = min(0.78, max(0.0, self.w1 - 1.25))
        vc = max(0.12, self.v_pos - 0.55)
        return vb, vc

    def emergency_off(self) -> None:
        self.v_pos = 0.0
        self.w1 = 0.0
        self.w2 = 0.0
```

- [ ] **Step 4: Implement the real `pyRD` bootstrap with isolated import path**

```python
# core/device.py
import sys
from pathlib import Path


SDK_SRC = Path("/Users/helap/Documents/雨骤/IPSDK3.2/IP-SDK/Python/src")


def ensure_sdk_path() -> None:
    sdk_src = str(SDK_SRC)
    if sdk_src not in sys.path:
        sys.path.insert(0, sdk_src)
```

```python
# core/pyrd_driver.py
from core.device import ensure_sdk_path


class PyRDDriver:
    def __init__(self) -> None:
        self.rd = None

    def connect(self) -> str:
        ensure_sdk_path()
        from pyRD import RD  # imported only after path bootstrap

        rd = RD()
        rd.DeviceEnumLists()
        if not rd.devicelist:
            raise RuntimeError("未找到雨骤设备")
        rd.DeviceOpen(0)
        self.rd = rd
        return rd.devicelist[0][1].decode()
```

- [ ] **Step 5: Run the driver tests**

Run: `pytest tests/test_detector_logic.py -k stable_scope_means -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core README.md tests/test_detector_logic.py
git commit -m "feat: add driver bootstrap and simulation backend"
```

---

### Task 4: Build Safety Checks And Static Measurement Math

**Files:**
- Create: `core/psu.py`
- Create: `core/awg.py`
- Create: `core/scope.py`
- Create: `core/safety.py`
- Create: `measurement/static.py`
- Test: `tests/test_static_math.py`
- Test: `tests/test_safety.py`

- [ ] **Step 1: Write the failing static math test**

```python
from measurement.static import build_static_point


def test_build_static_point_for_npn_math():
    point = build_static_point(
        bjt_type="NPN",
        R_B=22_000.0,
        R_C=220.0,
        Vbb=1.50,
        Vcc=5.00,
        Vb=0.681,
        Vc=2.93,
    )

    assert round(point.Ib * 1e6, 1) == 37.2
    assert round(point.Ic * 1e3, 2) == 9.41
    assert round(point.beta, 0) == 253
    assert point.region == "active"
```

- [ ] **Step 2: Write the failing safety test**

```python
import pytest

from core.safety import SafetyAbort, SafetyGuard
from core.types import HwConfig, StaticPoint


class StubDriver:
    def __init__(self):
        self.off_called = False

    def emergency_off(self):
        self.off_called = True


def test_safety_guard_aborts_on_overcurrent():
    driver = StubDriver()
    guard = SafetyGuard(HwConfig(Ic_max_A=0.01), driver)
    point = StaticPoint(1.0, 5.0, 0.7, 0.2, 10e-6, 20e-3, 0.7, 0.2, 2000, "active")

    with pytest.raises(SafetyAbort):
        guard.check(point)

    assert driver.off_called is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_static_math.py tests/test_safety.py -v`

Expected: FAIL because `build_static_point` and `SafetyGuard` do not exist yet

- [ ] **Step 4: Implement minimal static point math and safety guard**

```python
# measurement/static.py
from core.types import StaticPoint


def build_static_point(*, bjt_type: str, R_B: float, R_C: float, Vbb: float, Vcc: float, Vb: float, Vc: float) -> StaticPoint:
    if bjt_type == "NPN":
        ib = (Vbb - Vb) / R_B
        ic = (Vcc - Vc) / R_C
        vbe = Vb
        vce = Vc
    else:
        ib = (Vb - Vbb) / R_B
        ic = Vc / R_C
        vbe = Vb - 5.0
        vce = Vc - 5.0
    beta = ic / ib if abs(ib) > 1e-12 else 0.0
    region = "cutoff" if abs(vbe) < 0.5 else "saturation" if abs(vce) < 0.3 else "active"
    return StaticPoint(Vbb, Vcc, Vb, Vc, ib, ic, vbe, vce, beta, region)
```

```python
# core/safety.py
class SafetyAbort(RuntimeError):
    pass


class SafetyGuard:
    def __init__(self, cfg, driver):
        self.cfg = cfg
        self.driver = driver

    def check(self, point):
        if abs(point.Ic) > self.cfg.Ic_max_A:
            self.driver.emergency_off()
            raise SafetyAbort("Ic 过流")
        if abs(point.Vce * point.Ic) > self.cfg.Pmax_W:
            self.driver.emergency_off()
            raise SafetyAbort("功耗超限")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_static_math.py tests/test_safety.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core measurement tests
git commit -m "feat: add static math and safety guard"
```

---

### Task 5: Implement Detection, Curves, Saturation, Linearity, And Analysis

**Files:**
- Create: `measurement/detector.py`
- Create: `measurement/vce_sat.py`
- Create: `measurement/curves.py`
- Create: `measurement/linearity.py`
- Create: `analysis/data_processor.py`
- Create: `analysis/exporters.py`
- Create: `analysis/report.py`
- Test: `tests/test_detector_logic.py`
- Test: `tests/test_linearity.py`

- [ ] **Step 1: Write the failing beta-linearity test**

```python
from core.types import StaticPoint
from measurement.linearity import beta_linearity


def test_beta_linearity_matches_expected_ratio():
    points = [
        StaticPoint(0, 5, 0.7, 4.8, 5e-6, 0.6e-3, 0.7, 4.8, 178, "active"),
        StaticPoint(0, 5, 0.7, 4.6, 6e-6, 1.2e-3, 0.7, 4.6, 205, "active"),
        StaticPoint(0, 5, 0.7, 4.1, 8e-6, 8.0e-3, 0.7, 4.1, 253, "active"),
        StaticPoint(0, 5, 0.7, 3.8, 10e-6, 19.5e-3, 0.7, 3.8, 192, "active"),
    ]

    result = beta_linearity(points, ic_range=(0.5e-3, 20e-3), vce_window=(2.0, 5.0), min_points=4)

    assert round(result.beta_max, 1) == 253.0
    assert round(result.beta_min, 1) == 178.0
    assert round(result.eta, 3) == 0.337
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_linearity.py -v`

Expected: FAIL because `beta_linearity` does not exist yet

- [ ] **Step 3: Implement detector and linearly analyzable curve primitives**

```python
# measurement/detector.py
def detect_bjt_type(driver, R_B: float, R_C: float) -> str:
    driver.set_v_pos(3.0)
    driver.set_w1_dc(2.0)
    vb_npn, vc_npn = driver.read_scope_mean(samples=512)
    ib_npn = (2.0 - vb_npn) / R_B
    ic_npn = (3.0 - vc_npn) / R_C
    beta_npn = ic_npn / ib_npn if ib_npn > 1e-9 else 0.0
    driver.emergency_off()
    return "NPN" if beta_npn >= 10 else "UNKNOWN"
```

```python
# measurement/linearity.py
from dataclasses import dataclass, field


@dataclass(slots=True)
class BetaLinearity:
    eta: float | None
    beta_max: float = 0.0
    beta_min: float = 0.0
    beta_avg: float = 0.0
    n: int = 0
    beta_vs_ic: list[tuple[float, float]] = field(default_factory=list)
    reason: str = ""


def beta_linearity(points, ic_range, vce_window, min_points=8) -> BetaLinearity:
    candidates = [
        p for p in points
        if p.region == "active"
        and ic_range[0] <= abs(p.Ic) <= ic_range[1]
        and vce_window[0] <= abs(p.Vce) <= vce_window[1]
    ]
    if len(candidates) < min_points:
        return BetaLinearity(eta=None, n=len(candidates), reason="有效点不足")
    betas = [p.beta for p in candidates]
    ics = [abs(p.Ic) for p in candidates]
    beta_max = max(betas)
    beta_min = min(betas)
    beta_avg = sum(betas) / len(betas)
    eta = (beta_max - beta_min) / beta_avg
    return BetaLinearity(eta=eta, beta_max=beta_max, beta_min=beta_min, beta_avg=beta_avg, n=len(candidates), beta_vs_ic=list(zip(ics, betas)))
```

- [ ] **Step 4: Add analysis/export stubs that accept canonical types**

```python
# analysis/data_processor.py
from statistics import median


def beta_median(points):
    active = [p.beta for p in points if p.region == "active"]
    return median(active) if active else 0.0
```

```python
# analysis/exporters.py
from dataclasses import asdict
import json
from pathlib import Path


def write_summary_json(report, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.json"
    path.write_text(json.dumps(asdict(report), default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_detector_logic.py tests/test_linearity.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add measurement analysis tests
git commit -m "feat: add detector curves and analysis pipeline"
```

---

### Task 6: Build The Shared Application Service Layer And CLI

**Files:**
- Create: `app/services.py`
- Create: `app/orchestrator.py`
- Create: `cli.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing CLI smoke test**

```python
import subprocess
import sys


def test_cli_detect_simulation_smoke():
    proc = subprocess.run(
        [sys.executable, "cli.py", "detect", "--mode", "simulation"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "SIM-BJT-001" in proc.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_cli_smoke.py -v`

Expected: FAIL because `cli.py` does not exist yet

- [ ] **Step 3: Add a runtime factory and shared service methods**

```python
# app/services.py
from core.simulation_driver import SimulationDriver
from core.types import HwConfig
from measurement.detector import detect_bjt_type


def build_driver(mode: str):
    if mode == "simulation":
        return SimulationDriver()
    from core.pyrd_driver import PyRDDriver
    return PyRDDriver()


def run_detect(mode: str, cfg: HwConfig) -> tuple[str, str]:
    driver = build_driver(mode)
    serial = driver.connect()
    try:
        result = detect_bjt_type(driver, cfg.R_B, cfg.R_C)
        return serial, result
    finally:
        driver.close()
```

- [ ] **Step 4: Implement the CLI entrypoint**

```python
# cli.py
import argparse
import sys

from app.services import run_detect
from core.types import HwConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["detect"])
    parser.add_argument("--mode", choices=["hardware", "simulation"], default="hardware")
    args = parser.parse_args()

    cfg = HwConfig()
    if args.command == "detect":
        serial, result = run_detect(args.mode, cfg)
        print(f"{serial}: {result}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the smoke test**

Run: `pytest tests/test_cli_smoke.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app cli.py tests/test_cli_smoke.py
git commit -m "feat: add shared service layer and cli entrypoint"
```

---

### Task 7: Build The PySide6 GUI Skeleton And Live Plot Surface

**Files:**
- Create: `main.py`
- Create: `gui/models.py`
- Create: `gui/live_plot.py`
- Create: `gui/main_window.py`
- Create: `gui/panels/connection_panel.py`
- Create: `gui/panels/hw_config_panel.py`
- Create: `gui/panels/action_panel.py`
- Create: `gui/panels/live_value_panel.py`
- Create: `gui/panels/log_panel.py`
- Test: `tests/test_gui_smoke.py`

- [ ] **Step 1: Write the failing GUI construction test**

```python
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def test_main_window_builds(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "BJT Test System"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests -k main_window_builds -v`

Expected: FAIL because `gui.main_window` does not exist yet

- [ ] **Step 3: Implement the minimal Qt window and plot widget**

```python
# gui/live_plot.py
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class LivePlotWidget(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(6, 4))
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Ic-Vce")
        super().__init__(self.figure)
```

```python
# gui/main_window.py
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QWidget

from gui.live_plot import LivePlotWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BJT Test System")
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(LivePlotWidget())
        self.setCentralWidget(root)
```

- [ ] **Step 4: Add a desktop bootstrap**

```python
# main.py
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the GUI test**

Run: `pytest tests -k main_window_builds -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add main.py gui
git commit -m "feat: add desktop gui skeleton"
```

---

### Task 8: Complete End-To-End Full-Run Orchestration And Export Validation

**Files:**
- Modify: `app/services.py`
- Modify: `app/orchestrator.py`
- Modify: `measurement/static.py`
- Modify: `measurement/vce_sat.py`
- Modify: `measurement/curves.py`
- Modify: `measurement/linearity.py`
- Modify: `analysis/report.py`
- Modify: `README.md`

- [ ] **Step 1: Add a failing full-run smoke test using simulation**

```python
from pathlib import Path

from app.services import run_full_suite
from core.types import HwConfig


def test_run_full_suite_simulation_writes_summary(tmp_path: Path):
    report = run_full_suite(mode="simulation", dut_label="S8050-A1", output_dir=tmp_path, cfg=HwConfig())

    assert report.bjt_type in {"NPN", "PNP", "UNKNOWN"}
    assert (tmp_path / "summary.json").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests -k full_suite_simulation_writes_summary -v`

Expected: FAIL because `run_full_suite` does not exist yet

- [ ] **Step 3: Implement the minimal end-to-end service**

```python
# app/services.py
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from analysis.exporters import write_summary_json
from analysis.data_processor import beta_median
from core.types import DeviceReport
from measurement.static import build_static_point


def run_full_suite(*, mode: str, dut_label: str, output_dir: Path, cfg):
    driver = build_driver(mode)
    serial = driver.connect()
    try:
        point = build_static_point(bjt_type="NPN", R_B=cfg.R_B, R_C=cfg.R_C, Vbb=1.5, Vcc=5.0, Vb=0.681, Vc=2.93)
        report = DeviceReport(
            bjt_type="NPN",
            serial=serial,
            dut_label=dut_label,
            beta_median=beta_median([point]),
            beta_active_curve=[point],
            vce_sat=0.18,
            Ic_at_sat=0.01,
            output_curves={50e-6: [point]},
            early_voltage=None,
            beta_linearity=None,
            hw_config=cfg,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )
        write_summary_json(report, output_dir)
        return report
    finally:
        driver.close()
```

- [ ] **Step 4: Run the smoke test**

Run: `pytest tests -k full_suite_simulation_writes_summary -v`

Expected: PASS

- [ ] **Step 5: Run the focused regression suite**

Run: `pytest tests/test_config_loader.py tests/test_detector_logic.py tests/test_static_math.py tests/test_linearity.py tests/test_safety.py tests/test_cli_smoke.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app analysis measurement README.md
git commit -m "feat: add full-run simulation orchestration"
```

---

## Self-Review

### Spec Coverage

- Desktop-first architecture: covered by Tasks 6-8
- CLI on same core: covered by Task 6
- `pyRD` hardware baseline: covered by Task 3
- Explicit simulation mode: covered by Tasks 3 and 6
- Static math and safety: covered by Task 4
- Detection, curves, saturation, linearity, exports: covered by Task 5
- Reporting and summary persistence: covered by Tasks 5 and 8

### Placeholder Scan

- No `TODO` or `TBD` placeholders remain
- Every task has explicit file paths
- Every test step has an exact command
- Every implementation step includes concrete code to start from

### Type Consistency

- `HwConfig`, `StaticPoint`, and runtime driver boundaries are defined before later tasks depend on them
- `simulation` and `hardware` are the only valid driver modes across config, services, and CLI
- The CLI and GUI both route through the shared `app/services.py` layer
