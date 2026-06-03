from __future__ import annotations

import json
from pathlib import Path

from app.services import build_runtime
from core.types import HwConfig
from measurement.detector import detect_bjt_type
from measurement.static import measure_static_point

from ai.runtime_guard import check_abort_after_point
from ai.safety import evaluate_execution_request
from ai.test_planner import TestPlan


def _config_from_plan(plan: TestPlan) -> HwConfig:
    cfg = HwConfig()
    cfg.Ic_max_A = min(cfg.Ic_max_A, float(plan.ic_limit_a))
    cfg.Pmax_W = min(cfg.Pmax_W, float(plan.power_limit_w))
    return cfg


def _measurement_schedule(plan: TestPlan) -> list[dict[str, float]]:
    if plan.static_points:
        return plan.static_points
    return [{"vcc": 3.0, "vbb": 2.0}]


def execute_plan(
    plan: TestPlan,
    *,
    mode: str = "simulation",
    output_dir: Path | None = None,
    allow_hardware: bool = False,
    token_valid: bool | None = None,
) -> dict:
    if token_valid is None:
        token_valid = mode != "hardware"

    decision = evaluate_execution_request(
        plan=plan,
        mode=mode,
        allow_hardware=allow_hardware,
        token_valid=token_valid,
    )
    if decision.status != "allow":
        return {
            "plan": plan.to_dict(),
            "skipped": True,
            "reason": decision.reasons[0] if decision.reasons else "策略阻止执行。",
            "policy_tags": decision.tags,
        }

    cfg = _config_from_plan(plan)
    runtime = build_runtime(mode, cfg)
    result: dict = {
        "plan": plan.to_dict(),
        "mode": mode,
        "serial": runtime.serial,
        "measurements": [],
        "limits": {
            "ic_limit_a": cfg.Ic_max_A,
            "power_limit_w": cfg.Pmax_W,
            "vcc_max": cfg.Vcc_max,
        },
    }
    try:
        detected = detect_bjt_type(runtime.driver, runtime.config.R_B, runtime.config.R_C)
        result["detected_bjt_type"] = detected

        if detected != "NPN":
            result["skipped"] = True
            result["reason"] = "实时检测结果不是明确 NPN，停止自动执行。"
            return result

        for point_cfg in _measurement_schedule(plan):
            point = measure_static_point(
                runtime.driver,
                bjt_type="NPN",
                cfg=runtime.config,
                Vbb=float(point_cfg["vbb"]),
                Vcc=float(point_cfg["vcc"]),
                samples=plan.sample_count,
            )
            result["measurements"].append(
                {
                    "Vbb": point.Vbb,
                    "Vcc": point.Vcc,
                    "Vbe": point.Vbe,
                    "Vce": point.Vce,
                    "Ib": point.Ib,
                    "Ic": point.Ic,
                    "beta": point.beta,
                    "region": point.region,
                }
            )
            if mode == "hardware":
                decision = check_abort_after_point(
                    plan=plan,
                    point=result["measurements"][-1],
                    history=result["measurements"][:-1],
                )
                if decision.should_abort:
                    result["aborted"] = True
                    result["abort_reason"] = decision.reason
                    result["abort_tags"] = decision.tags
                    result["aborted_after_index"] = len(result["measurements"]) - 1
                    break
    finally:
        disable_all = getattr(runtime.driver, "disable_all", None)
        if callable(disable_all):
            disable_all()
        else:
            runtime.driver.emergency_off()
        runtime.driver.close()

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "ai_execution.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["execution_json"] = str(path)
    return result


def execute_plan_simulation(plan: TestPlan, output_dir: Path | None = None) -> dict:
    return execute_plan(plan, mode="simulation", output_dir=output_dir)
