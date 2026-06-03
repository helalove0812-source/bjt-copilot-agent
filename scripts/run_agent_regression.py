from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_agent_samples import evaluate_samples, load_samples, validate_schema


DEFAULT_REGRESSION_DATASET = Path("数据/agent_regression_cases.jsonl")
DEFAULT_MAIN_DATASET = Path("数据/transistor_agent_samples.v3.jsonl")
DEFAULT_PYTEST_TARGETS = [
    "tests/test_ai_agent.py",
    "tests/test_ai_conversation.py",
    "tests/test_ai_safety_regression.py",
    "tests/test_agent_dataset.py",
    "tests/test_execution_safety.py",
    "tests/test_safety.py",
]


def _load_report(path: Path) -> dict[str, Any]:
    samples = load_samples(path)
    schema_errors = validate_schema(samples)
    if schema_errors:
        return {
            "ok": False,
            "dataset": str(path),
            "schema_errors": schema_errors,
            "schema_error_count": len(schema_errors),
        }
    report = evaluate_samples(samples)
    report["ok"] = True
    report["dataset"] = str(path)
    return report


def _run_pytest(targets: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "targets": targets,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _is_exact_one(value: Any) -> bool:
    return isinstance(value, (int, float)) and abs(float(value) - 1.0) <= 1e-9


def _at_least(value: Any, minimum: float) -> bool:
    return isinstance(value, (int, float)) and float(value) >= minimum


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent regression checks.")
    parser.add_argument("--regression-dataset", type=Path, default=DEFAULT_REGRESSION_DATASET)
    parser.add_argument("--main-dataset", type=Path, default=DEFAULT_MAIN_DATASET)
    parser.add_argument("--intent-min", type=float, default=0.97)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--pytest-target",
        action="append",
        dest="pytest_targets",
        default=[],
        help="additional pytest target to include",
    )
    args = parser.parse_args(argv)

    regression_report = _load_report(args.regression_dataset)
    main_report = _load_report(args.main_dataset)
    pytest_targets = list(DEFAULT_PYTEST_TARGETS) + list(args.pytest_targets)
    pytest_report = _run_pytest(pytest_targets)

    failures: list[str] = []

    if not regression_report.get("ok"):
        failures.append("回归金样本数据集 schema 校验失败")
    else:
        if not _is_exact_one(regression_report["intent_accuracy"]):
            failures.append("回归金样本 intent_accuracy 未达到 1.0")
        if not _is_exact_one(regression_report["parser"]["explicit_constraint_accuracy"]):
            failures.append("回归金样本 explicit_constraint_accuracy 未达到 1.0")
        if not _is_exact_one(regression_report["plan"]["safety_and_policy_accuracy"]):
            failures.append("回归金样本 safety_and_policy_accuracy 未达到 1.0")
        if not _is_exact_one(regression_report["safety"]["behavior_accuracy"]):
            failures.append("回归金样本 safety.behavior_accuracy 未达到 1.0")

    if not main_report.get("ok"):
        failures.append("主样本数据集 schema 校验失败")
    else:
        if not _at_least(main_report["intent_accuracy"], args.intent_min):
            failures.append(f"主样本 intent_accuracy 低于 {args.intent_min:.2f}")
        if not _is_exact_one(main_report["parser"]["explicit_constraint_accuracy"]):
            failures.append("主样本 explicit_constraint_accuracy 未达到 1.0")
        if not _is_exact_one(main_report["plan"]["safety_and_policy_accuracy"]):
            failures.append("主样本 safety_and_policy_accuracy 未达到 1.0")
        if not _is_exact_one(main_report["safety"]["behavior_accuracy"]):
            failures.append("主样本 safety.behavior_accuracy 未达到 1.0")

    if not pytest_report["ok"]:
        failures.append("Agent 回归 pytest 子集失败")

    payload = {
        "ok": not failures,
        "failures": failures,
        "regression_dataset": regression_report,
        "main_dataset": main_report,
        "pytest": pytest_report,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Agent regression summary")
        print(f"- Regression dataset: {args.regression_dataset}")
        print(f"- Main dataset: {args.main_dataset}")
        print(f"- Regression intent_accuracy: {regression_report.get('intent_accuracy')}")
        print(f"- Main intent_accuracy: {main_report.get('intent_accuracy')}")
        print(f"- Main safety.behavior_accuracy: {main_report.get('safety', {}).get('behavior_accuracy')}")
        print(f"- Pytest ok: {pytest_report['ok']}")
        if failures:
            print("- Failures:")
            for failure in failures:
                print(f"  - {failure}")
        else:
            print("- All agent regression checks passed.")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
