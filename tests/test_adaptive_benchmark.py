from __future__ import annotations

import json
import subprocess
import sys

from ai.adaptive_benchmark import benchmark_adaptive_vs_fixed


def test_adaptive_benchmark_compares_same_point_budget() -> None:
    report = benchmark_adaptive_vs_fixed(model="S8050", adaptive_iterations=2, adaptive_batch_size=2)
    data = report.to_dict()

    assert data["model"] == "S8050"
    assert data["comparison"]["same_point_budget"] is True
    assert data["adaptive"]["point_count"] == data["fixed_grid"]["point_count"]
    assert data["comparison"]["point_budget"] == data["adaptive"]["point_count"]
    assert data["adaptive"]["model_card"].startswith(".model DUT_S8050 NPN")
    assert data["fixed_grid"]["model_card"].startswith(".model DUT_S8050 NPN")
    assert data["comparison"]["adaptive_residual_ratio"] is not None
    assert "fixed_grid_match" in data["comparison"]
    assert data["comparison"]["fixed_grid_match"]["max_fixed_points"] >= data["comparison"]["point_budget"]
    assert "lower_bound_point_reduction_fraction" in data["comparison"]
    assert "adaptive_beats_full_fixed_grid" in data["comparison"]
    if data["comparison"]["fixed_grid_match"]["matched"]:
        assert data["comparison"]["point_reduction_fraction_vs_fixed_match"] is not None
    else:
        assert data["comparison"]["lower_bound_point_reduction_fraction"] is not None


def test_adaptive_benchmark_script_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_adaptive_benchmark.py",
            "--model",
            "S8050",
            "--iterations",
            "2",
            "--batch-size",
            "2",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["reports"][0]["comparison"]["same_point_budget"] is True
    assert "mean_point_reduction_fraction_vs_fixed_match" in payload["summary"]
    assert "mean_lower_bound_point_reduction_fraction" in payload["summary"]


def test_adaptive_benchmark_script_writes_markdown(tmp_path) -> None:
    output = tmp_path / "adaptive_report.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_adaptive_benchmark.py",
            "--model",
            "S8050",
            "--model",
            "2N3904",
            "--iterations",
            "2",
            "--batch-size",
            "2",
            "--markdown-out",
            str(output),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["markdown_report"] == str(output)
    text = output.read_text(encoding="utf-8")
    assert "# Adaptive Characterization Benchmark" in text
    assert "| S8050 |" in text
    assert "| 2N3904 |" in text
