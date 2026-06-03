# BJTagent Profile Save Status Design

## Goal

为当前 Web UI 增加“型号是否已保存到本地型号库”的前端显式提示，但只通过聊天区中的 `BJTagent` 系统消息呈现，不新增顶部持久状态卡，也不修改后端协议。

本阶段目标是让用户在未知型号测试完成后，能够更直观地看到：

- 当前型号尚未保存到本地型号库
- 当前型号已成功保存到本地型号库

同时保持提示克制，不在每轮对话中反复刷屏。

## Current Problem

当前前端已经具备：

- `BJTagent` 状态卡
- 未知型号补全提示
- 聊天区 `system` 气泡行动日志
- `conversation_state` 的保存与回传

但新增“用户确认后写入本地型号库”的能力后，前端还没有把这条状态明确显示出来。

当前缺口是：

- 用户只能从后端普通回复文本中自己读出“尚未保存”或“已保存”
- 聊天区没有统一的 `BJTagent` 行动提示来标记这类状态变化
- 同一型号如果后端多次重复提示“尚未保存”，前端可能重复显示，影响可读性

## Design Choice

本阶段采用“聊天区系统提示 + 同型号去重”方案：

- 主显示位置放在聊天区 `system` 气泡
- 不把这项状态放进顶部状态卡
- 只在保存相关事件发生时提示
- 同一型号在同一会话中，“尚未保存”提示只显示一次
- 保存成功后显示一次“已保存到本地型号库”

不采用以下方案：

- 顶部状态卡持久显示：会让状态卡承担过多职责
- 每轮涉及该型号都重复提示：噪音太大
- 只显示保存成功，不显示尚未保存：缺少行动引导

## Scope

### In Scope

- 在 [App.jsx](file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx) 中检测后端回复里的“尚未保存/已保存”语义
- 把这两类事件统一转成 `BJTagent` 风格的 `system` 气泡
- 为同一型号增加会话级去重逻辑
- 新增或更新最小前端 smoke test

### Out Of Scope

- 修改后端返回结构
- 新增顶部状态卡字段
- 新增复杂前端标签、徽章或表单
- 新增浏览器级端到端测试

## UI Placement

用户已确认这项状态主要显示在聊天区，而不是顶部状态卡。

因此只在现有聊天区里增加两类 `BJTagent` 系统提示：

- `BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库`
- `BJTagent：已保存到本地型号库，后续可直接复用`

这两条提示属于行动日志的一部分，视觉风格保持和现有 `system` 气泡一致。

## Trigger Rules

### Unsaved Prompt

当后端回复文本中包含以下语义时，前端追加一条统一的 `system` 提示：

- `尚未保存到本地型号库`
- `你可以回复“保存这个型号”`
- `你可以回复“写入库”`

统一渲染为：

- `BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库`

### Saved Prompt

当后端回复文本中包含以下语义时，前端追加一条统一的 `system` 提示：

- `已将 XXX 写入本地型号库`
- `后续再次测试该型号时，会优先使用本地已确认参数`

统一渲染为：

- `BJTagent：已保存到本地型号库，后续可直接复用`

## Model Resolution

前端需要尽量判断当前提示对应的是哪个型号，以便做去重。

推荐按以下优先级取型号：

1. `conversationState.candidate_profile.model`
2. `conversationState.pending_profile_model`
3. `currentPlan.model`

如果以上都拿不到，则可以退化为“无型号去重”，但第一版尽量优先用已有上下文，不新增后端字段。

## Deduplication Rules

### Unsaved Dedup

同一型号在同一会话中，“尚未保存”提示只显示一次。

需要一个轻量会话级前端记忆，例如：

- `unsavedProfileNoticeByModel`

语义：

- 某型号已经显示过“尚未保存”提示，则本轮后续不再重复插入

### Saved Transition

当收到“已保存到本地型号库”的语义时：

- 显示一次“已保存”系统提示
- 清除该型号的“尚未保存已提示”标记
- 记录该型号本轮已经保存，避免后续再次出现“尚未保存”提示

这样能形成明确的状态跃迁：

- 未保存
- 已保存

而不是让前端在保存成功后仍继续提示“尚未保存”。

## Data Source Strategy

本阶段不新增后端字段，前端只基于：

- 后端自然语言回复文本
- 已有 `conversationState`
- 已有 `currentPlan`

来推断是否需要插入“尚未保存/已保存”的系统提示。

这是一个刻意的最小方案，优点是：

- 不需要同步修改后端 API
- 只动前端体验层
- 与当前 `BJTagent` 行动日志机制一致

## Implementation Notes

推荐在 [App.jsx](file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx) 的 AI 面板消息处理链路中实现：

- 先把后端 `response` 作为普通 AI 回复插入
- 再根据该回复文本是否命中保存语义，决定是否额外插入 `system` 气泡
- 复用现有 `addAgentMessage()` 或等价辅助函数

推荐新增轻量 `ref` 或 `state`：

- 记录本轮哪些型号已经显示过“尚未保存”
- 记录哪些型号已经显示过“已保存”

第一版不需要把这部分提升成复杂 reducer。

## Testing Strategy

### New / Updated Tests

建议新增最小 smoke，例如：

- `tests/test_frontend_profile_save_status_smoke.py`

断言内容：

- 存在“尚未保存到本地库”的 `BJTagent` 提示文案
- 存在“已保存到本地型号库”的 `BJTagent` 提示文案
- 存在某种同型号去重状态记忆逻辑
- 不破坏现有 `conversation_state` 和行动日志结构

也可以更新现有前端 smoke，但单独文件更清晰。

### Verification

继续要求：

- `npm run build`
- `python3 -m pytest tests/test_frontend_abort_smoke.py tests/test_frontend_agent_experience_smoke.py tests/test_gui_smoke.py tests/test_cli_smoke.py -q`

如果新增前端 smoke，则一并执行。

## Risks

- 如果只靠回复文本匹配，文案一旦变化，前端提示可能失效
- 如果不做去重，同一型号可能重复刷“尚未保存”
- 如果保存成功后不清理旧状态，后续仍可能出现错误的“尚未保存”提示

因此第一版要坚持：

- 只匹配少量稳定语义
- 同型号去重
- 保存成功后做状态切换

## Decision

本阶段采用“聊天区 `BJTagent` 系统提示 + 保存相关事件触发 + 同型号去重”的最小前端体验方案，不修改后端协议，不扩展顶部状态卡。
