from __future__ import annotations

from ai.safety import ExecutionPolicyDecision
from app.runtime import Runtime
from app.services import run_full_suite, run_npn_static_bringup, run_scan_curves
from ai.test_planner import build_test_plan
from ai.tools import execute_plan, preflight_plan
from api_server import _hardware_token_valid_from_payload
from core.types import HwConfig


class DummyDriver:
    def __init__(self) -> None:
        self.closed = False
        self.disabled = False

    def disable_all(self) -> None:
        self.disabled = True

    def emergency_off(self) -> None:
        self.disabled = True

    def close(self) -> None:
        self.closed = True


def test_execute_plan_routes_gate_through_policy(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    calls: list[dict] = []

    def fake_evaluate_execution_request(*, plan, mode, allow_hardware, token_valid):
        calls.append(
            {
                "plan": plan,
                "mode": mode,
                "allow_hardware": allow_hardware,
                "token_valid": token_valid,
            }
        )
        return ExecutionPolicyDecision(
            status="deny",
            reasons=["policy denied execution"],
            tags=["policy_gate_blocked"],
        )

    monkeypatch.setattr("ai.tools.evaluate_execution_request", fake_evaluate_execution_request)

    result = execute_plan(plan, mode="hardware", allow_hardware=True)

    assert calls == [
        {
            "plan": plan,
            "mode": "hardware",
            "allow_hardware": True,
            "token_valid": False,
        }
    ]
    assert result["skipped"] is True
    assert result["reason"] == "policy denied execution"
    assert result["policy_tags"] == ["policy_gate_blocked"]


def test_execute_plan_accepts_explicit_hardware_confirmation(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    calls: list[dict] = []

    def fake_evaluate_execution_request(*, plan, mode, allow_hardware, token_valid):
        calls.append(
            {
                "plan": plan,
                "mode": mode,
                "allow_hardware": allow_hardware,
                "token_valid": token_valid,
            }
        )
        return ExecutionPolicyDecision(status="deny", reasons=["stop"], tags=["gate"])

    monkeypatch.setattr("ai.tools.evaluate_execution_request", fake_evaluate_execution_request)

    execute_plan(plan, mode="hardware", allow_hardware=True, token_valid=True)

    assert calls == [
        {
            "plan": plan,
            "mode": "hardware",
            "allow_hardware": True,
            "token_valid": True,
        }
    ]


def test_api_hardware_confirmation_phrase_is_required() -> None:
    assert _hardware_token_valid_from_payload("simulation", {}) is True
    assert _hardware_token_valid_from_payload("hardware", {}) is False
    assert _hardware_token_valid_from_payload("hardware", {"hardware_confirmation": "确认硬件执行"}) is True
    assert _hardware_token_valid_from_payload("hardware", {"hardware_confirmation_token": "确认硬件执行"}) is True
    assert _hardware_token_valid_from_payload("hardware", {"hardware_confirmation": "yes"}) is False


def test_preflight_plan_uses_policy_without_runtime(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    def fail_build_runtime(*args, **kwargs):
        del args, kwargs
        raise AssertionError("preflight must not create a runtime")

    monkeypatch.setattr("ai.tools.build_runtime", fail_build_runtime)

    blocked = preflight_plan(plan, mode="hardware", allow_hardware=False)
    confirmation = preflight_plan(plan, mode="hardware", allow_hardware=True)
    ready = preflight_plan(plan, mode="hardware", allow_hardware=True, token_valid=True)

    assert blocked["status"] == "deny"
    assert blocked["ok_to_execute"] is False
    assert blocked["will_touch_hardware"] is False
    assert blocked["policy_tags"] == ["blocked_hardware_execution"]
    assert blocked["preflight_summary"]
    assert [check["id"] for check in blocked["checks"]] == [
        "dry_run",
        "bjt_type",
        "hardware_allowance",
        "hardware_confirmation",
    ]
    assert blocked["checks"][0]["status"] == "pass"
    assert blocked["checks"][2]["status"] == "fail"
    assert confirmation["status"] == "require_confirm"
    assert confirmation["requires_confirmation"] is True
    assert confirmation["checks"][3]["status"] == "pending"
    assert ready["status"] == "allow"
    assert ready["ok_to_execute"] is True
    assert ready["checks"][3]["status"] == "pass"


def test_execute_plan_aborts_hardware_run_when_runtime_guard_triggers(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="HW-ABORT")

    def fake_build_runtime(mode, cfg):
        del mode, cfg
        return runtime

    def fake_detect_bjt_type(detector_driver, rb, rc):
        del detector_driver, rb, rc
        return "NPN"

    def fake_measure_static_point(*args, **kwargs):
        del args, kwargs
        return type(
            "Point",
            (),
            {
                "Vbb": 1.0,
                "Vcc": 3.0,
                "Vbe": 0.8,
                "Vce": 0.1,
                "Ib": 0.0001,
                "Ic": 0.031,
                "beta": 310.0,
                "region": "saturation",
            },
        )()

    monkeypatch.setattr("ai.tools.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ai.tools.detect_bjt_type", fake_detect_bjt_type)
    monkeypatch.setattr("ai.tools.measure_static_point", fake_measure_static_point)

    result = execute_plan(plan, mode="hardware", allow_hardware=True, token_valid=True)

    assert result["aborted"] is True
    assert result["abort_reason"]
    assert result["abort_tags"] == ["runtime_ic_limit_exceeded"]
    assert result["aborted_after_index"] == 0
    assert len(result["measurements"]) == 1
    assert driver.disabled is True
    assert driver.closed is True


def test_execute_plan_stops_when_realtime_detection_is_unknown(monkeypatch) -> None:
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="SIM-UNKNOWN")
    plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    monkeypatch.setattr("ai.tools.build_runtime", lambda mode, cfg: runtime)
    monkeypatch.setattr("ai.tools.detect_bjt_type", lambda driver, rb, rc: "UNKNOWN")

    result = execute_plan(plan, mode="simulation", allow_hardware=False)

    assert result["skipped"] is True
    assert "明确 NPN" in result["reason"]
    assert result["measurements"] == []
    assert driver.disabled is True
    assert driver.closed is True


def test_run_scan_curves_stops_when_detection_is_unknown(monkeypatch) -> None:
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="SIM-UNKNOWN")

    monkeypatch.setattr("app.services.build_runtime", lambda mode, cfg: runtime)
    monkeypatch.setattr("app.services.detect_bjt_type", lambda driver, rb, rc: "UNKNOWN")

    try:
        run_scan_curves("simulation", HwConfig())
    except RuntimeError as exc:
        assert "明确 NPN" in str(exc)
    else:
        raise AssertionError("run_scan_curves should stop on UNKNOWN detection")
    assert driver.disabled is True
    assert driver.closed is True


def test_run_npn_static_bringup_stops_when_detection_is_unknown(monkeypatch) -> None:
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="SIM-UNKNOWN")

    monkeypatch.setattr("app.services.build_runtime", lambda mode, cfg: runtime)
    monkeypatch.setattr("app.services.detect_bjt_type", lambda driver, rb, rc: "UNKNOWN")

    try:
        run_npn_static_bringup("simulation", HwConfig(), vcc=3.0, vbb=2.0)
    except RuntimeError as exc:
        assert "明确 NPN" in str(exc)
    else:
        raise AssertionError("run_npn_static_bringup should stop on UNKNOWN detection")
    assert driver.disabled is True
    assert driver.closed is True


def test_run_full_suite_stops_when_detection_is_unknown(monkeypatch, tmp_path) -> None:
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="SIM-UNKNOWN")

    monkeypatch.setattr("app.services.build_runtime", lambda mode, cfg: runtime)
    monkeypatch.setattr("app.services.detect_bjt_type", lambda driver, rb, rc: "UNKNOWN")

    try:
        run_full_suite(mode="simulation", dut_label="DUT", output_dir=tmp_path, cfg=HwConfig())
    except RuntimeError as exc:
        assert "明确 NPN" in str(exc)
    else:
        raise AssertionError("run_full_suite should stop on UNKNOWN detection")
    assert driver.disabled is True
    assert driver.closed is True
