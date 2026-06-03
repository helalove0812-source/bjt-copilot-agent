from __future__ import annotations

import json
import os
from pathlib import Path

import api_server
from ai.datasheet_lookup import DatasheetLookupResult, DatasheetSearchResult
from ai.test_planner import build_test_plan
from ai.transistor_db import TransistorProfile


class FakeHandler:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.sent_status: int | None = None
        self.sent_payload: dict | None = None

    def _read_payload(self) -> dict:
        return dict(self.payload)

    def _send_json(self, status: int, payload: dict) -> None:
        self.sent_status = status
        self.sent_payload = json.loads(json.dumps(payload, ensure_ascii=False))

    def _user_profile_store_path(self) -> Path:
        return Path(os.environ.get("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))


def call_execute_plan_handler(payload: dict) -> tuple[int, dict]:
    handler = FakeHandler(payload)
    api_server.ApiHandler._handle_execute_plan(handler)
    assert handler.sent_status is not None
    assert handler.sent_payload is not None
    return handler.sent_status, handler.sent_payload


def call_preflight_plan_handler(payload: dict) -> tuple[int, dict]:
    handler = FakeHandler(payload)
    api_server.ApiHandler._handle_preflight_plan(handler)
    assert handler.sent_status is not None
    assert handler.sent_payload is not None
    return handler.sent_status, handler.sent_payload


def call_ai_chat_handler(payload: dict) -> tuple[int, dict]:
    handler = FakeHandler(payload)
    api_server.ApiHandler._handle_ai_chat(handler)
    assert handler.sent_status is not None
    assert handler.sent_payload is not None
    return handler.sent_status, handler.sent_payload


def call_run_action_handler(payload: dict) -> tuple[int, dict]:
    handler = FakeHandler(payload)
    api_server.ApiHandler._handle_run_action(handler)
    assert handler.sent_status is not None
    assert handler.sent_payload is not None
    return handler.sent_status, handler.sent_payload


def test_api_server_main_loads_dotenv_before_serving(monkeypatch) -> None:
    calls = []

    class FakeServer:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler

        def serve_forever(self):
            calls.append(("serve", self.address))
            raise KeyboardInterrupt

    monkeypatch.setattr(api_server, "load_dotenv", lambda: calls.append(("dotenv", None)))
    monkeypatch.setattr(api_server, "ThreadingHTTPServer", FakeServer)

    try:
        api_server.main()
    except KeyboardInterrupt:
        pass

    assert calls[0] == ("dotenv", None)
    assert calls[1] == ("serve", ("127.0.0.1", 8765))


def test_ai_chat_returns_pending_profile_state_for_unknown_model(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "测一下 XYZ123",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["plan"] is None
    assert "未知型号" in result["response"]
    assert result["agent_state"] == "awaiting_profile_fields"
    assert result["required_inputs"] == ["管型", "Vceo", "Ic 最大值", "Ptot"]
    assert result["agent_steps"][-1]["status"] == "waiting"
    assert result["conversation_state"]["pending_profile_model"] == "XYZ123"
    assert result["conversation_state"]["pending_profile_fields"] == {}
    assert result["intent_debug"]["final_intent"]["action"] == "create_plan"
    assert result["intent_debug"]["final_source"] == "local"


def test_ai_chat_can_build_unknown_model_plan_from_datasheet_lookup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    profile = TransistorProfile(
        model="C1815",
        bjt_type="NPN",
        description="联网 datasheet 搜索提取的 NPN 小信号三极管",
        vceo_max_v=50.0,
        ic_max_a=0.15,
        p_tot_w=0.4,
        hfe_typical=(70, 700),
        package="TO-92",
        pinout_hint="联网资料提示：不同厂商可能存在 ECB/EBC 差异。",
        confidence="datasheet_lookup",
    )

    def fake_lookup(model: str):
        return DatasheetLookupResult(
            ok=True,
            model=model,
            query=f"{model} transistor datasheet",
            profile=profile,
            sources=[DatasheetSearchResult(title="C1815 datasheet", url="https://example.test/c1815.pdf")],
            confidence="high",
        )

    monkeypatch.setattr(api_server, "lookup_datasheet_profile", fake_lookup)

    status, result = call_ai_chat_handler(
        {
            "text": "测试 C1815",
            "mode": "hardware",
            "context": {},
            "ai_settings": {"provider": "local", "datasheet_lookup": True},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["intent"] == "create_plan"
    assert result["plan"]["model"] == "C1815"
    assert result["plan"]["profile"]["confidence"] == "datasheet_lookup"
    assert result["conversation_state"]["pending_profile_model"] is None
    assert result["datasheet_lookup"]["ok"] is True
    assert result["datasheet_lookup"]["sources"][0]["url"] == "https://example.test/c1815.pdf"


def test_ai_chat_auto_imports_datasheet_profile_into_user_library(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    profile = TransistorProfile(
        model="C1815",
        bjt_type="NPN",
        description="联网 datasheet 搜索提取的 NPN 小信号三极管",
        vceo_max_v=50.0,
        ic_max_a=0.15,
        p_tot_w=0.4,
        hfe_typical=(70, 700),
        package="TO-92",
        pinout_hint="联网资料提示：不同厂商可能存在 ECB/EBC 差异。",
        confidence="datasheet_lookup",
    )

    def fake_lookup(model: str):
        return DatasheetLookupResult(
            ok=True,
            model=model,
            query=f"{model} transistor datasheet",
            profile=profile,
            sources=[DatasheetSearchResult(title="C1815 datasheet", url="https://example.test/c1815.pdf")],
            confidence="high",
        )

    monkeypatch.setattr(api_server, "lookup_datasheet_profile", fake_lookup)

    status, result = call_ai_chat_handler(
        {
            "text": "测试 C1815",
            "mode": "hardware",
            "context": {},
            "ai_settings": {"provider": "local", "datasheet_lookup": True},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert "自动写入本地型号库" in result["response"]
    record = api_server.get_user_profile_record(tmp_path / "profiles.json", "C1815")
    assert record["model"] == "C1815"
    assert record["source"] == "datasheet_lookup"
    assert record["confirmed_by_user"] is False
    assert record["package"] == "TO-92"


def test_ai_chat_does_not_overwrite_existing_user_profile_when_auto_importing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    store = tmp_path / "profiles.json"
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(store))
    api_server.create_user_profile(
        store,
        {
            "model": "C1815",
            "bjt_type": "NPN",
            "vceo_max_v": 60.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
            "source": "user_confirmed",
            "confirmed_by_user": True,
        },
    )
    profile = TransistorProfile(
        model="C1815",
        bjt_type="NPN",
        description="联网 datasheet 搜索提取的 NPN 小信号三极管",
        vceo_max_v=50.0,
        ic_max_a=0.15,
        p_tot_w=0.4,
        hfe_typical=(70, 700),
        package="TO-92",
        pinout_hint="联网资料提示：不同厂商可能存在 ECB/EBC 差异。",
        confidence="datasheet_lookup",
    )

    def fake_lookup(model: str):
        return DatasheetLookupResult(
            ok=True,
            model=model,
            query=f"{model} transistor datasheet",
            profile=profile,
            sources=[DatasheetSearchResult(title="C1815 datasheet", url="https://example.test/c1815.pdf")],
            confidence="high",
        )

    monkeypatch.setattr(api_server, "lookup_datasheet_profile", fake_lookup)

    status, result = call_ai_chat_handler(
        {
            "text": "测试 C1815",
            "mode": "hardware",
            "context": {},
            "ai_settings": {"provider": "local", "datasheet_lookup": True},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert "本地型号库已存在 C1815" in result["response"]
    record = api_server.get_user_profile_record(store, "C1815")
    assert record["vceo_max_v"] == 60.0
    assert record["ic_max_a"] == 0.2
    assert record["confirmed_by_user"] is True


def test_ai_chat_preserves_pending_profile_fields_across_turns(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "NPN，40V",
            "mode": "simulation",
            "context": {
                "pending_profile_model": "XYZ123",
                "pending_profile_fields": {},
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["plan"] is None
    assert "还需要" in result["response"]
    assert result["agent_state"] == "awaiting_profile_fields"
    assert result["required_inputs"] == ["Ic 最大值", "Ptot"]
    assert result["conversation_state"]["pending_profile_model"] == "XYZ123"
    assert result["conversation_state"]["pending_profile_fields"] == {
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
    }


def test_ai_chat_accepts_nested_conversation_state_from_frontend(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "Ic 最大 200mA",
            "mode": "simulation",
            "context": {
                "conversation_state": {
                    "pending_profile_model": "XYZ123",
                    "pending_profile_fields": {
                        "bjt_type": "NPN",
                        "vceo_max_v": 40.0,
                    },
                }
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["agent_state"] == "awaiting_profile_fields"
    assert result["conversation_state"]["pending_profile_model"] == "XYZ123"
    assert result["conversation_state"]["pending_profile_fields"] == {
        "bjt_type": "NPN",
        "vceo_max_v": 40.0,
        "ic_max_a": 0.2,
    }


def test_ai_chat_builds_plan_after_pending_profile_is_complete(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "继续生成计划",
            "mode": "simulation",
            "context": {
                "pending_profile_model": "XYZ123",
                "pending_profile_fields": {
                    "bjt_type": "NPN",
                    "vceo_max_v": 40.0,
                    "ic_max_a": 0.2,
                    "p_tot_w": 0.5,
                },
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["plan"]["model"] == "XYZ123"
    assert result["plan"]["profile"]["confidence"] == "user_supplied"
    assert result["agent_state"] == "plan_ready"
    assert "运行仿真" in result["next_actions"]
    assert result["conversation_state"]["current_plan"]["model"] == "XYZ123"
    assert result["conversation_state"]["pending_profile_model"] is None
    assert result["conversation_state"]["pending_profile_fields"] == {}


def test_ai_chat_exposes_plan_ready_agent_view(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "测 S8050，重点看 beta",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["plan"]["model"] == "S8050"
    assert result["agent_state"] == "plan_ready"
    assert result["required_inputs"] == []
    assert "运行仿真" in result["next_actions"]
    assert "请求硬件执行确认" in result["next_actions"]
    assert result["conversation_state"]["current_plan"]["model"] == "S8050"


def test_ai_chat_lists_user_profiles_for_library_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    status, created = call_ai_chat_handler(
        {
            "text": "列出已保存型号",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert created["ok"] is True
    assert created["intent"] == "manage_profile_library"
    assert created["agent_state"] == "profile_library_ready"


def test_ai_chat_disables_profile_after_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    api_server.create_user_profile(
        tmp_path / "profiles.json",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    first_status, first = call_ai_chat_handler(
        {
            "text": "禁用 XYZ123",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )
    second_status, second = call_ai_chat_handler(
        {
            "text": "确认",
            "mode": "simulation",
            "context": {
                "conversation_state": first["conversation_state"],
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert first_status == 200
    assert first["agent_state"] == "awaiting_profile_library_confirmation"
    assert first["conversation_state"]["pending_library_action"]["action"] == "disable_profile"
    assert second_status == 200
    assert second["agent_state"] == "profile_library_ready"
    assert second["conversation_state"]["pending_library_action"] is None
    record = api_server.get_user_profile_record(tmp_path / "profiles.json", "XYZ123")
    assert record["enabled"] is False


def test_ai_chat_updates_profile_after_critical_change_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    monkeypatch.setenv("BJT_USER_PROFILE_STORE", str(tmp_path / "profiles.json"))
    api_server.create_user_profile(
        tmp_path / "profiles.json",
        {
            "model": "XYZ123",
            "bjt_type": "NPN",
            "vceo_max_v": 40.0,
            "ic_max_a": 0.2,
            "p_tot_w": 0.5,
        },
    )

    first_status, first = call_ai_chat_handler(
        {
            "text": "更新 XYZ123 Ic 到 300mA",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )
    second_status, second = call_ai_chat_handler(
        {
            "text": "确认更新",
            "mode": "simulation",
            "context": {
                "conversation_state": first["conversation_state"],
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert first_status == 200
    assert first["agent_state"] == "awaiting_profile_library_confirmation"
    assert "critical_changes" in first["conversation_state"]["pending_library_action"]
    assert second_status == 200
    assert second["agent_state"] == "profile_library_ready"
    record = api_server.get_user_profile_record(tmp_path / "profiles.json", "XYZ123")
    assert record["ic_max_a"] == 0.3


def test_ai_chat_exposes_hardware_confirmation_agent_view(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    status, result = call_ai_chat_handler(
        {
            "text": "开始执行硬件测试",
            "mode": "hardware",
            "context": {"current_plan": plan.to_dict()},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["intent"] == "execute_hardware"
    assert result["agent_state"] == "awaiting_hardware_confirmation"
    assert result["required_inputs"] == ["确认硬件执行"]
    assert "使用执行按钮并输入确认短语" in result["next_actions"]


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


def test_ai_chat_compares_execution_history_from_context(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    history = [
        {
            "measurements": [
                {"beta": 40.0, "region": "active", "Ic": 0.001, "Vce": 2.5},
                {"beta": 60.0, "region": "active", "Ic": 0.002, "Vce": 2.2},
            ]
        },
        {
            "measurements": [
                {"beta": 80.0, "region": "active", "Ic": 0.003, "Vce": 2.4},
                {"beta": 100.0, "region": "saturation", "Ic": 0.004, "Vce": 0.1},
            ]
        },
    ]

    status, result = call_ai_chat_handler(
        {
            "text": "这两次测量有什么区别",
            "mode": "simulation",
            "context": {"execution_history": history},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["intent"] == "explain_result"
    assert result["agent_state"] == "diagnosing"
    assert "最近两次执行对比" in result["response"]
    assert result["conversation_state"]["execution_history"][-1]["measurements"][0]["beta"] == 80.0


def test_ai_chat_autonomously_refines_plan_from_execution_context(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")
    plan = build_test_plan(model="S8050", goal="beta", depth="standard")

    status, result = call_ai_chat_handler(
        {
            "text": "下一步你自己看着办，优化一下计划",
            "mode": "simulation",
            "context": {
                "current_plan": plan.to_dict(),
                "current_execution": {
                    "mode": "hardware",
                    "measurements": [
                        {"beta": 310.0, "region": "saturation", "Ic": 0.031, "Vce": 0.1},
                    ],
                    "aborted": True,
                    "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
                },
            },
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert result["intent"] == "modify_plan"
    assert result["agent_state"] == "plan_refined"
    assert result["plan"]["ic_limit_a"] < plan.ic_limit_a
    assert result["completed_actions"]
    assert "自动生成下一版安全计划" in result["response"]
    assert {"modify_plan", "clamp_current", "clamp_power"}.issubset(
        {item["action"] for item in result["completed_action_items"]}
    )
    assert result["conversation_state"]["current_plan"]["ic_limit_a"] == result["plan"]["ic_limit_a"]
    assert result["conversation_state"]["agent_activity_history"][-1]["type"] == "plan_refined"
    assert result["conversation_state"]["agent_activity_history"][-1]["completed_actions"] == result["completed_actions"]


def test_ai_chat_returns_structured_next_action_items(monkeypatch) -> None:
    monkeypatch.setenv("BJT_AI_MODE", "local")

    status, result = call_ai_chat_handler(
        {
            "text": "测 S8050，重点看 beta",
            "mode": "simulation",
            "context": {},
            "ai_settings": {"provider": "local"},
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert any(item["action"] == "run_simulation" for item in result["next_action_items"])
    assert any(item["action"] == "request_hardware_confirmation" for item in result["next_action_items"])


def test_execute_plan_api_requires_hardware_confirmation_phrase(monkeypatch) -> None:
    calls: list[dict] = []
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    def fake_execute_plan(plan, *, mode, output_dir=None, allow_hardware=False, token_valid=None):
        calls.append(
            {
                "mode": mode,
                "output_dir": output_dir,
                "allow_hardware": allow_hardware,
                "token_valid": token_valid,
                "model": plan.model,
            }
        )
        return {
            "plan": plan.to_dict(),
            "mode": mode,
            "skipped": not token_valid,
            "reason": "missing confirmation" if not token_valid else "",
        }

    monkeypatch.setattr(api_server, "execute_plan", fake_execute_plan)

    missing_status, missing = call_execute_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "plan": plan.to_dict(),
        },
    )
    confirmed_status, confirmed = call_execute_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "hardware_confirmation": "确认硬件执行",
            "plan": plan.to_dict(),
        },
    )

    assert missing_status == 200
    assert missing["ok"] is True
    assert missing["execution"]["skipped"] is True
    assert missing["agent_state"] == "execution_skipped"
    assert "查看跳过原因" in missing["next_actions"]
    assert confirmed_status == 200
    assert confirmed["ok"] is True
    assert confirmed["execution"]["skipped"] is False
    assert confirmed["agent_state"] == "execution_complete"
    assert "解释结果" in confirmed["next_actions"]
    assert calls == [
        {
            "mode": "hardware",
            "output_dir": None,
            "allow_hardware": True,
            "token_valid": False,
            "model": "S8050",
        },
        {
            "mode": "hardware",
            "output_dir": None,
            "allow_hardware": True,
            "token_valid": True,
            "model": "S8050",
        },
    ]


def test_execute_plan_api_allows_simulation_without_confirmation(monkeypatch) -> None:
    calls: list[dict] = []
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="simulation")

    def fake_execute_plan(plan, *, mode, output_dir=None, allow_hardware=False, token_valid=None):
        calls.append({"mode": mode, "allow_hardware": allow_hardware, "token_valid": token_valid})
        return {"plan": plan.to_dict(), "mode": mode, "measurements": []}

    monkeypatch.setattr(api_server, "execute_plan", fake_execute_plan)

    status, result = call_execute_plan_handler(
        {
            "mode": "simulation",
            "allow_hardware": False,
            "plan": plan.to_dict(),
        },
    )

    assert status == 200
    assert result["ok"] is True
    assert result["agent_state"] == "execution_complete"
    assert calls == [{"mode": "simulation", "allow_hardware": False, "token_valid": True}]


def test_preflight_plan_api_requires_confirmation_without_execution(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    def fail_execute_plan(*args, **kwargs):
        del args, kwargs
        raise AssertionError("preflight endpoint must not execute the plan")

    monkeypatch.setattr(api_server, "execute_plan", fail_execute_plan)

    status, result = call_preflight_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "plan": plan.to_dict(),
        },
    )

    assert status == 200
    assert result["ok"] is True
    assert result["preflight"]["status"] == "require_confirm"
    assert result["preflight"]["requires_confirmation"] is True
    assert result["preflight"]["will_touch_hardware"] is False
    assert result["preflight"]["preflight_summary"]
    assert [check["id"] for check in result["preflight"]["checks"]] == [
        "dry_run",
        "bjt_type",
        "hardware_allowance",
        "hardware_confirmation",
    ]
    assert result["preflight"]["checks"][3]["status"] == "pending"
    assert result["agent_state"] == "awaiting_hardware_confirmation"
    assert result["required_inputs"] == ["确认硬件执行"]
    assert result["agent_steps"][-1]["detail"] == result["preflight"]["preflight_summary"]


def test_preflight_api_returns_canonical_blocked_reason(monkeypatch) -> None:
    plan = build_test_plan(
        model="S8550",
        goal="beta",
        depth="standard",
        mode="hardware",
        bjt_type="PNP",
    )

    def fail_execute_plan(*args, **kwargs):
        del args, kwargs
        raise AssertionError("preflight endpoint must not execute the plan")

    monkeypatch.setattr(api_server, "execute_plan", fail_execute_plan)

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


def test_preflight_plan_api_reports_ready_after_confirmation_phrase(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    def fail_execute_plan(*args, **kwargs):
        del args, kwargs
        raise AssertionError("preflight endpoint must not execute the plan")

    monkeypatch.setattr(api_server, "execute_plan", fail_execute_plan)

    status, result = call_preflight_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "hardware_confirmation": "确认硬件执行",
            "plan": plan.to_dict(),
        },
    )

    assert status == 200
    assert result["ok"] is True
    assert result["preflight"]["status"] == "allow"
    assert result["preflight"]["ok_to_execute"] is True
    assert result["preflight"]["will_touch_hardware"] is False
    assert result["preflight"]["preflight_summary"].startswith("预检通过")
    assert result["preflight"]["checks"][3]["status"] == "pass"
    assert result["agent_state"] == "preflight_ready"
    assert result["agent_steps"][-1]["label"] == "策略允许"


def test_execute_plan_api_exposes_aborted_agent_view(monkeypatch) -> None:
    plan = build_test_plan(model="S8050", goal="beta", depth="standard", mode="hardware")

    def fake_execute_plan(plan, *, mode, output_dir=None, allow_hardware=False, token_valid=None):
        return {
            "plan": plan.to_dict(),
            "mode": mode,
            "serial": "HW-ABORT",
            "measurements": [{"Ic": 0.031, "Vce": 0.1, "beta": 310.0, "region": "saturation"}],
            "aborted": True,
            "abort_reason": "当前 Ic 超过计划上限，已停止后续硬件测量。",
        }

    monkeypatch.setattr(api_server, "execute_plan", fake_execute_plan)

    status, result = call_execute_plan_handler(
        {
            "mode": "hardware",
            "allow_hardware": True,
            "hardware_confirmation": "确认硬件执行",
            "plan": plan.to_dict(),
        },
    )

    assert status == 200
    assert result["ok"] is True
    assert result["agent_state"] == "aborted"
    assert result["execution_state"] == "aborted"
    assert result["blocked_reason"] == "runtime_abort"
    safety_actions = [item["action"] for item in result["safety_action_items"]]
    assert "inspect_abort_reason" in safety_actions
    assert "lower_limits_and_check_wiring" in safety_actions
    assert "降低限值或检查接线后重试" in result["next_actions"]
    assert result["agent_steps"][-1]["label"] == "运行时安全中止"


def test_run_action_full_suite_passes_scan_mode_and_returns_latest_measurement(monkeypatch) -> None:
    captured: dict = {}

    class DummyPoint:
        def __init__(self, *, Vbb, Vcc, Vbe, Vce, Ib, Ic, beta, region) -> None:
            self.Vbb = Vbb
            self.Vcc = Vcc
            self.Vbe = Vbe
            self.Vce = Vce
            self.Ib = Ib
            self.Ic = Ic
            self.beta = beta
            self.region = region

    class DummyReport:
        serial = "HW-FULL"
        bjt_type = "NPN"
        beta_median = 123.4
        vce_sat = 0.12
        Ic_at_sat = 0.008
        output_curves = {
            10e-6: [
                DummyPoint(Vbb=1.0, Vcc=0.5, Vbe=0.7, Vce=0.4, Ib=10e-6, Ic=0.001, beta=100.0, region="active"),
                DummyPoint(Vbb=1.0, Vcc=1.0, Vbe=0.7, Vce=0.9, Ib=10e-6, Ic=0.002, beta=110.0, region="active"),
            ]
        }
        reference_point = DummyPoint(Vbb=2.0, Vcc=3.0, Vbe=0.72, Vce=2.8, Ib=20e-6, Ic=0.004, beta=200.0, region="active")

    def fake_run_full_suite(*, mode, dut_label, output_dir, cfg, scan_mode):
        captured["mode"] = mode
        captured["dut_label"] = dut_label
        captured["output_dir"] = str(output_dir)
        captured["scan_mode"] = scan_mode
        captured["cfg"] = cfg
        return DummyReport()

    monkeypatch.setattr(api_server, "run_full_suite", fake_run_full_suite)

    status, result = call_run_action_handler(
        {
            "action": "full_suite",
            "mode": "hardware",
            "allow_hardware": True,
            "scan_mode": "hardware",
            "dut_label": "WEB-DUT-1",
            "config": {
                "hw_config": {
                    "R_B": 22000,
                    "R_C": 220,
                    "Ic_max_A": 0.03,
                    "Pmax_W": 0.3,
                }
            },
        }
    )

    assert status == 200
    assert result["ok"] is True
    assert captured["mode"] == "hardware"
    assert captured["dut_label"] == "WEB-DUT-1"
    assert captured["scan_mode"] == "hardware"
    assert result["action"] == "full_suite"
    assert result["result"]["serial"] == "HW-FULL"
    assert result["result"]["latest_measurement"]["Vcc"] == 3.0
    assert len(result["result"]["measurements"]) == 2
