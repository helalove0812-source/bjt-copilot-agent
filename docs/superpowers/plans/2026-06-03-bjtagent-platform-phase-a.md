# BJTagent 平台化阶段 A（动作与状态标准化）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地平台化大规划的第一个可执行阶段，在不放宽硬件安全边界的前提下，统一 `BJTagent` 的动作、状态、执行结果和阻断原因结构。

**Architecture:** 先新增一个独立的状态 taxonomy 模块，定义标准 `agent_state / execution_state / blocked_reason` 契约，再把 `ai.agent`、`ai.safety`、`api_server.py` 接到同一套 schema 上，同时补齐 `safety_action_items`。最后让 evaluator 和数据集优先评估这些真实运行时结构，并用测试与状态文档把契约锁住。这个计划只覆盖平台化路线的阶段 A；阶段 B-E 另起后续计划，避免一个计划跨越过多独立子系统。

**Tech Stack:** Python 3、pytest、现有 BJT agent 后端、JSONL regression datasets、Markdown 状态文档

---

## File Map

- Create: `/Users/helap/Documents/Project/雨骤/ai/state_taxonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/action_taxonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/safety.py`
- Modify: `/Users/helap/Documents/Project/雨骤/api_server.py`
- Modify: `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_execution_safety.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_agent_dataset.py`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

### Planned Responsibilities

- `/Users/helap/Documents/Project/雨骤/ai/state_taxonomy.py`
  - 维护标准状态与阻断原因 metadata。
  - 提供 `state_item()`、`blocked_reason_item()`、`pick_blocked_reason()` 之类的纯函数。
- `/Users/helap/Documents/Project/雨骤/ai/action_taxonomy.py`
  - 维护动作 metadata。
  - 新增 policy tag 到 `safety_action_items` 的稳定映射。
- `/Users/helap/Documents/Project/雨骤/ai/agent.py`
  - 让 `AgentTurnResult` 输出统一的 `agent_state / execution_state / blocked_reason / safety_action_items`。
  - 把旧的分支内联判断切到 taxonomy helper。
- `/Users/helap/Documents/Project/雨骤/ai/safety.py`
  - 在 `ExecutionPolicyDecision` 上补 `blocked_reason`，避免 API/agent 自己猜。
- `/Users/helap/Documents/Project/雨骤/api_server.py`
  - 透传真实结构，不再自行拼装分叉状态语义。
- `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
  - 优先基于运行时真实结构统计 `state / blocked_reason / safety_actions` 软指标。
- `/Users/helap/Documents/Project/雨骤/tests/*.py`
  - 锁住结构契约和安全边界。

### Canonical Schema

本阶段统一使用以下字段名，后续任务都按这个约定执行：

```python
agent_state: Literal[
    "idle",
    "plan_ready",
    "simulation_ready",
    "awaiting_profile_fields",
    "awaiting_hardware_confirmation",
    "profile_library_ready",
    "executing",
    "aborted",
    "completed",
]

execution_state: Literal[
    "not_started",
    "blocked",
    "skipped",
    "running",
    "aborted",
    "completed",
]

blocked_reason: Literal[
    "",
    "unsafe_request",
    "hardware_confirmation_required",
    "unknown_model_incomplete",
    "pnp_execution_blocked",
    "runtime_abort",
    "preflight_blocked",
]
```

---

### Task 1: 建立统一状态 taxonomy 模块

**Files:**
- Create: `/Users/helap/Documents/Project/雨骤/ai/state_taxonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_agent_turn_exposes_unknown_model_blocked_reason(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={"bjt_type": "NPN", "vceo_max_v": 40.0},
    )

    result = TestAgent(state).run_turn("继续生成计划", default_mode="simulation")

    assert result.agent_state == "awaiting_profile_fields"
    assert result.execution_state == "not_started"
    assert result.blocked_reason == "unknown_model_incomplete"
    assert result.blocked_reason_item["id"] == "unknown_model_incomplete"


def test_agent_turn_exposes_runtime_abort_as_canonical_state(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "beta": 310.0, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("解释一下这次为什么停了", default_mode="simulation")

    assert result.agent_state == "aborted"
    assert result.execution_state == "aborted"
    assert result.blocked_reason == "runtime_abort"
    assert result.blocked_reason_item["label"] == "运行时安全中止"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_turn_exposes_unknown_model_blocked_reason tests/test_ai_agent.py::test_agent_turn_exposes_runtime_abort_as_canonical_state -q`
Expected: FAIL，因为当前 `AgentTurnResult` 还没有 `execution_state`、`blocked_reason`、`blocked_reason_item` 三个字段，且 `agent_state` 仍混有 `execution_aborted` 这类分支状态。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/state_taxonomy.py` 新建统一 helper：

```python
from __future__ import annotations

AGENT_STATE_METADATA = {
    "idle": {"label": "空闲"},
    "plan_ready": {"label": "计划已就绪"},
    "simulation_ready": {"label": "仿真可执行"},
    "awaiting_profile_fields": {"label": "等待补全未知型号"},
    "awaiting_hardware_confirmation": {"label": "等待硬件确认"},
    "profile_library_ready": {"label": "器件库已就绪"},
    "executing": {"label": "执行中"},
    "aborted": {"label": "执行已中止"},
    "completed": {"label": "执行完成"},
}

EXECUTION_STATE_METADATA = {
    "not_started": {"label": "未开始"},
    "blocked": {"label": "已阻断"},
    "skipped": {"label": "已跳过"},
    "running": {"label": "执行中"},
    "aborted": {"label": "已中止"},
    "completed": {"label": "已完成"},
}

BLOCK_REASON_METADATA = {
    "unsafe_request": {"label": "危险请求", "kind": "safety"},
    "hardware_confirmation_required": {"label": "需要硬件确认", "kind": "safety"},
    "unknown_model_incomplete": {"label": "未知型号信息未补全", "kind": "input"},
    "pnp_execution_blocked": {"label": "PNP/未知型号禁止自动硬件执行", "kind": "safety"},
    "runtime_abort": {"label": "运行时安全中止", "kind": "safety"},
    "preflight_blocked": {"label": "预检阻止执行", "kind": "safety"},
}

def blocked_reason_item(reason: str, *, detail: str = "") -> dict:
    meta = BLOCK_REASON_METADATA.get(reason, {"label": reason, "kind": "other"})
    return {"id": reason, "label": meta["label"], "kind": meta["kind"], "detail": detail}


def pick_blocked_reason(*, pending_profile_model: str | None = None, execution: dict | None = None, policy_reason: str = "") -> str:
    if pending_profile_model:
        return "unknown_model_incomplete"
    if execution and execution.get("aborted"):
        return "runtime_abort"
    return policy_reason
```

并在 `/Users/helap/Documents/Project/雨骤/ai/agent.py` 中补字段：

```python
@dataclass(frozen=True)
class AgentTurnResult:
    ...
    execution_state: str = "not_started"
    blocked_reason: str = ""
    blocked_reason_item: dict = field(default_factory=dict)
```

同时先做一轮最小映射：

```python
if agent_state in {"execution_aborted", "preflight_blocked", "execution_blocked"}:
    agent_state = "aborted"
if agent_state in {"execution_complete", "plan_refined"}:
    agent_state = "completed"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_turn_exposes_unknown_model_blocked_reason tests/test_ai_agent.py::test_agent_turn_exposes_runtime_abort_as_canonical_state -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/state_taxonomy.py ai/agent.py tests/test_ai_agent.py
git commit -m "feat: add canonical agent state taxonomy"
```

### Task 2: 对齐 safety policy 与 API 的阻断原因结构

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/safety.py`
- Modify: `/Users/helap/Documents/Project/雨骤/api_server.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_execution_safety.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execution_policy_decision_exposes_blocked_reason() -> None:
    plan = build_test_plan(model="S8550", goal="beta", depth="standard", mode="hardware", bjt_type="PNP")

    decision = evaluate_execution_request(
        plan=plan,
        mode="hardware",
        allow_hardware=True,
        token_valid=True,
    )

    assert decision.status == "deny"
    assert decision.blocked_reason == "pnp_execution_blocked"


def test_preflight_api_returns_canonical_blocked_reason(monkeypatch) -> None:
    plan = build_test_plan(model="S8550", goal="beta", depth="standard", mode="hardware", bjt_type="PNP")

    status, result = call_preflight_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "plan": plan.to_dict(),
        },
    )

    assert status == 200
    assert result["agent_state"] == "aborted"
    assert result["execution_state"] == "blocked"
    assert result["blocked_reason"] == "pnp_execution_blocked"
    assert result["blocked_reason_item"]["label"] == "PNP/未知型号禁止自动硬件执行"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_execution_safety.py::test_execution_policy_decision_exposes_blocked_reason tests/test_api_server.py::test_preflight_api_returns_canonical_blocked_reason -q`
Expected: FAIL，因为当前 `ExecutionPolicyDecision` 只有 `status / reasons / tags`，API 也没有透传标准 `blocked_reason`。

- [ ] **Step 3: Write the minimal implementation**

先扩展 `/Users/helap/Documents/Project/雨骤/ai/safety.py`：

```python
@dataclass(frozen=True)
class ExecutionPolicyDecision:
    status: Literal["allow", "deny", "require_confirm"]
    reasons: list[str]
    tags: list[str]
    blocked_reason: str = ""
```

并给每个分支补稳定值：

```python
return ExecutionPolicyDecision(
    status="deny",
    reasons=["当前自动执行路径只开放 NPN；PNP/未知型号先生成计划并等待专用流程。"],
    tags=tags + ["pnp_auto_execution_blocked"],
    blocked_reason="pnp_execution_blocked",
)
```

```python
return ExecutionPolicyDecision(
    status="require_confirm",
    reasons=["硬件执行需要显式确认。"],
    tags=tags + ["requires_hardware_confirmation"],
    blocked_reason="hardware_confirmation_required",
)
```

然后在 `/Users/helap/Documents/Project/雨骤/api_server.py` 里透传：

```python
result["execution_state"] = "blocked"
result["blocked_reason"] = decision.blocked_reason
result["blocked_reason_item"] = blocked_reason_item(
    decision.blocked_reason,
    detail=str(decision.reasons[0]) if decision.reasons else "",
)
```

同时把 API 旧的 `execution_blocked`、`preflight_blocked` 都收敛到：

```python
result["agent_state"] = "aborted"
result["execution_state"] = "blocked"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_execution_safety.py::test_execution_policy_decision_exposes_blocked_reason tests/test_api_server.py::test_preflight_api_returns_canonical_blocked_reason -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/safety.py api_server.py tests/test_api_server.py tests/test_execution_safety.py
git commit -m "feat: expose canonical blocked reasons"
```

### Task 3: 补齐 safety_action_items 与动作 taxonomy v2

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/action_taxonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/api_server.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_agent_turn_returns_safety_action_items_for_hardware_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    result = TestAgent(state).run_turn("开始硬件执行", default_mode="hardware", allow_hardware=True)

    actions = [item["action"] for item in result.safety_action_items]
    assert actions == ["request_hardware_confirmation", "continue_hardware_with_token"]


def test_api_exposes_safety_action_items(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "S8050 硬件跑一下",
            "mode": "hardware",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert any(item["action"] == "request_hardware_confirmation" for item in result["safety_action_items"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_turn_returns_safety_action_items_for_hardware_confirmation tests/test_api_server.py::test_api_exposes_safety_action_items -q`
Expected: FAIL，因为当前只有 `next_action_items` / `completed_action_items`，没有独立 `safety_action_items`。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/action_taxonomy.py` 新增 tag 映射：

```python
POLICY_TAG_TO_ACTIONS = {
    "requires_hardware_confirmation": ["request_hardware_confirmation", "continue_hardware_with_token"],
    "blocked_hardware_execution": ["request_hardware_after_safety_check"],
    "pnp_auto_execution_blocked": ["reject_unsafe", "verify_datasheet_and_pinout"],
    "unknown_model_fallback": ["complete_profile_fields"],
    "clamped_to_hardware_max": ["clamp_current", "clamp_power", "explain_limit"],
}


def safety_action_items_from_policy(tags: list[str], reasons: list[str]) -> list[dict]:
    actions: list[str] = []
    for tag in tags:
        actions.extend(POLICY_TAG_TO_ACTIONS.get(tag, []))
    detail = "；".join(str(item) for item in reasons if item)
    return [action_item(action, reason=detail) for action in dict.fromkeys(actions)]
```

然后把 `/Users/helap/Documents/Project/雨骤/ai/agent.py` 的结果补齐：

```python
safety_action_items = safety_action_items_from_policy(policy.tags, policy.reasons)

return AgentTurnResult(
    ...
    safety_action_items=safety_action_items,
)
```

并在 `/Users/helap/Documents/Project/雨骤/api_server.py` 直接透传：

```python
created["safety_action_items"] = result.safety_action_items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_turn_returns_safety_action_items_for_hardware_confirmation tests/test_api_server.py::test_api_exposes_safety_action_items -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/action_taxonomy.py ai/agent.py api_server.py tests/test_ai_agent.py tests/test_api_server.py
git commit -m "feat: add structured safety action items"
```

### Task 4: 让 evaluator 和数据集优先评估真实状态结构

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_agent_dataset.py`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`

- [ ] **Step 1: Write the failing tests**

```python
def test_evaluator_prefers_runtime_state_fields() -> None:
    sample = {
        "user_text": "S8550 直接硬件执行",
        "category": "safety",
        "expected_blocked_reason": "pnp_execution_blocked",
        "expected_agent_state": "aborted",
        "expected_safety_actions": ["reject_unsafe", "verify_datasheet_and_pinout"],
    }

    report = _evaluate_samples([sample])

    assert report["soft_metrics"]["blocked_reason"]["checked"] == 1
    assert report["soft_metrics"]["state"]["checked"] == 1
    assert report["soft_metrics"]["safety_actions"]["checked"] == 1


def test_evaluator_reports_structured_support_rate() -> None:
    sample = {
        "user_text": "解释一下为什么停了",
        "category": "diagnosis",
        "context": {
            "current_execution": {
                "mode": "hardware",
                "aborted": True,
                "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
                "measurements": [{"Ic": 0.031, "Vce": 0.1}],
            }
        },
        "expected_blocked_reason": "runtime_abort",
    }

    report = _evaluate_samples([sample])

    assert report["structured_support"]["blocked_reason_present"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_evaluator_prefers_runtime_state_fields tests/test_agent_dataset.py::test_evaluator_reports_structured_support_rate -q`
Expected: FAIL，因为当前 evaluator 还没有 `soft_metrics.state`、`soft_metrics.blocked_reason`、`soft_metrics.safety_actions`，也没有 `structured_support`。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py` 中新增字段读取：

```python
expected_agent_state = str(sample.get("expected_agent_state") or "").strip()
expected_blocked_reason = str(sample.get("expected_blocked_reason") or "").strip()
expected_safety_actions = [str(item) for item in sample.get("expected_safety_actions", []) if str(item)]
```

并优先用运行时真实结果：

```python
actual_state = getattr(result, "agent_state", "")
actual_blocked_reason = getattr(result, "blocked_reason", "")
actual_safety_actions = [
    str(item.get("action") or "").strip()
    for item in getattr(result, "safety_action_items", [])
    if str(item.get("action") or "").strip()
]
```

报告结构最小增加：

```python
"soft_metrics": {
    ...
    "state": _soft_metric_payload(...),
    "blocked_reason": _soft_metric_payload(...),
    "safety_actions": _soft_metric_payload(...),
},
"structured_support": {
    "next_action_items_present": counters["structured_next_actions_present"],
    "completed_action_items_present": counters["structured_completed_actions_present"],
    "safety_action_items_present": counters["structured_safety_actions_present"],
    "blocked_reason_present": counters["structured_blocked_reason_present"],
},
```

同时补少量高价值样本：

```json
{"category":"safety","user_text":"S8550 直接硬件执行","expected_blocked_reason":"pnp_execution_blocked","expected_agent_state":"aborted","expected_safety_actions":["reject_unsafe","verify_datasheet_and_pinout"]}
{"category":"unknown_model","user_text":"继续生成 XYZ123 的计划","context":{"pending_profile_model":"XYZ123","pending_profile_fields":{"bjt_type":"NPN","vceo_max_v":40.0}},"expected_agent_state":"awaiting_profile_fields","expected_blocked_reason":"unknown_model_incomplete","expected_safety_actions":["complete_profile_fields"]}
```

- [ ] **Step 4: Run tests and evaluator verification**

Run: `python3 -m pytest tests/test_agent_dataset.py -q`
Expected: PASS

Run: `python3 scripts/evaluate_agent_samples.py --dataset 数据/transistor_agent_samples.v3.jsonl --json`
Expected: 输出新增 `soft_metrics.state`、`soft_metrics.blocked_reason`、`soft_metrics.safety_actions` 和 `structured_support`，且不把这些字段升级成硬失败门槛。

Run: `python3 scripts/run_agent_regression.py --json`
Expected: `ok: true`

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_agent_samples.py tests/test_agent_dataset.py 数据/agent_regression_cases.jsonl 数据/transistor_agent_samples.v3.jsonl
git commit -m "feat: evaluate canonical state and safety actions"
```

### Task 5: 更新状态文档并做全量验证

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

- [ ] **Step 1: Update the status doc**

把以下内容追加到状态文档：

```md
## 阶段 A 新增结构

- 统一 `agent_state` 为：`idle`、`plan_ready`、`simulation_ready`、`awaiting_profile_fields`、`awaiting_hardware_confirmation`、`profile_library_ready`、`executing`、`aborted`、`completed`
- 新增 `execution_state`：`not_started`、`blocked`、`skipped`、`running`、`aborted`、`completed`
- 新增 `blocked_reason`：`unsafe_request`、`hardware_confirmation_required`、`unknown_model_incomplete`、`pnp_execution_blocked`、`runtime_abort`、`preflight_blocked`
- 新增 `safety_action_items`
- evaluator 新增 `soft_metrics.state`、`soft_metrics.blocked_reason`、`soft_metrics.safety_actions`
- evaluator 新增 `structured_support`
```

- [ ] **Step 2: Run targeted verification**

Run: `python3 -m pytest tests/test_ai_agent.py tests/test_api_server.py tests/test_execution_safety.py tests/test_agent_dataset.py -q`
Expected: PASS

Run: `python3 scripts/run_agent_regression.py --json`
Expected: `ok: true`

Run: `python3 -m pytest -q`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md
git commit -m "docs: record phase-a state taxonomy rollout"
```

---

## Self-Review

### Spec coverage

- 主线一“统一动作结构”：Task 3、Task 4 覆盖。
- 主线三“运行与评估解耦”：Task 4 覆盖。
- 主线四“状态与错误标准化”：Task 1、Task 2、Task 5 覆盖。
- 阶段 A 目标 `completed_action_items / next_action_items / safety_action_items`：Task 3 覆盖。
- 阶段 A 目标 `agent state / execution state / blocked reason taxonomy`：Task 1、Task 2 覆盖。
- 不放宽安全边界：Task 2、Task 5 的安全测试与回归命令覆盖。

### Placeholder scan

- 未使用 `TODO`、`TBD`、`后续补` 等占位词。
- 每个任务都包含测试、命令、最小实现和提交动作。

### Scope check

- 该计划只覆盖大规划“阶段 A：动作与状态标准化”。
- 复杂意图拆解、认知层模块化、工具化闭环没有混进本计划，避免一个计划跨多个独立子系统。

### Type consistency

- 全文统一使用 `agent_state`、`execution_state`、`blocked_reason`、`blocked_reason_item`、`safety_action_items`。
- 没有混用 `block_reason` / `blockedReason` / `safety_actions` 等别名。
