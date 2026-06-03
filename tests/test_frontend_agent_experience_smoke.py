from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_ai_chat_roundtrip_persists_conversation_state() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "const [conversationState, setConversationState] = useState(null);" in source
    assert "conversation_state: conversationState," in source
    assert "setConversationState(data.conversation_state || null);" in source


def test_bjtagent_status_and_unknown_model_copy_exist() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent" in source
    assert "等待补充未知型号规格" in source
    assert "当前正在补全：" in source
    assert "已记录字段：" in source
    assert "缺失字段：" in source


def test_bjtagent_action_log_copy_exists() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent：识别到未知型号，进入规格补全流程" in source
    assert "BJTagent：已记录规格字段，继续等待缺失信息" in source
    assert "BJTagent：规格已完整，可生成保守计划" in source
    assert "BJTagent：当前为硬件模式，执行前仍需要确认" in source
