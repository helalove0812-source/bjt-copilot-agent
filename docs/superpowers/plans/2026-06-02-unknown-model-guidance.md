# Unknown Model Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为未知型号请求增加会话内追问补全能力，在用户补齐关键规格后生成基于临时 profile 的安全计划。

**Architecture:** 在会话状态中增加待补全的未知型号规格状态；本地规则层负责提取 `bjt_type / Vceo / Ic_max / Ptot`；planner 支持 `profile_override`，以便用会话级临时 profile 生成计划而不污染数据库。

**Tech Stack:** Python 3.9、dataclasses、pytest、正则提取

---

### Task 1: 会话状态与未知型号追问

**Files:**
- Modify: `ai/conversation.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: 写失败测试**

```python
def test_unknown_model_request_enters_pending_profile_state() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("测一下 XYZ123", state)
    response = answer_from_context(intent, state)

    assert state.pending_profile_model == "XYZ123"
    assert state.pending_profile_fields == {}
    assert "未知型号" in response
    assert "Vceo" in response
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_unknown_model_request_enters_pending_profile_state -q`
Expected: FAIL，提示状态里没有 `pending_profile_model` 或未知型号仍直接按普通 create_plan 处理

- [ ] **Step 3: 写最小实现**

```python
@dataclass
class AIConversationState:
    ...
    pending_profile_model: str | None = None
    pending_profile_fields: dict[str, float | str] = field(default_factory=dict)


def _is_unknown_model_request(model: str | None, state: AIConversationState) -> bool:
    return bool(model and model != "UNKNOWN" and lookup_transistor(model).confidence == "fallback")


def answer_from_context(intent: AIIntent, state: AIConversationState) -> str:
    if state.pending_profile_model and not state.pending_profile_fields:
        return "这是未知型号。为安全建计划，请补充：管型、Vceo、Ic 最大值、Ptot。"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_unknown_model_request_enters_pending_profile_state -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/conversation.py tests/test_ai_conversation.py
git commit -m "feat: prompt for unknown model profile fields"
```

### Task 2: 规格提取与多轮补全

**Files:**
- Modify: `ai/rules.py`
- Modify: `ai/conversation.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: 写失败测试**

```python
def test_unknown_model_profile_fields_can_be_filled_incrementally() -> None:
    state = AIConversationState(pending_profile_model="XYZ123", pending_profile_fields={})

    first = infer_intent_locally("NPN，40V", state)
    assert state.pending_profile_fields == {"bjt_type": "NPN", "vceo_max_v": 40.0}

    second = infer_intent_locally("Ic 最大 200mA，Ptot 500mW", state)
    assert state.pending_profile_fields == {
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
        "ic_max_a": 0.2,
        "p_tot_w": 0.5,
    }
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_unknown_model_profile_fields_can_be_filled_incrementally -q`
Expected: FAIL，说明当前不会提取或保存这些规格

- [ ] **Step 3: 写最小实现**

```python
def extract_profile_fields(text: str) -> dict[str, float | str]:
    fields = {}
    if "NPN" in text.upper():
        fields["bjt_type"] = "NPN"
    elif "PNP" in text.upper():
        fields["bjt_type"] = "PNP"
    ...
    return fields


if state.pending_profile_model:
    state.pending_profile_fields.update(extract_profile_fields(text))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_unknown_model_profile_fields_can_be_filled_incrementally -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/rules.py ai/conversation.py tests/test_ai_conversation.py
git commit -m "feat: collect unknown model profile fields across turns"
```

### Task 3: 临时 profile 与 planner override

**Files:**
- Modify: `ai/transistor_db.py`
- Modify: `ai/test_planner.py`
- Modify: `ai/conversation.py`
- Modify: `tests/test_ai_agent.py`

- [ ] **Step 1: 写失败测试**

```python
def test_unknown_model_builds_plan_after_profile_fields_complete(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )
    agent = TestAgent(state)

    result = agent.run_turn("继续生成计划")

    assert result.plan is not None
    assert result.plan.model == "XYZ123"
    assert result.plan.profile["confidence"] == "user_supplied"
    assert agent.state.pending_profile_model is None
    assert agent.state.pending_profile_fields == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_agent.py::test_unknown_model_builds_plan_after_profile_fields_complete -q`
Expected: FAIL，说明 planner 还不能接收会话级 profile override

- [ ] **Step 3: 写最小实现**

```python
def build_profile_from_fields(model: str, fields: dict[str, float | str]) -> TransistorProfile:
    return TransistorProfile(
        model=model,
        bjt_type=fields["bjt_type"],
        description="用户补充规格的临时 profile",
        vceo_max_v=float(fields["vceo_max_v"]),
        ic_max_a=float(fields["ic_max_a"]),
        p_tot_w=float(fields["p_tot_w"]),
        hfe_typical=(0, 0),
        confidence="user_supplied",
    )


def build_test_plan(..., profile_override: TransistorProfile | None = None) -> TestPlan:
    profile = profile_override or lookup_transistor(model)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ai_agent.py::test_unknown_model_builds_plan_after_profile_fields_complete -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/transistor_db.py ai/test_planner.py ai/conversation.py tests/test_ai_agent.py
git commit -m "feat: build plans from user-supplied unknown model profiles"
```

### Task 4: 全量回归验证

**Files:**
- Modify: `README.md`
- Test: `tests/test_ai_conversation.py`

- [ ] **Step 1: 写失败测试**

```python
def test_unknown_model_prompt_lists_missing_fields() -> None:
    state = AIConversationState(pending_profile_model="XYZ123", pending_profile_fields={"bjt_type": "NPN"})

    response = answer_from_context(AIIntent(action="answer"), state)

    assert "Ic" in response
    assert "Ptot" in response
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_unknown_model_prompt_lists_missing_fields -q`
Expected: FAIL，说明追问文案还不会根据缺失字段动态变化

- [ ] **Step 3: 写最小实现**

```python
def _missing_profile_fields(fields: dict[str, float | str]) -> list[str]:
    ...

return "已记录：...。还需要：{0}。".format("、".join(missing))
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
- 现有安全与执行基线不退化

- [ ] **Step 5: Commit**

```bash
git add README.md ai/conversation.py ai/rules.py ai/transistor_db.py ai/test_planner.py tests/test_ai_conversation.py tests/test_ai_agent.py
git commit -m "feat: guide unknown models with conversational profile completion"
```
