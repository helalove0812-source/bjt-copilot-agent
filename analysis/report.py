from __future__ import annotations

from pathlib import Path


def build_report_summary(report, artifacts):
    artifact_paths = {
        name: str(path)
        for name, path in artifacts.items()
    }
    return {
        "headline": {
            "dut_label": report.dut_label,
            "serial": report.serial,
            "bjt_type": report.bjt_type,
            "beta_median": report.beta_median,
            "vce_sat": report.vce_sat,
        },
        "artifact_count": len(artifact_paths),
        "artifacts": artifact_paths,
    }


def build_artifact_manifest(output_dir: Path) -> dict:
    return {
        "summary_json": output_dir / "summary.json",
    }
