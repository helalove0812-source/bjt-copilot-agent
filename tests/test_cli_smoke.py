from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cli import main
import pytest

from app.services import run_full_suite, run_hardware_selftest, run_scope_check
from core.types import HwConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_detect_simulation_smoke() -> None:
    proc = subprocess.run(
        [sys.executable, "cli.py", "detect", "--mode", "simulation"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "SIM-BJT-001" in proc.stdout


def test_cli_selftest_simulation_smoke() -> None:
    proc = subprocess.run(
        [sys.executable, "cli.py", "selftest", "--mode", "simulation"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["scope_mean"]["ch1"] >= 0.0
    assert payload["scope_mean"]["ch2"] >= 0.0


def test_cli_scope_check_delegates_to_orchestrator(monkeypatch, capsys) -> None:
    captured = {}

    class DummyOrchestrator:
        def __init__(self, config):
            captured["config"] = config

        def scope_check(self, mode, samples, frequency_hz):
            captured["call"] = (mode, samples, frequency_hz)
            return {
                "serial": "SIM-BJT-001",
                "samples": samples,
                "frequency_hz": frequency_hz,
                "mean": {"ch1": 0.1, "ch2": 0.2},
            }

    monkeypatch.setattr("cli.AppOrchestrator", DummyOrchestrator)

    exit_code = main(
        ["scope-check", "--mode", "simulation", "--samples", "512", "--freq", "20000"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert captured["call"] == ("simulation", 512, 20000)
    assert json.loads(out)["mean"] == {"ch1": 0.1, "ch2": 0.2}


def test_run_full_suite_simulation_writes_summary(tmp_path: Path) -> None:
    report = run_full_suite(
        mode="simulation",
        dut_label="S8050-A1",
        output_dir=tmp_path,
        cfg=HwConfig(),
    )

    assert report.bjt_type in {"NPN", "PNP", "UNKNOWN"}
    assert (tmp_path / "summary.json").exists()


class FakeDriver:
    def __init__(self) -> None:
        self.events = []

    def connect(self) -> str:
        self.events.append("connect")
        return "SERIAL-001"

    def close(self) -> None:
        self.events.append("close")

    def set_v_pos(self, volts: float) -> None:
        self.events.append(("v_pos", volts))

    def set_w1_dc(self, volts: float) -> None:
        self.events.append(("w1", volts))

    def set_w2_dc(self, volts: float) -> None:
        self.events.append(("w2", volts))

    def read_scope_mean(
        self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200
    ):
        self.events.append(("scope", samples, frequency_hz, timeout_ms))
        return 0.11, 1.22

    def disable_all(self) -> None:
        self.events.append("disable_all")

    def device_info(self):
        return {"model": "Model S", "serial": "SERIAL-001"}


def test_run_hardware_selftest_orders_outputs_and_shutdown(monkeypatch) -> None:
    fake = FakeDriver()

    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    result = run_hardware_selftest("hardware", HwConfig())

    assert result["serial"] == "SERIAL-001"
    assert result["scope_mean"] == {"ch1": 0.11, "ch2": 1.22}
    assert fake.events[0] == "connect"
    assert fake.events[-2] == "disable_all"
    assert fake.events[-1] == "close"


def test_run_scope_check_reads_requested_scope_mean_and_shutdown(monkeypatch) -> None:
    fake = FakeDriver()

    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    result = run_scope_check("hardware", HwConfig(), samples=512, frequency_hz=20000)

    assert result == {
        "serial": "SERIAL-001",
        "samples": 512,
        "frequency_hz": 20000,
        "mean": {"ch1": 0.11, "ch2": 1.22},
    }
    assert fake.events == [
        "connect",
        "disable_all",
        ("scope", 512, 20000, 200),
        "disable_all",
        "close",
    ]


def test_run_scope_check_disables_outputs_and_closes_on_timeout(monkeypatch) -> None:
    class TimeoutDriver(FakeDriver):
        def read_scope_mean(
            self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200
        ):
            self.events.append(("scope", samples, frequency_hz, timeout_ms))
            raise TimeoutError("示波器采样超时")

    fake = TimeoutDriver()
    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    with pytest.raises(TimeoutError, match="示波器采样超时"):
        run_scope_check("hardware", HwConfig(), samples=128, frequency_hz=50000)

    assert fake.events == [
        "connect",
        "disable_all",
        ("scope", 128, 50000, 200),
        "disable_all",
        "close",
    ]


def test_run_npn_static_bringup_returns_static_point(monkeypatch) -> None:
    from app.services import run_npn_static_bringup

    class StaticPointDriver(FakeDriver):
        def read_scope_mean(
            self, samples: int, frequency_hz: int = 100000, timeout_ms: int = 200
        ):
            self.events.append(("scope", samples, frequency_hz, timeout_ms))
            return 0.68, 1.10

    fake = StaticPointDriver()
    monkeypatch.setattr("app.services.build_driver", lambda mode: fake)

    point = run_npn_static_bringup("hardware", HwConfig(), vcc=3.0, vbb=2.0)

    assert round(point.Vbe, 2) == 0.68
    assert round(point.Vce, 2) == 1.10
    assert fake.events[-2] == "disable_all"
    assert fake.events[-1] == "close"


def test_cli_npn_static_delegates_to_orchestrator(monkeypatch, capsys) -> None:
    captured = {}

    class DummyOrchestrator:
        def __init__(self, config):
            captured["config"] = config

        def npn_static(self, mode, vcc, vbb):
            captured["call"] = (mode, vcc, vbb)
            return type(
                "Point",
                (),
                {"Vbe": 0.68, "Vce": 2.9, "Ib": 1e-5, "Ic": 2e-3, "beta": 200.0},
            )()

    monkeypatch.setattr("cli.AppOrchestrator", DummyOrchestrator)

    exit_code = main(
        ["npn-static", "--mode", "simulation", "--vcc", "3.0", "--vbb", "2.0"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert captured["call"] == ("simulation", 3.0, 2.0)
    assert json.loads(out) == {
        "Vbe": 0.68,
        "Vce": 2.9,
        "Ib": 1e-05,
        "Ic": 0.002,
        "beta": 200.0,
    }
