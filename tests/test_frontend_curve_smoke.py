from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_output_chart_groups_points_by_vbb_and_draws_curves() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "const curveGroups = useMemo" in source
    assert "Vbb ${point.vbb.toFixed(2)}V" in source
    assert "<path className=\"curve\" d={d} />" in source
    assert "Ic (${yAxis.unit})" in source


def test_frontend_consumes_latest_measurement_focus_point() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "const [focusMeasurement, setFocusMeasurement] = useState(null);" in source
    assert "const latestPoint = focusMeasurement || measurements[measurements.length - 1] || null;" in source
    assert "applyMeasurements(execution.measurements || [], execution.latest_measurement || null)" in source
    assert "applyMeasurements(result.measurements, result.latest_measurement || null)" in source


def test_frontend_clears_focus_measurement_before_new_scan_like_actions() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "setFocusMeasurement(null);" in source
    assert "setMeasurements([]);" in source
    assert 'if (["static", "vce_sat", "scan_curves", "full_suite"].includes(action)) {' in source
