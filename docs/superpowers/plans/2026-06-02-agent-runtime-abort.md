# Agent Runtime Abort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 BJT Agent 的 `hardware` 执行路径增加运行时安全中止机制，在异常测量出现时停止后续点并返回结构化中止结果。

**Architecture:** 新增 `ai/runtime_guard.py` 作为执行中判据层，只负责对当前点和历史点做中止判断。`ai/tools.py` 在硬件逐点执行时调用该判据层并写入 `aborted` 结果字段，保持现有执行前策略层和执行后摘要层不变。

**Tech Stack:** Python 3.9、dataclasses、pytest

---

### Task 1: 运行时判据层与单测

**Files:**
- Create: `ai/runtime_guard.py`
- Create: `tests/test_ai_runtime_guard.py`

- [ ] **Step 1: 写失败测试**

```python
from ai.runtime_guard import RuntimeAbortDecision, check_abort_after_point
from ai.test_planner import TestPlan


def make_plan() -> TestPlan:
    return TestPlan(
        model="S8050",
        bjt_type="NPN",
        goal="beta",
        depth="standard",
        mode="hardware",
        vcc_steps=[0.0, 1.0, 2.0],
        vbb_steps=[1.0, 2.0],
        static_points=[{"vcc": 1.0, "vbb": 1.0}],
        ic_limit_a=0.03,
        power_limit_w=0.3,
        sample_count=2048,
        scan_mode="software",
        steps=["x"],
        safety_notes=[],
        profile={"confidence": "catalog"},
    )


def test_runtime_guard_aborts_when_ic_exceeds_limit() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.031, "Vce": 2.0},
        history=[],
    )

    assert decision.should_abort is True
    assert "runtime_ic_limit_exceeded" in decision.tags


def test_runtime_guard_aborts_when_power_exceeds_limit() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.02, "Vce": 20.0},
        history=[],
    )

    assert decision.should_abort is True
    assert "runtime_power_limit_exceeded" in decision.tags


def test_runtime_guard_aborts_on_two_point_instability_trend() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.0065, "Vce": 1.0},
        history=[{"Ic": 0.004, "Vce": 1.7}],
    )

    assert decision.should_abort is True
    assert "runtime_instability_trend" in decision.tags


def test_runtime_guard_allows_normal_point() -> None:
    decision = check_abort_after_point(
        plan=make_plan(),
        point={"Ic": 0.005, "Vce": 2.4},
        history=[{"Ic": 0.004, "Vce": 2.5}],
    )

    assert decision == RuntimeAbortDecision(should_abort=False, reason="", tags=[])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_runtime_guard.py -q`
Expected: FAIL，提示 `ai.runtime_guard` 不存在

- [ ] **Step 3: 写最小实现**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeAbortDecision:
    should_abort: bool
    reason: str
    tags: list[str]


def check_abort_after_point(*, plan, point: dict, history: list[dict]) -> RuntimeAbortDecision:
    ic = float(point.get("Ic", 0.0))
    vce = float(point.get("Vce", 0.0))
    if ic > float(plan.ic_limit_a):
        return RuntimeAbortDecision(True, "当前 Ic 超过计划上限，已停止后续硬件测量。", ["runtime_ic_limit_exceeded"])
    if ic * vce > float(plan.power_limit_w):
        return RuntimeAbortDecision(True, "当前功耗超过计划上限，已停止后续硬件测量。", ["runtime_power_limit_exceeded"])
    if history:
        last = history[-1]
        if ic - float(last.get("Ic", 0.0)) >= 0.002 and float(last.get("Vce", 0.0)) - vce >= 0.5:
            return RuntimeAbortDecision(True, "检测到 Ic 上升且 Vce 下降的异常趋势，已停止后续硬件测量。", ["runtime_instability_trend"])
    return RuntimeAbortDecision(False, "", [])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_runtime_guard.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/runtime_guard.py tests/test_ai_runtime_guard.py
git commit -m "feat: add runtime abort guard"
```

### Task 2: 执行层接入运行时判据

**Files:**
- Modify: `ai/tools.py`
- Modify: `tests/test_execution_safety.py`
- Test: `tests/test_ai_runtime_guard.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_plan_aborts_hardware_run_when_runtime_guard_triggers(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    driver = DummyDriver()
    runtime = Runtime(config=HwConfig(), driver=driver, serial="HW-ABORT")

    monkeypatch.setattr("ai.tools.build_runtime", lambda mode, cfg: runtime)
    monkeypatch.setattr("ai.tools.detect_bjt_type", lambda driver, rb, rc: "NPN")
    monkeypatch.setattr(
        "ai.tools.measure_static_point",
        lambda *args, **kwargs: type(
            "Point",
            (),
            {"Vbb": 1.0, "Vcc": 3.0, "Vbe": 0.8, "Vce": 0.1, "Ib": 0.0001, "Ic": 0.031, "beta": 310.0, "region": "saturation"},
        )(),
    )

    result = execute_plan(plan, mode="hardware", allow_hardware=True, token_valid=True)

    assert result["aborted"] is True
    assert result["abort_reason"]
    assert result["abort_tags"] == ["runtime_ic_limit_exceeded"]
    assert result["aborted_after_index"] == 0
    assert len(result["measurements"]) == 1
    assert driver.disabled is True
    assert driver.closed is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_execution_safety.py::test_execute_plan_aborts_hardware_run_when_runtime_guard_triggers -q`
Expected: FAIL，提示结果中没有 `aborted` 字段或未提前停止

- [ ] **Step 3: 写最小实现**

```python
from ai.runtime_guard import check_abort_after_point

# 在 execute_plan() 的逐点循环中：
measurement = {...}
result["measurements"].append(measurement)
if mode == "hardware":
    decision = check_abort_after_point(plan=plan, point=measurement, history=result["measurements"][:-1])
    if decision.should_abort:
        result["aborted"] = True
        result["abort_reason"] = decision.reason
        result["abort_tags"] = decision.tags
        result["aborted_after_index"] = len(result["measurements"]) - 1
        break
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_execution_safety.py tests/test_ai_runtime_guard.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/tools.py tests/test_execution_safety.py tests/test_ai_runtime_guard.py
git commit -m "feat: abort hardware execution on runtime risk"
```

### Task 3: 结构化结果与回归验证

**Files:**
- Modify: `ai/agent.py`
- Modify: `ai/assistant.py`
- Modify: `tests/test_ai_agent.py`
- Modify: `README.md`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_preserves_aborted_execution_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")
    agent = TestAgent(state)

    monkeypatch.setattr(
        "ai.agent.execute_plan",
        lambda *args, **kwargs: {
            "mode": "hardware",
            "serial": "HW-ABORT",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "beta": 310.0, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
            "abort_tags": ["runtime_ic_limit_exceeded"],
            "aborted_after_index": 0,
        },
    )

    first = agent.run_turn("开始执行硬件测试", default_mode="hardware", allow_hardware=True)
    second = agent.run_turn(
        "开始执行硬件测试",
        default_mode="hardware",
        allow_hardware=True,
        hardware_confirmation_token=first.hardware_confirmation_token,
    )

    assert second.execution["aborted"] is True
    assert second.execution["abort_tags"] == ["runtime_ic_limit_exceeded"]
    assert agent.state.current_execution == second.execution
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_preserves_aborted_execution_result -q`
Expected: FAIL，如果 agent 未正确保留或摘要未兼容 `aborted` 结构

- [ ] **Step 3: 写最小实现**

```python
# 如摘要层需要最小兼容：
if execution.get("aborted"):
    summary = "执行已因安全判据中止。{0}".format(execution.get("abort_reason", ""))
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python3 -m pytest tests/test_ai_agent.py -q
python3 -m pytest -q
python3 scripts/run_agent_regression.py --json
```

Expected:

- Agent 测试 PASS
- 全量 pytest PASS
- 统一回归脚本 PASS

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py ai/assistant.py tests/test_ai_agent.py README.md
git commit -m "feat: report runtime aborts in agent execution"
```
