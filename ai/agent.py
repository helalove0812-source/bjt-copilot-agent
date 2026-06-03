from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets

from core.types import HwConfig

from ai.action_taxonomy import action_items_from_labels, safety_action_items_from_policy
from ai.assistant import build_execution_stats, summarize_execution_with_ai, summarize_plan_with_ai
from ai.autonomy import refine_plan_after_execution
from ai.conversation import (
    AIConversationState,
    AIIntent,
    CandidateProfileState,
    answer_from_context,
    apply_intent_to_plan,
    interpret_user_message,
)
from ai.rules import diagnose_context, diagnose_tags
from ai.safety import evaluate_execution_request
from ai.state_taxonomy import blocked_reason_item, canonical_agent_state, pick_blocked_reason, pick_execution_state
from ai.test_planner import TestPlan
from ai.tools import execute_plan
from ai.transistor_db import TransistorProfile
from ai.user_profile_store import (
    DuplicateUserProfileError,
    InvalidUserProfileStoreError,
    delete_user_profile,
    get_user_profile_record,
    list_user_profiles,
    save_user_profile,
    toggle_user_profile_enabled,
    update_user_profile,
    update_user_profile_record,
)


@dataclass(frozen=True)
class AgentTurnResult:
    response: str
    intent: AIIntent
    plan: TestPlan | None = None
    execution: dict | None = None
    execution_summary: str = ""
    used_ai_api: bool = False
    llm_provider: str = "local"
    llm_usage: dict | None = None
    hardware_confirmation_required: bool = False
    hardware_confirmation_token: str = ""
    agent_state: str = "idle"
    execution_state: str = "not_started"
    blocked_reason: str = ""
    blocked_reason_item: dict = field(default_factory=dict)
    required_inputs: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    next_action_items: list[dict] = field(default_factory=list)
    diagnosis_tags: list[str] = field(default_factory=list)
    completed_actions: list[str] = field(default_factory=list)
    completed_action_items: list[dict] = field(default_factory=list)
    safety_action_items: list[dict] = field(default_factory=list)
    agent_steps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "response": self.response,
            "intent": self.intent.action,
            "plan": self.plan.to_dict() if self.plan else None,
            "execution": self.execution,
            "execution_summary": self.execution_summary,
            "used_ai_api": self.used_ai_api,
            "llm_provider": self.llm_provider,
            "llm_usage": self.llm_usage or {},
            "hardware_confirmation_required": self.hardware_confirmation_required,
            "hardware_confirmation_token": self.hardware_confirmation_token,
            "agent_state": self.agent_state,
            "execution_state": self.execution_state,
            "blocked_reason": self.blocked_reason,
            "blocked_reason_item": self.blocked_reason_item,
            "required_inputs": self.required_inputs,
            "next_actions": self.next_actions,
            "next_action_items": self.next_action_items,
            "diagnosis_tags": self.diagnosis_tags,
            "completed_actions": self.completed_actions,
            "completed_action_items": self.completed_action_items,
            "safety_action_items": self.safety_action_items,
            "agent_steps": self.agent_steps,
        }


class TestAgent:
    """Stateful BJT test agent that plans, executes simulation, and explains results."""

    __test__ = False

    def __init__(self, state: AIConversationState | None = None, *, cfg: HwConfig | None = None) -> None:
        self.state = state or AIConversationState()
        self.cfg = cfg
        self._hardware_confirmation: dict | None = None

    def run_turn(
        self,
        text: str,
        *,
        default_mode: str = "simulation",
        allow_hardware: bool = False,
        hardware_confirmation_token: str = "",
        output_dir: Path | None = None,
        logs: list[str] | None = None,
    ) -> AgentTurnResult:
        intent, used_ai, provider, usage = interpret_user_message(text, self.state, default_mode=default_mode)
        plan: TestPlan | None = None
        execution: dict | None = None
        execution_summary = ""
        hardware_confirmation_required = False
        issued_hardware_token = ""
        agent_state = "idle"
        required_inputs: list[str] = []
        next_actions: list[str] = []
        diagnosis_tags_out: list[str] = []
        completed_actions: list[str] = []
        safety_policy_tags: list[str] = []
        safety_policy_reasons: list[str] = []
        agent_steps: list[dict] = [_agent_step("done", "解析意图", intent.action)]

        if intent.action in {"create_plan", "modify_plan"}:
            missing_profile_inputs = _missing_profile_inputs(self.state.pending_profile_fields)
            if self.state.pending_profile_model and missing_profile_inputs:
                response = answer_from_context(intent, self.state)
                agent_state = "awaiting_profile_fields"
                required_inputs = missing_profile_inputs
                next_actions = [
                    "补充未知型号的管型、耐压、电流和功耗规格",
                    "改用数据库中已有型号重新生成计划",
                ]
                agent_steps.append(
                    _agent_step(
                        "waiting",
                        "补全未知型号规格",
                        "还需要：" + "、".join(required_inputs),
                    )
                )
            elif intent.action == "modify_plan" and _looks_like_autonomous_refine(text) and self.state.current_plan and self.state.current_execution:
                work = refine_plan_after_execution(
                    self.state.current_plan,
                    self.state.current_execution,
                    user_text=text,
                    cfg=self.cfg,
                )
                plan = work.plan
                response = work.response
                used_ai = used_ai or work.used_ai_api
                provider = _merge_provider(provider, work.llm_provider if work.used_ai_api else "")
                usage = _merge_usage(usage, work.llm_usage)
                self.state.current_plan = plan
                agent_state = "plan_refined"
                completed_actions = work.completed_actions
                self.state.record_agent_activity(
                    {
                        "type": "plan_refined",
                        "summary": "自主优化当前测试计划",
                        "completed_actions": completed_actions,
                        "plan": plan.to_dict(),
                    }
                )
                next_actions = _plan_next_actions(plan)
                agent_steps.append(_agent_step("done", "自主优化计划", "；".join(completed_actions)))
            else:
                plan = apply_intent_to_plan(intent, self.state, cfg=self.cfg)
                _sync_candidate_profile_from_plan(self.state, plan)
                response, summary_used_ai, summary_provider, summary_usage = summarize_plan_with_ai(plan, text)
                if plan.bjt_type == "PNP":
                    response = (
                        "已识别为 PNP 型号 {0}。当前自动执行路径只开放 NPN，因为 PNP 的偏置和接线方向不同。"
                        "已为你生成保守筛查计划；继续前请先核对 datasheet、E/B/C 引脚和夹具方向，并从低压人工确认开始。"
                    ).format(plan.model)
                used_ai = used_ai or summary_used_ai
                provider = _merge_provider(provider, summary_provider if summary_used_ai else "")
                usage = _merge_usage(usage, summary_usage)
                self.state.current_plan = plan
                agent_state = "plan_ready"
                next_actions = _plan_next_actions(plan)
                agent_steps.append(_agent_step("done", "生成测试计划", "{0} / {1}".format(plan.model, plan.goal)))

        elif intent.action == "execute_simulation":
            plan = self.state.current_plan
            if plan is None:
                response = "当前没有可执行计划。请先告诉我要测试的型号和目标。"
                agent_state = "idle"
                required_inputs = ["晶体管型号", "测试目标"]
                next_actions = ["生成测试计划"]
                agent_steps.append(_agent_step("waiting", "等待测试需求", "需要型号和目标"))
            else:
                execution = execute_plan(plan, mode="simulation", output_dir=output_dir, allow_hardware=False)
                self.state.record_execution(execution)
                if execution.get("skipped"):
                    response = "执行已跳过：{0}".format(execution.get("reason", "未知原因"))
                    execution_summary = response
                    agent_state = "execution_skipped"
                else:
                    response, exec_used_ai, exec_provider, exec_usage = summarize_execution_with_ai(execution)
                    execution_summary = response
                    used_ai = used_ai or exec_used_ai
                    provider = _merge_provider(provider, exec_provider if exec_used_ai else "")
                    usage = _merge_usage(usage, exec_usage)
                    agent_state = "execution_aborted" if execution.get("aborted") else "execution_complete"
                    if not execution.get("aborted"):
                        response = _append_profile_save_prompt(response, plan, self.state)
                        execution_summary = response
                self.state.current_summary = execution_summary
                diagnosis_tags_out = diagnose_tags(
                    str(execution.get("abort_reason") or execution_summary or response),
                    measurements=execution.get("measurements") or [],
                )
                next_actions = _execution_next_actions(execution, plan)
                agent_steps.append(_agent_step("done", "执行仿真", agent_state))

        elif intent.action == "execute_hardware":
            plan = self.state.current_plan
            if plan is None:
                response = "当前没有可执行计划。请先生成硬件测试计划。"
                agent_state = "idle"
                required_inputs = ["硬件测试计划"]
                next_actions = ["生成测试计划"]
                agent_steps.append(_agent_step("waiting", "等待硬件计划", "没有可执行计划"))
            else:
                token_valid = self._hardware_confirmation_valid(plan, hardware_confirmation_token)
                decision = evaluate_execution_request(
                    plan=plan,
                    mode="hardware",
                    allow_hardware=allow_hardware,
                    token_valid=token_valid,
                )
                if decision.status == "require_confirm":
                    safety_policy_tags = list(decision.tags)
                    safety_policy_reasons = list(decision.reasons)
                    hardware_confirmation_required = True
                    issued_hardware_token = self._issue_hardware_confirmation(plan)
                    response = "硬件执行需要显式确认；我已生成一次性确认令牌，未打开真实输出。"
                    agent_state = "awaiting_hardware_confirmation"
                    required_inputs = ["硬件确认令牌"]
                    next_actions = ["使用一次性令牌继续硬件执行", "取消或修改当前计划"]
                    agent_steps.append(_agent_step("waiting", "等待硬件确认", "未打开真实输出"))
                elif decision.status == "deny":
                    safety_policy_tags = list(decision.tags)
                    safety_policy_reasons = list(decision.reasons)
                    if "pnp_auto_execution_blocked" in decision.tags:
                        response = "当前自动执行路径只开放 NPN；PNP/未知型号请先生成计划并走专用流程。"
                    elif "blocked_hardware_execution" in decision.tags:
                        response = "硬件执行还需要调用方显式允许；我已保留当前计划，未打开真实输出。"
                    else:
                        response = decision.reasons[0] if decision.reasons else "执行已跳过：策略阻止执行。"
                    agent_state = "execution_blocked"
                    next_actions = ["查看阻止原因", "修改计划或切换为仿真模式"]
                    agent_steps.append(_agent_step("blocked", "硬件策略检查", response))
                else:
                    execution = execute_plan(
                        plan,
                        mode="hardware",
                        output_dir=output_dir,
                        allow_hardware=True,
                        token_valid=True,
                    )
                    self._hardware_confirmation = None
                    self.state.record_execution(execution)
                    if execution.get("skipped"):
                        response = "执行已跳过：{0}".format(execution.get("reason", "未知原因"))
                        execution_summary = response
                        agent_state = "execution_skipped"
                    else:
                        response, exec_used_ai, exec_provider, exec_usage = summarize_execution_with_ai(execution)
                        execution_summary = response
                        used_ai = used_ai or exec_used_ai
                        provider = _merge_provider(provider, exec_provider if exec_used_ai else "")
                        usage = _merge_usage(usage, exec_usage)
                        agent_state = "execution_aborted" if execution.get("aborted") else "execution_complete"
                    if not execution.get("aborted"):
                        response = _append_profile_save_prompt(response, plan, self.state)
                        execution_summary = response
                    self.state.current_summary = execution_summary
                    diagnosis_tags_out = diagnose_tags(
                        str(execution.get("abort_reason") or execution_summary or response),
                        measurements=execution.get("measurements") or [],
                    )
                    next_actions = _execution_next_actions(execution, plan)
                    agent_steps.append(_agent_step("done", "执行硬件测试", agent_state))

        elif intent.action in {"save_profile", "update_profile"}:
            response, agent_state = _persist_candidate_profile(intent.action, self.state)
            if agent_state == "profile_saved":
                completed_actions = ["已写入用户型号库"] if intent.action == "save_profile" else ["已更新用户型号库"]
                next_actions = ["继续用该型号生成计划", "执行仿真", "解释结果"]
                agent_steps.append(_agent_step("done", "保存候选型号", completed_actions[0]))
            else:
                next_actions = ["继续补全候选规格", "检查本地型号库配置"]
                agent_steps.append(_agent_step("blocked", "保存候选型号", response))

        elif intent.action == "manage_profile_library":
            response, agent_state, completed_actions = _handle_profile_library_command(intent, text, self.state)
            if agent_state == "awaiting_profile_library_confirmation":
                required_inputs = ["明确确认当前器件库操作"]
                next_actions = ["回复确认继续执行", "回复取消放弃当前器件库操作"]
                agent_steps.append(_agent_step("waiting", "等待器件库确认", response))
            else:
                next_actions = ["打开器件库面板查看详情", "新增或更新器件资料", "启用/禁用或删除现有记录"]
                agent_steps.append(_agent_step("ready", "切换器件库", response))

        elif intent.action == "explain_result":
            current_measurements = (self.state.current_execution or {}).get("measurements") or []
            if _looks_like_diagnosis(text) or logs:
                response = diagnose_context(
                    text,
                    logs=logs or [],
                    measurements=current_measurements,
                )
                diagnosis_tags_out = diagnose_tags(text, logs=logs or [], measurements=current_measurements)
            else:
                response = answer_from_context(intent, self.state)
                diagnosis_tags_out = diagnose_tags(text, measurements=current_measurements)
            agent_state = "diagnosing"
            next_actions = _diagnosis_next_actions(self.state.current_plan)
            agent_steps.append(_agent_step("done", "分析上下文", "诊断/解释结果"))

        elif _looks_like_diagnosis(text):
            current_measurements = (self.state.current_execution or {}).get("measurements") or []
            response = diagnose_context(
                text,
                logs=logs or [],
                measurements=current_measurements,
            )
            diagnosis_tags_out = diagnose_tags(text, logs=logs or [], measurements=current_measurements)
            agent_state = "diagnosing"
            next_actions = _diagnosis_next_actions(self.state.current_plan)
            agent_steps.append(_agent_step("done", "分析上下文", "诊断/解释结果"))

        else:
            response = answer_from_context(intent, self.state)
            if self.state.pending_profile_model:
                agent_state = "awaiting_profile_fields"
                required_inputs = _missing_profile_inputs(self.state.pending_profile_fields)
                next_actions = ["继续补充未知型号规格", "改用数据库中已有型号重新生成计划"]
                detail = "还需要：" + "、".join(required_inputs) if required_inputs else "规格已完整，可继续生成计划"
                agent_steps.append(_agent_step("waiting", "补全未知型号规格", detail))
            elif self.state.current_plan:
                agent_state = "plan_ready"
                next_actions = _plan_next_actions(self.state.current_plan)
                agent_steps.append(_agent_step("ready", "复用当前计划", self.state.current_plan.model))
            else:
                agent_state = "idle"
                required_inputs = ["晶体管型号", "测试目标"]
                next_actions = ["生成测试计划"]
                agent_steps.append(_agent_step("waiting", "等待测试需求", "需要型号和目标"))

        self.state.add("user", text)
        self.state.add("assistant", response)
        execution_context = execution or self.state.current_execution
        pending_profile_model = self.state.pending_profile_model if self.state.pending_profile_model else None
        blocked_reason = pick_blocked_reason(
            pending_profile_model=pending_profile_model,
            execution=execution_context,
        )
        execution_state = pick_execution_state(
            execution=execution_context,
            raw_agent_state=agent_state,
            blocked_reason=blocked_reason,
        )
        agent_state = canonical_agent_state(
            raw_agent_state=agent_state,
            execution_state=execution_state,
            pending_profile_model=pending_profile_model,
        )
        safety_action_items = safety_action_items_from_policy(safety_policy_tags, safety_policy_reasons)
        return AgentTurnResult(
            response=response,
            intent=intent,
            plan=plan,
            execution=execution,
            execution_summary=execution_summary,
            used_ai_api=used_ai,
            llm_provider=provider,
            llm_usage=usage,
            hardware_confirmation_required=hardware_confirmation_required,
            hardware_confirmation_token=issued_hardware_token,
            agent_state=agent_state,
            execution_state=execution_state,
            blocked_reason=blocked_reason,
            blocked_reason_item=blocked_reason_item(
                blocked_reason,
                detail=str((execution_context or {}).get("abort_reason") or ""),
            ),
            required_inputs=required_inputs,
            next_actions=next_actions,
            next_action_items=_action_items_from_labels(next_actions),
            diagnosis_tags=diagnosis_tags_out,
            completed_actions=completed_actions,
            completed_action_items=_action_items_from_labels(completed_actions),
            safety_action_items=safety_action_items,
            agent_steps=agent_steps,
        )

    def _issue_hardware_confirmation(self, plan: TestPlan) -> str:
        token = secrets.token_urlsafe(18)
        self._hardware_confirmation = {
            "token": token,
            "plan_hash": _plan_hash(plan),
            "expires_at": datetime.now() + timedelta(minutes=5),
        }
        return token

    def _hardware_confirmation_valid(self, plan: TestPlan, token: str) -> bool:
        if not token or not self._hardware_confirmation:
            return False
        if token != self._hardware_confirmation.get("token"):
            return False
        if _plan_hash(plan) != self._hardware_confirmation.get("plan_hash"):
            return False
        expires_at = self._hardware_confirmation.get("expires_at")
        return isinstance(expires_at, datetime) and datetime.now() <= expires_at


def _looks_like_diagnosis(text: str) -> bool:
    return any(word in text for word in ("诊断", "异常", "接反", "开路", "短路", "不导通", "断了", "功耗", "全是 0", "全是0", "对调", "为什么", "不对"))


def _looks_like_autonomous_refine(text: str) -> bool:
    return any(word in text for word in ("优化", "自动调整", "自己看着办", "下一步", "你来定", "帮我调整", "改进计划"))


def _plan_hash(plan: TestPlan) -> str:
    payload = json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _agent_step(status: str, label: str, detail: str = "") -> dict:
    return {"status": status, "label": label, "detail": detail}


def _action_items_from_labels(labels: list[str]) -> list[dict]:
    return action_items_from_labels(labels)


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
    if any("分阶段策略" in note for note in plan.safety_notes):
        actions = ["先运行保守仿真", "结果正常后加深计划", "解释或调整当前计划"]
    if plan.bjt_type == "NPN":
        actions.append("请求硬件执行确认")
    else:
        actions.append("核对 datasheet、引脚和夹具方向后再走专用流程")
    return actions


def _execution_next_actions(execution: dict | None, plan: TestPlan | None = None) -> list[str]:
    if not execution:
        return ["生成测试计划"]
    if execution.get("aborted"):
        return ["查看中止原因", "降低限值或检查接线后重试", "解释已保留的测量点"]
    if execution.get("skipped"):
        return ["查看跳过原因", "修改计划或切换为仿真模式"]
    stats = build_execution_stats(execution)
    region_counts = stats.get("region_counts") or {}
    active = int(region_counts.get("active", 0))
    saturation = int(region_counts.get("saturation", 0))
    cutoff = int(region_counts.get("cutoff", 0))
    point_count = int(stats.get("point_count") or 0)
    if point_count == 0:
        return ["检查为什么没有测量点", "重新运行保守仿真", "修改计划或切换模式"]
    if saturation >= max(2, active):
        return ["降低 Vbb 上沿后复测", "检查 Vce 工作窗口", "解释结果"]
    if cutoff >= max(2, active):
        return ["提高 Vbb 起点或检查基极支路", "重新运行保守仿真", "解释结果"]
    if active >= 2:
        actions = ["解释结果"]
        if plan and plan.depth != "deep":
            actions.insert(0, "结果稳定后加深计划")
        actions.extend(["调整计划后重测", "导出或查看执行数据"])
        return actions
    return ["解释结果", "调整计划后重测", "导出或查看执行数据"]


def _diagnosis_next_actions(plan: TestPlan | None) -> list[str]:
    actions = ["根据诊断修改计划", "重新运行仿真验证"]
    if plan and any("分阶段策略" in note for note in plan.safety_notes):
        actions.insert(0, "结果正常后加深计划")
    if plan and plan.bjt_type == "NPN":
        actions.append("确认安全后再请求硬件执行")
    return actions


def _merge_provider(primary: str, secondary: str) -> str:
    values = [value for value in (primary, secondary) if value and value != "local"]
    if not values:
        return primary or secondary or "local"
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def _merge_usage(primary: dict | None, secondary: dict | None) -> dict:
    merged: dict = dict(primary or {})
    for key, value in (secondary or {}).items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] += value
        elif key not in merged:
            merged[key] = value
    return merged


def _sync_candidate_profile_from_plan(state: AIConversationState, plan: TestPlan) -> None:
    profile = plan.profile or {}
    if profile.get("confidence") != "user_supplied":
        return
    state.candidate_profile = CandidateProfileState(
        model=plan.model,
        fields={
            "bjt_type": str(profile["bjt_type"]),
            "vceo_max_v": float(profile["vceo_max_v"]),
            "ic_max_a": float(profile["ic_max_a"]),
            "p_tot_w": float(profile["p_tot_w"]),
        },
    )


def _append_profile_save_prompt(response: str, plan: TestPlan | None, state: AIConversationState) -> str:
    if not plan or plan.profile.get("confidence") != "user_supplied" or state.candidate_profile is None:
        return response
    prompt = (
        "{0} 当前使用的是本次会话中的候选规格，尚未保存到本地型号库。"
        "如果这组参数确认可用，你可以回复“保存这个型号”或“更新这个型号”。"
    ).format(plan.model)
    if prompt in response:
        return response
    return response + "\n\n" + prompt


def _persist_candidate_profile(action: str, state: AIConversationState) -> tuple[str, str]:
    candidate = state.candidate_profile
    if candidate is None:
        return "当前没有可保存的候选型号资料。", "idle"
    if _missing_profile_inputs(candidate.fields):
        return _missing_profile_response(candidate), "awaiting_profile_fields"

    profile = TransistorProfile(
        model=candidate.model,
        bjt_type=str(candidate.fields["bjt_type"]).upper(),
        description="用户确认沉淀的型号参数",
        vceo_max_v=float(candidate.fields["vceo_max_v"]),
        ic_max_a=float(candidate.fields["ic_max_a"]),
        p_tot_w=float(candidate.fields["p_tot_w"]),
        hfe_typical=(0, 0),
        confidence="user_confirmed",
    )
    store_path = Path(os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))
    try:
        if action == "update_profile":
            update_user_profile(store_path, profile)
            return "已更新 {0} 的本地型号库记录。".format(profile.model), "profile_saved"
        save_user_profile(store_path, profile)
        return "已将 {0} 写入本地型号库。".format(profile.model), "profile_saved"
    except DuplicateUserProfileError:
        return "本地型号库中已存在 {0}；如需覆盖，请明确说“更新这个型号”。".format(profile.model), "awaiting_profile_fields"
    except InvalidUserProfileStoreError:
        return "本地型号库存储失败，请先修复配置文件。", "awaiting_profile_fields"


def _handle_profile_library_command(intent: AIIntent, text: str, state: AIConversationState) -> tuple[str, str, list[str]]:
    del text
    store_path = Path(os.getenv("BJT_USER_PROFILE_STORE", "config/user_transistor_profiles.json"))
    if intent.response == "list_profiles":
        items = list_user_profiles(store_path)
        if not items:
            return "本地器件库当前为空。你可以先新增一个器件记录。", "profile_library_ready", []
        models = "、".join(item["model"] for item in items[:8])
        return f"本地器件库当前共有 {len(items)} 条记录：{models}。", "profile_library_ready", []
    if intent.response == "view_profile" and intent.model:
        record = get_user_profile_record(store_path, intent.model)
        return (
            f"{record['model']}：{record['bjt_type']}，Vceo {record['vceo_max_v']}V，"
            f"Ic {float(record['ic_max_a']) * 1000:.0f}mA，Ptot {float(record['p_tot_w']) * 1000:.0f}mW。"
        ), "profile_library_ready", []
    if intent.response == "cancel_pending_library_action":
        state.pending_library_action = None
        return "已取消当前器件库操作。", "profile_library_ready", []
    if intent.response == "confirm_pending_library_action":
        pending = state.pending_library_action or {}
        action_name = str(pending.get("action") or "")
        model = str(pending.get("model") or "")
        if not action_name or not model:
            return "当前没有待确认的器件库操作。", "profile_library_ready", []
        if action_name == "delete_profile":
            delete_user_profile(store_path, model)
            state.pending_library_action = None
            return f"已删除 {model}。", "profile_library_ready", [f"已删除 {model}"]
        if action_name == "disable_profile":
            toggle_user_profile_enabled(store_path, model, enabled=False)
            state.pending_library_action = None
            return f"已禁用 {model}。", "profile_library_ready", [f"已禁用 {model}"]
        if action_name == "enable_profile":
            toggle_user_profile_enabled(store_path, model, enabled=True)
            state.pending_library_action = None
            return f"已启用 {model}。", "profile_library_ready", [f"已启用 {model}"]
        if action_name == "update_profile":
            patch = pending.get("patch") if isinstance(pending.get("patch"), dict) else {}
            update_user_profile_record(store_path, model, patch, require_confirmation=True)
            state.pending_library_action = None
            return f"已更新 {model}。", "profile_library_ready", [f"已更新 {model}"]
        return "当前没有可执行的器件库操作。", "profile_library_ready", []
    if intent.response in {"delete_profile", "disable_profile", "enable_profile"} and intent.model:
        state.pending_library_action = {"action": intent.response, "model": intent.model}
        label = {
            "delete_profile": "删除",
            "disable_profile": "禁用",
            "enable_profile": "启用",
        }[intent.response]
        return f"即将{label} {intent.model}。如确认，请回复“确认{label}”或直接回复“确认”。", "awaiting_profile_library_confirmation", []
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
            return (
                f"你正在修改安全关键字段：{changes}。如确认，请回复“确认更新”或直接回复“确认”。",
                "awaiting_profile_library_confirmation",
                [],
            )
        state.pending_library_action = None
        return f"已更新 {intent.model}。", "profile_library_ready", [f"已更新 {intent.model}"]
    return "已进入器件库管理。你可以列出、查看、更新、启用/禁用或删除本地型号记录。", "profile_library_ready", []


def _missing_profile_response(candidate) -> str:
    return "候选型号 {0} 规格还不完整，还需要：{1}。".format(
        candidate.model,
        "、".join(_missing_profile_inputs(candidate.fields)),
    )
