from __future__ import annotations

import json
from datetime import datetime

from analysis.data_processor import beta_median
from analysis.exporters import write_summary_json
from analysis.report import build_report_summary
from core.types import DeviceReport, HwConfig, StaticPoint
from measurement.linearity import beta_linearity


def test_beta_linearity_matches_expected_ratio():
    points = [
        StaticPoint(0, 5, 0.7, 4.8, 5e-6, 0.6e-3, 0.7, 4.8, 178.0, "active"),
        StaticPoint(0, 5, 0.7, 4.6, 6e-6, 1.2e-3, 0.7, 4.6, 205.0, "active"),
        StaticPoint(0, 5, 0.7, 4.1, 8e-6, 8.0e-3, 0.7, 4.1, 253.0, "active"),
        StaticPoint(0, 5, 0.7, 3.8, 10e-6, 19.5e-3, 0.7, 3.8, 192.0, "active"),
    ]

    result = beta_linearity(
        points,
        ic_range=(0.5e-3, 20e-3),
        vce_window=(2.0, 5.0),
        min_points=4,
    )

    assert round(result.beta_max, 1) == 253.0
    assert round(result.beta_min, 1) == 178.0
    assert round(result.eta, 3) == 0.362


def test_beta_median_and_exports_use_canonical_report(tmp_path):
    points = [
        StaticPoint(0, 5, 0.7, 4.8, 5e-6, 0.6e-3, 0.7, 4.8, 178.0, "active"),
        StaticPoint(0, 5, 0.7, 0.2, 8e-6, 10e-3, 0.7, 0.2, 90.0, "saturation"),
        StaticPoint(0, 5, 0.7, 4.1, 8e-6, 8.0e-3, 0.7, 4.1, 253.0, "active"),
    ]
    report = DeviceReport(
        bjt_type="NPN",
        serial="SIM-BJT-001",
        dut_label="S8050-A1",
        beta_median=beta_median(points),
        beta_active_curve=[points[0], points[2]],
        vce_sat=0.18,
        Ic_at_sat=0.012,
        output_curves={10e-6: [points[0]], 8e-6: [points[2]]},
        early_voltage=None,
        beta_linearity=None,
        hw_config=HwConfig(),
        started_at=datetime(2026, 5, 25, 10, 0, 0),
        finished_at=datetime(2026, 5, 25, 10, 0, 5),
    )

    summary_path = write_summary_json(report, tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report_summary = build_report_summary(report, {"summary_json": summary_path})

    assert report.beta_median == 215.5
    assert summary["dut_label"] == "S8050-A1"
    assert report_summary["artifact_count"] == 1
    assert report_summary["headline"]["serial"] == "SIM-BJT-001"
