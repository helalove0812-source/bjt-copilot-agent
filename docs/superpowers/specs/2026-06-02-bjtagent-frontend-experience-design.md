# BJTagent Frontend Experience Design

## Goal

把当前 Web UI 从“仪器控制台 + 聊天框”提升为更像测试 Agent 工作流的界面，但保持后端协议和 Agent 核心逻辑不变。

本阶段只做前端体验层：

- 在 [App.jsx](file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx) 中保存并回传 `conversation_state`
- 在 AI 面板顶部展示 `BJTagent` 当前状态
- 为未知型号补全流程增加轻量可视提示
- 在聊天区增加 `BJTagent` 风格的行动日志
- 新增最小前端 smoke test

本阶段不修改：

- `ai/*.py`
- [api_server.py](file:///Users/helap/Documents/Project/雨骤/api_server.py)
- `scripts/*.py`
- `数据/*.jsonl`

## Current Problem

当前右侧 AI 面板已经能发送 `/api/ai-chat`，但仍然更像普通聊天框：

- 前端只回传 `current_plan / measurements / logs / messages`
- 前端不保存 `conversation_state`
- 未知型号多轮补全流程没有前端可见状态
- 界面没有集中显示“当前 Agent 在做什么”

因此即使后端已经支持：

- `conversation_state.pending_profile_model`
- `conversation_state.pending_profile_fields`
- `conversation_state.current_plan`

用户在 Web UI 中仍然很难读懂多轮流程是否正在推进。

## Design Choice

本阶段采用“AI 面板顶部状态卡 + 轻量行动日志”方案：

- 顶部状态卡负责展示当前 `BJTagent` 状态
- 状态卡下方展示未知型号补全提示
- 聊天流中插入少量 `system` 风格的 `BJTagent` 行动日志
- `/api/ai-chat` 返回的 `conversation_state` 在前端持有，并在下一轮请求中带回

不采用“只做状态卡、不做行动日志”的方案，因为那样虽然能看到状态，但工作流感不足。

也不采用“独立时间线侧栏”的方案，因为改动较大，且容易与现有聊天区、日志区职责重叠。

## Scope

### In Scope

- 保存 `/api/ai-chat` 返回的 `conversation_state`
- 下一轮 `/api/ai-chat` 请求回传 `conversation_state`
- 顶部展示 `BJTagent` 当前状态
- 展示未知型号补全过程的已知字段 / 缺失字段
- 插入 `BJTagent` 风格的行动日志
- 补最小前端 smoke

### Out Of Scope

- 修改后端会话状态机
- 修改 Agent 决策逻辑
- 新增复杂未知型号表单
- 新增前端路由或多页面结构
- 修改执行接口协议

## Conversation State Integration

### Stored State

前端新增 `conversationState`，用于保存 `/api/ai-chat` 返回的：

- `pending_profile_model`
- `pending_profile_fields`
- `current_plan`

### Request Flow

当前 [App.jsx](file:///Users/helap/Documents/Project/雨骤/frontend/src/App.jsx) 发送 `/api/ai-chat` 时，`context` 中已经包含：

- `current_plan`
- `measurements`
- `logs`
- `messages`

本阶段新增：

- `conversation_state`

这样未知型号多轮补全流程可以成立：

1. 用户请求测试未知型号
2. 后端返回 `pending_profile_model`
3. 前端保存该状态并展示“正在补全”
4. 用户补充部分字段
5. 前端把 `conversation_state` 回传
6. 后端继续追问剩余字段
7. 规格补齐后前端收到计划并载入测试点

## BJTagent Status Model

前端引入一个轻量状态映射，不伪造后端内部推理链，只基于当前已知前端状态生成可见标签。

推荐状态：

- `空闲`
- `等待补充未知型号规格`
- `已生成计划`
- `仿真可执行`
- `等待硬件确认`
- `执行中`
- `执行中止`
- `执行完成`

### Mapping Rules

- `执行中`：`busy = true`
- `等待补充未知型号规格`：`conversationState.pending_profile_model` 存在
- `等待硬件确认`：已有计划且 `runMode = hardware` 且当前未执行
- `仿真可执行`：已有计划且 `runMode = simulation` 且当前未执行
- `执行中止`：最近一次执行结果为 `aborted`
- `执行完成`：最近一次执行成功完成
- `已生成计划`：已有计划但不满足上面更具体的执行态
- `空闲`：无计划、无待补全状态、无执行态

状态卡只显示最终外显状态，不显示推理细节。

## Unknown Model Hint UI

如果 `pending_profile_model` 存在，在 AI 面板顶部状态卡内显示轻量补全提示。

显示内容：

- `当前正在补全：XYZ123`
- `已记录字段：NPN / Vceo 40V / Ic 200mA / Ptot 500mW`
- `缺失字段：...`

前端不做复杂表单，也不要求用户点击补全；用户仍通过聊天输入继续回答。

缺失字段通过前端对 4 个目标键的比较得到：

- `bjt_type`
- `vceo_max_v`
- `ic_max_a`
- `p_tot_w`

## BJTagent Action Log

聊天区增加一种 `system` 风格气泡，用于显示更像 Agent 工作推进的行动日志。

这些日志不是隐藏推理链，也不是伪造思维过程；它们只描述前端已经明确知道的状态变化。

推荐文案：

- `BJTagent：识别到未知型号，进入规格补全流程`
- `BJTagent：已记录规格字段，继续等待缺失信息`
- `BJTagent：规格已完整，可生成保守计划`
- `BJTagent：计划已载入测试点`
- `BJTagent：当前为硬件模式，执行前仍需要确认`
- `BJTagent：执行开始，等待测量结果`
- `BJTagent：检测到执行中止，已保留现有测量点`
- `BJTagent：执行完成，结果已返回界面`

### Trigger Sources

行动日志只来自这些可观察事件：

- 收到新的 `conversation_state`
- `pending_profile_fields` 增加
- `pending_profile_model` 首次出现
- 计划载入成功
- 执行开始
- 执行中止
- 执行完成

如果事件未发生，不补日志，不猜测后端内部状态。

## UI Placement

用户已确认主入口放在 `AI 面板顶部`。

因此布局为：

- AI 面板标题：`BJTagent`
- 标题下方：状态卡
- 聊天区：用户消息 / Agent 回复 / `BJTagent` 行动日志
- 输入区：保持现有发送方式

这样能在不拆大结构的前提下，把聊天面板转成 Agent 工作流面板。

## Testing Strategy

### New / Updated Tests

更新：

- [test_frontend_abort_smoke.py](file:///Users/helap/Documents/Project/雨骤/tests/test_frontend_abort_smoke.py)
  - 保持 runtime abort 日志断言

新增：

- `tests/test_frontend_agent_experience_smoke.py`
  - 断言 `conversation_state` 被保存并回传
  - 断言存在 `BJTagent` 状态文案
  - 断言存在未知型号补全提示文案
  - 断言存在关键行动日志文案

### Verification

继续要求：

- `npm run build`
- `python3 -m pytest tests/test_frontend_abort_smoke.py tests/test_gui_smoke.py tests/test_cli_smoke.py -q`

如果新增前端 smoke，则一并执行。

## Risks

- 如果行动日志写得太像真实推理链，容易造成“前端伪造智能过程”的误解
- 如果状态映射覆盖过宽，可能和真实后端状态不一致
- 如果把 `conversation_state` 与已有 `currentPlan` 处理混乱，可能破坏当前计划编辑路径

因此本阶段坚持：

- 只显示可观察状态
- 不展示内部推理链
- 不改后端协议
- 优先保持现有计划编辑与执行路径可用

## Decision

本阶段采用“`BJTagent` 顶部状态卡 + `conversation_state` 回传 + 未知型号轻量提示 + Agent 行动日志 + 最小前端 smoke”方案。
