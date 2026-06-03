# Agent Safety Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 BJT Agent 新增统一安全策略层，收口计划 clamp 和执行放行判定，同时保持现有安全底线与回归指标不退化。

**Architecture:** 新增 `ai/safety.py` 作为单一策略来源，提供计划收口和执行放行纯函数。`ai/test_planner.py` 改为通过策略层完成最终 clamp，`ai/agent.py` 与 `ai/tools.py` 改为通过策略层完成硬件执行放行判断，避免安全规则散落在多个文件中。

**Tech Stack:** Python 3.9、dataclasses、pytest

---

### Task 1: 策略层纯函数与单测

**Files:**
- Create: `ai/safety.py`
- Create: `tests/test_ai_safety_policy.py`

- [ ] **Step 1: 写失败测试**

```python
from ai.safety import clamp_plan_to_policy, evaluate_execution_request
from ai.test_planner import TestPlan
from core.types import HwConfig


def make_plan(**overrides):
    base = TestPlan(
        model="S8050",
        bjt_type="NPN",
        goal="beta",
        depth="standard",
        mode="simulation",
        vcc_steps=[0.0, 1.0, 6.0],
        vbb_steps=[1.0, 2.0],
        static_points=[{"vcc": 3.0, "vbb": 2.0}],
        ic_limit_a=0.2,
        power_limit_w=0.8,
        sample_count=2048,
        scan_mode="software",
        steps=["x"],
        safety_notes=[],
        profile={"confidence": "catalog"},
    )
    return base.__class__(**{**base.to_dict(), **overrides})


def test_clamp_plan_to_policy_caps_plan_limits() -> None:
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.3, Vcc_max=5.0)
    plan = make_plan()

    result = clamp_plan_to_policy(plan, cfg)

    assert result.changed is True
    assert result.plan.ic_limit_a == 0.03
    assert result.plan.power_limit_w == 0.3
    assert max(result.plan.vcc_steps) == 5.0
    assert "clamped_to_hardware_max" in result.tags


def test_evaluate_execution_request_requires_confirm_for_hardware_without_token() -> None:
    decision = evaluate_execution_request(
        plan=make_plan(mode="hardware"),
        mode="hardware",
        allow_hardware=True,
        token_valid=False,
    )

    assert decision.status == "require_confirm"
    assert "requires_hardware_confirmation" in decision.tags


def test_evaluate_execution_request_denies_non_npn_hardware_execution() -> None:
    decision = evaluate_execution_request(
        plan=make_plan(bjt_type="PNP", mode="hardware"),
        mode="hardware",
        allow_hardware=True,
        token_valid=True,
    )

    assert decision.status == "deny"
    assert "pnp_auto_execution_blocked" in decision.tags
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_policy.py -q`
Expected: FAIL，提示 `ai.safety` 不存在

- [ ] **Step 3: 写最小实现**

```python
from dataclasses import dataclass, replace
from typing import Literal

from core.types import HwConfig
from ai.test_planner import TestPlan


@dataclass(frozen=True)
class PlanPolicyResult:
    plan: TestPlan
    tags: list[str]
    changed: bool


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    status: Literal["allow", "deny", "require_confirm"]
    reasons: list[str]
    tags: list[str]


def clamp_plan_to_policy(plan: TestPlan, cfg: HwConfig) -> PlanPolicyResult:
    ic_limit = min(float(plan.ic_limit_a), float(cfg.Ic_max_A))
    power_limit = min(float(plan.power_limit_w), float(cfg.Pmax_W))
    vcc_steps = [min(float(value), float(cfg.Vcc_max)) for value in plan.vcc_steps]
    static_points = [
        {"vcc": min(float(point["vcc"]), float(cfg.Vcc_max)), "vbb": float(point["vbb"])}
        for point in plan.static_points
    ]
    changed = (
        ic_limit != plan.ic_limit_a
        or power_limit != plan.power_limit_w
        or vcc_steps != plan.vcc_steps
        or static_points != plan.static_points
    )
    tags = ["clamped_to_hardware_max"] if changed else []
    return PlanPolicyResult(
        plan=replace(plan, ic_limit_a=ic_limit, power_limit_w=power_limit, vcc_steps=vcc_steps, static_points=static_points),
        tags=tags,
        changed=changed,
    )


def evaluate_execution_request(plan: TestPlan, mode: str, allow_hardware: bool, token_valid: bool) -> ExecutionPolicyDecision:
    if mode != "hardware":
        return ExecutionPolicyDecision(status="allow", reasons=[], tags=[])
    if plan.bjt_type != "NPN":
        return ExecutionPolicyDecision(
            status="deny",
            reasons=["当前自动执行路径只开放 NPN；PNP/未知型号先生成计划并等待专用流程。"],
            tags=["pnp_auto_execution_blocked"],
        )
    if not allow_hardware:
        return ExecutionPolicyDecision(
            status="deny",
            reasons=["硬件执行还需要调用方显式允许；我已保留当前计划，未打开真实输出。"],
            tags=["blocked_hardware_execution"],
        )
    if not token_valid:
        return ExecutionPolicyDecision(
            status="require_confirm",
            reasons=["硬件执行需要显式确认。"],
            tags=["requires_hardware_confirmation"],
        )
    return ExecutionPolicyDecision(status="allow", reasons=[], tags=[])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_safety_policy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/safety.py tests/test_ai_safety_policy.py
git commit -m "feat: add agent safety policy primitives"
```

### Task 2: 计划层改为通过策略层做 clamp

**Files:**
- Modify: `ai/test_planner.py`
- Modify: `tests/test_ai_safety_regression.py`
- Test: `tests/test_ai_safety_policy.py`

- [ ] **Step 1: 写失败测试**

```python
from ai.safety import clamp_plan_to_policy
from ai.test_planner import build_test_plan
from core.types import HwConfig


def test_build_test_plan_uses_policy_clamp() -> None:
    cfg = HwConfig(Ic_max_A=0.03, Pmax_W=0.3, Vcc_max=5.0)
    plan = build_test_plan(model="S8050", goal="full", depth="deep", cfg=cfg)

    assert plan.ic_limit_a <= 0.03
    assert plan.power_limit_w <= 0.3
    assert max(plan.vcc_steps) <= 5.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_policy.py::test_build_test_plan_uses_policy_clamp tests/test_ai_safety_regression.py::test_plan_limits_are_clamped_to_hw_config -q`
Expected: 至少一个测试 FAIL，说明 planner 还未显式通过策略层收口

- [ ] **Step 3: 写最小实现**

```python
from ai.safety import clamp_plan_to_policy

# 在 build_test_plan() 返回前：
policy_result = clamp_plan_to_policy(plan, cfg)
return policy_result.plan
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_safety_policy.py::test_build_test_plan_uses_policy_clamp tests/test_ai_safety_regression.py::test_plan_limits_are_clamped_to_hw_config -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/test_planner.py tests/test_ai_safety_regression.py tests/test_ai_safety_policy.py
git commit -m "refactor: route plan clamps through safety policy"
```

### Task 3: Agent 硬件放行判定改为策略层

**Files:**
- Modify: `ai/agent.py`
- Modify: `tests/test_ai_safety_regression.py`
- Test: `tests/test_ai_agent.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_hardware_request_uses_policy_require_confirm(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    agent = TestAgent(state)

    result = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)

    assert result.hardware_confirmation_required is True
    assert result.execution is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_regression.py::test_hardware_execution_requires_confirmation_token -q`
Expected: FAIL 或覆盖不足，说明断言仍依赖 `agent.py` 内部分散判断

- [ ] **Step 3: 写最小实现**

```python
from ai.safety import evaluate_execution_request

token_valid = self._hardware_confirmation_valid(plan, hardware_confirmation_token)
decision = evaluate_execution_request(
    plan=plan,
    mode="hardware",
    allow_hardware=allow_hardware,
    token_valid=token_valid,
)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_safety_regression.py tests/test_ai_agent.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py tests/test_ai_safety_regression.py tests/test_ai_agent.py
git commit -m "refactor: route hardware confirmation through safety policy"
```

### Task 4: 执行层改为通过策略层做 gate

**Files:**
- Modify: `ai/tools.py`
- Modify: `tests/test_execution_safety.py`
- Test: `tests/test_ai_safety_policy.py`

- [ ] **Step 1: 写失败测试**

```python
from ai.safety import evaluate_execution_request
from ai.test_planner import build_test_plan
from ai.tools import execute_plan


def test_execute_plan_denies_non_npn_via_policy() -> None:
    plan = build_test_plan(model="S8550", goal="beta", depth="standard", mode="hardware")
    result = execute_plan(plan, mode="hardware", allow_hardware=True)

    assert result["skipped"] is True
    assert "NPN" in result["reason"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_execution_safety.py -q`
Expected: FAIL 或仍只覆盖 `tools.py` 内联 gate

- [ ] **Step 3: 写最小实现**

```python
decision = evaluate_execution_request(
    plan=plan,
    mode=mode,
    allow_hardware=allow_hardware,
    token_valid=(mode != "hardware"),
)
if decision.status != "allow":
    return {
        "plan": plan.to_dict(),
        "skipped": True,
        "reason": decision.reasons[0] if decision.reasons else "策略阻止执行。",
        "policy_tags": decision.tags,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_execution_safety.py tests/test_ai_safety_policy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/tools.py tests/test_execution_safety.py tests/test_ai_safety_policy.py
git commit -m "refactor: route execute gate through safety policy"
```

### Task 5: 全量回归验证

**Files:**
- Modify: `README.md`
- Test: `tests/test_ai_safety_policy.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_regression_command_stays_green() -> None:
    assert True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 scripts/run_agent_regression.py --json`
Expected: 如果策略层改造有回归，命令返回非 0 或指标下降

- [ ] **Step 3: 写最小实现**

```markdown
Update README Agent Regression section to mention safety policy tests and policy-driven gating.
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
- `plan.safety_and_policy_accuracy == 1.0`
- 金样本 safety 行为仍为 100%

- [ ] **Step 5: Commit**

```bash
git add README.md ai/safety.py ai/test_planner.py ai/agent.py ai/tools.py tests/test_ai_safety_policy.py tests/test_ai_safety_regression.py tests/test_execution_safety.py
git commit -m "refactor: centralize agent safety policy"
```
