# User Profile Library Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为用户型号库增加完整管理能力，包括前端 `器件库` 面板、`BJTagent` 对话快捷入口、后端 CRUD API 与关键字段更新确认流。

**Architecture:** 在现有 `config/user_transistor_profiles.json` 基础上增加统一管理层，负责列表、搜索、详情、新增、更新、删除、启用/禁用和关键字段确认。前端右侧面板扩展为 `BJTagent / 器件库` 双标签，对话命令只做快捷入口和联动，不绕过管理 API 和现有 `SafetyGuard`。

**Tech Stack:** Python 3、dataclasses、JSON 文件持久化、`BaseHTTPRequestHandler` API、React、现有前端 smoke、pytest

---

## File Structure

- Create: `tests/test_user_profile_manager.py`
- Modify: `ai/user_profile_store.py`
- Modify: `ai/transistor_db.py`
- Modify: `ai/conversation.py`
- Modify: `ai/agent.py`
- Modify: `api_server.py`
- Modify: `frontend/src/App.jsx`
- Create: `tests/test_api_user_profiles.py`
- Create: `tests/test_frontend_device_library_smoke.py`
- Modify: `tests/test_ai_conversation.py`
- Modify: `tests/test_ai_agent.py`

### Task 1: Expand User Profile Store Into A Manager

**Files:**
- Modify: `ai/user_profile_store.py`
- Create: `tests/test_user_profile_manager.py`

- [ ] **Step 1: Write the failing manager tests**

```python
from pathlib import Path

from ai.user_profile_store import (
    create_user_profile,
    delete_user_profile,
    get_user_profile,
    list_user_profiles,
    search_user_profiles,
    toggle_user_profile_enabled,
    update_user_profile_record,
)


def test_list_user_profiles_returns_metadata_and_enabled_flag(tmp_path: Path) -> None:
    create_user_profile(
        tmp_path / "profiles.json",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
            "enabled": True,
        },
    )

    items = list_user_profiles(tmp_path / "profiles.json")

    assert items[0]["model"] == "XYZ123"
    assert items[0]["enabled"] is True


def test_search_user_profiles_filters_by_model_fragment(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})
    create_user_profile(store, {"model": "ABC999", "bjt_type": "PNP", "vceo_max_v": 30.0, "ic_max_a": 0.1, "p_tot_w": 0.4})

    items = search_user_profiles(store, "xyz")

    assert [item["model"] for item in items] == ["XYZ123"]


def test_toggle_user_profile_enabled_changes_runtime_flag(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})

    record = toggle_user_profile_enabled(store, "XYZ123", enabled=False)

    assert record["enabled"] is False
    assert get_user_profile(store, "XYZ123")["enabled"] is False


def test_update_user_profile_record_reports_critical_field_changes(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})

    result = update_user_profile_record(store, "XYZ123", {"ic_max_a": 0.3}, require_confirmation=False)

    assert result["status"] == "confirmation_required"
    assert result["critical_changes"][0]["field"] == "ic_max_a"


def test_delete_user_profile_removes_existing_record(tmp_path: Path) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(store, {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})

    delete_user_profile(store, "XYZ123")

    assert list_user_profiles(store) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_user_profile_manager.py -q`
Expected: FAIL with import errors for the new manager functions.

- [ ] **Step 3: Implement the minimal manager API**

```python
CRITICAL_PROFILE_FIELDS = {"bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"}


def list_user_profiles(path: Path) -> list[dict]:
    ...


def search_user_profiles(path: Path, query: str) -> list[dict]:
    ...


def get_user_profile(path: Path, model: str) -> dict:
    ...


def create_user_profile(path: Path, payload: Mapping[str, object]) -> dict:
    ...


def update_user_profile_record(
    path: Path,
    model: str,
    payload: Mapping[str, object],
    *,
    require_confirmation: bool,
) -> dict:
    ...


def delete_user_profile(path: Path, model: str) -> None:
    ...


def toggle_user_profile_enabled(path: Path, model: str, *, enabled: bool) -> dict:
    ...
```

- [ ] **Step 4: Run tests to verify it passes**

Run: `python3 -m pytest tests/test_user_profile_manager.py -q`
Expected: PASS

### Task 2: Keep Runtime Lookup Safe

**Files:**
- Modify: `ai/transistor_db.py`
- Test: `tests/test_user_profile_manager.py`

- [ ] **Step 1: Write the failing enabled-only lookup test**

```python
from ai.transistor_db import lookup_transistor
from ai.user_profile_store import create_user_profile


def test_lookup_transistor_ignores_disabled_user_profiles(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "profiles.json"
    create_user_profile(
        store,
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 55.0,
            "ic_max_a": 0.3,
            "p_tot_w": 0.6,
            "enabled": False,
        },
    )
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))

    profile = lookup_transistor("XYZ123")

    assert profile.confidence == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_user_profile_manager.py::test_lookup_transistor_ignores_disabled_user_profiles -q`
Expected: FAIL because lookup still returns the disabled user record.

- [ ] **Step 3: Implement enabled-only runtime filtering**

```python
def lookup_transistor(model: str) -> TransistorProfile:
    ...
    if key in user_profiles and user_profiles[key].get("enabled", True):
        return _profile_from_user_record(user_profiles[key])
    ...
```

- [ ] **Step 4: Run the targeted tests**

Run: `python3 -m pytest tests/test_user_profile_manager.py -q`
Expected: PASS

### Task 3: Add Conversation Intents For Library Management

**Files:**
- Modify: `ai/conversation.py`
- Modify: `tests/test_ai_conversation.py`

- [ ] **Step 1: Write the failing conversation tests**

```python
def test_library_command_lists_saved_profiles() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("列出已保存型号", state)

    assert intent.action == "manage_profile_library"
    assert intent.response == "list_profiles"


def test_library_command_views_specific_profile() -> None:
    state = AIConversationState()

    intent = infer_intent_locally("查看 XYZ123", state)

    assert intent.action == "manage_profile_library"
    assert intent.model == "XYZ123"
    assert intent.response == "view_profile"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_conversation.py -q`
Expected: FAIL because `manage_profile_library` is not yet supported.

- [ ] **Step 3: Add the minimal local intent parsing**

```python
IntentAction = Literal[
    ...,
    "manage_profile_library",
]

if _looks_like_library_list_command(text):
    return AIIntent(action="manage_profile_library", response="list_profiles")
if _looks_like_library_view_command(text, guessed_model):
    return AIIntent(action="manage_profile_library", model=guessed_model, response="view_profile")
```

- [ ] **Step 4: Run the conversation tests**

Run: `python3 -m pytest tests/test_ai_conversation.py -q`
Expected: PASS

### Task 4: Route Library Commands Through The Agent

**Files:**
- Modify: `ai/agent.py`
- Modify: `tests/test_ai_agent.py`

- [ ] **Step 1: Write the failing agent tests**

```python
def test_agent_lists_saved_profiles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    create_user_profile(tmp_path / "profiles.json", {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})

    result = TestAgent().run_turn("列出已保存型号")

    assert result.intent.action == "manage_profile_library"
    assert "XYZ123" in result.response
    assert result.agent_state == "profile_library_ready"


def test_agent_requests_confirmation_for_critical_profile_update(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    create_user_profile(tmp_path / "profiles.json", {"model": "XYZ123", "bjt_type": "NPN", "vceo_max_v": 40.0, "ic_max_a": 0.2, "p_tot_w": 0.5})

    result = TestAgent().run_turn("把 XYZ123 的 Ic 最大值改成 300mA")

    assert result.agent_state == "awaiting_profile_update_confirmation"
    assert "二次确认" in result.response
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_agent.py -q`
Expected: FAIL because the agent does not handle library management actions yet.

- [ ] **Step 3: Implement minimal routing and confirmation state**

```python
elif intent.action == "manage_profile_library":
    response, agent_state, next_actions = _handle_profile_library_management(intent, text, self.state)
```

- [ ] **Step 4: Run the agent tests**

Run: `python3 -m pytest tests/test_ai_agent.py -q`
Expected: PASS

### Task 5: Expose User Profile CRUD APIs

**Files:**
- Modify: `api_server.py`
- Create: `tests/test_api_user_profiles.py`

- [ ] **Step 1: Write the failing API tests**

```python
def test_get_user_profiles_returns_saved_items(...) -> None:
    ...


def test_post_user_profile_creates_record(...) -> None:
    ...


def test_put_user_profile_requires_confirmation_for_critical_change(...) -> None:
    ...


def test_post_toggle_enabled_updates_enabled_flag(...) -> None:
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_api_user_profiles.py -q`
Expected: FAIL with 404 or missing handler errors.

- [ ] **Step 3: Add minimal API handlers**

```python
def do_GET(self) -> None:
    if self.path.startswith("/api/user-profiles"):
        self._handle_user_profiles_get()
        return

def do_POST(self) -> None:
    if self.path == "/api/user-profiles":
        self._handle_user_profiles_create()
        return
    if self.path.endswith("/toggle-enabled"):
        self._handle_user_profiles_toggle()
        return
```

- [ ] **Step 4: Run the API tests**

Run: `python3 -m pytest tests/test_api_user_profiles.py -q`
Expected: PASS

### Task 6: Build The Device Library Panel

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `tests/test_frontend_device_library_smoke.py`

- [ ] **Step 1: Write the failing frontend smoke**

```python
from pathlib import Path

APP = Path("frontend/src/App.jsx").read_text(encoding="utf-8")


def test_device_library_panel_has_primary_tabs() -> None:
    assert '["BJTagent", "器件库"]' in APP


def test_device_library_panel_has_search_and_create_controls() -> None:
    assert "搜索器件库" in APP
    assert "新增器件" in APP


def test_device_library_panel_has_enable_disable_and_delete_actions() -> None:
    assert "启用" in APP
    assert "禁用" in APP
    assert "删除" in APP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_frontend_device_library_smoke.py -q`
Expected: FAIL because the device library panel does not exist yet.

- [ ] **Step 3: Implement the right-panel tab switch and device library UI**

```jsx
const [rightPanel, setRightPanel] = useState("BJTagent");
...
<Segmented options={["BJTagent", "器件库"]} value={rightPanel} onChange={setRightPanel} />
{rightPanel === "BJTagent" ? <AIPanel ... /> : <DeviceLibraryPanel ... />}
```

- [ ] **Step 4: Run the frontend smoke**

Run: `python3 -m pytest tests/test_frontend_device_library_smoke.py -q`
Expected: PASS

### Task 7: Add Frontend API Wiring And Chat Shortcut Linkage

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `tests/test_frontend_device_library_smoke.py`

- [ ] **Step 1: Write the failing linkage smoke**

```python
def test_device_library_panel_fetches_user_profiles() -> None:
    assert "/api/user-profiles" in APP


def test_agent_library_commands_can_switch_to_library_panel() -> None:
    assert "setRightPanel(\"器件库\")" in APP
```

- [ ] **Step 2: Run the smoke to verify it fails**

Run: `python3 -m pytest tests/test_frontend_device_library_smoke.py -q`
Expected: FAIL because the panel does not fetch profiles or react to agent library commands.

- [ ] **Step 3: Implement the minimal fetch and panel switching logic**

```jsx
const loadUserProfiles = async () => {
  const data = await fetchJson("/api/user-profiles");
  setUserProfiles(data.items || []);
};

if (looksLikeLibraryCommand(data.intent, data.response)) {
  setRightPanel("器件库");
}
```

- [ ] **Step 4: Run the smoke again**

Run: `python3 -m pytest tests/test_frontend_device_library_smoke.py -q`
Expected: PASS

### Task 8: Verify Existing Frontend Agent Experience Stays Intact

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `tests/test_frontend_agent_experience_smoke.py`
- Test: `tests/test_frontend_profile_save_status_smoke.py`

- [ ] **Step 1: Run the existing frontend smokes**

Run: `python3 -m pytest tests/test_frontend_agent_experience_smoke.py tests/test_frontend_profile_save_status_smoke.py -q`
Expected: FAIL only if the new right-panel integration breaks current `BJTagent` behavior.

- [ ] **Step 2: Fix any regressions with the smallest possible changes**

```jsx
{rightPanel === "BJTagent" ? (
  <AIPanel ... />
) : (
  <DeviceLibraryPanel ... />
)}
```

- [ ] **Step 3: Re-run the frontend smokes**

Run: `python3 -m pytest tests/test_frontend_agent_experience_smoke.py tests/test_frontend_profile_save_status_smoke.py tests/test_frontend_device_library_smoke.py -q`
Expected: PASS

### Task 9: Full Verification

**Files:**
- Modify only if verification finds regressions

- [ ] **Step 1: Run targeted Python tests**

Run: `python3 -m pytest tests/test_user_profile_manager.py tests/test_api_user_profiles.py tests/test_ai_conversation.py tests/test_ai_agent.py -q`
Expected: PASS

- [ ] **Step 2: Run targeted frontend smokes**

Run: `python3 -m pytest tests/test_frontend_device_library_smoke.py tests/test_frontend_profile_save_status_smoke.py tests/test_frontend_agent_experience_smoke.py tests/test_frontend_abort_smoke.py -q`
Expected: PASS

- [ ] **Step 3: Build the frontend**

Run: `npm run build`
Working directory: `/Users/helap/Documents/Project/雨骤/frontend`
Expected: PASS with Vite production build output.

- [ ] **Step 4: Run the agent regression gate**

Run: `python3 scripts/run_agent_regression.py --json`
Expected: PASS with safety-related metrics still at `1.0`.

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -q`
Expected: PASS
