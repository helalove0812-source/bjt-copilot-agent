# BJTagent Profile Save Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端聊天区为未知型号补充“尚未保存到本地库 / 已保存到本地型号库”的 `BJTagent` 系统提示，并对同一型号做会话级去重。

**Architecture:** 复用现有 `App.jsx` 中的 `BJTagent` 行动日志机制，不改后端协议，只根据后端自然语言回复、`conversationState` 和 `currentPlan` 推断当前型号及保存状态。通过前端 `ref` 记录“某型号是否已经提示过未保存/已保存”，保证聊天区提示克制且不重复。

**Tech Stack:** React、`useState` / `useRef` / `useEffect`、现有 `App.jsx` 聊天区系统消息机制、pytest 源码级 smoke

---

## File Structure

- Modify: `frontend/src/App.jsx`
- Create: `tests/test_frontend_profile_save_status_smoke.py`
- Test: `tests/test_frontend_agent_experience_smoke.py`
- Test: `tests/test_frontend_abort_smoke.py`

### Task 1: Add a Failing Smoke for Save Status Copy

**Files:**
- Create: `tests/test_frontend_profile_save_status_smoke.py`
- Test: `frontend/src/App.jsx`

- [ ] **Step 1: Write the failing smoke test**

```python
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_profile_save_status_copy_exists() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库" in source
    assert "BJTagent：已保存到本地型号库，后续可直接复用" in source


def test_profile_save_status_has_dedup_memory() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "unsavedProfileNoticeRef" in source
    assert "savedProfileNoticeRef" in source


def test_profile_save_status_uses_existing_context_sources() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "conversationState?.candidate_profile?.model" in source
    assert "conversationState?.pending_profile_model" in source
    assert "currentPlan?.model" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_frontend_profile_save_status_smoke.py -q`
Expected: FAIL because the new save-status strings and dedup refs do not exist in `App.jsx`

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_frontend_profile_save_status_smoke.py
git commit -m "test: add failing smoke for profile save status copy"
```

### Task 2: Implement Save Status Message Detection in `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_profile_save_status_smoke.py`

- [ ] **Step 1: Add minimal helper constants and refs**

```jsx
const PROFILE_UNSAVED_MESSAGE = "BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库";
const PROFILE_SAVED_MESSAGE = "BJTagent：已保存到本地型号库，后续可直接复用";
```

```jsx
const unsavedProfileNoticeRef = useRef(new Set());
const savedProfileNoticeRef = useRef(new Set());
```

- [ ] **Step 2: Add a helper to resolve the current model**

```jsx
const candidateProfileModel = conversationState?.candidate_profile?.model || "";
const pendingProfileModel = conversationState?.pending_profile_model || "";
const resolvedProfileModel = candidateProfileModel || pendingProfileModel || currentPlan?.model || "";
```

- [ ] **Step 3: Add minimal semantic match helpers**

```jsx
function looksLikeUnsavedProfileResponse(text) {
  return text.includes("尚未保存到本地型号库")
    && (text.includes("保存这个型号") || text.includes("写入库"));
}

function looksLikeSavedProfileResponse(text) {
  return text.includes("写入本地型号库")
    || text.includes("已将") && text.includes("本地型号库");
}
```

- [ ] **Step 4: Insert save-status system messages after the AI reply**

```jsx
setMsgs((m) => [...m, { role: "ai", text: data.response }]);

if (resolvedProfileModel && looksLikeUnsavedProfileResponse(data.response)) {
  if (!unsavedProfileNoticeRef.current.has(resolvedProfileModel) && !savedProfileNoticeRef.current.has(resolvedProfileModel)) {
    unsavedProfileNoticeRef.current.add(resolvedProfileModel);
    addAgentMessage(PROFILE_UNSAVED_MESSAGE);
  }
}

if (resolvedProfileModel && looksLikeSavedProfileResponse(data.response)) {
  unsavedProfileNoticeRef.current.delete(resolvedProfileModel);
  if (!savedProfileNoticeRef.current.has(resolvedProfileModel)) {
    savedProfileNoticeRef.current.add(resolvedProfileModel);
    addAgentMessage(PROFILE_SAVED_MESSAGE);
  }
}
```

- [ ] **Step 5: Run the new smoke to verify it passes**

Run: `python3 -m pytest tests/test_frontend_profile_save_status_smoke.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_profile_save_status_smoke.py
git commit -m "feat: show BJTagent profile save status in chat log"
```

### Task 3: Guard the Existing Frontend Agent Experience

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_agent_experience_smoke.py`
- Test: `tests/test_frontend_abort_smoke.py`

- [ ] **Step 1: Run existing frontend smoke tests**

Run: `python3 -m pytest tests/test_frontend_agent_experience_smoke.py tests/test_frontend_abort_smoke.py tests/test_frontend_profile_save_status_smoke.py -q`
Expected: PASS

- [ ] **Step 2: If needed, make the minimal compatibility adjustment**

```jsx
const addAgentMessage = (text) =>
  setMsgs((m) => [...m, { role: "system", text }]);
```

```jsx
setConversationState(data.conversation_state || null);
if (data.plan) onPlanReady?.(data.plan);
setMsgs((m) => [...m, { role: "ai", text: data.response }]);
```

Use this step only if the new save-status logic accidentally breaks:
- existing `conversation_state` roundtrip copy
- existing unknown-model action log copy
- existing runtime abort log copy

- [ ] **Step 3: Re-run frontend smoke after any adjustment**

Run: `python3 -m pytest tests/test_frontend_agent_experience_smoke.py tests/test_frontend_abort_smoke.py tests/test_frontend_profile_save_status_smoke.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_agent_experience_smoke.py tests/test_frontend_abort_smoke.py tests/test_frontend_profile_save_status_smoke.py
git commit -m "test: protect existing BJTagent frontend smoke coverage"
```

### Task 4: Run Build and Target Verification

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_profile_save_status_smoke.py`
- Test: `tests/test_frontend_agent_experience_smoke.py`
- Test: `tests/test_frontend_abort_smoke.py`
- Test: `tests/test_gui_smoke.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: Run the frontend build**

Run: `npm run build`
Working directory: `/Users/helap/Documents/Project/雨骤/frontend`
Expected: build succeeds without new frontend errors

- [ ] **Step 2: Run the requested verification suite**

Run: `python3 -m pytest tests/test_frontend_profile_save_status_smoke.py tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py tests/test_gui_smoke.py tests/test_cli_smoke.py -q`
Expected: PASS

- [ ] **Step 3: Run diagnostics on edited files**

Check:
- `file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx`
- `file:///Users/helap/Documents/Project/雨骤/tests/test_frontend_profile_save_status_smoke.py`

Expected: no new error-level diagnostics

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx tests/test_frontend_profile_save_status_smoke.py
git commit -m "chore: verify frontend profile save status flow"
```

## Self-Review

- Spec coverage: 计划覆盖了聊天区系统提示、未保存/已保存两类文案、同型号去重、基于 `conversationState/currentPlan` 的型号解析、最小 smoke 和前端构建验证。
- Placeholder scan: 每个任务都给出了精确文件、代码片段、命令和预期结果，没有 `TODO/TBD` 或“自行实现”类占位。
- Type consistency: 计划统一使用 `PROFILE_UNSAVED_MESSAGE`、`PROFILE_SAVED_MESSAGE`、`unsavedProfileNoticeRef`、`savedProfileNoticeRef` 和 `resolvedProfileModel`，命名在各任务之间保持一致。
