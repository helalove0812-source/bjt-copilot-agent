from __future__ import annotations

from ai.tool_runtime import BJTToolRuntime


def test_tool_schema_exposes_strict_hardware_contract() -> None:
    schema = next(item for item in BJTToolRuntime().schemas() if item.name == "run_static_point")
    llm_schema = schema.to_llm_schema()

    assert llm_schema["category"] == "instrument"
    assert llm_schema["dangerous"] is True
    assert llm_schema["requires_confirmation"] is True
    assert llm_schema["requires_asset_lock"] is True
    assert llm_schema["supports_dry_run"] is True
    assert llm_schema["safety"]["max_voltage_v"] == 5.5
    assert llm_schema["parameters"]["properties"]["dry_run"]["type"] == "boolean"
    assert llm_schema["preconditions"] == [
        "fixture_connected",
        "current_plan_loaded_or_explicit_point",
        "dut_power_off",
    ]
    assert "outputs_disabled_after_point" in llm_schema["postconditions"]


def test_tool_registry_rejects_unexpected_arguments_before_handler() -> None:
    record = BJTToolRuntime().dispatch("run_static_point", {"vcc": 3.0, "vbb": 2.0, "surprise": True})

    assert record.result["ok"] is False
    assert record.result["error_code"] == "invalid_arguments"
    assert "unexpected argument" in record.result["error"]


def test_tool_registry_rejects_unsafe_voltage_before_handler() -> None:
    record = BJTToolRuntime().dispatch("run_static_point", {"mode": "simulation", "vcc": 6.0, "vbb": 2.0})

    assert record.result["ok"] is False
    assert record.result["blocked_reason"] == "safety_limit_exceeded"
    assert "max_voltage_v" in record.result["error"]


def test_tool_registry_requires_human_approval_for_hardware_token_rule() -> None:
    record = BJTToolRuntime().dispatch(
        "run_static_point",
        {
            "mode": "hardware",
            "vcc": 3.0,
            "vbb": 2.0,
            "allow_hardware": True,
            "token_valid": False,
        },
    )

    assert record.result["ok"] is False
    assert record.result["blocked_reason"] == "hardware_confirmation_required"
    assert record.result["tool"] == "run_static_point"


def test_tool_registry_dry_run_reports_contract_without_executing_handler() -> None:
    runtime = BJTToolRuntime()

    record = runtime.dispatch("run_static_point", {"mode": "simulation", "vcc": 3.0, "vbb": 2.0, "dry_run": True})

    assert record.result["ok"] is True
    assert record.result["dry_run"] is True
    assert record.result["would_call"] == "run_static_point"
    assert record.result["ready"] is True
    assert record.result["contract"]["dangerous"] is True
    assert runtime.current_execution is None
    assert [item["status"] for item in record.result["precondition_checks"]] == ["passed", "passed", "skipped"]


def test_tool_registry_blocks_failed_precondition_before_handler() -> None:
    record = BJTToolRuntime().dispatch("run_curve_scan", {"mode": "simulation"})

    assert record.result["ok"] is False
    assert record.result["blocked_reason"] == "precondition_failed"
    assert record.result["precondition_checks"][1]["name"] == "current_plan_loaded"
    assert record.result["precondition_checks"][1]["status"] == "failed"


def test_tool_registry_attaches_postcondition_checks_after_success() -> None:
    record = BJTToolRuntime().dispatch("run_static_point", {"mode": "simulation", "vcc": 3.0, "vbb": 2.0})

    assert record.result["ok"] is True
    assert "postcondition_checks" in record.result
    checks = {item["name"]: item["status"] for item in record.result["postcondition_checks"]}
    assert checks["measurements_within_plan_limits"] == "passed"
    assert checks["outputs_disabled_after_point"] == "skipped"
