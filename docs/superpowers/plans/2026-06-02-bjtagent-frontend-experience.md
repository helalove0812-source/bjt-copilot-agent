# BJTagent Frontend Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Web UI 增加 `BJTagent` 状态卡、未知型号补全提示、`conversation_state` 保存回传和轻量行动日志，让右侧 AI 面板更像测试 Agent 工作流界面。

**Architecture:** 在 [App.jsx](file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx) 内集中持有前端 Agent 体验状态：保存 `/api/ai-chat` 返回的 `conversation_state`，基于 `busy / plan / runMode / 执行结果` 推导可见状态，并在 AI 面板顶部渲染状态卡与未知型号补全提示。聊天流新增 `system` 消息类型，只展示前端可观察到的状态变化，不展示内部推理链。

**Tech Stack:** React 19、Vite、JSX、pytest、前端 smoke（源码字符串断言）

---

### Task 1: 为 BJTagent 体验层补失败 smoke

**Files:**
- Modify: `tests/test_frontend_abort_smoke.py`
- Create: `tests/test_frontend_agent_experience_smoke.py`
- Test: `frontend/src/App.jsx`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 -m pytest tests/test_frontend_agent_experience_smoke.py -q
```

Expected: FAIL，提示 `conversation_state`、`BJTagent` 状态文案或行动日志文案尚不存在。

- [ ] **Step 3: 保持现有 abort smoke**

```python
def test_execute_plan_logs_runtime_abort_reason_and_kept_points() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "execution.aborted" in source
    assert 'addLog(`执行已中止: ${execution.abort_reason || "未知原因"}`);' in source
    assert 'addLog(`已保留 ${nextMeasurements.length} 个测量点`);' in source
```

- [ ] **Step 4: 运行 smoke 组合确认当前仅新测试失败**

Run:

```bash
python3 -m pytest tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py -q
```

Expected: `test_frontend_abort_smoke.py` PASS，新建体验层 smoke FAIL。

- [ ] **Step 5: Commit**

```bash
git add tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py
git commit -m "test: add frontend agent experience smoke checks"
```

### Task 2: 在 App.jsx 接入 conversation_state 与 BJTagent 状态卡

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_agent_experience_smoke.py`

- [ ] **Step 1: 写最小状态结构**

```jsx
const [conversationState, setConversationState] = useState(null);
const [agentStatus, setAgentStatus] = useState("空闲");
const [lastExecutionState, setLastExecutionState] = useState("idle");
```

- [ ] **Step 2: 在 `/api/ai-chat` 请求里回传 conversation_state**

```jsx
body: JSON.stringify({
  text: q,
  mode: config.runMode,
  config: backendConfig,
  context: {
    current_plan: contextPlan,
    conversation_state: conversationState,
    measurements,
    logs: logs.map((item) => `${item.t} ${item.m}`),
    messages: msgs.map((item) => ({ role: item.role === "me" ? "user" : "assistant", content: item.text })),
  },
  ai_settings: {
    provider: provider === 1 ? "deepseek" : "local",
    model,
    api_key: apiKey,
  },
})
```

- [ ] **Step 3: 在 `/api/ai-chat` 响应里保存 conversation_state**

```jsx
const data = await res.json();
if (!res.ok || !data.ok) throw new Error(data.error || "API unavailable");
setApiOnline(true);
setConversationState(data.conversation_state || null);
if (data.plan) onPlanReady?.(data.plan);
setMsgs((m) => [...m, { role: "ai", text: data.response }]);
```

- [ ] **Step 4: 添加缺失字段与状态推导 helper**

```jsx
const PROFILE_FIELD_LABELS = {
  bjt_type: "管型",
  vceo_max_v: "Vceo",
  ic_max_a: "Ic",
  p_tot_w: "Ptot",
};

function missingProfileFields(state) {
  const fields = state?.pending_profile_fields || {};
  return ["bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"].filter((key) => !(key in fields));
}

function deriveAgentStatus({ busy, conversationState, currentPlan, runMode, lastExecutionState }) {
  if (busy) return "执行中";
  if (lastExecutionState === "aborted") return "执行中止";
  if (lastExecutionState === "completed") return "执行完成";
  if (conversationState?.pending_profile_model) return "等待补充未知型号规格";
  if (currentPlan && runMode === "hardware") return "等待硬件确认";
  if (currentPlan && runMode === "simulation") return "仿真可执行";
  if (currentPlan) return "已生成计划";
  return "空闲";
}
```

- [ ] **Step 5: 渲染顶部状态卡**

```jsx
<div className="agent-state-card">
  <div className="agent-state-head">
    <h4>BJTagent</h4>
    <span className="agent-state-pill">{agentStatus}</span>
  </div>
  {conversationState?.pending_profile_model && (
    <div className="agent-profile-hint">
      <div>{`当前正在补全：${conversationState.pending_profile_model}`}</div>
      <div>{`已记录字段：${formatKnownProfileFields(conversationState.pending_profile_fields)}`}</div>
      <div>{`缺失字段：${formatMissingProfileFields(missingProfileFields(conversationState))}`}</div>
    </div>
  )}
</div>
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
python3 -m pytest tests/test_frontend_agent_experience_smoke.py -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_agent_experience_smoke.py
git commit -m "feat: add bjtagent state card and conversation state roundtrip"
```

### Task 3: 为聊天区增加 BJTagent 行动日志

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_agent_experience_smoke.py`

- [ ] **Step 1: 增加 system 消息写入 helper**

```jsx
const addAgentMessage = (text) =>
  setMsgs((m) => [...m, { role: "system", text }]);
```

- [ ] **Step 2: 在 conversation_state 变化时生成行动日志**

```jsx
useEffect(() => {
  if (!conversationState?.pending_profile_model) return;
  addAgentMessage("BJTagent：识别到未知型号，进入规格补全流程");
}, [conversationState?.pending_profile_model]);

useEffect(() => {
  const fields = conversationState?.pending_profile_fields || {};
  const count = Object.keys(fields).length;
  if (count > 0 && missingProfileFields(conversationState).length > 0) {
    addAgentMessage("BJTagent：已记录规格字段，继续等待缺失信息");
  }
  if (count === 4) {
    addAgentMessage("BJTagent：规格已完整，可生成保守计划");
  }
}, [conversationState?.pending_profile_fields]);
```

- [ ] **Step 3: 在计划与执行节点补行动日志**

```jsx
const handlePlanReady = (plan) => {
  ...
  addLog(`AI 计划已载入测试点: ${plan.model} / ${plan.goal} / ${plan.static_points?.length || 0} 个点。`);
  addAgentMessage("BJTagent：计划已载入测试点");
  if (config.runMode === "hardware") {
    addAgentMessage("BJTagent：当前为硬件模式，执行前仍需要确认");
  }
};

addAgentMessage("BJTagent：执行开始，等待测量结果");

if (execution.aborted) {
  addAgentMessage("BJTagent：检测到执行中止，已保留现有测量点");
} else {
  addAgentMessage("BJTagent：执行完成，结果已返回界面");
}
```

- [ ] **Step 4: 为聊天区添加 `system` 样式**

```jsx
{msgs.length === 0 ? INTRO : msgs.map((m, i) => (
  <div key={i} className={"bubble " + m.role}>{m.text}</div>
))}
```

```css
.bubble.system{
  align-self:center;
  background:var(--bg-fill);
  color:var(--label-2);
  border:1px dashed var(--separator);
  max-width:96%;
}
```

- [ ] **Step 5: 运行 smoke 组合确认通过**

Run:

```bash
python3 -m pytest tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py
git commit -m "feat: add bjtagent action log in chat panel"
```

### Task 4: 构建、目标 smoke 与最小前端说明

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `README.md`
- Test: `tests/test_frontend_abort_smoke.py`
- Test: `tests/test_frontend_agent_experience_smoke.py`
- Test: `tests/test_gui_smoke.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: 如需补一条最小前端说明，只补事实描述**

```md
Web UI 的 `BJTagent` 面板会保存并回传 `conversation_state`，用于支持未知型号多轮规格补全；界面显示的是规则 + LLM 可选辅助 + 本地安全策略驱动的 Agent 工作流状态，而不是隐藏推理链。
```

- [ ] **Step 2: 运行前端构建**

Run:

```bash
cd /Users/helap/Documents/Project/雨骤/frontend
npm run build
```

Expected: `vite build` 成功，无构建错误。

- [ ] **Step 3: 运行目标 pytest**

Run:

```bash
cd /Users/helap/Documents/Project/雨骤
python3 -m pytest tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py tests/test_gui_smoke.py tests/test_cli_smoke.py -q
```

Expected: PASS；如有 warnings，仅记录现有依赖 warnings，不新增前端相关失败。

- [ ] **Step 4: 做编辑后诊断检查**

Run diagnostics for:

```text
file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx
file:///Users/helap/Documents/Project/雨骤/tests/test_frontend_agent_experience_smoke.py
```

Expected: 无新的诊断错误。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py README.md
git commit -m "feat: add bjtagent frontend workflow experience"
```
