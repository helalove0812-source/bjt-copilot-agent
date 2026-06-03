# BJTagent 动作建议结构化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 BJTagent 的动作建议从零散中文文案收敛成稳定的结构化输出，并让 API 与 evaluator 优先消费真实动作结构。

**Architecture:** 先在 `ai.agent` 中统一动作对象与 taxonomy，再把 `ai.autonomy` 的已完成动作改成结构化标签，随后让 `api_server.py` 与 `scripts/evaluate_agent_samples.py` 优先读取真实结构化动作，最后用 agent/API/数据集测试锁定契约。整个过程保持 `expected_actions` 为软统计，不升级成硬门槛。

**Tech Stack:** Python 3、pytest、现有 BJT agent 后端、JSON regression datasets

---

### Task 1: 统一动作对象契约

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing test**

```python
def test_agent_completed_actions_are_structured_labels(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [{"beta": 310.0, "region": "saturation", "Ic": 0.031, "Vce": 0.1}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("下一步你自己看着办，优化一下计划")

    assert "clamp_current" in result.completed_actions
    assert "clamp_power" in result.completed_actions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_completed_actions_are_structured_labels -q`
Expected: FAIL，因为当前 `completed_actions` 仍是整句中文，不是稳定 taxonomy。

- [ ] **Step 3: Write minimal implementation**

```python
ACTION_LABELS = {
    "clamp_current": "降低 Ic 上限",
    "clamp_power": "降低功耗上限",
}

def _action(label: str, *, reason: str = "", priority: str = "medium", kind: str = "plan") -> dict:
    return {"action": label, "reason": reason, "priority": priority, "kind": kind}
```

并将：

- `completed_actions` 改成 taxonomy 标签列表
- `next_action_items` 改成以 `action` 为主键的稳定结构

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_completed_actions_are_structured_labels -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py tests/test_ai_agent.py
git commit -m "feat: structure agent action outputs"
```

### Task 2: 让自主优化输出结构化完成动作

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/autonomy.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing test**

```python
def test_agent_autonomous_refine_exposes_structured_completed_actions(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [{"beta": 310.0, "region": "saturation", "Ic": 0.031, "Vce": 0.1}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("下一步你自己看着办，优化一下计划")

    assert {"modify_plan", "clamp_current", "clamp_power"}.issubset(set(result.completed_actions))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_autonomous_refine_exposes_structured_completed_actions -q`
Expected: FAIL，因为 `ai.autonomy` 仍返回中文句子。

- [ ] **Step 3: Write minimal implementation**

```python
completed_actions.extend(["modify_plan", "clamp_current", "clamp_power"])
```

并把解释文案改为通过标签映射生成，而不是把中文句子塞回结构字段。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_autonomous_refine_exposes_structured_completed_actions -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/autonomy.py tests/test_ai_agent.py
git commit -m "feat: add structured autonomous action labels"
```

### Task 3: 对齐 API 输出契约

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/api_server.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

```python
def test_ai_chat_returns_structured_next_action_items(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "测 S8050，重点看 beta",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert any(item["action"] == "run_simulation" for item in result["next_action_items"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_server.py::test_ai_chat_returns_structured_next_action_items -q`
Expected: FAIL，如果 API 仍只回传统 label/id 结构或未对齐 agent 输出。

- [ ] **Step 3: Write minimal implementation**

```python
created["next_action_items"] = result.next_action_items
created["completed_actions"] = result.completed_actions
created["diagnosis_tags"] = result.diagnosis_tags
```

确保 API handler 优先透传真实结构化动作输出，而不是重新拼中文。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_server.py::test_ai_chat_returns_structured_next_action_items -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api_server.py tests/test_api_server.py
git commit -m "feat: expose structured action outputs in api"
```

### Task 4: evaluator 优先消费真实结构化动作

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_agent_dataset.py`

- [ ] **Step 1: Write the failing test**

```python
def test_evaluator_prefers_real_structured_actions() -> None:
    sample = {
        "category": "modify",
        "user_text": "Ic 不超过 10mA",
        "expected_actions": ["modify_plan", "clamp_current"],
    }
    actual = {
        "next_action_items": [{"action": "modify_plan"}, {"action": "clamp_current"}],
        "completed_actions": [],
    }

    assert _actual_actions_from_agent_output(sample, actual) == ["clamp_current", "modify_plan"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_evaluator_prefers_real_structured_actions -q`
Expected: FAIL，如果 evaluator 仍只靠启发式词法映射。

- [ ] **Step 3: Write minimal implementation**

```python
def _actual_actions(...):
    if structured_actions:
        return sorted(set(structured_actions))
    return _fallback_actions_from_text(...)
```

并补少量高价值样本，覆盖：

- `apply_conservative_defaults`
- `run_wiring_check`
- `reject_unsafe`
- `explain_limit`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_evaluator_prefers_real_structured_actions -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_agent_samples.py tests/test_agent_dataset.py 数据/agent_regression_cases.jsonl 数据/transistor_agent_samples.v3.jsonl
git commit -m "feat: evaluate structured action outputs"
```

### Task 5: 全量验证与状态更新

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

- [ ] **Step 1: Update status doc**

记录：

- taxonomy 已覆盖哪些路径
- 哪些动作仍在回退映射
- 给后续前端消费的稳定字段

- [ ] **Step 2: Run targeted verification**

Run: `python3 scripts/run_agent_regression.py --json`
Expected: `ok: true`

Run: `python3 -m pytest -q`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md
git commit -m "docs: update structured action status"
```
