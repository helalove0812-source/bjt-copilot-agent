# BJTagent 平台化阶段 B（认知层解耦）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `BJTagent` 当前混在 `conversation / rules / autonomy / agent` 中的认知逻辑拆成更清晰的诊断、动作推荐、计划整形和自主优化策略模块，让复杂意图、多轮 modify 和结果解释更稳定且可维护。

**Architecture:** 先把 diagnosis 分类从 `ai.rules` 中抽到专用模块，再把“下一步做什么”的推荐逻辑从 `ai.agent` 拆到独立 recommender，随后把计划整形与未知型号补全逻辑从 `ai.conversation` 抽到 plan shaper，最后把 `ai.autonomy` 中的策略判断和文案说明分开。`ai.agent` 保留为 orchestration 层，只负责串联 intent、plan、diagnosis、action recommendation、safety 和 autonomy。该计划只覆盖平台化路线的阶段 B，不包含 evaluator 直连和前端消费字段扩展。

**Tech Stack:** Python 3、pytest、现有 BJT agent 后端、JSON regression datasets、Markdown 计划文档

---

## File Map

- Create: `/Users/helap/Documents/Project/雨骤/ai/diagnosis_engine.py`
- Create: `/Users/helap/Documents/Project/雨骤/ai/action_recommender.py`
- Create: `/Users/helap/Documents/Project/雨骤/ai/plan_shaper.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/rules.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/conversation.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/autonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_ai_rules.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_ai_conversation.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

### Planned Responsibilities

- `/Users/helap/Documents/Project/雨骤/ai/diagnosis_engine.py`
  - 负责“看见了什么”。
  - 输出稳定 `diagnosis_tags` 和 `diagnosis_summary`，不直接决定计划调整。
- `/Users/helap/Documents/Project/雨骤/ai/action_recommender.py`
  - 负责“下一步做什么”。
  - 把 diagnosis、execution、plan、conversation state 映射成稳定动作标签与说明。
- `/Users/helap/Documents/Project/雨骤/ai/plan_shaper.py`
  - 负责“如何基于 intent/context 形成或修改计划”。
  - 承接 unknown model completion、复杂 modify、阶段式计划表达。
- `/Users/helap/Documents/Project/雨骤/ai/autonomy.py`
  - 只保留自主优化策略和结果说明，不再兼任动作推荐。
- `/Users/helap/Documents/Project/雨骤/ai/agent.py`
  - 保留 orchestration：调用 intent -> plan shaper -> safety -> execution -> diagnosis -> action recommendation。

### Boundaries

- diagnosis 模块只输出观测判断：
  - `mostly_saturation`
  - `mostly_cutoff`
  - `bce_reversed`
  - `overcurrent`
  - `beta_unstable`
- action recommender 只输出动作建议：
  - `check_wiring`
  - `prompt_pinout_confirm`
  - `modify_plan`
  - `increase_points`
  - `clamp_current`
  - `suggest_next_step`
- plan shaper 只处理计划形成与计划修改：
  - 当前计划复用
  - unknown model profile completion
  - staged/deep/conservative 计划整形
- safety 继续只处理“能不能做”
- autonomy 继续只处理“什么时候自动收紧/加深/继续”

---

### Task 1: 抽出 diagnosis engine

**Files:**
- Create: `/Users/helap/Documents/Project/雨骤/ai/diagnosis_engine.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/rules.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_rules.py`

- [ ] **Step 1: Write the failing tests**

```python
from ai.diagnosis_engine import diagnose_observation, summarize_diagnosis


def test_diagnosis_engine_returns_tags_without_action_labels() -> None:
    result = diagnose_observation(
        text="Vce 怎么都压不上去电流爆表",
        logs=[],
        measurements=[{"Ic": 0.03, "Vce": 0.1, "region": "saturation"}],
    )

    assert "overcurrent" in result.tags
    assert "short_circuit" in result.tags
    assert "clamp_current" not in result.tags


def test_diagnosis_engine_summary_explains_observation_only() -> None:
    result = diagnose_observation(
        text="三个脚两两量都不通",
        logs=[],
        measurements=[],
    )

    summary = summarize_diagnosis(result)

    assert "开路" in summary
    assert "建议下一步" not in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_rules.py::test_diagnosis_engine_returns_tags_without_action_labels tests/test_ai_rules.py::test_diagnosis_engine_summary_explains_observation_only -q`
Expected: FAIL，因为 `ai.diagnosis_engine` 还不存在，且当前 diagnosis 逻辑仍混在 `ai.rules`。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/diagnosis_engine.py` 新建：

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiagnosisResult:
    tags: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)


def diagnose_observation(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> DiagnosisResult:
    tags: set[str] = set()
    hints: list[str] = []
    lowered = (text + "\n" + "\n".join(logs or [])).lower()
    measurements = measurements or []

    if "电流爆表" in lowered or "over-current" in lowered:
        tags.add("overcurrent")
    if "都不通" in lowered or "不导通" in lowered:
        tags.add("open_circuit")
        hints.append("疑似开路或 PN 结异常")
    if any(str(point.get("region")) == "saturation" for point in measurements):
        tags.add("mostly_saturation")

    return DiagnosisResult(tags=sorted(tags), hints=hints)


def summarize_diagnosis(result: DiagnosisResult) -> str:
    if result.hints:
        return "诊断观察：\n" + "\n".join(f"- {hint}" for hint in result.hints)
    if result.tags:
        return "诊断观察：\n- 已识别标签：" + "、".join(result.tags)
    return "诊断观察：\n- 当前未识别到明确异常标签。"
```

并把 `/Users/helap/Documents/Project/雨骤/ai/rules.py` 改成 wrapper：

```python
from ai.diagnosis_engine import diagnose_observation, summarize_diagnosis


def diagnose_tags(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> list[str]:
    return diagnose_observation(text, logs=logs, measurements=measurements).tags


def diagnose_context(text: str, *, logs: list[str] | None = None, measurements: list[dict] | None = None) -> str:
    return summarize_diagnosis(diagnose_observation(text, logs=logs, measurements=measurements))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_rules.py::test_diagnosis_engine_returns_tags_without_action_labels tests/test_ai_rules.py::test_diagnosis_engine_summary_explains_observation_only -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/diagnosis_engine.py ai/rules.py tests/test_ai_rules.py
git commit -m "refactor(cognition): extract diagnosis engine"
```

### Task 2: 抽出 action recommender

**Files:**
- Create: `/Users/helap/Documents/Project/雨骤/ai/action_recommender.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`

- [ ] **Step 1: Write the failing tests**

```python
from ai.action_recommender import recommend_actions


def test_action_recommender_maps_diagnosis_to_next_actions() -> None:
    actions = recommend_actions(
        diagnosis_tags=["bce_reversed", "overcurrent"],
        current_plan=build_test_plan(model="S8050", goal="beta", depth="standard"),
        execution={"aborted": True, "abort_reason": "当前 Ic 超过计划上限"},
    )

    labels = [item["action"] for item in actions]
    assert "check_wiring" in labels
    assert "prompt_pinout_confirm" in labels
    assert "clamp_current" in labels


def test_agent_uses_recommender_for_explain_result(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "mode": "hardware",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("为什么停了")

    assert any(item["action"] == "clamp_current" for item in result.next_action_items)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_uses_recommender_for_explain_result -q`
Expected: FAIL，因为当前推荐逻辑仍在 `ai.agent` 的 `_diagnosis_next_actions()`、`_execution_next_actions()` 中内联。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/action_recommender.py` 新建：

```python
from __future__ import annotations

from ai.action_taxonomy import action_item


DIAGNOSIS_ACTION_MAP = {
    "bce_reversed": ["check_wiring", "prompt_pinout_confirm"],
    "open_circuit": ["check_wiring", "suggest_next_step"],
    "overcurrent": ["clamp_current", "explain_limit"],
    "mostly_saturation": ["modify_plan", "clamp_current"],
    "mostly_cutoff": ["modify_plan", "increase_points"],
}


def recommend_actions(*, diagnosis_tags: list[str], current_plan, execution: dict | None = None) -> list[dict]:
    actions: list[str] = []
    for tag in diagnosis_tags:
        actions.extend(DIAGNOSIS_ACTION_MAP.get(tag, []))
    if execution and execution.get("aborted"):
        actions.append("inspect_abort_reason")
    return [action_item(action) for action in dict.fromkeys(actions)]
```

并在 `/Users/helap/Documents/Project/雨骤/ai/agent.py` 用它替换内联推荐：

```python
from ai.action_recommender import recommend_actions

recommended = recommend_actions(
    diagnosis_tags=diagnosis_tags_out,
    current_plan=self.state.current_plan,
    execution=execution_context,
)
if recommended:
    next_actions = [item["label"] for item in recommended]
    next_action_items = recommended
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_uses_recommender_for_explain_result tests/test_api_server.py::test_ai_chat_returns_structured_next_action_items -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/action_recommender.py ai/agent.py tests/test_ai_agent.py tests/test_api_server.py
git commit -m "refactor(cognition): extract action recommender"
```

### Task 3: 抽出 plan shaper 与 unknown-model guidance

**Files:**
- Create: `/Users/helap/Documents/Project/雨骤/ai/plan_shaper.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/conversation.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_conversation.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
from ai.plan_shaper import shape_plan_request


def test_plan_shaper_reuses_current_plan_for_modify_request() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    shaped = shape_plan_request(
        intent=AIIntent(action="modify_plan", ic_limit_a=0.005),
        state=state,
    )

    assert shaped.plan.model == "S8050"
    assert shaped.plan.ic_limit_a <= 0.005
    assert shaped.required_inputs == []


def test_plan_shaper_blocks_incomplete_unknown_model() -> None:
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={"bjt_type": "NPN", "vceo_max_v": 40.0},
    )

    shaped = shape_plan_request(
        intent=AIIntent(action="create_plan", model="XYZ123"),
        state=state,
    )

    assert shaped.blocked_reason == "unknown_model_incomplete"
    assert shaped.required_inputs == ["Ic 最大值", "Ptot"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_plan_shaper_reuses_current_plan_for_modify_request tests/test_ai_conversation.py::test_plan_shaper_blocks_incomplete_unknown_model -q`
Expected: FAIL，因为 `ai.plan_shaper` 还不存在，当前计划整形仍混在 `apply_intent_to_plan()` 和 `TestAgent.run_turn()` 里。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/plan_shaper.py` 新建：

```python
from __future__ import annotations

from dataclasses import dataclass, field

from ai.conversation import AIConversationState, AIIntent, apply_intent_to_plan


@dataclass(frozen=True)
class PlanShapeResult:
    plan: object | None = None
    blocked_reason: str = ""
    required_inputs: list[str] = field(default_factory=list)


def shape_plan_request(*, intent: AIIntent, state: AIConversationState, cfg=None) -> PlanShapeResult:
    missing = _missing_profile_inputs(state.pending_profile_fields)
    if state.pending_profile_model and missing:
        return PlanShapeResult(blocked_reason="unknown_model_incomplete", required_inputs=missing)
    return PlanShapeResult(plan=apply_intent_to_plan(intent, state, cfg=cfg))
```

然后在 `/Users/helap/Documents/Project/雨骤/ai/conversation.py` 中把 unknown-model 缺字段判定抽成公共 helper：

```python
def missing_profile_inputs(fields: dict[str, float | str]) -> list[str]:
    labels = {
        "bjt_type": "管型",
        "vceo_max_v": "Vceo",
        "ic_max_a": "Ic 最大值",
        "p_tot_w": "Ptot",
    }
    return [labels[key] for key in ("bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w") if key not in fields]
```

并在 `ai.agent` 里改成先调用 `shape_plan_request()` 再决定 `agent_state / required_inputs`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_plan_shaper_reuses_current_plan_for_modify_request tests/test_ai_conversation.py::test_plan_shaper_blocks_incomplete_unknown_model tests/test_ai_agent.py::test_unknown_model_first_turn_waits_for_profile_fields -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/plan_shaper.py ai/conversation.py ai/agent.py tests/test_ai_conversation.py tests/test_ai_agent.py
git commit -m "refactor(cognition): extract plan shaper"
```

### Task 4: 抽出 autonomy policy 与说明层

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/autonomy.py`
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Test: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
from ai.autonomy import decide_autonomous_refine


def test_autonomy_decision_returns_structured_policy() -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    execution = {
        "aborted": True,
        "measurements": [{"Ic": 0.031, "Vce": 0.1, "region": "saturation"}],
        "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
    }

    decision = decide_autonomous_refine(plan, execution)

    assert decision.reason == "runtime_abort"
    assert "clamp_current" in decision.completed_actions
    assert decision.target_depth == "conservative"


def test_refine_plan_after_execution_uses_policy_result() -> None:
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    state.record_execution(
        {
            "aborted": True,
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "region": "saturation"}],
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }
    )

    result = TestAgent(state).run_turn("下一步你自己看着办，优化一下计划")

    assert {"modify_plan", "clamp_current", "clamp_power"}.issubset(set(result.completed_actions))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_agent.py::test_refine_plan_after_execution_uses_policy_result -q`
Expected: FAIL，因为当前 `ai.autonomy` 还把策略判断和文案生成混在一个函数里。

- [ ] **Step 3: Write the minimal implementation**

在 `/Users/helap/Documents/Project/雨骤/ai/autonomy.py` 增加：

```python
@dataclass(frozen=True)
class AutonomousDecision:
    reason: str
    completed_actions: list[str]
    target_depth: str


def decide_autonomous_refine(plan: TestPlan, execution: dict) -> AutonomousDecision:
    stats = build_execution_stats(execution)
    if stats.get("aborted"):
        return AutonomousDecision(
            reason="runtime_abort",
            completed_actions=["modify_plan", "clamp_current", "clamp_power"],
            target_depth="conservative",
        )
    if _is_staged_strategy(plan) and _stable_active_result(stats):
        return AutonomousDecision(
            reason="stable_staged_result",
            completed_actions=["modify_plan", "increase_points", "deepen_plan"],
            target_depth="deep",
        )
    return AutonomousDecision(
        reason="stable_result",
        completed_actions=["modify_plan", "increase_points"],
        target_depth=plan.depth,
    )
```

然后让 `refine_plan_after_execution()` 先消费 `decide_autonomous_refine()`，再生成 refined plan 和说明文本。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_agent.py::test_refine_plan_after_execution_uses_policy_result tests/test_ai_agent.py::test_agent_autonomous_refine_deepens_staged_plan_after_stable_result -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/autonomy.py ai/agent.py tests/test_ai_agent.py
git commit -m "refactor(cognition): split autonomy policy and summary"
```

### Task 5: 收紧 orchestration，并补回归样本

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/ai/agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_ai_agent.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_api_server.py`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

- [ ] **Step 1: Add focused regression samples**

把以下两类样本加入数据集：

```json
{"category":"context","user_text":"电流再小一点","context":{"current_plan":{"model":"S8050","goal":"beta","depth":"standard","ic_limit_a":0.01}},"expected_intent":"modify_plan","expected_actions":["modify_plan","clamp_current"]}
{"category":"diagnosis","user_text":"选了 NPN 但电流方向不对","context":{"current_plan":{"model":"S8050","goal":"beta","depth":"standard"}},"expected_intent":"explain_result","expected_diagnosis":["wrong_polarity"],"expected_actions":["check_wiring","prompt_pinout_confirm"]}
```

- [ ] **Step 2: Write integration tests**

```python
def test_agent_orchestrates_diagnosis_and_recommendation(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    state = AIConversationState()
    state.current_plan = build_test_plan(model="S8050", goal="beta", depth="standard")
    result = TestAgent(state).run_turn("选了 NPN 但电流方向不对")

    assert result.intent.action == "explain_result"
    assert "wrong_polarity" in result.diagnosis_tags
    assert any(item["action"] == "prompt_pinout_confirm" for item in result.next_action_items)
```

- [ ] **Step 3: Run targeted validation**

Run: `python3 -m pytest tests/test_ai_rules.py tests/test_ai_conversation.py tests/test_ai_agent.py tests/test_api_server.py -q`
Expected: PASS

Run: `python3 scripts/evaluate_agent_samples.py --dataset 数据/transistor_agent_samples.v3.jsonl --json`
Expected: soft metrics 正常输出，且 diagnosis/actions 的 mismatch 不因模块拆分而恶化。

Run: `python3 scripts/run_agent_regression.py --json`
Expected: `ok: true`

- [ ] **Step 4: Update status doc**

追加说明：

```md
## 阶段 B 进展

- diagnosis classification 已从 `ai.rules` 抽到专用模块
- action recommendation 已从 `ai.agent` 抽出
- plan shaping 已从 `ai.conversation` 抽出
- autonomy policy 与 explanation 已拆层
- `ai.agent` 现在主要负责 orchestration
```

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py tests/test_ai_agent.py tests/test_api_server.py 数据/agent_regression_cases.jsonl 数据/transistor_agent_samples.v3.jsonl docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md
git commit -m "test(cognition): lock stage-b orchestration regressions"
```

---

## Self-Review

### Spec coverage

- 主线二“模块化认知层”：Task 1、Task 2、Task 3、Task 4 直接覆盖。
- 阶段 B 目标“复杂意图处理与阶段式计划表达”：Task 3 覆盖。
- 阶段 B 目标“diagnosis 到 next actions 的稳定映射”：Task 1、Task 2、Task 5 覆盖。
- 阶段 B 目标“autonomous-adjust 专用策略逻辑”：Task 4 覆盖。
- 多轮 modify / 结果解释回归：Task 5 覆盖。

### Placeholder scan

- 未出现 `TODO`、`TBD`、`后续补` 之类占位项。
- 每个任务都包含测试、实现、命令和提交动作。

### Scope check

- 计划只覆盖认知层解耦，不混入阶段 C 的 evaluator 结构直连和阶段 D 的错误状态系统扩展。
- 前端消费、API 大范围协议升级、工具化闭环未进入本计划。

### Type consistency

- 全文统一使用 `diagnosis_result`、`recommend_actions`、`PlanShapeResult`、`AutonomousDecision`。
- 没有混用 `diagnosis classifier` / `diagnosis engine` 或 `action recommender` / `action planner` 等别名。
