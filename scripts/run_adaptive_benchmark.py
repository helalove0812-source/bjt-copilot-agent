from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.adaptive_benchmark import benchmark_adaptive_vs_fixed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare adaptive characterization against fixed-grid characterization.")
    parser.add_argument("--model", action="append", default=[], help="BJT model to benchmark. Can be repeated.")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown-out", type=Path, default=None, help="write a Markdown benchmark report")
    args = parser.parse_args(argv)

    models = args.model or ["S8050"]
    reports = [
        benchmark_adaptive_vs_fixed(
            model=model,
            adaptive_iterations=args.iterations,
            adaptive_batch_size=args.batch_size,
        ).to_dict()
        for model in models
    ]
    payload = {
        "ok": True,
        "models": models,
        "reports": reports,
        "summary": _summary(reports),
    }
    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(_markdown_report(payload), encoding="utf-8")
        payload["markdown_report"] = str(args.markdown_out)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Adaptive characterization benchmark")
        for report in reports:
            comparison = report["comparison"]
            print(
                "- {0}: points={1}, residual_delta={2}, confidence_delta={3}, point_reduction={4}, lower_bound_reduction={5}".format(
                    report["model"],
                    comparison["point_budget"],
                    comparison["residual_delta_fixed_minus_adaptive"],
                    comparison["confidence_delta_adaptive_minus_fixed"],
                    comparison["point_reduction_fraction_vs_fixed_match"],
                    comparison["lower_bound_point_reduction_fraction"],
                )
            )
    return 0


def _summary(reports: list[dict]) -> dict:
    deltas = [
        report["comparison"]["residual_delta_fixed_minus_adaptive"]
        for report in reports
        if isinstance(report["comparison"].get("residual_delta_fixed_minus_adaptive"), (int, float))
    ]
    ratios = [
        report["comparison"]["adaptive_residual_ratio"]
        for report in reports
        if isinstance(report["comparison"].get("adaptive_residual_ratio"), (int, float))
    ]
    return {
        "count": len(reports),
        "mean_residual_delta_fixed_minus_adaptive": round(sum(deltas) / len(deltas), 6) if deltas else None,
        "mean_adaptive_residual_ratio": round(sum(ratios) / len(ratios), 6) if ratios else None,
        "mean_point_reduction_fraction_vs_fixed_match": _mean(
            [
                report["comparison"].get("point_reduction_fraction_vs_fixed_match")
                for report in reports
                if isinstance(report["comparison"].get("point_reduction_fraction_vs_fixed_match"), (int, float))
            ]
        ),
        "mean_lower_bound_point_reduction_fraction": _mean(
            [
                report["comparison"].get("lower_bound_point_reduction_fraction")
                for report in reports
                if isinstance(report["comparison"].get("lower_bound_point_reduction_fraction"), (int, float))
            ]
        ),
        "adaptive_beats_full_fixed_grid_count": sum(1 for report in reports if report["comparison"].get("adaptive_beats_full_fixed_grid") is True),
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _markdown_report(payload: dict) -> str:
    lines = [
        "# Adaptive Characterization Benchmark",
        "",
        "This report compares belief-driven adaptive characterization against fixed-grid characterization in simulation.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Per-Model Results",
            "",
            "| Model | Adaptive Points | Fixed Same-Budget Residual | Adaptive Residual | Residual Ratio | Fixed Match | Point Reduction | Lower Bound Reduction | Beats Full Fixed | Confidence Δ |",
            "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | ---: |",
        ]
    )
    for report in payload["reports"]:
        comparison = report["comparison"]
        fixed_match = comparison["fixed_grid_match"]
        fixed_match_label = (
            str(fixed_match.get("fixed_points_to_match"))
            if fixed_match.get("matched")
            else f">{fixed_match.get('max_fixed_points')}"
        )
        lines.append(
            "| {model} | {points} | {fixed_residual} | {adaptive_residual} | {ratio} | {fixed_match} | {point_reduction} | {lower_bound} | {beats} | {confidence_delta} |".format(
                model=report["model"],
                points=comparison["point_budget"],
                fixed_residual=report["fixed_grid"]["residual_overall_mean_abs"],
                adaptive_residual=report["adaptive"]["residual_overall_mean_abs"],
                ratio=comparison["adaptive_residual_ratio"],
                fixed_match=fixed_match_label,
                point_reduction=comparison["point_reduction_fraction_vs_fixed_match"],
                lower_bound=comparison["lower_bound_point_reduction_fraction"],
                beats=comparison["adaptive_beats_full_fixed_grid"],
                confidence_delta=comparison["confidence_delta_adaptive_minus_fixed"],
            )
        )
    lines.extend(["", "## Notes", "", "- Residuals are normalized mean absolute current residuals with low-current clipping for stability.", "- Lower-bound reduction is used when adaptive beats the full fixed grid before fixed-grid reaches the same residual."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
