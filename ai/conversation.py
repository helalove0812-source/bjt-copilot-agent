from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import os
import re
from typing import Any, Literal

from core.types import HwConfig

from ai.assistant import local_execution_summary, build_execution_stats
from ai.llm_client import LLMUnavailable, chat_text
from ai.rules import extract_profile_fields, infer_rule_decision
from ai.test_planner import TestDepth, TestGoal, TestPlan, build_test_plan, extract_model_guess, infer_depth, infer_goal
from ai.transistor_db import build_profile_from_fields, lookup_transistor


IntentAction = Literal[
    "create_plan",
    "modify_plan",
    "execute_simulation",
    "execute_hardware",
    "explain_result",
    "manage_profile_library",
    "save_profile",
    "update_profile",
    "answer",
]


@dataclass
class ConversationMessage:
    role: str
    content: str


@dataclass
class CandidateProfileState:
    model: str
    fields: dict[str, float | str] = field(default_factory=dict)


@dataclass
class AIConversationState:
    messages: list[ConversationMessage] = field(default_factory=list)
    current_plan: TestPlan | None = None
    current_execution: dict | None = None
    execution_history: list[dict] = field(default_factory=list)
    agent_activity_history: list[dict] = field(default_factory=list)
    current_summary: str = ""
    candidate_profile: CandidateProfileState | None = None
    pending_profile_model: str | None = None
    pending_profile_fields: dict[str, float | str] = field(default_factory=dict)
    pending_library_action: dict[str, object] | None = None

    def __post_init__(self) -> None:
        self.sync_candidate_profile()

    def add(self, role: str, content: str) -> None:
        self.messages.append(ConversationMessage(role=role, content=content))
        self._trim_messages()

    def _trim_messages(self, limit: int = 12) -> None:
        if len(self.messages) <= limit:
            return
        overflow = len(self.messages) - limit
        if overflow % 2:
            overflow += 1
        self.messages = self.messages[min(overflow, len(self.messages)) :]
        while self.messages and self.messages[0].role == "assistant":
            self.messages.pop(0)

    def record_execution(self, execution: dict, *, limit: int = 5) -> None:
        self.current_execution = execution
        self.execution_history.append(execution)
        if len(self.execution_history) > limit:
            self.execution_history = self.execution_history[-limit:]

    def record_agent_activity(self, activity: dict, *, limit: int = 10) -> None:
        self.agent_activity_history.append(activity)
        if len(self.agent_activity_history) > limit:
            self.agent_activity_history = self.agent_activity_history[-limit:]

    def sync_candidate_profile(self) -> CandidateProfileState | None:
        if self.candidate_profile is None:
            if self.pending_profile_model:
                self.candidate_profile = CandidateProfileState(
                    model=self.pending_profile_model,
                    fields=dict(self.pending_profile_fields),
                )
        else:
            self.pending_profile_model = self.candidate_profile.model
            self.pending_profile_fields = self.candidate_profile.fields
        return self.candidate_profile

    def set_candidate_profile(self, model: str, fields: dict[str, float | str] | None = None) -> CandidateProfileState:
        self.candidate_profile = CandidateProfileState(model=model, fields=dict(fields or {}))
        self.pending_profile_model = self.candidate_profile.model
        self.pending_profile_fields = self.candidate_profile.fields
        return self.candidate_profile

    def clear_candidate_profile(self) -> None:
        self.candidate_profile = None
        self.pending_profile_model = None
        self.pending_profile_fields = {}

    def to_context(self) -> dict:
        candidate_profile = self.sync_candidate_profile()
        return {
            "messages": [asdict(message) for message in self.messages],
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "current_execution": self.current_execution,
            "execution_history": self.execution_history,
            "agent_activity_history": self.agent_activity_history,
            "current_summary": self.current_summary,
            "candidate_profile": asdict(candidate_profile) if candidate_profile else None,
            "pending_profile_model": self.pending_profile_model,
            "pending_profile_fields": self.pending_profile_fields,
            "pending_library_action": dict(self.pending_library_action) if self.pending_library_action else None,
        }


@dataclass(frozen=True)
class AIIntent:
    action: IntentAction
    model: str | None = None
    goal: TestGoal | None = None
    depth: TestDepth | None = None
    mode: str | None = None
    ic_limit_a: float | None = None
    power_limit_w: float | None = None
    vcc_max: float | None = None
    vbb_points: int | None = None
    library_patch: dict[str, object] | None = None
    response: str = ""


def interpret_user_message(
    text: str,
    state: AIConversationState,
    *,
    default_mode: str = "simulation",
) -> tuple[AIIntent, bool, str, dict]:
    if os.getenv("BJT_AI_MODE", "local") == "local":
        return infer_intent_locally(text, state, default_mode=default_mode), False, "local", {}

    prompt = json.dumps(
        {
            "user_message": text,
            "default_mode": default_mode,
            "context": state.to_context(),
            "allowed_actions": [
                "create_plan",
                "modify_plan",
                "execute_simulation",
                "execute_hardware",
                "explain_result",
                "manage_profile_library",
                "save_profile",
                "update_profile",
                "answer",
            ],
            "schema": {
                "action": "one allowed action",
                "model": "optional transistor model like S8050",
                "goal": "optional: auto/beta/vce_sat/curves/screening/full",
                "depth": "optional: conservative/standard/deep",
                "mode": "optional: simulation/hardware",
                "ic_limit_a": "optional numeric current limit in ampere",
                "power_limit_w": "optional numeric power limit in watt",
                "vcc_max": "optional numeric maximum Vcc in volt",
                "vbb_points": "optional integer number of Vbb static points",
                "library_patch": "optional dict for profile library updates",
                "response": "short Chinese explanation of what you decided",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    instructions = """你是 BJT 测试系统的上下文意图解析器。
你必须根据用户消息和历史上下文判断下一步动作，并只输出 JSON 对象，不要输出 Markdown。
如果用户在说“保守一点、Ic 不超过 10mA、Vcc 最高 3V、多测几个点、解释刚才结果、重新执行”等，要引用当前计划或当前执行结果。
不要发明硬件能力，不要要求超过安全限制。"""
    try:
        result = chat_text(system_text=instructions, user_text=prompt)
        data = _parse_json_object(result.text)
        return _intent_from_mapping(data, text, state, default_mode), True, "{0}:{1}".format(result.provider, result.model), result.usage
    except (LLMUnavailable, ValueError, TypeError):
        return infer_intent_locally(text, state, default_mode=default_mode), False, "local", {}


def apply_intent_to_plan(intent: AIIntent, state: AIConversationState, *, cfg: HwConfig | None = None) -> TestPlan:
    state.sync_candidate_profile()
    base = state.current_plan
    pending_profile_override = None
    if base is None and state.pending_profile_model and _pending_profile_is_complete(state.pending_profile_fields):
        pending_profile_override = build_profile_from_fields(state.pending_profile_model, state.pending_profile_fields)

    model = (
        intent.model
        or (base.model if base else None)
        or (pending_profile_override.model if pending_profile_override else None)
        or extract_model_guess(intent.response)
        or "UNKNOWN"
    )
    if model == "UNKNOWN" and base is not None:
        model = base.model
    goal = intent.goal or (base.goal if base else "auto")
    depth = intent.depth or (base.depth if base else "standard")
    mode = intent.mode or (base.mode if base else "simulation")
    requested_model = model
    downgrade_reason = ""
    if _requires_unknown_fallback_for_unsafe_current(intent, model):
        downgrade_reason = (
            f"用户请求的 Ic 上限超过 {model} 的资料额定值，计划已降级为 UNKNOWN 保守兜底；"
            "接硬件前必须重新确认 datasheet、限流和器件身份。"
        )
        model = "UNKNOWN"

    plan = build_test_plan(
        model=model,
        goal=goal,
        depth=depth,
        mode=mode,
        cfg=cfg,
        profile_override=pending_profile_override,
    )
    if downgrade_reason and not any(downgrade_reason in note for note in plan.safety_notes):
        plan = replace(
            plan,
            safety_notes=plan.safety_notes + [downgrade_reason, f"原始用户提到型号：{requested_model}。"],
        )
    if intent.ic_limit_a is not None or intent.power_limit_w is not None or intent.vcc_max is not None or intent.vbb_points is not None:
        plan = _copy_plan_with_overrides(plan, intent, cfg or HwConfig())
    if "分阶段策略" in intent.response and not any("分阶段策略" in note for note in plan.safety_notes):
        plan = replace(
            plan,
            safety_notes=plan.safety_notes
            + ["分阶段策略：先低风险验证；若 beta、Ic 和工作区分布正常，再切换 deep 计划加密测试。"],
        )
    if pending_profile_override and plan.model == pending_profile_override.model:
        state.clear_candidate_profile()
    return plan


def answer_from_context(intent: AIIntent, state: AIConversationState) -> str:
    state.sync_candidate_profile()
    if state.pending_profile_model:
        if not state.pending_profile_fields:
            return "这是未知型号。为安全建计划，请补充：管型、Vceo、Ic 最大值、Ptot。"
        return _pending_profile_follow_up(state.pending_profile_fields)
    if intent.action == "explain_result" and "对比" in intent.response and len(state.execution_history) >= 2:
        return _compare_recent_executions(state.execution_history[-2], state.execution_history[-1])
    if intent.action == "explain_result" and state.current_execution:
        return local_execution_summary(build_execution_stats(state.current_execution))
    if intent.response:
        return intent.response
    if state.current_plan:
        return "我会基于当前 {0} / {1} 计划继续处理。".format(state.current_plan.model, state.current_plan.goal)
    return "请告诉我要测试的晶体管型号和目标。"


def infer_intent_locally(text: str, state: AIConversationState, *, default_mode: str = "simulation") -> AIIntent:
    state.sync_candidate_profile()
    lowered = text.lower()
    mode = _infer_mode(text, lowered, default_mode)
    if state.pending_library_action:
        pending_model = str(state.pending_library_action.get("model") or "").strip() or None
        if any(word in text for word in ("取消", "算了", "先别", "不用了")):
            return AIIntent(action="manage_profile_library", model=pending_model, response="cancel_pending_library_action")
        if any(word in text for word in ("确认", "继续")):
            return AIIntent(action="manage_profile_library", model=pending_model, response="confirm_pending_library_action")
    if _looks_like_abort_question(text, lowered):
        return AIIntent(action="explain_result", response="解释执行中止原因。")
    is_execution_request = any(word in lowered for word in ("执行", "run")) or any(word in text for word in ("执行测试", "跑全套", "上电跑", "跑一下"))
    explicit_execution_without_plan = (
        any(word in lowered for word in ("执行", "run"))
        or any(word in text for word in ("执行测试", "上电跑", "自动跑", "直接跑"))
    )
    if is_execution_request and (state.current_plan or explicit_execution_without_plan):
        if mode == "hardware":
            return AIIntent(action="execute_hardware", mode="hardware", response="按当前计划执行硬件测试。")
        return AIIntent(action="execute_simulation", mode="simulation", response="按当前计划执行仿真测试。")
    if state.current_plan and state.current_execution and _looks_like_autonomous_refine(text):
        return AIIntent(action="modify_plan", response="自主优化当前测试计划。")
    if _looks_like_execution_comparison(text, lowered) and (state.execution_history or state.current_execution):
        return AIIntent(action="explain_result", response="对比最近两次执行结果。")
    if state.current_plan and _looks_like_normal_then_deepen_request(text):
        return AIIntent(
            action="modify_plan",
            depth="deep",
            response="结果看起来正常，下一步切换为 deep 计划加密测试。",
        )
    if "列出已保存型号" in text or "列出器件库" in text or "查看器件库" in text:
        return AIIntent(action="manage_profile_library", response="list_profiles")
    if ("查看 " in text or "打开 " in text or "定位 " in text) and "器件" in text or ("查看 " in text and _extract_context_model_guess(text) != "UNKNOWN"):
        guessed_model = _extract_context_model_guess(text)
        if guessed_model != "UNKNOWN":
            return AIIntent(action="manage_profile_library", model=guessed_model, response="view_profile")
    if any(word in text for word in ("启用 ", "恢复 ")) and _extract_context_model_guess(text) != "UNKNOWN":
        return AIIntent(action="manage_profile_library", model=_extract_context_model_guess(text), response="enable_profile")
    if any(word in text for word in ("禁用 ", "停用 ")) and _extract_context_model_guess(text) != "UNKNOWN":
        return AIIntent(action="manage_profile_library", model=_extract_context_model_guess(text), response="disable_profile")
    if any(word in text for word in ("删除 ", "移除 ")) and _extract_context_model_guess(text) != "UNKNOWN":
        return AIIntent(action="manage_profile_library", model=_extract_context_model_guess(text), response="delete_profile")
    library_patch = _extract_library_update_patch(text)
    if any(word in text for word in ("更新 ", "修改 ", "改成 ", "改为 ")) and _extract_context_model_guess(text) != "UNKNOWN" and library_patch:
        return AIIntent(
            action="manage_profile_library",
            model=_extract_context_model_guess(text),
            library_patch=library_patch,
            response="update_profile",
        )
    if any(word in lowered for word in ("解释", "为什么", "结果", "总结", "诊断", "异常", "接反", "没电流", "没反应", "报错", "连接失败", "识别不到", "连不上", "pyrd", "超时", "不稳定", "短路", "开路", "没导通", "限流", "over-current", "过流", "偏低", "饱和区", "差很多", "保护", "低一大截", "不导通", "断了", "截止", "超了", "全是0", "全是 0", "找不到", "对调", "反了", "压在一起", "方向不对", "timeout", "贴着横轴", "爆表", "都不通", "pd 超过", "太大功耗", "跳", "饱和", "ocp", "手册说")):
        if "直接给我" not in text:
            if state.current_execution or "logs" in lowered or any(word in lowered for word in ("pyrd", "报错", "连接失败", "连不上", "超时", "过流")):
                return AIIntent(action="explain_result", response="解释刚才的测试结果或异常。")
            if state.current_plan:
                return AIIntent(action="explain_result", response="对当前状况进行诊断。")
            if _looks_like_standalone_fault_description(text, lowered):
                return AIIntent(action="explain_result", response="根据故障描述给出诊断建议。")

    if state.candidate_profile and (_looks_like_profile_save_command(text, lowered) or _looks_like_profile_update_command(text, lowered)):
        if not _pending_profile_is_complete(state.candidate_profile.fields):
            return AIIntent(action="answer", model=state.candidate_profile.model, response=_pending_profile_follow_up(state.candidate_profile.fields))
        if _looks_like_profile_update_command(text, lowered):
            return AIIntent(action="update_profile", model=state.candidate_profile.model, response="按当前候选规格更新型号资料。")
        return AIIntent(action="save_profile", model=state.candidate_profile.model, response="按当前候选规格保存新型号资料。")

    if state.pending_profile_model:
        extracted_fields = extract_profile_fields(text)
        if extracted_fields:
            merged_fields = dict(state.pending_profile_fields)
            merged_fields.update(extracted_fields)
            state.set_candidate_profile(state.pending_profile_model, merged_fields)
            state.sync_candidate_profile()
            return AIIntent(action="answer", response=_pending_profile_follow_up(state.pending_profile_fields))

    guessed_model = _extract_context_model_guess(text)
    has_model = guessed_model != "UNKNOWN"
    has_current = state.current_plan is not None
    is_plan_edit = any(word in text for word in ("保守", "安全", "低压", "加深", "深入", "加密", "多测", "少一点", "降低", "提高", "不超过", "别超过", "上限", "限制", "改", "调整", "别动", "翻倍", "增加"))
    action: IntentAction = "modify_plan" if has_current and (not has_model or is_plan_edit) else "create_plan"
    
    if action == "create_plan" and "测" not in text and "画" not in text and "筛选" not in text and "过一下" not in text:
        # If there's no clear creation verb but it's classified as create, maybe it's just a constraint update.
        if has_current and any(word in text for word in ("档", "起", "基础")):
            action = "modify_plan"
    
    if not has_model and has_current:
        guessed_model = state.current_plan.model
        has_model = True

    if not has_current and action == "create_plan" and _is_unknown_model_request(guessed_model if has_model else None):
        state.set_candidate_profile(guessed_model, {})

    rule = infer_rule_decision(text, {"has_plan": has_current})
    ic_limit = rule.ic_limit_a
    power_limit = rule.power_limit_w
    vcc_max = rule.vcc_max
    vbb_points = rule.vbb_points
    depth = rule.depth or infer_depth(text)
    goal = rule.goal or infer_goal(text)
    profile = lookup_transistor(guessed_model) if has_model else None
    
    if goal == "auto" and has_current:
        goal = state.current_plan.goal
    if depth == "standard" and has_current:
        depth = state.current_plan.depth
    if not has_current and action == "create_plan" and state.pending_profile_model and depth == "standard":
        depth = "conservative"
    if profile and profile.bjt_type == "PNP" and not has_current and action == "create_plan":
        if goal == "auto":
            goal = "screening"
        if goal == "screening" and depth == "standard":
            depth = "conservative"
    if _looks_like_uncertain_screening_request(text) and depth == "standard":
        depth = "conservative"
    if _looks_like_explicit_low_risk_screening(text) and goal == "auto":
        goal = "screening"

    intent = AIIntent(
        action=action,
        model=guessed_model if has_model else None,
        goal=goal if goal != "auto" else None,
        depth=depth,
        mode=mode,
        ic_limit_a=ic_limit,
        power_limit_w=power_limit,
        vcc_max=vcc_max,
        vbb_points=vbb_points,
        response=rule.response or "已根据上下文理解你的测试需求。",
    )
    if action in {"create_plan", "modify_plan"} and _looks_like_staged_deepen_request(text):
        return _with_staged_deepen_response(intent)
    return intent


def _is_unknown_model_request(model: str | None) -> bool:
    return bool(model and model != "UNKNOWN" and lookup_transistor(model).confidence == "fallback")


def _requires_unknown_fallback_for_unsafe_current(intent: AIIntent, model: str) -> bool:
    if intent.ic_limit_a is None or model == "UNKNOWN":
        return False
    profile = lookup_transistor(model)
    if profile.confidence == "fallback":
        return False
    return float(intent.ic_limit_a) > float(profile.ic_max_a)


def _looks_like_execution_comparison(text: str, lowered: str) -> bool:
    del lowered
    comparison_words = ("对比", "比较", "区别", "差异", "变化", "不同")
    history_words = ("两次", "上次", "这次", "前一次", "刚才")
    return any(word in text for word in comparison_words) and any(word in text for word in history_words)


def _looks_like_autonomous_refine(text: str) -> bool:
    return any(word in text for word in ("优化", "自动调整", "自己看着办", "下一步", "你来定", "帮我调整", "改进计划"))


def _looks_like_abort_question(text: str, lowered: str) -> bool:
    abort_words = ("中止", "停止", "abort", "aborted")
    question_words = ("为什么", "原因", "怎么回事", "解释", "诊断")
    return any(word in lowered for word in abort_words) and any(word in text for word in question_words)


def _looks_like_standalone_fault_description(text: str, lowered: str) -> bool:
    del lowered
    fault_words = (
        "短路",
        "蜂鸣",
        "不导通",
        "断了",
        "功耗",
        "超了",
        "全是0",
        "全是 0",
        "当 NPN",
        "当 PNP",
        "对调",
        "接反",
        "引脚顺序",
        "脚位",
        "hFE",
        "hfe",
        "beta 低",
        "Beta 低",
        "偏低",
        "低一大截",
        "方向不对",
        "pd 超过",
        "太大功耗",
    )
    return any(word in text for word in fault_words)


def _looks_like_uncertain_screening_request(text: str) -> bool:
    uncertainty_words = ("不确定型号", "型号不确定", "不知道型号", "没丝印", "丝印不清", "拆机件", "不确定管型")
    screening_words = ("低风险", "保守", "筛查", "筛一下", "验管", "先测", "先看")
    return any(word in text for word in uncertainty_words) or (
        "不确定" in text and any(word in text for word in screening_words)
    )


def _looks_like_explicit_low_risk_screening(text: str) -> bool:
    return any(word in text for word in ("低风险筛查", "低风险", "筛查", "筛一下"))


def _looks_like_staged_deepen_request(text: str) -> bool:
    first_words = ("先", "第一步", "先保守", "先低风险")
    condition_words = ("如果", "正常", "通过", "没问题", "稳定")
    deepen_words = ("再加深", "再深入", "再加密", "再详细", "加深", "加密")
    return (
        any(word in text for word in first_words)
        and any(word in text for word in condition_words)
        and any(word in text for word in deepen_words)
    )


def _looks_like_normal_then_deepen_request(text: str) -> bool:
    normal_words = ("正常", "通过", "没问题", "稳定", "结果还行")
    deepen_words = ("加深", "深入", "加密", "更详细", "下一步")
    return any(word in text for word in normal_words) and any(word in text for word in deepen_words)


def _with_staged_deepen_response(intent: AIIntent) -> AIIntent:
    note = "分阶段策略：先低风险验证；若 beta、Ic 和工作区分布正常，再切换 deep 计划加密测试。"
    response = intent.response or ""
    if note not in response:
        response = (response.rstrip("。") + "。" if response else "") + note
    return AIIntent(
        action=intent.action,
        model=intent.model,
        goal=intent.goal,
        depth="conservative",
        mode=intent.mode,
        ic_limit_a=intent.ic_limit_a,
        power_limit_w=intent.power_limit_w,
        vcc_max=intent.vcc_max,
        vbb_points=intent.vbb_points,
        library_patch=intent.library_patch,
        response=response,
    )


def _compare_recent_executions(previous: dict, latest: dict) -> str:
    previous_stats = build_execution_stats(previous)
    latest_stats = build_execution_stats(latest)
    lines = [
        "最近两次执行对比：第一次 {0} 个测量点，第二次 {1} 个测量点。".format(
            previous_stats["point_count"],
            latest_stats["point_count"],
        )
    ]
    beta_line = _metric_delta_line("Beta 中位数", previous_stats.get("beta_median"), latest_stats.get("beta_median"))
    if beta_line:
        lines.append(beta_line)
    active_line = _metric_delta_line(
        "Active 区 beta 中位数",
        previous_stats.get("active_beta_median"),
        latest_stats.get("active_beta_median"),
    )
    if active_line:
        lines.append(active_line)
    ic_line = _metric_delta_line("最大 Ic", previous_stats.get("ic_max_a"), latest_stats.get("ic_max_a"), scale=1000.0, unit=" mA")
    if ic_line:
        lines.append(ic_line)
    lines.append(
        "工作区分布：第一次 {0}；第二次 {1}。".format(
            _format_region_counts(previous_stats["region_counts"]),
            _format_region_counts(latest_stats["region_counts"]),
        )
    )
    if latest_stats.get("aborted"):
        lines.append("第二次执行已中止：{0}".format(latest_stats.get("abort_reason") or "触发了运行时安全判据。"))
    elif previous_stats.get("aborted") and not latest_stats.get("aborted"):
        lines.append("第二次没有触发中止，说明这轮限值或工作点更稳定。")
    return "\n".join(lines)


def _metric_delta_line(label: str, previous: float | None, latest: float | None, *, scale: float = 1.0, unit: str = "") -> str:
    if previous is None or latest is None:
        return ""
    previous_value = float(previous) * scale
    latest_value = float(latest) * scale
    delta = latest_value - previous_value
    sign = "+" if delta >= 0 else ""
    return "{0}: {1:.2f}{4} -> {2:.2f}{4}，变化 {3}{5:.2f}{4}。".format(
        label,
        previous_value,
        latest_value,
        sign,
        unit,
        delta,
    )


def _format_region_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "无测量点"
    return ", ".join("{0}={1}".format(key, value) for key, value in sorted(counts.items()))


def _pending_profile_follow_up(fields: dict[str, float | str]) -> str:
    recorded: list[str] = []
    if fields.get("bjt_type"):
        recorded.append(str(fields["bjt_type"]))
    if fields.get("vceo_max_v") is not None:
        recorded.append(f"Vceo {_format_profile_number(float(fields['vceo_max_v']))}V")
    if fields.get("ic_max_a") is not None:
        recorded.append(f"Ic 最大值 {_format_profile_number(float(fields['ic_max_a']) * 1000)}mA")
    if fields.get("p_tot_w") is not None:
        recorded.append(f"Ptot {_format_profile_number(float(fields['p_tot_w']) * 1000)}mW")

    missing = _missing_profile_fields(fields)
    if missing:
        return "已记录：" + "、".join(recorded) + "。还需要：" + "、".join(missing) + "。"
    return "已记录完整规格：" + "、".join(recorded) + "。"


def _missing_profile_fields(fields: dict[str, float | str]) -> list[str]:
    missing_labels = {
        "bjt_type": "管型",
        "vceo_max_v": "Vceo",
        "ic_max_a": "Ic 最大值",
        "p_tot_w": "Ptot",
    }
    return [missing_labels[name] for name in ("bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w") if name not in fields]


def _pending_profile_is_complete(fields: dict[str, float | str]) -> bool:
    return all(name in fields for name in ("bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"))


def _format_profile_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _infer_mode(text: str, lowered: str, default_mode: str) -> str:
    if "仿真" in text or "simulation" in lowered:
        return "simulation"
    if "硬件" in text or "hardware" in lowered or "上电" in text:
        return "hardware"
    return default_mode


def _intent_from_mapping(data: dict[str, Any], text: str, state: AIConversationState, default_mode: str) -> AIIntent:
    action = data.get("action")
    if action not in {"create_plan", "modify_plan", "execute_simulation", "execute_hardware", "explain_result", "manage_profile_library", "save_profile", "update_profile", "answer"}:
        return infer_intent_locally(text, state, default_mode=default_mode)
    return AIIntent(
        action=action,
        model=data.get("model") or None,
        goal=data.get("goal") if data.get("goal") in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else None,
        depth=data.get("depth") if data.get("depth") in {"conservative", "standard", "deep"} else None,
        mode=data.get("mode") if data.get("mode") in {"simulation", "hardware"} else None,
        ic_limit_a=_safe_float(data.get("ic_limit_a")),
        power_limit_w=_safe_float(data.get("power_limit_w")),
        vcc_max=_safe_float(data.get("vcc_max")),
        vbb_points=_safe_int(data.get("vbb_points")),
        library_patch=data.get("library_patch") if isinstance(data.get("library_patch"), dict) else None,
        response=str(data.get("response") or ""),
    )


def _copy_plan_with_overrides(plan: TestPlan, intent: AIIntent, cfg: HwConfig) -> TestPlan:
    data = plan.to_dict()
    if intent.ic_limit_a is not None:
        data["ic_limit_a"] = round(max(0.001, min(float(intent.ic_limit_a), cfg.Ic_max_A)), 6)
    if intent.power_limit_w is not None:
        data["power_limit_w"] = round(max(0.005, min(float(intent.power_limit_w), cfg.Pmax_W)), 6)
    if intent.vcc_max is not None:
        existing_stop = max(data["vcc_steps"]) if data["vcc_steps"] else min(cfg.Vcc_max, 5.0)
        limit = max(0.5, min(float(intent.vcc_max), cfg.Vcc_max, max(existing_stop, cfg.Vcc_max)))
        data["vcc_steps"] = [value for value in data["vcc_steps"] if value <= limit]
        if not data["vcc_steps"] or data["vcc_steps"][-1] < limit:
            data["vcc_steps"].append(round(limit, 3))
        for point in data["static_points"]:
            point["vcc"] = min(point["vcc"], round(limit, 3))
    if intent.vbb_points is not None and data["vbb_steps"]:
        count = max(2, min(int(intent.vbb_points), 16))
        start = min(data["vbb_steps"])
        stop = max(data["vbb_steps"])
        step = (stop - start) / float(count - 1)
        data["vbb_steps"] = [round(start + i * step, 3) for i in range(count)]
        if data["goal"] == "beta":
            vcc = data["static_points"][0]["vcc"] if data["static_points"] else 3.0
            data["static_points"] = [{"vcc": vcc, "vbb": value} for value in data["vbb_steps"]]

    return TestPlan(
        model=data["model"],
        bjt_type=data["bjt_type"],
        goal=data["goal"],
        depth=data["depth"],
        mode=data["mode"],
        vcc_steps=data["vcc_steps"],
        vbb_steps=data["vbb_steps"],
        static_points=data["static_points"],
        ic_limit_a=data["ic_limit_a"],
        power_limit_w=data["power_limit_w"],
        sample_count=data["sample_count"],
        scan_mode=data["scan_mode"],
        steps=data["steps"],
        safety_notes=data["safety_notes"],
        profile=data["profile"],
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object")
    return json.loads(stripped[start : end + 1])


def _extract_current_limit_a(text: str) -> float | None:
    rule = infer_rule_decision(text)
    if rule.ic_limit_a is not None:
        return rule.ic_limit_a
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ma|毫安)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r"(?:ic|电流).*?(\d+(?:\.\d+)?)\s*a", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_context_model_guess(text: str) -> str:
    for guess in _model_candidates(text):
        upper = guess.upper()
        if re.fullmatch(r"\d+(?:MA|MV|V|A|W|MW)", upper):
            continue
        return guess
    return "UNKNOWN"


def _model_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for raw in text.replace(",", " ").replace("，", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in "-_")
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            candidates.append(token)
    return candidates


def _extract_library_update_patch(text: str) -> dict[str, object]:
    patch: dict[str, object] = {}
    upper_text = text.upper()
    if re.search(r"\bNPN\b", upper_text):
        patch["bjt_type"] = "NPN"
    elif re.search(r"\bPNP\b", upper_text):
        patch["bjt_type"] = "PNP"

    voltage_match = re.search(r"(?:VCEO|Vceo|耐压).*?(\d+(?:\.\d+)?)\s*V", text, re.IGNORECASE)
    if voltage_match:
        patch["vceo_max_v"] = float(voltage_match.group(1))

    current_match = re.search(r"(?:IC|Ic|电流).*?(\d+(?:\.\d+)?)\s*(mA|A)", text, re.IGNORECASE)
    if current_match:
        value = float(current_match.group(1))
        patch["ic_max_a"] = value / 1000.0 if current_match.group(2).lower() == "ma" else value

    power_match = re.search(r"(?:PTOT|Ptot|功耗).*?(\d+(?:\.\d+)?)\s*(mW|W)", text, re.IGNORECASE)
    if power_match:
        value = float(power_match.group(1))
        patch["p_tot_w"] = value / 1000.0 if power_match.group(2).lower() == "mw" else value
    return patch


def _looks_like_profile_save_command(text: str, lowered: str) -> bool:
    return any(
        phrase in text
        for phrase in ("保存这个型号", "保存该型号", "保存这个规格", "保存到资料库", "保存到数据库", "把这个型号保存", "记住这个型号", "存档这个型号")
    ) or "save profile" in lowered


def _looks_like_profile_update_command(text: str, lowered: str) -> bool:
    return any(
        phrase in text
        for phrase in ("更新这个型号", "更新该型号", "更新这个规格", "覆盖这个型号", "覆盖这个规格", "改写这个型号")
    ) or "update profile" in lowered


def _extract_voltage_limit(text: str) -> float | None:
    rule = infer_rule_decision(text)
    if rule.vcc_max is not None:
        return rule.vcc_max
    match = re.search(r"(?:vcc|电压).*?(?:不超过|最高|上限|到)\s*(\d+(?:\.\d+)?)\s*v?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _extract_point_count(text: str) -> int | None:
    rule = infer_rule_decision(text)
    if rule.vbb_points is not None:
        return rule.vbb_points
    match = re.search(r"(\d+)\s*个?点", text)
    if match:
        return int(match.group(1))
    if "多测" in text or "加密" in text:
        return 10
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
