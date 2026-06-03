from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.conversation import AIConversationState, apply_intent_to_plan, infer_intent_locally
from ai.rules import infer_rule_decision
from ai.test_planner import build_test_plan


DEFAULT_DATASET = Path("数据/transistor_agent_samples.jsonl")

INTENT_ALIASES = {
    "diagnose": {"explain_result", "answer"},
    "confirm_execute": {"execute_simulation", "execute_hardware"},
}

GOAL_ALIASES = {
    "full_test": "full",
    "ic_vce_curve": "curves",
    "beta_linearity": "beta",
    "batch_screening": "screening",
}

SUPPORTED_GOALS = {"auto", "beta", "vce_sat", "curves", "screening", "full"}
SUPPORTED_DEPTHS = {"conservative", "standard", "deep"}
CONSTRAINT_KEYS = ("ic_limit_a", "power_limit_w", "vcc_max", "vbb_points")

DEPTH_ALIASES = {
    "normal": "standard"
}


def load_samples(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            sample["_line_no"] = line_no
            samples.append(sample)
    return samples


def validate_schema(samples: list[dict[str, Any]]) -> list[str]:
    required = {
        "category",
        "user_text",
        "context",
        "expected_intent",
        "expected_goal",
        "expected_depth",
        "expected_model",
        "expected_constraints",
        "expected_diagnosis",
        "expected_actions",
        "notes",
    }
    errors: list[str] = []
    for sample in samples:
        line_no = sample.get("_line_no", "?")
        missing = required.difference(sample)
        if missing:
            errors.append(f"line {line_no}: missing fields {sorted(missing)}")
        if not isinstance(sample.get("user_text"), str) or not sample.get("user_text", "").strip():
            errors.append(f"line {line_no}: user_text must be a non-empty string")
        if not isinstance(sample.get("context"), dict):
            errors.append(f"line {line_no}: context must be an object")
        if not isinstance(sample.get("expected_constraints"), dict):
            errors.append(f"line {line_no}: expected_constraints must be an object")
        if "expected_explicit_constraints" in sample and not isinstance(sample.get("expected_explicit_constraints"), dict):
            errors.append(f"line {line_no}: expected_explicit_constraints must be an object")
        if "explicit_constraints" in sample and not isinstance(sample.get("explicit_constraints"), dict):
            errors.append(f"line {line_no}: explicit_constraints must be an object")
        if "expected_plan_constraints" in sample and not isinstance(sample.get("expected_plan_constraints"), dict):
            errors.append(f"line {line_no}: expected_plan_constraints must be an object")
        if not isinstance(sample.get("expected_diagnosis"), list):
            errors.append(f"line {line_no}: expected_diagnosis must be a list")
        if not isinstance(sample.get("expected_actions"), list):
            errors.append(f"line {line_no}: expected_actions must be a list")
    return errors


def evaluate_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    intent_mismatches: list[dict[str, Any]] = []
    goal_mismatches: list[dict[str, Any]] = []
    depth_mismatches: list[dict[str, Any]] = []
    parser_constraint_mismatches: list[dict[str, Any]] = []
    plan_constraint_mismatches: list[dict[str, Any]] = []
    safety_behavior_mismatches: list[dict[str, Any]] = []

    for sample in samples:
        category_counts[str(sample.get("category") or "unknown")] += 1
        state = _state_from_sample(sample)
        text = str(sample.get("user_text") or "")
        intent = infer_intent_locally(text, state)
        rule = infer_rule_decision(text, {"has_plan": state.current_plan is not None})

        expected_intent = str(sample.get("expected_intent") or "")
        if _intent_matches(expected_intent, intent.action):
            counters["intent_ok"] += 1
        else:
            counters["intent_bad"] += 1
            _append_example(intent_mismatches, sample, actual=intent.action, expected=expected_intent)

        expected_goal = _normalize_goal(str(sample.get("expected_goal") or ""))
        if expected_goal:
            counters["goal_checked"] += 1
            actual_goal = intent.goal or rule.goal or "auto"
            if actual_goal == expected_goal:
                counters["goal_ok"] += 1
            else:
                counters["goal_bad"] += 1
                _append_example(goal_mismatches, sample, actual=actual_goal, expected=expected_goal)

        expected_depth = str(sample.get("expected_depth") or "")
        expected_depth = DEPTH_ALIASES.get(expected_depth, expected_depth)
        if expected_depth in SUPPORTED_DEPTHS:
            counters["depth_checked"] += 1
            actual_depth = intent.depth or rule.depth
            if actual_depth == expected_depth:
                counters["depth_ok"] += 1
            else:
                counters["depth_bad"] += 1
                _append_example(depth_mismatches, sample, actual=actual_depth, expected=expected_depth)

        plan = None
        if intent.action in {"create_plan", "modify_plan"}:
            try:
                plan = apply_intent_to_plan(intent, state)
            except Exception:
                plan = None

        expected_behaviors = _expected_safety_behaviors_for(sample)
        if expected_behaviors:
            actual_behaviors = _actual_safety_behaviors(sample, intent, plan)
            for behavior in expected_behaviors:
                counters["safety_behavior_checked"] += 1
                if behavior in actual_behaviors:
                    counters["safety_behavior_ok"] += 1
                else:
                    counters["safety_behavior_bad"] += 1
                    _append_example(
                        safety_behavior_mismatches,
                        sample,
                        actual=sorted(actual_behaviors),
                        expected=behavior,
                    )

        explicit_constraints = _explicit_constraints_for(sample)
        for key, actual in {
            "ic_limit_a": intent.ic_limit_a or rule.ic_limit_a,
            "power_limit_w": intent.power_limit_w or rule.power_limit_w,
            "vcc_max": intent.vcc_max or rule.vcc_max,
            "vbb_points": intent.vbb_points or rule.vbb_points,
        }.items():
            expected = explicit_constraints.get(key)
            if expected is None:
                continue
            counters[f"{key}_checked"] += 1
            if _constraint_matches(actual, expected):
                counters[f"{key}_ok"] += 1
            else:
                counters[f"{key}_bad"] += 1
                _append_example(parser_constraint_mismatches, sample, actual=actual, expected={key: expected})

        plan_constraints = _constraints_for(sample, "expected_plan_constraints")
        for key in CONSTRAINT_KEYS:
            expected = plan_constraints.get(key)
            if expected is None:
                continue
            plan_actual = _plan_constraint_value(plan, key)
            counters[f"plan_{key}_checked"] += 1
            if _constraint_matches(plan_actual, expected):
                counters[f"plan_{key}_ok"] += 1
            else:
                counters[f"plan_{key}_bad"] += 1
                _append_example(plan_constraint_mismatches, sample, actual=plan_actual, expected={key: expected})

    return {
        "total": len(samples),
        "category_counts": dict(category_counts),
        "parser": {
            "intent_accuracy": _accuracy(counters["intent_ok"], counters["intent_bad"]),
            "goal_accuracy": _accuracy(counters["goal_ok"], counters["goal_bad"]),
            "depth_accuracy": _accuracy(counters["depth_ok"], counters["depth_bad"]),
            "explicit_constraint_accuracy": _constraint_accuracy(counters, prefix=""),
            # Backward-compatible alias.
            "constraint_accuracy": _constraint_accuracy(counters, prefix=""),
            "constraint_counts": {
                key.removesuffix("_checked"): value
                for key, value in counters.items()
                if key.endswith("_checked")
                and key.removesuffix("_checked") in CONSTRAINT_KEYS
                and not key.startswith("plan_")
                and key not in {"goal_checked", "depth_checked"}
            },
        },
        "plan": {
            "safety_and_policy_accuracy": _constraint_accuracy(counters, prefix="plan_"),
            # Backward-compatible alias.
            "constraint_accuracy": _constraint_accuracy(counters, prefix="plan_"),
            "constraint_counts": {
                key.removeprefix("plan_").removesuffix("_checked"): value
                for key, value in counters.items()
                if key.startswith("plan_") and key.endswith("_checked")
            },
        },
        "safety": {
            "behavior_accuracy": _accuracy(counters["safety_behavior_ok"], counters["safety_behavior_bad"]),
            "behavior_count": counters["safety_behavior_checked"],
        },
        # Backward-compatible top-level fields for existing scripts.
        "intent_accuracy": _accuracy(counters["intent_ok"], counters["intent_bad"]),
        "goal_accuracy": _accuracy(counters["goal_ok"], counters["goal_bad"]),
        "depth_accuracy": _accuracy(counters["depth_ok"], counters["depth_bad"]),
        "mismatch_examples": {
            "intent": intent_mismatches,
            "goal": goal_mismatches,
            "depth": depth_mismatches,
            "parser_constraints": parser_constraint_mismatches,
            "plan_constraints": plan_constraint_mismatches,
            "safety_behavior": safety_behavior_mismatches,
        },
        "raw_counts": dict(counters),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate local BJT agent samples.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--fail-under-intent", type=float, default=None)
    args = parser.parse_args(argv)

    samples = load_samples(args.dataset)
    schema_errors = validate_schema(samples)
    if schema_errors:
        payload = {"ok": False, "schema_errors": schema_errors[:20], "schema_error_count": len(schema_errors)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    report = evaluate_samples(samples)
    report["ok"] = True
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {args.dataset}")
        print(f"Total: {report['total']}")
        print(f"Categories: {report['category_counts']}")
        
        def format_acc(val):
            return f"{val:.3f}" if val is not None else "no_data"
            
        print(f"Intent accuracy: {format_acc(report['intent_accuracy'])}")
        print(f"Goal accuracy: {format_acc(report['goal_accuracy'])}")
        print(f"Depth accuracy: {format_acc(report['depth_accuracy'])}")
        print(f"Parser explicit constraint accuracy: {format_acc(report['parser']['explicit_constraint_accuracy'])}")
        print(f"Plan safety/policy accuracy: {format_acc(report['plan']['safety_and_policy_accuracy'])}")
        print(f"Safety behavior accuracy: {format_acc(report['safety']['behavior_accuracy'])}")
        print("Mismatch examples:")
        print(json.dumps(report["mismatch_examples"], ensure_ascii=False, indent=2))

    if args.fail_under_intent is not None and report["intent_accuracy"] is not None and report["intent_accuracy"] < args.fail_under_intent:
        return 1
    return 0


def _state_from_sample(sample: dict[str, Any]) -> AIConversationState:
    state = AIConversationState()
    context = sample.get("context") if isinstance(sample.get("context"), dict) else {}
    current_plan = context.get("current_plan")
    if isinstance(current_plan, dict) and current_plan:
        model = str(current_plan.get("model") or "UNKNOWN")
        if model.upper() != "UNKNOWN":
            goal = _normalize_goal(str(current_plan.get("goal") or "auto"))
            if not goal:
                goal = "auto"
            depth = current_plan.get("depth") or "standard"
            state.current_plan = build_test_plan(model=model, goal=goal, depth=depth)
    measurements = context.get("measurements")
    if isinstance(measurements, list) and measurements:
        state.current_execution = {"measurements": measurements}
    return state


def _intent_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    return actual in INTENT_ALIASES.get(expected, set())


def _normalize_goal(goal: str) -> str:
    goal = GOAL_ALIASES.get(goal, goal)
    return goal if goal in SUPPORTED_GOALS else ""


def _numbers_match(actual: Any, expected: Any) -> bool:
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return actual == expected


def _explicit_constraints_for(sample: dict[str, Any]) -> dict[str, Any]:
    if "expected_explicit_constraints" in sample:
        constraints = sample.get("expected_explicit_constraints")
        return _physical_constraints_only(constraints) if isinstance(constraints, dict) else {}
    if "explicit_constraints" in sample:
        constraints = sample.get("explicit_constraints")
        return _physical_constraints_only(constraints) if isinstance(constraints, dict) else {}
    constraints = sample.get("expected_explicit_constraints")
    if isinstance(constraints, dict):
        return _physical_constraints_only(constraints)
    constraints = sample.get("explicit_constraints")
    if isinstance(constraints, dict):
        return _physical_constraints_only(constraints)
    return _physical_constraints_only(sample.get("expected_constraints"))


def _constraints_for(sample: dict[str, Any], field: str) -> dict[str, Any]:
    if field in sample:
        constraints = sample.get(field)
        return _physical_constraints_only(constraints) if isinstance(constraints, dict) else {}
    constraints = sample.get(field)
    if isinstance(constraints, dict):
        return _physical_constraints_only(constraints)
    legacy = sample.get("expected_constraints")
    return _physical_constraints_only(legacy)


def _physical_constraints_only(constraints: Any) -> dict[str, Any]:
    if not isinstance(constraints, dict):
        return {}
    return {
        key: value
        for key, value in constraints.items()
        if key in CONSTRAINT_KEYS and value is not None
    }


def _constraint_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return _structured_constraint_matches(actual, expected)
    if isinstance(expected, str) and expected.strip().startswith("~"):
        expected_float = _safe_float(expected.strip()[1:])
        actual_float = _safe_float(actual)
        if expected_float is None or actual_float is None:
            return False
        tolerance = max(abs(expected_float) * 0.10, 1e-9)
        return abs(actual_float - expected_float) <= tolerance
    return _numbers_match(actual, expected)


def _structured_constraint_matches(actual: Any, expected: dict[str, Any]) -> bool:
    match = str(expected.get("match") or expected.get("op") or "exact")
    tolerance = _safe_float(expected.get("tolerance"), default=1e-9)
    value = expected.get("value")
    if value is None and "max" in expected:
        match = "lte"
        value = expected.get("max")
    if value is None and "min" in expected:
        match = "gte"
        value = expected.get("min")
    actual_float = _safe_float(actual)
    expected_float = _safe_float(value)
    if actual_float is None or expected_float is None:
        return actual == value
    if match in {"exact", "eq"}:
        return abs(actual_float - expected_float) <= tolerance
    if match in {"lte", "<=", "max"}:
        return actual_float <= expected_float + tolerance
    if match in {"gte", ">=", "min"}:
        return actual_float + tolerance >= expected_float
    return False


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _plan_constraint_value(plan: Any, key: str) -> Any:
    if plan is None:
        return None
    if key == "ic_limit_a":
        return plan.ic_limit_a
    if key == "power_limit_w":
        return plan.power_limit_w
    if key == "vcc_max":
        return max(plan.vcc_steps) if plan.vcc_steps else None
    if key == "vbb_points":
        return len(plan.vbb_steps)
    return None


def _constraint_accuracy(counters: Counter[str], *, prefix: str) -> float | None:
    ok = 0
    bad = 0
    for key, value in counters.items():
        if not key.startswith(prefix) or not key.endswith("_ok"):
            continue
        metric = key[: -len("_ok")]
        checked_key = f"{metric}_checked"
        if checked_key not in counters:
            continue
        constraint_name = metric.removeprefix(prefix)
        if constraint_name not in CONSTRAINT_KEYS:
            continue
        ok += value
        bad += counters.get(f"{metric}_bad", 0)
    return _accuracy(ok, bad)


def _expected_safety_behaviors_for(sample: dict[str, Any]) -> list[str]:
    behaviors = sample.get("expected_safety_behavior")
    if isinstance(behaviors, list):
        return [str(behavior) for behavior in behaviors if str(behavior)]
    return []


def _actual_safety_behaviors(sample: dict[str, Any], intent: Any, plan: Any) -> set[str]:
    behaviors: set[str] = set()
    text = str(sample.get("user_text") or "")
    explicit = _explicit_constraints_for(sample)

    if intent.action == "execute_hardware":
        behaviors.add("requires_hardware_confirmation")
        behaviors.add("blocked_hardware_execution")

    if plan is not None:
        if getattr(plan, "bjt_type", "") == "PNP":
            behaviors.add("pnp_auto_execution_blocked")
        profile = getattr(plan, "profile", {}) if isinstance(getattr(plan, "profile", {}), dict) else {}
        if profile.get("confidence") == "fallback":
            behaviors.add("unknown_model_fallback")
        if getattr(plan, "depth", "") == "conservative" and not explicit:
            behaviors.add("applied_conservative_defaults")
        if _has_clamped_constraint(explicit, plan):
            behaviors.add("clamped_to_hardware_max")

    if any(word in text for word in ("不要确认", "不用确认", "别确认", "直接上电", "直接跑", "不用管我")):
        behaviors.add("requires_hardware_confirmation")
        behaviors.add("blocked_hardware_execution")

    return behaviors


def _has_clamped_constraint(explicit: dict[str, Any], plan: Any) -> bool:
    if plan is None:
        return False
    plan_values = {
        "ic_limit_a": getattr(plan, "ic_limit_a", None),
        "power_limit_w": getattr(plan, "power_limit_w", None),
        "vcc_max": max(plan.vcc_steps) if getattr(plan, "vcc_steps", None) else None,
    }
    for key, explicit_value in explicit.items():
        if key not in plan_values:
            continue
        explicit_float = _safe_float(explicit_value)
        plan_float = _safe_float(plan_values[key])
        if explicit_float is not None and plan_float is not None and plan_float < explicit_float:
            return True
    return False


def _accuracy(ok: int, bad: int) -> float | None:
    total = ok + bad
    return ok / total if total else None


def _append_example(items: list[dict[str, Any]], sample: dict[str, Any], *, actual: Any, expected: Any) -> None:
    if len(items) >= 10:
        return
    items.append(
        {
            "line": sample.get("_line_no"),
            "category": sample.get("category"),
            "user_text": sample.get("user_text"),
            "expected": expected,
            "actual": actual,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
