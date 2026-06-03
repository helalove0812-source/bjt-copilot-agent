# Agent Regression Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 BJT Agent 建立第一版可量化回归基线，包含金样本集、安全回归测试、统一回归命令和最小 CI。

**Architecture:** 继续复用现有样本评估器与 pytest 体系，不改业务规则。新增一份小而硬的回归样本集、一组专门验证安全门的测试、一个统一脚本把样本评估与测试命令串起来，再用最小 GitHub Actions workflow 固化为 CI 入口。

**Tech Stack:** Python 3.9、pytest、JSONL、GitHub Actions

---

### Task 1: 回归样本集

**Files:**
- Create: `数据/agent_regression_cases.jsonl`
- Test: `tests/test_agent_dataset.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_regression_dataset_schema_is_valid() -> None:
    samples = load_samples(Path("数据/agent_regression_cases.jsonl"))
    assert len(samples) >= 8
    assert validate_schema(samples) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_agent_regression_dataset_schema_is_valid -q`
Expected: FAIL，提示找不到 `数据/agent_regression_cases.jsonl`

- [ ] **Step 3: 写最小实现**

```json
{"category":"plan","user_text":"S8050 跑全套","context":{},"expected_intent":"create_plan","expected_goal":"full","expected_depth":"deep","expected_model":"S8050","expected_constraints":{},"expected_explicit_constraints":{},"expected_plan_constraints":{},"expected_safety_behavior":[],"expected_diagnosis":[],"expected_actions":["create_plan"],"notes":"无当前计划时建全套计划"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_agent_regression_dataset_schema_is_valid -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 数据/agent_regression_cases.jsonl tests/test_agent_dataset.py
git commit -m "test: add agent regression dataset"
```

### Task 2: 安全回归测试

**Files:**
- Create: `tests/test_ai_safety_regression.py`
- Modify: `tests/test_agent_dataset.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_safety_regression_suite() -> None:
    assert True
```
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_safety_regression.py -q`
Expected: FAIL，提示文件不存在

- [ ] **Step 3: 写最小实现**

```python
from ai.agent import TestAgent
from ai.test_planner import build_test_plan
from core.types import HwConfig


def test_unknown_model_uses_fallback_profile() -> None:
    plan = build_test_plan(model="XYZ123", goal="auto", depth="standard")
    assert plan.profile["confidence"] == "fallback"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_safety_regression.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ai_safety_regression.py tests/test_agent_dataset.py
git commit -m "test: add agent safety regression suite"
```

### Task 3: 统一回归命令

**Files:**
- Create: `scripts/run_agent_regression.py`
- Modify: `README.md`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_regression_runner_smoke(tmp_path) -> None:
    result = subprocess.run(["python3", "scripts/run_agent_regression.py", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "agent regression" in result.stdout.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_agent_regression_runner_smoke -q`
Expected: FAIL，提示脚本不存在

- [ ] **Step 3: 写最小实现**

```python
import argparse
import subprocess
import sys

parser = argparse.ArgumentParser(description="Run agent regression checks.")
parser.add_argument("--help-only", action="store_true")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 scripts/run_agent_regression.py --help`
Expected: 输出帮助信息并退出 0

- [ ] **Step 5: Commit**

```bash
git add scripts/run_agent_regression.py README.md
git commit -m "chore: add agent regression runner"
```

### Task 4: 最小 CI

**Files:**
- Create: `.github/workflows/agent-regression.yml`
- Test: `scripts/run_agent_regression.py`

- [ ] **Step 1: 写失败测试**

```python
def test_agent_regression_workflow_exists() -> None:
    assert Path(".github/workflows/agent-regression.yml").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_agent_regression_workflow_exists -q`
Expected: FAIL，提示 workflow 不存在

- [ ] **Step 3: 写最小实现**

```yaml
name: agent-regression
on:
  push:
  pull_request:
jobs:
  agent-regression:
    runs-on: ubuntu-latest
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_agent_dataset.py::test_agent_regression_workflow_exists -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/agent-regression.yml tests/test_agent_dataset.py
git commit -m "ci: add agent regression workflow"
```
