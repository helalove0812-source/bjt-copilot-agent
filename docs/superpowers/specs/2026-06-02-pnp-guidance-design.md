# PNP Guidance Design

## Goal

为 BJT Agent 增加 `PNP` 引导路径：当用户请求测试 `PNP` 三极管时，系统不再只是拒绝自动执行，而是生成一个极保守的引导计划，并明确说明接线差异、风险边界和下一步建议。

本阶段不开放 `PNP` 自动执行，不实现半自动执行，不新增新的硬件确认流程。

## Current Problem

当前系统对 `PNP` 的处理已经足够安全：

- planner 会生成偏保守的 `PNP` 计划
- [safety.py](file:///Users/helap/Documents/Project/雨骤/ai/safety.py) 会阻断 `PNP` 自动执行
- [tools.py](file:///Users/helap/Documents/Project/雨骤/ai/tools.py) 只开放明确 `NPN` 的自动执行路径

但用户体验上仍有断点：

- 用户只知道“不能自动执行”，不知道下一步应该做什么
- 虽然已有计划和 `safety_notes`，但没有形成明确的“引导计划”语义
- 对话层没有把 `PNP` 请求收敛成更保守的默认目标

## Design Choice

本阶段采用“说明与引导 + 极保守计划”的方案：

- 保持执行层拒绝 `PNP` 自动执行
- 在对话与计划层把 `PNP` 请求转成更保守的引导计划
- 通过响应文案明确解释为什么不能自动执行，以及用户应如何继续

不采用新增 `PNP guidance mode` 的方案，因为当前阶段只需要体验增强，不需要扩大现有模式和执行状态机。

## Scope

### In Scope

- `PNP` 请求时生成更保守的默认计划
- 默认目标偏 `screening`
- 默认深度偏 `conservative`
- 强化 `PNP` 的引导说明和 `safety_notes`
- Agent 返回明确的“引导性响应”

### Out Of Scope

- `PNP` 自动执行
- `PNP` 半自动执行
- 新的 token 或确认链路
- 新的 CLI 模式

## Planner Behavior

当型号查库后确认是 `PNP` 时，planner 的默认行为调整为：

- `goal` 默认优先 `screening`
- `depth` 默认优先 `conservative`
- `mode` 保持原值，但 `safety_notes` 更明确地表达：
  - 自动执行未开放
  - 接线极性与 `NPN` 不同
  - 先核对 datasheet 和引脚
  - 仅建议低压、人工确认路径

这并不改变执行层的安全底线，只是让计划更符合“引导计划”的用途。

## Conversation Behavior

当用户请求测试明确的 `PNP` 型号，例如：

- `测一下 S8550`
- `帮我看 2N3906`

系统应：

1. 仍然创建计划
2. 将默认目标收敛为保守筛查用途
3. 在响应中明确说明：
   - 当前自动执行路径只开放 `NPN`
   - `PNP` 的偏置和接线方向不同
   - 建议先核对引脚、datasheet、夹具方向
   - 当前给出的是保守引导计划

## Response Style

第一版文案以清晰为主，不追求复杂对话风格。

推荐响应包含 3 个部分：

1. 已识别为 `PNP`
2. 自动执行未开放的原因
3. 已生成保守筛查计划，可用于人工低压确认

例如：

- “已识别为 PNP 型号 S8550。当前自动执行路径只开放 NPN，因为 PNP 的偏置和接线方向不同。已为你生成一个保守筛查计划；继续前请先核对 datasheet、E/B/C 引脚和夹具方向。”

## Safety Notes

`PNP` 计划应至少包含以下引导信息：

- 当前项目的自动测试路径偏 `NPN`
- `PNP` 不建议直接自动执行
- 先核对引脚定义和封装批次差异
- 建议从低压、低电流、人工确认开始

## Testing Strategy

更新测试覆盖：

- `tests/test_ai_conversation.py`
  - `PNP` 请求默认收敛为 `screening + conservative`
- `tests/test_ai_agent.py`
  - `PNP` 请求返回引导性响应，而不是普通计划摘要
- `tests/test_ai_safety_regression.py`
  - `PNP` 计划仍然保留自动执行阻断语义

继续要求：

- `python3 -m pytest -q`
- `python3 scripts/run_agent_regression.py --json`

必须保持当前阶段二和阶段三的安全回归不退化。

## Risks

- 如果把 `PNP` 默认目标改得太激进，会削弱“引导计划”的保守意义
- 如果只改文案不改计划默认值，用户依然得不到真正适合人工确认的保守计划
- 如果在本阶段引入执行链路变化，会扩大风险面

因此第一版坚持：

- 只做保守计划与引导文案
- 不改执行底线

## Decision

本阶段采用“`PNP` 引导响应 + 极保守 `screening` 计划”的方案。
