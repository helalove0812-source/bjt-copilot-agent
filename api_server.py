from __future__ import annotations

import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.services import (
    build_driver,
    run_detect,
    run_full_suite,
    run_hardware_selftest,
    run_npn_static_bringup,
    run_scan_curves,
    run_scope_check,
)
from ai.action_taxonomy import action_items_from_labels, safety_action_items_from_labels
from ai.assistant import summarize_plan_with_ai
from ai.autonomy import refine_plan_after_execution
from ai.conversation import (
    AIConversationState,
    answer_from_context,
    apply_intent_to_plan,
    interpret_user_message,
)
from ai.rules import diagnose_context
from ai.safety import evaluate_execution_request
from ai.state_taxonomy import blocked_reason_item
from ai.test_planner import TestPlan, plan_from_text
from ai.tools import execute_plan, preflight_plan
from ai.user_profile_store import (
    DuplicateUserProfileError,
    create_user_profile,
    delete_user_profile,
    get_user_profile_record,
    list_user_profiles,
    toggle_user_profile_enabled,
    update_user_profile_record,
)
from core.types import HwConfig
from measurement.vce_sat import estimate_vce_sat


def _num(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _range(value: object, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_num(value[0], default[0]), _num(value[1], default[1]))
    return default


def _hw_config(data: dict) -> HwConfig:
    hw = data.get("hw_config") if isinstance(data.get("hw_config"), dict) else {}
    return HwConfig(
        R_B=_num(hw.get("R_B"), 22e3),
        R_C=_num(hw.get("R_C"), 220.0),
        Ic_max_A=_num(hw.get("Ic_max_A"), 30e-3),
        Pmax_W=_num(hw.get("Pmax_W"), 0.30),
        lin_ic_lo_A=_range(hw.get("lin_ic_range"), (0.5e-3, 20e-3))[0],
        lin_ic_hi_A=_range(hw.get("lin_ic_range"), (0.5e-3, 20e-3))[1],
        lin_vce_window=_range(hw.get("lin_vce_window"), (2.0, 4.0)),
    )


def _float_list(values: object) -> list[float]:
    if not isinstance(values, list):
        return []
    return [_num(value, 0.0) for value in values]


def _static_points(values: object) -> list[dict[str, float]]:
    if not isinstance(values, list):
        return []
    points = []
    for item in values:
        if not isinstance(item, dict):
            continue
        vcc = _num(item.get("vcc"), float("nan"))
        vbb = _num(item.get("vbb"), float("nan"))
        if vcc == vcc and vbb == vbb:
            points.append({"vcc": round(vcc, 3), "vbb": round(vbb, 3)})
    return points


def _plan_from_mapping(data: dict) -> TestPlan:
    if not isinstance(data, dict):
        raise ValueError("plan is required")
    return TestPlan(
        model=str(data.get("model") or "UNKNOWN"),
        bjt_type=str(data.get("bjt_type") or "UNKNOWN"),
        goal=data.get("goal") if data.get("goal") in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else "auto",
        depth=data.get("depth") if data.get("depth") in {"conservative", "standard", "deep"} else "standard",
        mode=str(data.get("mode") or "hardware"),
        vcc_steps=_float_list(data.get("vcc_steps")),
        vbb_steps=_float_list(data.get("vbb_steps")),
        static_points=_static_points(data.get("static_points")),
        ic_limit_a=_num(data.get("ic_limit_a"), 0.03),
        power_limit_w=_num(data.get("power_limit_w"), 0.30),
        sample_count=int(_num(data.get("sample_count"), 2048)),
        scan_mode=str(data.get("scan_mode") or "software"),
        steps=[str(step) for step in data.get("steps", [])] if isinstance(data.get("steps"), list) else [],
        safety_notes=[str(note) for note in data.get("safety_notes", [])] if isinstance(data.get("safety_notes"), list) else [],
        profile=data.get("profile") if isinstance(data.get("profile"), dict) else {},
    )


def _point_to_dict(point) -> dict:
    return {
        "Vbb": point.Vbb,
        "Vcc": point.Vcc,
        "Vbe": point.Vbe,
        "Vce": point.Vce,
        "Ib": point.Ib,
        "Ic": point.Ic,
        "beta": point.beta,
        "region": point.region,
    }


def _points_to_dict(points) -> list[dict]:
    return [_point_to_dict(point) for point in points]


def _apply_ai_settings(payload: dict) -> None:
    settings = payload.get("ai_settings") if isinstance(payload.get("ai_settings"), dict) else {}
    provider = str(settings.get("provider") or "local")
    model = str(settings.get("model") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    if provider == "local":
        os.environ["BJT_AI_MODE"] = "local"
        return
    os.environ["BJT_AI_MODE"] = "cloud"
    os.environ["BJT_AI_PROVIDER"] = provider
    if provider == "deepseek":
        if model:
            os.environ["DEEPSEEK_MODEL"] = model
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key
    elif provider == "openai":
        if model:
            os.environ["OPENAI_MODEL"] = model
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key


def _execution_from_context(context: dict) -> dict | None:
    current_execution = context.get("current_execution")
    if isinstance(current_execution, dict):
        converted = _execution_from_mapping(current_execution)
        if converted:
            return converted
    measurements = context.get("measurements")
    return _execution_from_mapping({"measurements": measurements})


def _execution_from_mapping(data: dict) -> dict | None:
    measurements = data.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return None
    converted = []
    for item in measurements:
        if not isinstance(item, dict):
            continue
        converted.append(
            {
                "Vbb": _num(item.get("Vbb", item.get("vbb")), 0.0),
                "Vcc": _num(item.get("Vcc", item.get("vcc")), 0.0),
                "Vbe": _num(item.get("Vbe", item.get("vbe")), 0.0),
                "Vce": _num(item.get("Vce", item.get("vce")), 0.0),
                "Ib": _num(item.get("Ib", item.get("ib")), 0.0),
                "Ic": _num(item.get("Ic", item.get("ic")), 0.0),
                "beta": _num(item.get("beta"), 0.0),
                "region": str(item.get("region") or "unknown"),
            }
        )
    if not converted:
        return None
    result = dict(data)
    result["measurements"] = converted
    return result


def _hardware_token_valid_from_payload(mode: str, payload: dict) -> bool:
    if mode != "hardware":
        return True
    token = str(
        payload.get("hardware_confirmation_token")
        or payload.get("hardware_confirmation")
        or ""
    ).strip()
    return token == "确认硬件执行"


def _state_from_context(context: dict) -> AIConversationState:
    nested_state = context.get("conversation_state")
    if isinstance(nested_state, dict):
        merged_context = dict(nested_state)
        for key, value in context.items():
            if key != "conversation_state" and value is not None:
                merged_context[key] = value
        context = merged_context
    state = AIConversationState()
    pending_profile_model = context.get("pending_profile_model")
    pending_profile_fields = context.get("pending_profile_fields")
    if isinstance(pending_profile_model, str) and pending_profile_model.strip():
        state.pending_profile_model = pending_profile_model.strip()
    if isinstance(pending_profile_fields, dict):
        state.pending_profile_fields = {
            str(key): value
            for key, value in pending_profile_fields.items()
            if key in {"bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"}
        }
    pending_library_action = context.get("pending_library_action")
    if isinstance(pending_library_action, dict):
        state.pending_library_action = dict(pending_library_action)
    plan = context.get("current_plan")
    if isinstance(plan, dict):
        try:
            state.current_plan = _plan_from_mapping(plan)
        except ValueError:
            state.current_plan = None
    execution = _execution_from_context(context)
    if execution:
        state.current_execution = execution
    execution_history = context.get("execution_history")
    if isinstance(execution_history, list):
        for item in execution_history[-5:]:
            if isinstance(item, dict):
                converted = _execution_from_mapping(item)
                if converted:
                    state.execution_history.append(converted)
    if state.current_execution and not state.execution_history:
        state.execution_history.append(state.current_execution)
    agent_activity_history = context.get("agent_activity_history")
    if isinstance(agent_activity_history, list):
        for item in agent_activity_history[-10:]:
            if isinstance(item, dict):
                state.agent_activity_history.append(item)
    messages = context.get("messages")
    if isinstance(messages, list):
        for message in messages[-12:]:
            if isinstance(message, dict):
                role = str(message.get("role") or "")
                content = str(message.get("content") or "")
                if role and content:
                    state.add(role, content)
    return state


def _context_from_state(state: AIConversationState) -> dict:
    return {
        "current_plan": state.current_plan.to_dict() if state.current_plan else None,
        "current_execution": state.current_execution,
        "execution_history": state.execution_history,
        "agent_activity_history": state.agent_activity_history,
        "pending_profile_model": state.pending_profile_model,
        "pending_profile_fields": dict(state.pending_profile_fields),
        "pending_library_action": dict(state.pending_library_action) if state.pending_library_action else None,
    }


def _diagnose_locally(text: str, context: dict, state: AIConversationState) -> str:
    execution = state.current_execution or {}
    logs = [str(item) for item in context.get("logs", [])[-8:]] if isinstance(context.get("logs"), list) else []
    return diagnose_context(text, logs=logs, measurements=execution.get("measurements") or [])


def _missing_profile_inputs(fields: dict[str, float | str]) -> list[str]:
    labels = {
        "bjt_type": "管型",
        "vceo_max_v": "Vceo",
        "ic_max_a": "Ic 最大值",
        "p_tot_w": "Ptot",
    }
    return [labels[key] for key in ("bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w") if key not in fields]


def _plan_next_actions(plan: TestPlan) -> list[str]:
    actions = ["运行仿真", "解释或调整当前计划"]
    if plan.bjt_type == "NPN":
        actions.append("请求硬件执行确认")
    else:
        actions.append("核对 datasheet、引脚和夹具方向后再走专用流程")
    return actions


def _agent_step(status: str, label: str, detail: str = "") -> dict:
    return {"status": status, "label": label, "detail": detail}


def _chat_agent_view(intent_action: str, state: AIConversationState, plan: TestPlan | None) -> dict:
    steps = [_agent_step("done", "解析意图", intent_action)]
    if state.pending_library_action:
        detail = _pending_library_action_detail(state.pending_library_action)
        steps.append(_agent_step("waiting", "等待器件库确认", detail))
        return {
            "agent_state": "awaiting_profile_library_confirmation",
            "required_inputs": ["明确确认当前器件库操作"],
            "next_actions": ["回复确认继续执行", "回复取消放弃当前器件库操作"],
            "agent_steps": steps,
        }
    if state.pending_profile_model:
        required_inputs = _missing_profile_inputs(state.pending_profile_fields)
        detail = "还需要：" + "、".join(required_inputs) if required_inputs else "规格已完整，可继续生成计划"
        steps.append(_agent_step("waiting", "补全未知型号规格", detail))
        return {
            "agent_state": "awaiting_profile_fields",
            "required_inputs": required_inputs,
            "next_actions": ["继续补充未知型号规格", "改用数据库中已有型号重新生成计划"],
            "agent_steps": steps,
        }
    if intent_action == "execute_hardware":
        if state.current_plan is None:
            steps.append(_agent_step("waiting", "等待硬件计划", "没有可执行计划"))
            return {
                "agent_state": "idle",
                "required_inputs": ["硬件测试计划"],
                "next_actions": ["生成测试计划"],
                "agent_steps": steps,
            }
        steps.append(_agent_step("waiting", "等待硬件确认", "未打开真实输出"))
        return {
            "agent_state": "awaiting_hardware_confirmation",
            "required_inputs": ["确认硬件执行"],
            "next_actions": ["使用执行按钮并输入确认短语", "取消或修改当前计划"],
            "agent_steps": steps,
        }
    if intent_action == "execute_simulation":
        if state.current_plan is None:
            steps.append(_agent_step("waiting", "等待测试计划", "没有可执行计划"))
            return {
                "agent_state": "idle",
                "required_inputs": ["晶体管型号", "测试目标"],
                "next_actions": ["生成测试计划"],
                "agent_steps": steps,
            }
        steps.append(_agent_step("ready", "等待仿真执行", state.current_plan.model))
        return {
            "agent_state": "simulation_ready",
            "required_inputs": [],
            "next_actions": ["使用执行按钮运行仿真", "调整当前计划"],
            "agent_steps": steps,
        }
    if intent_action == "explain_result":
        steps.append(_agent_step("done", "分析上下文", "诊断/解释结果"))
        return {
            "agent_state": "diagnosing",
            "required_inputs": [],
            "next_actions": ["根据诊断修改计划", "重新运行仿真验证"],
            "agent_steps": steps,
        }
    if intent_action == "manage_profile_library":
        steps.append(_agent_step("ready", "切换器件库", "查看或维护已保存型号"))
        return {
            "agent_state": "profile_library_ready",
            "required_inputs": [],
            "next_actions": ["查看器件库详情", "新增或更新型号", "启用/禁用现有型号"],
            "agent_steps": steps,
        }
    current_plan = plan or state.current_plan
    if current_plan is not None:
        steps.append(_agent_step("done", "生成测试计划", "{0} / {1}".format(current_plan.model, current_plan.goal)))
        return {
            "agent_state": "plan_ready",
            "required_inputs": [],
            "next_actions": _plan_next_actions(current_plan),
            "agent_steps": steps,
        }
    steps.append(_agent_step("waiting", "等待测试需求", "需要型号和目标"))
    return {
        "agent_state": "idle",
        "required_inputs": ["晶体管型号", "测试目标"],
        "next_actions": ["生成测试计划"],
        "agent_steps": steps,
    }


def _looks_like_autonomous_refine(text: str) -> bool:
    return any(word in text for word in ("优化", "自动调整", "自己看着办", "下一步", "你来定", "帮我调整", "改进计划"))


def _execution_agent_view(result: dict) -> dict:
    steps = [_agent_step("done", "执行测试", str(result.get("mode") or "unknown"))]
    if result.get("skipped"):
        steps.append(_agent_step("blocked", "执行跳过", str(result.get("reason") or "未知原因")))
        return {
            "agent_state": "execution_skipped",
            "required_inputs": [],
            "next_actions": ["查看跳过原因", "修改计划或切换为仿真模式"],
            "agent_steps": steps,
        }
    if result.get("aborted"):
        steps.append(_agent_step("blocked", "运行时安全中止", str(result.get("abort_reason") or "触发安全判据")))
        return {
            "agent_state": "execution_aborted",
            "required_inputs": [],
            "next_actions": ["查看中止原因", "降低限值或检查接线后重试", "解释已保留的测量点"],
            "agent_steps": steps,
        }
    steps.append(_agent_step("done", "执行完成", "{0} 个测量点".format(len(result.get("measurements") or []))))
    return {
        "agent_state": "execution_complete",
        "required_inputs": [],
        "next_actions": ["解释结果", "调整计划后重测", "导出或查看执行数据"],
        "agent_steps": steps,
    }


def _canonical_policy_fields(*, blocked_reason: str, detail: str, execution_state: str) -> dict:
    return {
        "execution_state": execution_state,
        "blocked_reason": blocked_reason,
        "blocked_reason_item": blocked_reason_item(blocked_reason, detail=detail),
    }


def _preflight_agent_view(result: dict) -> dict:
    steps = [_agent_step("done", "硬件预检", str(result.get("mode") or "unknown"))]
    summary = str(result.get("preflight_summary") or "")
    if result.get("ok_to_execute"):
        steps.append(_agent_step("ready", "策略允许", summary or "仍未打开真实输出"))
        return {
            "agent_state": "preflight_ready",
            "required_inputs": [],
            "next_actions": ["输入确认短语后执行硬件测试", "先运行仿真复核"],
            "agent_steps": steps,
        }
    if result.get("requires_confirmation"):
        steps.append(_agent_step("waiting", "等待硬件确认", summary or "未打开真实输出"))
        return {
            "agent_state": "awaiting_hardware_confirmation",
            "required_inputs": ["确认硬件执行"],
            "next_actions": ["输入确认短语", "取消或修改当前计划"],
            "agent_steps": steps,
        }
    reasons = result.get("reasons") if isinstance(result.get("reasons"), list) else []
    detail = summary or (str(reasons[0]) if reasons else "策略阻止执行")
    steps.append(_agent_step("blocked", "策略阻止", detail))
    return {
        "agent_state": "aborted",
        "required_inputs": [],
        "next_actions": ["查看阻止原因", "修改计划或切换为仿真模式"],
        "agent_steps": steps,
    }


def _pending_library_action_detail(action: dict[str, object]) -> str:
    action_name = str(action.get("action") or "")
    model = str(action.get("model") or "UNKNOWN")
    if action_name == "delete_profile":
        return f"待确认删除 {model}"
    if action_name == "disable_profile":
        return f"待确认禁用 {model}"
    if action_name == "enable_profile":
        return f"待确认启用 {model}"
    if action_name == "update_profile":
        changes = action.get("critical_changes") if isinstance(action.get("critical_changes"), list) else []
        if changes:
            return f"待确认更新 {model} 的安全关键字段"
        return f"待确认更新 {model}"
    return f"待确认器件库操作：{model}"


def _handle_manage_profile_library(
    state: AIConversationState,
    intent,
    store_path: Path,
) -> tuple[str, list[str]]:
    if intent.response == "list_profiles":
        items = list_user_profiles(store_path)
        if items:
            models = "、".join(item["model"] for item in items[:8])
            return f"本地器件库当前共有 {len(items)} 条记录：{models}。已切到器件库后可继续查看、更新、启用/禁用或删除。", []
        return "本地器件库当前为空。已切到器件库后可新增首个型号记录。", []
    if intent.response == "view_profile" and intent.model:
        record = get_user_profile_record(store_path, intent.model)
        return (
            f"{record['model']}：{record['bjt_type']}，Vceo {record['vceo_max_v']}V，"
            f"Ic {float(record['ic_max_a']) * 1000:.0f}mA，Ptot {float(record['p_tot_w']) * 1000:.0f}mW。"
            "已切到器件库，可继续更新、启用/禁用或删除。"
        ), []
    if intent.response == "cancel_pending_library_action":
        state.pending_library_action = None
        return "已取消当前器件库操作。", []
    if intent.response == "confirm_pending_library_action":
        pending = state.pending_library_action or {}
        action_name = str(pending.get("action") or "")
        model = str(pending.get("model") or "")
        if not action_name or not model:
            return "当前没有待确认的器件库操作。", []
        if action_name == "delete_profile":
            delete_user_profile(store_path, model)
            state.pending_library_action = None
            return f"已删除 {model}。", [f"已删除 {model}"]
        if action_name == "disable_profile":
            toggle_user_profile_enabled(store_path, model, enabled=False)
            state.pending_library_action = None
            return f"已禁用 {model}。", [f"已禁用 {model}"]
        if action_name == "enable_profile":
            toggle_user_profile_enabled(store_path, model, enabled=True)
            state.pending_library_action = None
            return f"已启用 {model}。", [f"已启用 {model}"]
        if action_name == "update_profile":
            patch = pending.get("patch") if isinstance(pending.get("patch"), dict) else {}
            result = update_user_profile_record(
                store_path,
                model,
                patch,
                require_confirmation=True,
            )
            state.pending_library_action = None
            return f"已更新 {model}。", [f"已更新 {model}"]
        return "当前没有可执行的器件库操作。", []
    if intent.response in {"delete_profile", "disable_profile", "enable_profile"} and intent.model:
        state.pending_library_action = {"action": intent.response, "model": intent.model}
        label = {
            "delete_profile": "删除",
            "disable_profile": "禁用",
            "enable_profile": "启用",
        }[intent.response]
        return f"即将{label} {intent.model}。如确认，请回复“确认{label}”或直接回复“确认”。", []
    if intent.response == "update_profile" and intent.model and intent.library_patch:
        result = update_user_profile_record(
            store_path,
            intent.model,
            intent.library_patch,
            require_confirmation=False,
        )
        if result["status"] == "confirmation_required":
            state.pending_library_action = {
                "action": "update_profile",
                "model": intent.model,
                "patch": dict(intent.library_patch),
                "critical_changes": list(result["critical_changes"]),
            }
            changes = "；".join(
                f"{item['field']}: {item['old']} -> {item['new']}"
                for item in result["critical_changes"]
            )
            return f"你正在修改安全关键字段：{changes}。如确认，请回复“确认更新”或直接回复“确认”。", []
        state.pending_library_action = None
        return f"已更新 {intent.model}。", [f"已更新 {intent.model}"]
    return "已进入器件库管理。你可以列出、查看、更新、启用/禁用或删除本地型号记录。", []


class ApiHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(200, {"ok": True, "service": "bjt-api"})
            return
        if self.path.startswith("/api/user-profiles"):
            self._handle_user_profiles_list()
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/user-profiles":
            self._handle_user_profiles_create()
            return
        if self.path == "/api/user-profiles/update":
            self._handle_user_profiles_update()
            return
        if self.path == "/api/user-profiles/delete":
            self._handle_user_profiles_delete()
            return
        if self.path == "/api/user-profiles/toggle-enabled":
            self._handle_user_profiles_toggle_enabled()
            return
        if self.path == "/api/connect":
            self._handle_connect()
            return
        if self.path == "/api/emergency-off":
            self._handle_emergency_off()
            return
        if self.path == "/api/execute-plan":
            self._handle_execute_plan()
            return
        if self.path == "/api/preflight-plan":
            self._handle_preflight_plan()
            return
        if self.path == "/api/run-action":
            self._handle_run_action()
            return
        if self.path == "/api/ai-chat":
            self._handle_ai_chat()
            return
        if self.path != "/api/plan":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
            _apply_ai_settings(payload)
            text = str(payload.get("text") or "").strip()
            mode = str(payload.get("mode") or "simulation")
            config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            goal = config.get("test_goal") if config.get("test_goal") in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else None
            depth = config.get("static_depth") if config.get("static_depth") in {"conservative", "standard", "deep"} else None
            scan_mode = str(config.get("scan_mode") or "") or None
            detect_mode = config.get("detect_mode")
            bjt_type = detect_mode if detect_mode in {"NPN", "PNP"} else None
            if not text:
                raise ValueError("text is required")
            plan = plan_from_text(
                text,
                mode=mode,
                cfg=_hw_config(config),
                goal=goal,
                depth=depth,
                scan_mode=scan_mode,
                bjt_type=bjt_type,
            )
            summary, used_ai, provider, usage = summarize_plan_with_ai(plan, text)
            self._send_json(
                200,
                {
                    "ok": True,
                    "received_config": config,
                    "summary": summary,
                    "used_ai_api": used_ai,
                    "llm_provider": provider,
                    "llm_usage": usage,
                    "plan": plan.to_dict(),
                },
            )
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}

    def _user_profile_store_path(self) -> Path:
        return Path(os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))

    def _handle_user_profiles_list(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            query = str(params.get("query", [""])[0] or "")
            enabled_only = str(params.get("enabled_only", ["false"])[0]).lower() in {"1", "true", "yes"}
            model = str(params.get("model", [""])[0] or "").strip()
            if model:
                record = get_user_profile_record(self._user_profile_store_path(), model)
                self._send_json(200, {"ok": True, "record": record})
                return
            items = list_user_profiles(self._user_profile_store_path(), enabled_only=enabled_only)
            if query:
                needle = query.lower()
                items = [item for item in items if needle in str(item.get("model", "")).lower()]
            self._send_json(200, {"ok": True, "items": items})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_user_profiles_create(self) -> None:
        try:
            payload = self._read_payload()
            record = create_user_profile(self._user_profile_store_path(), payload)
            self._send_json(200, {"ok": True, "record": record})
        except DuplicateUserProfileError as exc:
            self._send_json(400, {"ok": False, "error": f"duplicate profile: {exc}"})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_user_profiles_update(self) -> None:
        try:
            payload = self._read_payload()
            model = str(payload.get("model") or "").strip()
            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
            result = update_user_profile_record(
                self._user_profile_store_path(),
                model,
                patch,
                require_confirmation=bool(payload.get("confirm_critical")),
            )
            self._send_json(200, {"ok": True, **result})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_user_profiles_delete(self) -> None:
        try:
            payload = self._read_payload()
            model = str(payload.get("model") or "").strip()
            delete_user_profile(self._user_profile_store_path(), model)
            self._send_json(200, {"ok": True, "deleted": model})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_user_profiles_toggle_enabled(self) -> None:
        try:
            payload = self._read_payload()
            model = str(payload.get("model") or "").strip()
            record = toggle_user_profile_enabled(
                self._user_profile_store_path(),
                model,
                enabled=bool(payload.get("enabled")),
            )
            self._send_json(200, {"ok": True, "record": record})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_connect(self) -> None:
        try:
            payload = self._read_payload()
            mode = str(payload.get("mode") or "hardware")
            if mode not in {"hardware", "simulation"}:
                raise ValueError("unsupported mode")
            driver = build_driver(mode)
            try:
                serial = driver.connect()
                device_info = getattr(driver, "device_info", None)
                info = device_info() if callable(device_info) else {"serial": serial}
            finally:
                close = getattr(driver, "close", None)
                if callable(close):
                    close()
            self._send_json(
                200,
                {
                    "ok": True,
                    "mode": mode,
                    "serial": serial,
                    "device_info": info,
                    "message": "设备探测成功，未保持输出会话。",
                },
            )
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_emergency_off(self) -> None:
        try:
            payload = self._read_payload()
            mode = str(payload.get("mode") or "hardware")
            if mode not in {"hardware", "simulation"}:
                raise ValueError("unsupported mode")
            driver = build_driver(mode)
            try:
                driver.connect()
                disable_all = getattr(driver, "disable_all", None)
                emergency_off = getattr(driver, "emergency_off", None)
                if callable(disable_all):
                    disable_all()
                elif callable(emergency_off):
                    emergency_off()
            finally:
                close = getattr(driver, "close", None)
                if callable(close):
                    close()
            self._send_json(200, {"ok": True, "mode": mode, "message": "已发送安全关断。"})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_execute_plan(self) -> None:
        try:
            payload = self._read_payload()
            mode = str(payload.get("mode") or "hardware")
            if mode not in {"hardware", "simulation"}:
                raise ValueError("unsupported mode")
            allow_hardware = bool(payload.get("allow_hardware"))
            if mode == "hardware" and not allow_hardware:
                raise ValueError("hardware execution requires allow_hardware=true")
            plan = _plan_from_mapping(payload.get("plan"))
            token_valid = _hardware_token_valid_from_payload(mode, payload)
            result = execute_plan(
                plan,
                mode=mode,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            decision = evaluate_execution_request(
                plan=plan,
                mode=mode,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            response = {"ok": True, "execution": result, **_execution_agent_view(result)}
            if result.get("aborted"):
                canonical = _canonical_policy_fields(
                    blocked_reason="runtime_abort",
                    detail=str(result.get("abort_reason") or ""),
                    execution_state="aborted",
                )
                result.update(canonical)
                response.update(canonical)
                response["agent_state"] = "aborted"
            elif result.get("skipped") and decision.status != "allow" and decision.blocked_reason:
                canonical = _canonical_policy_fields(
                    blocked_reason=decision.blocked_reason,
                    detail=str(decision.reasons[0]) if decision.reasons else "",
                    execution_state="blocked",
                )
                result.update(canonical)
                response.update(canonical)
                if decision.status == "deny":
                    response["agent_state"] = "aborted"
            elif result.get("skipped"):
                response.update(_canonical_policy_fields(blocked_reason="", detail="", execution_state="skipped"))
            else:
                response.update(_canonical_policy_fields(blocked_reason="", detail="", execution_state="completed"))
            self._send_json(200, response)
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_preflight_plan(self) -> None:
        try:
            payload = self._read_payload()
            mode = str(payload.get("mode") or "hardware")
            if mode not in {"hardware", "simulation"}:
                raise ValueError("unsupported mode")
            plan = _plan_from_mapping(payload.get("plan"))
            allow_hardware = bool(payload.get("allow_hardware"))
            token_valid = _hardware_token_valid_from_payload(mode, payload)
            result = preflight_plan(
                plan,
                mode=mode,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            decision = evaluate_execution_request(
                plan=plan,
                mode=mode,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            response = {"ok": True, "preflight": result, **_preflight_agent_view(result)}
            execution_state = "not_started" if decision.status == "allow" else "blocked"
            canonical = _canonical_policy_fields(
                blocked_reason=decision.blocked_reason,
                detail=str(decision.reasons[0]) if decision.reasons else "",
                execution_state=execution_state,
            )
            result.update(canonical)
            response.update(canonical)
            self._send_json(200, response)
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_run_action(self) -> None:
        try:
            payload = self._read_payload()
            mode = str(payload.get("mode") or "hardware")
            if mode not in {"hardware", "simulation"}:
                raise ValueError("unsupported mode")
            if mode == "hardware" and not bool(payload.get("allow_hardware")):
                raise ValueError("hardware action requires allow_hardware=true")
            config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            cfg = _hw_config(config)
            action = str(payload.get("action") or "")
            if action == "detect":
                serial, result = run_detect(mode, cfg)
                data = {"serial": serial, "detected_bjt_type": result}
            elif action == "selftest":
                data = run_hardware_selftest(mode, cfg)
            elif action == "scope_check":
                data = run_scope_check(
                    mode,
                    cfg,
                    samples=int(_num(payload.get("samples"), 2048)),
                    frequency_hz=int(_num(payload.get("frequency_hz"), 100000)),
                )
            elif action == "static":
                point = run_npn_static_bringup(
                    mode,
                    cfg,
                    vcc=_num(payload.get("vcc"), 3.0),
                    vbb=_num(payload.get("vbb"), 2.0),
                )
                data = {"measurements": [_point_to_dict(point)]}
            elif action == "vce_sat":
                point = run_npn_static_bringup(
                    mode,
                    cfg,
                    vcc=_num(payload.get("vcc"), 2.0),
                    vbb=_num(payload.get("vbb"), 2.2),
                )
                vce_sat, ic_at_sat = estimate_vce_sat(point, ic_floor_a=0.0)
                data = {
                    "measurements": [_point_to_dict(point)],
                    "vce_sat": vce_sat,
                    "ic_at_sat": ic_at_sat,
                }
            elif action == "scan_curves":
                points = run_scan_curves(mode, cfg, str(payload.get("scan_mode") or "software"))
                data = {"measurements": _points_to_dict(points), "point_count": len(points)}
            elif action == "full_suite":
                report = run_full_suite(
                    mode=mode,
                    dut_label=str(payload.get("dut_label") or "WEB-DUT"),
                    output_dir=Path("./analysis_out/web"),
                    cfg=cfg,
                    scan_mode=str(payload.get("scan_mode") or "software"),
                )
                measurements = []
                for _, curve_points in sorted(report.output_curves.items(), key=lambda item: item[0]):
                    measurements.extend(curve_points)
                data = {
                    "serial": report.serial,
                    "detected_bjt_type": report.bjt_type,
                    "measurements": _points_to_dict(measurements),
                    "latest_measurement": _point_to_dict(report.reference_point) if report.reference_point is not None else None,
                    "beta_median": report.beta_median,
                    "vce_sat": report.vce_sat,
                    "ic_at_sat": report.Ic_at_sat,
                    "output_dir": "analysis_out/web",
                }
            else:
                raise ValueError("unsupported action")
            self._send_json(200, {"ok": True, "mode": mode, "action": action, "result": data})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _handle_ai_chat(self) -> None:
        try:
            payload = self._read_payload()
            _apply_ai_settings(payload)
            text = str(payload.get("text") or "").strip()
            if not text:
                raise ValueError("text is required")
            mode = str(payload.get("mode") or "hardware")
            context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            state = _state_from_context(context)
            intent, used_ai, provider, usage = interpret_user_message(text, state, default_mode=mode)
            plan = None
            completed_actions: list[str] = []
            agent_state_override = ""
            if intent.action in {"create_plan", "modify_plan"}:
                if state.pending_profile_model and not state.pending_profile_fields:
                    response = answer_from_context(intent, state)
                elif intent.action == "modify_plan" and _looks_like_autonomous_refine(text) and state.current_plan and state.current_execution:
                    work = refine_plan_after_execution(
                        state.current_plan,
                        state.current_execution,
                        user_text=text,
                        cfg=_hw_config(config),
                    )
                    plan = work.plan
                    state.current_plan = plan
                    response = work.response
                    completed_actions = work.completed_actions
                    state.record_agent_activity(
                        {
                            "type": "plan_refined",
                            "summary": "自主优化当前测试计划",
                            "completed_actions": completed_actions,
                            "plan": plan.to_dict(),
                        }
                    )
                    agent_state_override = "plan_refined"
                    used_ai = used_ai or work.used_ai_api
                    provider = work.llm_provider if work.used_ai_api else provider
                    usage = work.llm_usage or usage
                else:
                    plan = apply_intent_to_plan(intent, state, cfg=_hw_config(config))
                    state.current_plan = plan
                    summary, summary_used_ai, summary_provider, summary_usage = summarize_plan_with_ai(plan, text)
                    used_ai = used_ai or summary_used_ai
                    provider = summary_provider if summary_used_ai else provider
                    usage = summary_usage or usage
                    response = summary
            elif intent.action in {"execute_simulation", "execute_hardware"}:
                response = "我已理解为执行请求。请使用左侧或测试点模块的执行按钮触发；硬件执行仍需要本地确认和 SafetyGuard。"
            elif intent.action == "manage_profile_library":
                response, completed_actions = _handle_manage_profile_library(
                    state,
                    intent,
                    self._user_profile_store_path(),
                )
            elif any(word in text for word in ("诊断", "异常", "接反", "开路", "短路", "为什么", "不对")):
                response = _diagnose_locally(text, context, state)
            else:
                response = answer_from_context(intent, state)
            agent_view = _chat_agent_view(intent.action, state, plan)
            if agent_state_override:
                agent_view["agent_state"] = agent_state_override
                agent_view["completed_actions"] = completed_actions
                agent_view["agent_steps"].append(
                    _agent_step("done", "自主优化计划", "；".join(completed_actions))
                )
            else:
                agent_view["completed_actions"] = completed_actions
            agent_view["next_action_items"] = action_items_from_labels(agent_view.get("next_actions", []))
            agent_view["completed_action_items"] = action_items_from_labels(completed_actions)
            agent_view["safety_action_items"] = safety_action_items_from_labels(agent_view.get("next_actions", []))
            self._send_json(
                200,
                {
                    "ok": True,
                    "response": response,
                    "intent": intent.action,
                    "used_ai_api": used_ai,
                    "llm_provider": provider,
                    "llm_usage": usage,
                    "plan": plan.to_dict() if plan else None,
                    "conversation_state": _context_from_state(state),
                    **agent_view,
                },
            )
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return None


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), ApiHandler)
    print("BJT API listening on http://127.0.0.1:8765")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
