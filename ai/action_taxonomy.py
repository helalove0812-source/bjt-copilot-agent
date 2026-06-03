from __future__ import annotations

import hashlib


ACTION_METADATA: dict[str, dict[str, str]] = {
    "create_plan": {"label": "生成测试计划", "kind": "plan", "priority": "medium"},
    "run_simulation": {"label": "运行仿真", "kind": "execute", "priority": "medium"},
    "run_conservative_simulation": {"label": "先运行保守仿真", "kind": "execute", "priority": "medium"},
    "rerun_conservative_simulation": {"label": "重新运行保守仿真", "kind": "execute", "priority": "medium"},
    "request_hardware_confirmation": {"label": "请求硬件执行确认", "kind": "safety", "priority": "high"},
    "deepen_plan_after_stable_result": {"label": "结果稳定后加深计划", "kind": "plan", "priority": "medium"},
    "deepen_plan": {"label": "加深计划", "kind": "plan", "priority": "medium"},
    "explain_result": {"label": "解释结果", "kind": "diagnosis", "priority": "medium"},
    "explain_retained_measurements": {"label": "解释已保留的测量点", "kind": "diagnosis", "priority": "medium"},
    "explain_or_modify_plan": {"label": "解释或调整当前计划", "kind": "diagnosis", "priority": "medium"},
    "modify_plan_from_diagnosis": {"label": "根据诊断修改计划", "kind": "plan", "priority": "medium"},
    "modify_plan_and_rerun": {"label": "调整计划后重测", "kind": "plan", "priority": "medium"},
    "modify_plan": {"label": "修改计划", "kind": "plan", "priority": "medium"},
    "clamp_current": {"label": "降低 Ic 上限", "kind": "safety", "priority": "high"},
    "clamp_power": {"label": "降低功耗上限", "kind": "safety", "priority": "high"},
    "increase_points": {"label": "增加测试点密度", "kind": "plan", "priority": "medium"},
    "run_wiring_check": {"label": "检查接线", "kind": "diagnosis", "priority": "high"},
    "check_wiring": {"label": "检查接线", "kind": "diagnosis", "priority": "high"},
    "prompt_pinout_confirm": {"label": "确认引脚定义", "kind": "safety", "priority": "high"},
    "suggest_next_step": {"label": "建议下一步", "kind": "diagnosis", "priority": "medium"},
    "reject_unsafe": {"label": "拒绝危险请求", "kind": "safety", "priority": "high"},
    "explain_limit": {"label": "解释安全限制", "kind": "safety", "priority": "high"},
    "lower_vbb_and_rerun": {"label": "降低 Vbb 上沿后复测", "kind": "plan", "priority": "medium"},
    "raise_vbb_or_check_base_path": {"label": "提高 Vbb 起点或检查基极支路", "kind": "diagnosis", "priority": "medium"},
    "inspect_vce_window": {"label": "检查 Vce 工作窗口", "kind": "diagnosis", "priority": "medium"},
    "inspect_base_path": {"label": "检查基极支路", "kind": "diagnosis", "priority": "medium"},
    "diagnose_missing_measurements": {"label": "检查为什么没有测量点", "kind": "diagnosis", "priority": "medium"},
    "inspect_abort_reason": {"label": "查看中止原因", "kind": "diagnosis", "priority": "high"},
    "inspect_skip_reason": {"label": "查看跳过原因", "kind": "diagnosis", "priority": "medium"},
    "inspect_block_reason": {"label": "查看阻止原因", "kind": "safety", "priority": "high"},
    "lower_limits_and_check_wiring": {"label": "降低限值或检查接线后重试", "kind": "safety", "priority": "high"},
    "continue_hardware_with_token": {"label": "使用一次性令牌继续硬件执行", "kind": "safety", "priority": "high"},
    "request_hardware_after_safety_check": {"label": "确认安全后再请求硬件执行", "kind": "safety", "priority": "high"},
    "cancel_or_modify_plan": {"label": "取消或修改当前计划", "kind": "plan", "priority": "medium"},
    "open_profile_library": {"label": "打开器件库", "kind": "library", "priority": "low"},
    "upsert_profile": {"label": "新增或更新器件资料", "kind": "library", "priority": "low"},
    "toggle_profile_enabled": {"label": "启用或禁用器件", "kind": "library", "priority": "low"},
    "export_or_view_execution_data": {"label": "导出或查看执行数据", "kind": "export", "priority": "low"},
    "verify_datasheet_and_pinout": {"label": "核对 datasheet 和引脚定义", "kind": "safety", "priority": "high"},
    "complete_profile_fields": {"label": "补充未知型号规格", "kind": "input", "priority": "medium"},
    "choose_known_model": {"label": "改用数据库中已有型号", "kind": "plan", "priority": "low"},
    "confirm_pending_action": {"label": "回复确认", "kind": "input", "priority": "medium"},
    "cancel_pending_action": {"label": "回复取消", "kind": "input", "priority": "low"},
}


LABEL_RULES: list[tuple[str, list[str]]] = [
    ("补充未知型号", ["complete_profile_fields"]),
    ("改用数据库", ["choose_known_model"]),
    ("继续补充候选规格", ["complete_profile_fields"]),
    ("检查本地型号库", ["open_profile_library"]),
    ("生成测试计划", ["create_plan"]),
    ("先运行保守仿真", ["run_conservative_simulation"]),
    ("重新运行保守仿真", ["rerun_conservative_simulation"]),
    ("运行仿真", ["run_simulation"]),
    ("执行仿真", ["run_simulation"]),
    ("结果正常后加深计划", ["deepen_plan_after_stable_result"]),
    ("结果稳定后加深计划", ["deepen_plan_after_stable_result"]),
    ("加深计划", ["deepen_plan"]),
    ("解释已保留", ["explain_retained_measurements"]),
    ("解释或调整", ["explain_or_modify_plan"]),
    ("解释结果", ["explain_result"]),
    ("根据诊断修改计划", ["modify_plan_from_diagnosis"]),
    ("调整计划后重测", ["modify_plan_and_rerun"]),
    ("修改计划", ["modify_plan"]),
    ("降低 Vbb", ["lower_vbb_and_rerun"]),
    ("提高 Vbb", ["raise_vbb_or_check_base_path"]),
    ("检查 Vce", ["inspect_vce_window"]),
    ("检查基极", ["inspect_base_path"]),
    ("检查为什么没有测量点", ["diagnose_missing_measurements"]),
    ("查看中止原因", ["inspect_abort_reason"]),
    ("降低限值", ["lower_limits_and_check_wiring"]),
    ("查看跳过原因", ["inspect_skip_reason"]),
    ("查看阻止原因", ["inspect_block_reason"]),
    ("请求硬件执行确认", ["request_hardware_confirmation"]),
    ("使用一次性令牌", ["continue_hardware_with_token"]),
    ("确认安全后再请求硬件执行", ["request_hardware_after_safety_check"]),
    ("取消或修改", ["cancel_or_modify_plan"]),
    ("回复确认", ["confirm_pending_action"]),
    ("回复取消", ["cancel_pending_action"]),
    ("打开器件库", ["open_profile_library"]),
    ("查看器件库", ["open_profile_library"]),
    ("新增或更新", ["upsert_profile"]),
    ("启用/禁用", ["toggle_profile_enabled"]),
    ("继续用该型号生成计划", ["create_plan"]),
    ("导出或查看执行数据", ["export_or_view_execution_data"]),
    ("核对 datasheet", ["verify_datasheet_and_pinout"]),
    ("检测到运行时中止", ["modify_plan", "clamp_current", "clamp_power"]),
    ("检测到饱和点偏多", ["modify_plan", "clamp_current"]),
    ("有效 active 点偏少", ["modify_plan", "increase_points"]),
    ("保守阶段结果稳定", ["modify_plan", "increase_points"]),
    ("结果较稳定", ["modify_plan", "increase_points"]),
    ("已写入用户型号库", ["upsert_profile"]),
    ("已更新用户型号库", ["upsert_profile"]),
    ("已删除", ["toggle_profile_enabled"]),
    ("已禁用", ["toggle_profile_enabled"]),
    ("已启用", ["toggle_profile_enabled"]),
]


def action_label(action: str) -> str:
    return ACTION_METADATA.get(action, {}).get("label", action)


def action_kind(action: str) -> str:
    return ACTION_METADATA.get(action, {}).get("kind", "other")


def action_priority(action: str) -> str:
    return ACTION_METADATA.get(action, {}).get("priority", "medium")


def action_item(action: str, *, label: str | None = None, reason: str = "") -> dict:
    return {
        "id": action,
        "action": action,
        "label": label or action_label(action),
        "kind": action_kind(action),
        "priority": action_priority(action),
        "reason": reason,
    }


def action_items_from_labels(labels: list[str]) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for label in labels:
        matched = False
        for needle, actions in LABEL_RULES:
            if needle in label:
                for action in actions:
                    key = (action, label)
                    if key not in seen:
                        items.append(action_item(action, label=label))
                        seen.add(key)
                matched = True
                break
        if not matched:
            action = _slugify_action_label(label)
            key = (action, label)
            if key not in seen:
                items.append(action_item(action, label=label))
                seen.add(key)
    return items


def _slugify_action_label(label: str) -> str:
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:10]
    return "action_" + digest
