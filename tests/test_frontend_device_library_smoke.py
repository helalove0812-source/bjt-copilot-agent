from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_device_library_panel_has_primary_tabs() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert '"BJTagent"' in source
    assert '"器件库"' in source
    assert "options={[\"BJTagent\", \"器件库\"]}" in source


def test_device_library_panel_has_search_and_create_controls() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "搜索器件库" in source
    assert "新增器件" in source
    assert "仅看启用" in source


def test_device_library_panel_uses_user_profile_api_routes() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "/api/user-profiles" in source
    assert "/api/user-profiles/update" in source
    assert "/api/user-profiles/delete" in source
    assert "/api/user-profiles/toggle-enabled" in source


def test_agent_library_commands_can_switch_to_library_panel() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert 'setRightPanel("器件库")' in source
    assert "列出已保存型号" in source
    assert "查看 " in source
