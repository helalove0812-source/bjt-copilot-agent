# Unknown Model Guidance Design

## Goal

为 BJT Agent 增加“未知型号追问补全”路径：当用户请求测试未知型号时，系统不再只给兜底计划，而是主动追问关键额定值，在会话内补全后生成更可信的安全计划。

本阶段只做未知型号追问与会话级临时 profile，不做跨会话持久化，不修改晶体管数据库，不实现 PNP 半自动执行。

## Current Problem

当前未知型号通过 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py) 的 fallback profile 进入流程：

- `bjt_type = "UNKNOWN"`
- `vceo_max_v = 12.0`
- `ic_max_a = 0.02`
- `p_tot_w = 0.1`

这保证了安全底线，但存在两个问题：

- 用户体验上，系统只会保守兜底，不会主动把“还缺什么参数”说清楚
- 对话链路上，用户即使补充了 datasheet 信息，系统也没有会话级结构去吸收这些规格并重新生成计划

## Design Choice

本阶段采用“会话内追问状态 + 临时 profile”方案：

- 在 [conversation.py](file:///Users/helap/Documents/Project/雨骤/ai/conversation.py) 中保存待补全状态
- 在会话内逐轮收集未知型号的关键规格
- 当规格收齐时，构造一个会话级临时 profile，交给 planner 生成计划

不采用“只给提示文案、不保存状态”的方案，因为那样用户第二轮回答后系统仍然需要重新猜上下文，闭环能力不足。

## Scope

### In Scope

- 未知型号触发主动追问
- 会话内保存待补全规格
- 支持多轮逐步补全
- 规格齐全后生成基于临时 profile 的安全计划

### Out Of Scope

- 将用户补充的型号写回 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py)
- 跨会话持久化
- PNP 自动或半自动执行
- 用户文案美化或复杂对话风格设计

## Required Fields

第一版只追问并存储 4 个关键字段：

- `bjt_type`
- `vceo_max_v`
- `ic_max_a`
- `p_tot_w`

收齐前不生成正式硬件计划；可以继续保持“待补全”状态并追问剩余字段。

## Conversation State

在 [conversation.py](file:///Users/helap/Documents/Project/雨骤/ai/conversation.py) 的 `AIConversationState` 中新增类似字段：

- `pending_profile_model: str | None`
- `pending_profile_fields: dict[str, float | str]`

语义：

- `pending_profile_model` 表示当前正在补全哪个未知型号
- `pending_profile_fields` 保存当前已知字段

如果用户切换到一个明确的已知型号，待补全状态可以被清空。

## Intent Flow

### Step 1: Unknown Model Request

当用户说：

- “测一下 XYZ123”
- “帮我测这个 MJ-998”

且型号查库命中 fallback profile 时，系统不直接结束，而是进入“待补全”状态，并回复：

- 这是未知型号
- 要安全建计划，请补充：`管型 / Vceo / Ic_max / Ptot`

### Step 2: Partial Field Update

用户接着补充一部分参数时，例如：

- “NPN，40V”

系统更新 `pending_profile_fields`，并继续追问剩余字段：

- 还缺 `Ic_max / Ptot`

### Step 3: Complete and Build

当 4 个字段齐全时，例如：

- “Ic 最大 200mA，Ptot 500mW”

系统构造会话级临时 profile，并基于它生成安全计划。

## Temporary Profile Construction

推荐新增一个会话级 helper，而不是直接改数据库。

可选实现方式：

- 在 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py) 增加一个轻量构造函数，例如：
  - `build_profile_from_fields(model, fields) -> TransistorProfile`
- 或在 planner/对话层本地构造 `TransistorProfile`

推荐放在 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py)，因为 `TransistorProfile` 的定义本来就在这里。

构造出的 profile：

- `model = 用户型号`
- `confidence = "user_supplied"`
- `description = "用户补充规格的临时 profile"`

Planner 使用该 profile 生成计划，但不写回 `_PROFILES`。

## Parsing Rules

第一版本地规则只支持简单、明确的表达：

- 管型：
  - `NPN`
  - `PNP`
- `Vceo`
  - `40V`
  - `Vceo 40V`
- `Ic_max`
  - `200mA`
  - `0.2A`
  - `Ic 最大 200mA`
- `Ptot`
  - `500mW`
  - `0.5W`
  - `功耗 500mW`

不追求复杂自然语言覆盖，第一版只支持高置信度规则提取。

## Planner Integration

目前 [test_planner.py](file:///Users/helap/Documents/Project/雨骤/ai/test_planner.py) 通过 `lookup_transistor(model)` 获取 profile。

阶段四需要允许 planner 接收一个显式 profile 或 profile override，避免必须改数据库。

建议：

- 在 `build_test_plan()` 中增加可选参数 `profile_override`
- 如果提供则优先使用该 profile

这样可以最小化侵入，同时不影响现有已知型号路径。

## User-Facing Responses

第一版文案目标是清晰，不追求花哨。

### Unknown Request

- “这是未知型号。为安全建计划，请补充：管型、Vceo、Ic 最大值、Ptot。”

### Partial Completion

- “已记录：NPN、Vceo 40V。还需要：Ic 最大值、Ptot。”

### Completion

- “已根据你补充的规格生成临时安全计划：……”

## Testing Strategy

### New / Updated Tests

更新：

- `tests/test_ai_conversation.py`
  - 未知型号触发追问
  - 部分字段补全继续追问
  - 全字段补全后生成计划
- `tests/test_ai_agent.py`
  - Agent 保留待补全状态
  - 会话内补全后可生成计划

如需要，可新增：

- `tests/test_transistor_profile_override.py`
  - 验证会话级临时 profile 不写回数据库

### Regression

继续要求：

- `python3 -m pytest -q`
- `python3 scripts/run_agent_regression.py --json`

阶段四第一步不要求马上扩主数据集，但不能破坏当前回归基线。

## Risks

- 如果追问状态与普通 `modify_plan` 流程混在一起，可能干扰已有多轮上下文解析
- 如果字段提取过于宽松，容易把普通约束误识别成 datasheet 规格
- 如果 profile override 做成全局注册，会污染现有数据库语义

因此第一版要坚持：

- 会话内状态
- 高置信度规则提取
- 临时 profile 不落库

## Decision

本阶段采用“会话内追问状态 + 会话级临时 profile + planner profile override”的方案。
