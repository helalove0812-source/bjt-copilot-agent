from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_ai_chat_roundtrip_persists_conversation_state() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "const [conversationState, setConversationState] = useState(null);" in source
    assert "conversation_state: conversationState," in source
    assert "setConversationState(data.conversation_state || null);" in source
    assert 'const [aiAgentMode, setAiAgentMode] = useState("tool_calling");' in source
    assert "agent_mode: agentMode," in source
    assert "provider: llmModel?.provider" in source
    assert "base_url: llmModel?.baseUrl" in source
    assert "api_key: llmModel?.apiKey" in source


def test_bjtagent_status_and_unknown_model_copy_exist() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent" in source
    assert "等待补充未知型号规格" in source
    assert "当前正在补全：" in source
    assert "已记录字段：" in source
    assert "缺失字段：" in source
    assert "任务列表" in source
    assert "长期记忆" in source
    assert "setAgentTrace" in source
    assert "data.tool_calls" in source
    assert "data.task_graph" in source
    assert "taskSubtasks" in source
    assert "pendingPlanUpdate" in source
    assert "formatPendingPlanUpdate" in source
    assert "formatToolTaskObjective" in source
    assert "agent-task-meta" in source
    assert 'const RIGHT_PANEL_OPTIONS = ["BJTagent", "设置", "器件库"];' in source
    assert "function AgentSettingsPanel" in source
    assert "settings-checks" in source
    assert "agent-controls" not in source
    assert "DEFAULT_LLM_MODELS" in source
    assert "添加模型" in source
    assert "模型列表" in source
    assert "LLM_MODEL_STORAGE_KEY" in source
    assert 'options={["本地", "DeepSeek"]}' not in source


def test_bjtagent_action_log_copy_exists() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent：识别到未知型号，进入规格补全流程" in source
    assert "BJTagent：已记录规格字段，继续等待缺失信息" in source
    assert "BJTagent：规格已完整，可生成保守计划" in source
    assert "BJTagent：当前为硬件模式，执行前仍需要确认" in source
    assert "const [handledAgentEventId, setHandledAgentEventId] = useState(null);" in source
    assert "agentEvent.id === handledAgentEventId" in source
