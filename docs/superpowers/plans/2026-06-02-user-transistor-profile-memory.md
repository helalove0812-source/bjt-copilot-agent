# User Transistor Profile Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为未知型号补全流程增加“LLM 可提议、用户显式确认后写入独立 JSON 型号库”的沉淀能力，同时保持现有 SafetyGuard、NPN gate 和硬件确认不变。

**Architecture:** 在现有会话内未知型号补全路径上增加候选 profile 状态，并新增一个独立的用户型号库读写模块。运行时查库顺序调整为“用户库 -> 内置库 -> fallback”，测试完成后仅在低风险成功路径主动提示保存，收到明确命令后才落库。

**Tech Stack:** Python 3、dataclasses、JSON 文件持久化、pytest、本地规则意图解析、现有 BJT Agent 状态机

---

## File Structure

- Create: `ai/user_profile_store.py`
- Create: `tests/test_transistor_profile_store.py`
- Modify: `ai/transistor_db.py`
- Modify: `ai/conversation.py`
- Modify: `ai/agent.py`
- Modify: `tests/test_ai_conversation.py`
- Modify: `tests/test_ai_agent.py`
- Create: `config/user_transistor_profiles.json`

### Task 1: Add User Profile Store

**Files:**
- Create: `ai/user_profile_store.py`
- Create: `tests/test_transistor_profile_store.py`
- Create: `config/user_transistor_profiles.json`

- [ ] **Step 1: Write the failing store tests**

```python
from pathlib import Path

from ai.transistor_db import TransistorProfile
from ai.user_profile_store import (
    DuplicateUserProfileError,
    InvalidUserProfileStoreError,
    load_user_profiles,
    save_user_profile,
    update_user_profile,
)


def _profile(model: str = "XYZ123") -> TransistorProfile:
    return TransistorProfile(
        model=model,
        bjt_type="NPN",
        description="用户确认沉淀的型号参数",
        vceo_max_v=40.0,
        ic_max_a=0.2,
        p_tot_w=0.5,
        hfe_typical=(0, 0),
        confidence="user_confirmed",
    )


def test_load_user_profiles_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_user_profiles(tmp_path / "missing.json") == {}


def test_save_user_profile_persists_profile(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"

    save_user_profile(store_path, _profile())

    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].confidence == "user_confirmed"
    assert loaded["XYZ123"].bjt_type == "NPN"


def test_save_user_profile_rejects_duplicate_without_update(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(store_path, _profile())

    try:
        save_user_profile(store_path, _profile())
    except DuplicateUserProfileError:
        pass
    else:
        raise AssertionError("expected duplicate save to be rejected")


def test_update_user_profile_overwrites_existing_entry(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(store_path, _profile())

    updated = TransistorProfile(
        model="XYZ123",
        bjt_type="NPN",
        description="更新后的用户确认型号参数",
        vceo_max_v=45.0,
        ic_max_a=0.25,
        p_tot_w=0.55,
        hfe_typical=(0, 0),
        confidence="user_confirmed",
    )
    update_user_profile(store_path, updated)

    loaded = load_user_profiles(store_path)
    assert loaded["XYZ123"].vceo_max_v == 45.0


def test_load_user_profiles_raises_clear_error_for_invalid_json(tmp_path: Path) -> None:
    store_path = tmp_path / "profiles.json"
    store_path.write_text("{bad json", encoding="utf-8")

    try:
        load_user_profiles(store_path)
    except InvalidUserProfileStoreError as exc:
        assert "profiles.json" in str(exc)
    else:
        raise AssertionError("expected invalid store to raise")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_transistor_profile_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.user_profile_store'`

- [ ] **Step 3: Write minimal store implementation**

```python
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Mapping

from ai.transistor_db import TransistorProfile, normalize_model_name


class InvalidUserProfileStoreError(RuntimeError):
    pass


class DuplicateUserProfileError(RuntimeError):
    pass


def _profile_from_mapping(data: Mapping[str, object]) -> TransistorProfile:
    hfe = data.get("hfe_typical", [0, 0])
    return TransistorProfile(
        model=str(data["model"]),
        bjt_type=str(data["bjt_type"]),
        description=str(data.get("description", "用户确认沉淀的型号参数")),
        vceo_max_v=float(data["vceo_max_v"]),
        ic_max_a=float(data["ic_max_a"]),
        p_tot_w=float(data["p_tot_w"]),
        hfe_typical=(int(hfe[0]), int(hfe[1])),
        package=str(data.get("package", "")),
        pinout_hint=str(data.get("pinout_hint", "")),
        confidence=str(data.get("confidence", "user_confirmed")),
    )


def load_user_profiles(path: Path) -> dict[str, TransistorProfile]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidUserProfileStoreError(f"invalid user profile store: {path}") from exc
    if not isinstance(payload, dict):
        raise InvalidUserProfileStoreError(f"invalid user profile store: {path}")
    return {
        normalize_model_name(model): _profile_from_mapping(profile)
        for model, profile in payload.items()
        if isinstance(profile, dict)
    }


def _write_profiles(path: Path, profiles: Mapping[str, TransistorProfile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    for key, profile in profiles.items():
        record = asdict(profile)
        record["hfe_typical"] = list(profile.hfe_typical)
        payload[key] = record
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def save_user_profile(path: Path, profile: TransistorProfile) -> None:
    profiles = load_user_profiles(path)
    key = normalize_model_name(profile.model)
    if key in profiles:
        raise DuplicateUserProfileError(profile.model)
    profiles[key] = profile
    _write_profiles(path, profiles)


def update_user_profile(path: Path, profile: TransistorProfile) -> None:
    profiles = load_user_profiles(path)
    profiles[normalize_model_name(profile.model)] = profile
    _write_profiles(path, profiles)
```

- [ ] **Step 4: Seed the default JSON store**

```json
{}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_transistor_profile_store.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/user_profile_store.py config/user_transistor_profiles.json tests/test_transistor_profile_store.py
git commit -m "feat: add user transistor profile store"
```

### Task 2: Make Lookup Prefer User Profiles

**Files:**
- Modify: `ai/transistor_db.py`
- Test: `tests/test_transistor_profile_store.py`

- [ ] **Step 1: Extend tests for lookup order**

```python
from ai.transistor_db import lookup_transistor


def test_lookup_transistor_prefers_user_store(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "profiles.json"
    save_user_profile(
        store_path,
        TransistorProfile(
            model="XYZ123",
            bjt_type="NPN",
            description="用户确认型号",
            vceo_max_v=55.0,
            ic_max_a=0.3,
            p_tot_w=0.6,
            hfe_typical=(0, 0),
            confidence="user_confirmed",
        ),
    )
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))

    profile = lookup_transistor("XYZ123")

    assert profile.confidence == "user_confirmed"
    assert profile.vceo_max_v == 55.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_transistor_profile_store.py::test_lookup_transistor_prefers_user_store -q`
Expected: FAIL because `lookup_transistor("XYZ123")` still returns fallback

- [ ] **Step 3: Modify lookup to read the user store first**

```python
import os
from pathlib import Path

from ai.user_profile_store import InvalidUserProfileStoreError, load_user_profiles


def _user_profile_store_path() -> Path:
    raw = os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json")
    return Path(raw)


def lookup_transistor(model: str) -> TransistorProfile:
    key = normalize_model_name(model)
    try:
        user_profiles = load_user_profiles(_user_profile_store_path())
    except InvalidUserProfileStoreError:
        user_profiles = {}
    if key in user_profiles:
        return user_profiles[key]
    if key in _PROFILES:
        return _PROFILES[key]
    return TransistorProfile(
        model=model.strip() or "UNKNOWN",
        bjt_type="UNKNOWN",
        description="未知 BJT 型号，使用低压保守探测方案",
        vceo_max_v=12.0,
        ic_max_a=0.02,
        p_tot_w=0.1,
        hfe_typical=(0, 0),
        pinout_hint="未知型号必须先确认 datasheet 和引脚，硬件模式只建议低压探测。",
        confidence="fallback",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_transistor_profile_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/transistor_db.py tests/test_transistor_profile_store.py
git commit -m "feat: prefer user transistor profiles during lookup"
```

### Task 3: Add Candidate Profile and Save Confirmation State

**Files:**
- Modify: `ai/conversation.py`
- Test: `tests/test_ai_conversation.py`

- [ ] **Step 1: Write failing conversation-state tests**

```python
def test_conversation_context_includes_candidate_profile_fields() -> None:
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
        candidate_profile={
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
        candidate_profile_source="llm_plus_user",
        pending_profile_save_confirmation=True,
    )

    context = state.to_context()

    assert context["candidate_profile"]["model"] == "XYZ123"
    assert context["candidate_profile_source"] == "llm_plus_user"
    assert context["pending_profile_save_confirmation"] is True


def test_unknown_model_complete_fields_create_candidate_profile() -> None:
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    plan = apply_intent_to_plan(AIIntent(action="create_plan"), state)

    assert plan.model == "XYZ123"
    assert state.candidate_profile is not None
    assert state.candidate_profile["model"] == "XYZ123"
    assert state.candidate_profile_source == "user_only"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_conversation_context_includes_candidate_profile_fields tests/test_ai_conversation.py::test_unknown_model_complete_fields_create_candidate_profile -q`
Expected: FAIL with unexpected `AIConversationState` arguments or missing keys in `to_context()`

- [ ] **Step 3: Add the new state fields and fill them during plan creation**

```python
@dataclass
class AIConversationState:
    messages: list[ConversationMessage] = field(default_factory=list)
    current_plan: TestPlan | None = None
    current_execution: dict | None = None
    execution_history: list[dict] = field(default_factory=list)
    agent_activity_history: list[dict] = field(default_factory=list)
    current_summary: str = ""
    pending_profile_model: str | None = None
    pending_profile_fields: dict[str, float | str] = field(default_factory=dict)
    candidate_profile: dict[str, Any] | None = None
    candidate_profile_source: str = ""
    pending_profile_save_confirmation: bool = False

    def to_context(self) -> dict:
        return {
            "messages": [asdict(message) for message in self.messages],
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "current_execution": self.current_execution,
            "execution_history": self.execution_history,
            "agent_activity_history": self.agent_activity_history,
            "current_summary": self.current_summary,
            "pending_profile_model": self.pending_profile_model,
            "pending_profile_fields": self.pending_profile_fields,
            "candidate_profile": self.candidate_profile,
            "candidate_profile_source": self.candidate_profile_source,
            "pending_profile_save_confirmation": self.pending_profile_save_confirmation,
        }
```

```python
if base is None and state.pending_profile_model and _pending_profile_is_complete(state.pending_profile_fields):
    pending_profile_override = build_profile_from_fields(state.pending_profile_model, state.pending_profile_fields)
    state.candidate_profile = {
        "model": pending_profile_override.model,
        "bjt_type": pending_profile_override.bjt_type,
        "vceo_max_v": pending_profile_override.vceo_max_v,
        "ic_max_a": pending_profile_override.ic_max_a,
        "p_tot_w": pending_profile_override.p_tot_w,
    }
    state.candidate_profile_source = "user_only"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_conversation_context_includes_candidate_profile_fields tests/test_ai_conversation.py::test_unknown_model_complete_fields_create_candidate_profile -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/conversation.py tests/test_ai_conversation.py
git commit -m "feat: track candidate transistor profiles in conversation state"
```

### Task 4: Add Save Prompt and Explicit Save Intents

**Files:**
- Modify: `ai/conversation.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: Add failing intent tests for save/update commands**

```python
def test_save_profile_command_stays_answer_without_pending_confirmation() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("保存这个型号", state)

    assert intent.action == "answer"


def test_save_profile_command_with_pending_confirmation_returns_save_intent() -> None:
    state = AIConversationState(
        candidate_profile={"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5},
        pending_profile_save_confirmation=True,
    )

    intent = infer_intent_locally("保存这个型号", state)

    assert intent.action == "answer"
    assert intent.response == "save_candidate_profile"


def test_update_profile_command_with_pending_confirmation_returns_update_intent() -> None:
    state = AIConversationState(
        candidate_profile={"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 45.0, "ic_max_a": 0.25, "p_tot_w": 0.55},
        pending_profile_save_confirmation=True,
    )

    intent = infer_intent_locally("更新这个型号", state)

    assert intent.action == "answer"
    assert intent.response == "update_candidate_profile"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_conversation.py::test_save_profile_command_with_pending_confirmation_returns_save_intent tests/test_ai_conversation.py::test_update_profile_command_with_pending_confirmation_returns_update_intent -q`
Expected: FAIL because save/update commands are not distinguished

- [ ] **Step 3: Add minimal parsing for explicit save/update commands**

```python
def _looks_like_profile_save(text: str) -> bool:
    return any(phrase in text for phrase in ("保存这个型号", "写入库", "记住这个 BJT", "保存 ")) and "更新" not in text


def _looks_like_profile_update(text: str) -> bool:
    return "更新这个型号" in text or "更新 " in text


def infer_intent_locally(text: str, state: AIConversationState, *, default_mode: str = "simulation") -> AIIntent:
    lowered = text.lower()
    if state.pending_profile_save_confirmation and _looks_like_profile_update(text):
        return AIIntent(action="answer", response="update_candidate_profile")
    if state.pending_profile_save_confirmation and _looks_like_profile_save(text):
        return AIIntent(action="answer", response="save_candidate_profile")
    # keep existing behavior below
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_conversation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/conversation.py tests/test_ai_conversation.py
git commit -m "feat: parse explicit profile save and update commands"
```

### Task 5: Persist Confirmed Profiles Through the Agent

**Files:**
- Modify: `ai/agent.py`
- Modify: `tests/test_ai_agent.py`

- [ ] **Step 1: Write failing agent tests for save prompt and persistence**

```python
from pathlib import Path


def test_agent_prompts_to_save_candidate_profile_after_successful_unknown_model_plan(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    state = AIConversationState(
        pending_profile_model="XYZ123",
        pending_profile_fields={
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    result = TestAgent(state).run_turn("继续生成计划")

    assert result.plan is not None
    assert state.pending_profile_save_confirmation is True
    assert "保存到本地型号库" in result.response


def test_agent_saves_candidate_profile_after_explicit_confirmation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))
    state = AIConversationState(
        candidate_profile={
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
        candidate_profile_source="llm_plus_user",
        pending_profile_save_confirmation=True,
    )

    result = TestAgent(state).run_turn("保存这个型号")

    assert "写入本地型号库" in result.response
    assert state.pending_profile_save_confirmation is False
    assert lookup_transistor("XYZ123").confidence == "user_confirmed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_agent.py::test_agent_prompts_to_save_candidate_profile_after_successful_unknown_model_plan tests/test_ai_agent.py::test_agent_saves_candidate_profile_after_explicit_confirmation -q`
Expected: FAIL because the agent neither prompts to save nor writes the store

- [ ] **Step 3: Implement prompt and persistence in `TestAgent.run_turn()`**

```python
from pathlib import Path

from ai.transistor_db import TransistorProfile
from ai.user_profile_store import DuplicateUserProfileError, save_user_profile, update_user_profile


def _candidate_profile_to_transistor_profile(candidate: dict, *, source: str) -> TransistorProfile:
    return TransistorProfile(
        model=str(candidate["model"]),
        bjt_type=str(candidate["bjt_type"]),
        description="用户确认沉淀的型号参数",
        vceo_max_v=float(candidate["vceo_max_v"]),
        ic_max_a=float(candidate["ic_max_a"]),
        p_tot_w=float(candidate["p_tot_w"]),
        hfe_typical=(0, 0),
        confidence="user_confirmed",
        package=str(candidate.get("package", "")),
        pinout_hint=str(candidate.get("pinout_hint", "")),
    )


def _user_store_path() -> Path:
    return Path(os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))
```

```python
if intent.action in {"create_plan", "modify_plan"}:
    ...
    if plan and plan.profile.get("confidence") == "user_supplied" and not self.state.pending_profile_save_confirmation:
        self.state.pending_profile_save_confirmation = True
        response = (
            response
            + "\n\n"
            + f"{plan.model} 当前使用的是本次会话中的候选规格，尚未保存到本地型号库。"
            + "如果这组参数确认可用，你可以回复“保存这个型号”或“写入库”。"
        )
```

```python
elif intent.action == "answer" and intent.response in {"save_candidate_profile", "update_candidate_profile"}:
    if not self.state.candidate_profile:
        response = "当前没有可保存的候选型号参数。"
    else:
        profile = _candidate_profile_to_transistor_profile(
            self.state.candidate_profile,
            source=self.state.candidate_profile_source,
        )
        try:
            if intent.response == "update_candidate_profile":
                update_user_profile(_user_store_path(), profile)
            else:
                save_user_profile(_user_store_path(), profile)
        except DuplicateUserProfileError:
            response = f"本地型号库中已存在 {profile.model}。如需更新，请明确说明“更新这个型号”。"
        else:
            self.state.pending_profile_save_confirmation = False
            response = f"已将 {profile.model} 写入本地型号库。后续再次测试该型号时，会优先使用本地已确认参数。"
            agent_state = "profile_saved"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_agent.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/agent.py tests/test_ai_agent.py
git commit -m "feat: persist confirmed candidate transistor profiles"
```

### Task 6: Add Lookup and Regression Guards

**Files:**
- Modify: `tests/test_ai_agent.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: Add regression test for follow-up session lookup**

```python
def test_saved_user_profile_is_used_in_followup_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store_path = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store_path))

    first = TestAgent(
        AIConversationState(
            candidate_profile={
                "model": "XYZ123",
                "bjt_type": "NPN",
                "vceo_max_v": 40.0,
                "ic_max_a": 0.2,
                "p_tot_w": 0.5,
            },
            pending_profile_save_confirmation=True,
        )
    )
    first.run_turn("保存这个型号")

    second = TestAgent()
    result = second.run_turn("测一下 XYZ123")

    assert result.plan is not None
    assert result.plan.model == "XYZ123"
    assert result.plan.profile["confidence"] == "user_confirmed"
    assert result.agent_state == "plan_ready"
```

- [ ] **Step 2: Run targeted tests**

Run: `python3 -m pytest tests/test_transistor_profile_store.py tests/test_ai_conversation.py tests/test_ai_agent.py -q`
Expected: PASS

- [ ] **Step 3: Run full verification**

Run: `python3 scripts/run_agent_regression.py --json`
Expected: all parser/safety policy gates remain green

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_ai_agent.py tests/test_ai_conversation.py tests/test_transistor_profile_store.py
git commit -m "test: cover persistent user transistor profile flow"
```

## Self-Review

- Spec coverage: 包含了独立 JSON 用户库、查库优先级、候选 profile 会话状态、测试后主动询问、显式确认新增与更新、JSON 损坏隔离、重复保存不覆盖、核心 pytest 和回归命令。
- Placeholder scan: 计划中的每个任务都给出了明确文件路径、测试片段、运行命令和预期结果，没有 `TODO/TBD` 占位符。
- Type consistency: 计划统一使用 `candidate_profile`、`candidate_profile_source`、`pending_profile_save_confirmation` 和 `config/user_transistor_profiles.json`，与 spec 中的命名一致。
