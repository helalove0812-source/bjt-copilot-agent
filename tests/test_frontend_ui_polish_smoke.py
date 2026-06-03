from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_ai_panel_state_is_hoisted_to_app_for_tab_switches() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert 'const [aiMessages, setAiMessages] = useState([]);' in source
    assert 'msgs={aiMessages}' in source
    assert 'setMsgs={setAiMessages}' in source


def test_bjtagent_system_messages_use_dedup_helper() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "const pushUniqueSystemMessage = (message, dedupeKey = message) =>" in source
    assert 'pushUniqueSystemMessage("BJTagent：识别到未知型号，进入规格补全流程"' in source
    assert 'pushUniqueSystemMessage("BJTagent：已记录规格字段，继续等待缺失信息"' in source


def test_unknown_model_panel_has_reply_hint_copy() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "可直接回复：" in source
    assert "NPN，Vceo 40V，Ic 200mA，Ptot 500mW" in source


def test_hardware_confirmation_copy_calls_out_real_risk() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "存在误接线、器件损坏或过流风险" in source
    assert "请确认器件、夹具、引脚、限流电阻、量程和供电状态已经检查" in source


def test_small_screen_layout_keeps_inspector_visible() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert '@media (max-width:1080px){.app{grid-template-columns:220px minmax(0,1fr);grid-template-areas:"sidebar content" "sidebar inspector"}' in source
    assert '@media (max-width:820px){.window{height:auto;min-height:calc(100vh - 56px)}.app{grid-template-columns:1fr;grid-template-areas:"sidebar" "content" "inspector"}' in source
    assert ".inspector{max-height:none}" in source


def test_desktop_layout_declares_three_panel_grid_areas() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert '.app{flex:1;display:grid;grid-template-columns:268px minmax(0,1fr) 320px;grid-template-areas:"sidebar content inspector";min-height:0}' in source


def test_agent_intent_debug_toggle_is_available() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "formatIntentDebug" in source
    assert "showIntentDebug" in source
    assert "debug_intent: showIntentDebug" in source
    assert "显示理解过程" in source
    assert "white-space:pre-wrap" in source
