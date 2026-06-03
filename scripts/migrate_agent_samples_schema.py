from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.rules import infer_rule_decision


DEFAULT_INPUT = Path("数据/transistor_agent_samples.jsonl")
DEFAULT_OUTPUT = Path("数据/transistor_agent_samples.v2.jsonl")
CONSTRAINT_KEYS = ("ic_limit_a", "power_limit_w", "vcc_max", "vbb_points")


def migrate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(sample)
    legacy = sample.get("expected_constraints") if isinstance(sample.get("expected_constraints"), dict) else {}

    if "expected_explicit_constraints" not in migrated:
        migrated["expected_explicit_constraints"] = _explicit_constraints_from_text(str(sample.get("user_text") or ""))
    if "expected_plan_constraints" not in migrated:
        migrated["expected_plan_constraints"] = {
            key: value
            for key, value in legacy.items()
            if key in CONSTRAINT_KEYS and value is not None
        }
    if "expected_safety_behavior" not in migrated:
        migrated["expected_safety_behavior"] = _safety_behavior(
            migrated["expected_explicit_constraints"],
            migrated["expected_plan_constraints"],
        )
    return migrated


def migrate_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    counts = {
        "total": 0,
        "explicit_constraint_samples": 0,
        "plan_constraint_samples": 0,
        "safety_behavior_samples": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            sample = json.loads(line)
            migrated = migrate_sample(sample)
            counts["total"] += 1
            if migrated["expected_explicit_constraints"]:
                counts["explicit_constraint_samples"] += 1
            if migrated["expected_plan_constraints"]:
                counts["plan_constraint_samples"] += 1
            if migrated["expected_safety_behavior"]:
                counts["safety_behavior_samples"] += 1
            target.write(json.dumps(migrated, ensure_ascii=False, separators=(",", ":")) + "\n")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate BJT agent samples to split constraint fields.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    counts = migrate_file(args.input, args.output)
    payload = {"ok": True, "input": str(args.input), "output": str(args.output), **counts}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _explicit_constraints_from_text(text: str) -> dict[str, Any]:
    decision = infer_rule_decision(text)
    values = {
        "ic_limit_a": decision.ic_limit_a,
        "power_limit_w": decision.power_limit_w,
        "vcc_max": decision.vcc_max,
        "vbb_points": decision.vbb_points,
    }
    return {key: value for key, value in values.items() if value is not None}


def _safety_behavior(explicit: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    behaviors: list[str] = []
    for key in ("ic_limit_a", "power_limit_w", "vcc_max"):
        explicit_value = _safe_float(explicit.get(key))
        plan_value = _safe_float(plan.get(key))
        if explicit_value is not None and plan_value is not None and plan_value < explicit_value:
            behaviors.append("clamped_to_hardware_max")
            break
    if plan and not explicit:
        behaviors.append("applied_policy_defaults")
    return behaviors


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
