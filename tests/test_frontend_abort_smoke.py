from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_execute_plan_logs_runtime_abort_reason_and_kept_points() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "execution.aborted" in source
    assert 'addLog(`执行已中止: ${execution.abort_reason || "未知原因"}`);' in source
    assert 'addLog(`已保留 ${nextMeasurements.length} 个测量点`);' in source
