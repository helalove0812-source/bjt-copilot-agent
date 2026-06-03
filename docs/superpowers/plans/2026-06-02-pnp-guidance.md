# PNP Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `PNP` 型号请求提供引导性保守计划和明确说明，而不是只给自动执行拒绝。

**Architecture:** 通过对话层和 planner 层把 `PNP` 请求默认收敛为 `screening + conservative`，并在响应中明确说明 `PNP` 接线差异、自动执行限制和下一步人工低压确认建议。执行层和安全策略层保持不变，继续阻断 `PNP` 自动执行。

**Tech Stack:** Python 3.9、pytest、现有 conversation/planner/agent 流程

---

### Task 1: `PNP` 请求默认收敛为保守筛查计划

**Files:**
- Modify: `ai/conversation.py`
- Modify: `ai/test_planner.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: 写失败测试**

```python
def test_pnp_request_defaults_to_screening_and_conservative() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("测一下 S8550", state)

    assert intent.action == "create_plan"
    assert intent.model == "S8550"
    assert intent.goal == "screening"
    assert intent.depth == "conservative"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_pnp_request_defaults_to_screening_and_conservative -q`
Expected: FAIL，说明当前 `PNP` 请求仍按普通目标/深度推断

- [ ] **Step 3: 写最小实现**

```python
if has_model and lookup_transistor(guessed_model).bjt_type == "PNP":
    if goal in (None, "auto", "beta", "full"):
        goal = "screening"
    if depth in (None, "standard", "deep"):
        depth = "conservative"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_pnp_request_defaults_to_screening_and_conservative -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/conversation.py ai/test_planner.py tests/test_ai_conversation.py
git commit -m "feat: default pnp requests to conservative screening plans"
```

### Task 2: 强化 `PNP` 计划的引导性安全说明

**Files:**
- Modify: `ai/test_planner.py`
- Modify: `tests/test_ai_safety_regression.py`

- [ ] **Step 1: 写失败测试**

```python
def test_pnp_plan_contains_guidance_notes() -> None:
    plan = build_test_plan(model="S8550", goal="screening", depth="conservative")

    notes = "\n".join(plan.safety_notes)
    assert "自动执行" in notes
    assert "NPN" in notes
    assert "datasheet" in notes or "引脚" in notes
    assert "低压" in notes
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_regression.py::test_pnp_plan_contains_guidance_notes -q`
Expected: FAIL，说明当前 `safety_notes` 还不够“引导计划”语义

- [ ] **Step 3: 写最小实现**

```python
if profile.bjt_type == "PNP":
    safety_notes.extend(
        [
            "当前自动执行路径只开放 NPN，PNP 计划仅用于引导和人工低压确认。",
            "PNP 的偏置和接线方向与 NPN 不同，继续前必须核对 datasheet 与 E/B/C 引脚。",
            "建议先从低压、低电流、人工确认路径开始，不要直接自动上电。",
        ]
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_safety_regression.py::test_pnp_plan_contains_guidance_notes -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/test_planner.py tests/test_ai_safety_regression.py
git commit -m "feat: add explicit guidance notes to pnp plans"
```

### Task 3: Agent 返回 `PNP` 引导响应

**Files:**
- Modify: `ai/agent.py`
- Modify: `ai/assistant.py`
- Modify: `tests/test_ai_agent.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_returns_guidance_response_for_pnp_plan(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    agent = TestAgent()

    result = agent.run_turn("测一下 S8550")

    assert result.plan is not None
    assert result.plan.bjt_type == "PNP"
    assert "PNP" in result.response
    assert "自动执行" in result.response
    assert "低压" in result.response or "人工确认" in result.response
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_returns_guidance_response_for_pnp_plan -q`
Expected: FAIL，说明当前仍返回普通计划摘要

- [ ] **Step 3: 写最小实现**

```python
if plan and plan.bjt_type == "PNP":
    response = (
        "已识别为 PNP 型号 {0}。当前自动执行路径只开放 NPN，因为 PNP 的偏置和接线方向不同。"
        "已为你生成保守筛查计划；继续前请先核对 datasheet、E/B/C 引脚和夹具方向，并从低压人工确认开始。"
    ).format(plan.model)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_returns_guidance_response_for_pnp_plan -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py ai/assistant.py tests/test_ai_agent.py
git commit -m "feat: return guided responses for pnp plans"
```

### Task 4: 全量回归验证

**Files:**
- Modify: `README.md`
- Test: `tests/test_ai_safety_regression.py`

- [ ] **Step 1: 写失败测试**

```python
def test_pnp_plan_remains_blocked_for_auto_hardware_execution() -> None:
    plan = build_test_plan(model="S8550", goal="screening", depth="conservative", mode="hardware")

    decision = evaluate_execution_request(
        plan=plan,
        mode="hardware",
        allow_hardware=True,
        token_valid=True,
    )

    assert decision.status == "deny"
    assert "pnp_auto_execution_blocked" in decision.tags
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_regression.py::test_pnp_plan_remains_blocked_for_auto_hardware_execution -q`
Expected: 如果本轮误改了执行底线，这里会 FAIL

- [ ] **Step 3: 写最小实现**

```markdown
Update README notes to explain that PNP requests now produce conservative guidance plans but auto-execution stays blocked.
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python3 -m pytest -q
python3 scripts/run_agent_regression.py --json
```

Expected:

- 全量 pytest PASS
- 统一回归脚本 PASS
- `PNP` 自动执行仍被阻断

- [ ] **Step 5: Commit**

```bash
git add README.md ai/conversation.py ai/test_planner.py ai/agent.py ai/assistant.py tests/test_ai_conversation.py tests/test_ai_agent.py tests/test_ai_safety_regression.py
git commit -m "feat: guide pnp requests with conservative plans"
```
