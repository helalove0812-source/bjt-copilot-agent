# User Transistor Profile Memory Design

## Goal

为当前 BJT Agent 增加“未知型号参数沉淀”能力：当用户测试一个库里不存在的 BJT 型号时，系统可以在会话内形成候选 profile，并在测试结束后主动询问是否保存；只有在用户再次明确确认后，才把该型号写入独立 JSON 型号库，供后续会话直接复用。

本阶段目标是让 Agent 具备“可审核的经验沉淀”能力，而不是让 LLM 或一次测试结果直接修改内置晶体管库。

## Current Problem

当前系统已经支持：

- 未知型号进入追问补全流程
- 在会话内收集 `bjt_type / vceo_max_v / ic_max_a / p_tot_w`
- 根据用户补充字段构造临时 profile 并生成计划

但当前能力只停留在会话内：

- 补充得到的 profile 不跨会话保存
- 下次再次测试同型号时，仍会重新进入未知型号流程
- LLM 即使能帮助整理候选参数，也没有受控的“入库”路径

这使系统缺少“沉淀”能力，重复测试同一型号时体验和效率都一般。

## Design Choice

本阶段采用“会话候选 + 用户确认 + 独立 JSON 持久化”方案：

- 继续复用现有未知型号补全流程
- 允许 LLM 在会话内提供候选参数建议
- 候选 profile 只保存在会话状态中，不直接入库
- 测试完成后由 Agent 主动询问是否保存
- 只有用户再发明确确认命令，才写入独立 JSON 型号库
- 运行时查库顺序调整为：用户 JSON 库 -> 内置库 -> fallback

不采用以下方案：

- 自动入库：风险过高，容易把错误 datasheet 或错误推断写死
- 直接写回 `transistor_db.py`：把运行时数据混入源码，不利于维护和审计
- 直接上 SQLite：对当前项目偏重，第一版收益不够高

## Scope

### In Scope

- 未知型号形成会话级候选 profile
- 允许 `LLM 提议 + 用户确认` 作为入库依据
- 新增独立 JSON 用户型号库
- 运行时优先查用户型号库
- 测试完成后主动询问是否保存
- 用户显式确认后落库
- 对重复保存、更新、JSON 损坏等情况给出可预测行为

### Out Of Scope

- 自动修改内置 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py)
- 自动放宽现有硬件安全门
- 将 PNP 入库后开放自动硬件执行
- 自动接受模糊确认词并入库
- 多用户同步、远程配置中心、数据库化管理

## Architecture

本阶段新增 3 个逻辑单元，保持边界清晰：

### 1. User Profile Store

一个独立 JSON 文件，例如：

- `config/user_transistor_profiles.json`

它只保存“用户明确确认后”的型号资料，不保存会话内未确认候选。

### 2. Candidate Profile State

在现有 `pending_profile_model / pending_profile_fields` 基础上，增加“候选 profile”概念：

- 候选可以来自用户明确补充
- 候选也可以叠加 LLM 提议
- 但在用户确认前，它只存在于当前会话中

### 3. Profile Store Integration

运行时查型号时：

1. 先查用户 JSON 库
2. 再查内置 `_PROFILES`
3. 再退回 fallback unknown

这样一旦某型号被确认保存，下次同型号就不再默认进入未知型号补全流程。

## Data Model

### User JSON Schema

建议按“型号名 -> profile”方式存储，查找最直接：

```json
{
  "XYZ123": {
    "model": "XYZ123",
    "bjt_type": "NPN",
    "vceo_max_v": 40.0,
    "ic_max_a": 0.2,
    "p_tot_w": 0.5,
    "package": "TO-92",
    "pinout_hint": "需核对批次引脚定义",
    "description": "用户确认沉淀的型号参数",
    "hfe_typical": [0, 0],
    "confidence": "user_confirmed",
    "source": "llm_plus_user_confirmation",
    "confirmed_by_user": true,
    "created_at": "2026-06-02T12:34:56Z",
    "updated_at": "2026-06-02T12:34:56Z"
  }
}
```

### Required Fields

第一版必须字段：

- `model`
- `bjt_type`
- `vceo_max_v`
- `ic_max_a`
- `p_tot_w`

这些字段足以支撑：

- planner 的保守计划生成
- safety policy 的基础判断
- 型号识别后的已知路径复用

### Optional Fields

第一版可选字段：

- `package`
- `pinout_hint`
- `description`
- `hfe_typical`
- `source`
- `created_at`
- `updated_at`

这些字段有价值，但不应阻塞入库。

### Confidence Semantics

建议明确 4 种来源语义：

- `catalog`: 内置库自带条目
- `fallback`: 未知型号保守兜底
- `user_supplied`: 当前会话内用户补充的临时 profile
- `user_confirmed`: 用户显式确认后写入 JSON 库的 profile

如果 LLM 参与候选生成，不单独引入 `llm_confirmed`。真正允许落库的是“用户确认”，不是 LLM 本身。

## Conversation State

现有 [conversation.py](file:///Users/helap/Documents/Project/雨骤/ai/conversation.py) 已具备：

- `pending_profile_model`
- `pending_profile_fields`

本阶段建议新增轻量状态：

- `candidate_profile`
- `candidate_profile_source`
- `pending_profile_save_confirmation`

语义：

- `candidate_profile`: 当前会话整理出的完整候选 profile
- `candidate_profile_source`: 标记来源，例如 `user_only` 或 `llm_plus_user`
- `pending_profile_save_confirmation`: 当前是否正等待用户显式确认写入库

第一版不需要把状态机拆得过细，避免复杂度膨胀。

## Data Flow

### Step 1: Unknown Model Request

用户请求测试一个未知型号，例如：

- “测一下 XYZ123”

系统查不到用户库和内置库，进入现有未知型号补全流程。

### Step 2: Candidate Profile Build

在补全过程中：

- 用户可以补 `NPN / Vceo / Ic / Ptot`
- 如果启用云端 LLM，LLM 可以给出候选字段建议
- 系统把高置信度用户输入与 LLM 提议整合为 `candidate_profile`

### Step 3: Plan and Test

基于 `candidate_profile` 生成计划并执行本次测试。

此时应明确告诉用户：

- 当前使用的是会话内候选 profile
- 该型号尚未写入本地型号库

### Step 4: Post-Test Save Prompt

仅当以下条件同时成立时，Agent 才主动询问是否保存：

- 当前型号原本不在用户库/内置库
- 本次流程确实使用过 `candidate_profile`
- 已经到达稳定结果点
- 当前不是高风险异常态

推荐主动询问文案：

- “XYZ123 当前使用的是本次会话中的候选规格，尚未保存到本地型号库。”
- “如果这组参数确认可用，你可以回复‘保存这个型号’或‘写入库’，我会将其写入本地型号库供下次直接使用。”

### Step 5: Explicit Confirmation

第一版只接受明确确认命令，例如：

- `保存这个型号`
- `写入库`
- `记住这个 BJT`
- `保存 XYZ123`
- `把 XYZ123 写入库`

以下词语不应当视为确认：

- `可以`
- `好`
- `行`
- `就这样`
- `下次记住`

### Step 6: Persist to User Store

收到明确确认后：

- 写入 `config/user_transistor_profiles.json`
- 将 `confidence` 标为 `user_confirmed`
- 回复用户保存成功

推荐成功提示：

- “已将 XYZ123 写入本地型号库。”
- “后续再次测试该型号时，会优先使用本地已确认参数，不再默认进入未知型号补全流程。”

## Safety Rules

这项能力是“知识沉淀”，不是“安全门放宽”。

以下规则必须保持不变：

- 仍然保留现有 `SafetyGuard`
- 仍然要求硬件确认
- 仍然不允许 `UNKNOWN -> NPN` 自动降级
- 即使保存成功，如果型号是 `PNP`，自动硬件执行仍然阻断
- 入库不代表该型号可以绕过 `allow_hardware` 或 token/确认短语

如果保存后的条目与硬件执行策略冲突，优先遵守现有安全策略，而不是遵守资料库。

## Conflict Handling

### Existing Model in User Store

如果用户 JSON 库里已存在同型号：

- `保存这个型号` 默认不覆盖
- Agent 提示“该型号已存在，如需更新，请明确说明‘更新这个型号’”

### Update Flow

第一版建议把“新增”和“更新”分开：

- `保存这个型号`: 只用于新增
- `更新这个型号`: 单独触发更新路径

这样可以避免误覆盖已确认资料。

### JSON Corruption

如果用户 JSON 文件损坏或无法解析：

- 不应导致整个 Agent 崩溃
- 应记录错误并回退到内置库 + fallback 流程
- 在用户尝试保存时，明确返回“本地型号库存储失败，请先修复配置文件”

### Partial Candidate

如果候选字段不完整：

- 不进入保存确认阶段
- 不允许写入用户库

### Abnormal Test Result

出现以下情况时，默认不主动建议保存：

- 硬件执行中止
- 检测结果不是明确 `NPN`
- 当前结果与候选参数明显冲突
- 当前仍然是 fallback 或不完整 profile

这样“沉淀”代表的是受控知识，而不是把任何一次测试结果都记录下来。

## File Placement

推荐新增：

- `config/user_transistor_profiles.json`

如需配套 loader/store helper，推荐新增独立模块，而不是继续堆在 [transistor_db.py](file:///Users/helap/Documents/Project/雨骤/ai/transistor_db.py) 里。

推荐职责划分：

- `transistor_db.py`: 内置 profile 定义、标准化、fallback
- 新模块：用户 profile store 的读取、校验、保存

这样可以避免把“静态内置库”和“运行时持久化库”混成一个文件。

## Testing Strategy

### New / Updated Tests

建议优先补这些测试：

- `tests/test_transistor_profile_store.py`
  - 读取空库
  - 保存新型号
  - 重复保存不覆盖
  - 显式更新才覆盖
  - JSON 损坏时优雅失败

- `tests/test_ai_conversation.py`
  - 未知型号形成候选 profile
  - 触发“是否保存”提示
  - 只有明确命令才进入落库

- `tests/test_ai_agent.py`
  - 会话内候选 profile 可用于建计划
  - 保存成功后后续会话同型号直接命中用户库

- `tests/test_transistor_db.py`
  - 查找顺序为“用户库 -> 内置库 -> fallback”

### Verification

实施后继续要求：

- `python3 -m pytest -q`
- `python3 scripts/run_agent_regression.py --json`

如果引入新的入库确认语句或状态，需要补回归样本，但不应为了入库功能破坏现有 safety 三项 100% 指标。

## Risks

- 如果把 LLM 提议直接当成已确认资料，容易把错误参数写入长期库
- 如果把保存确认做得太宽松，普通对话可能误触发落库
- 如果把用户库读取失败当成致命错误，会影响整个 Agent 可用性
- 如果把用户库条目优先级做错，可能导致已沉淀型号仍走 fallback

因此第一版必须坚持：

- 候选与正式入库分离
- 显式确认而不是模糊确认
- 用户库错误隔离，不拖垮主流程
- 安全策略优先于资料库存储

## Decision

本阶段采用“现有未知型号补全流程 + 会话候选 profile + LLM 提议但不直接入库 + 测试后主动询问 + 用户显式确认后写入独立 JSON 型号库”的方案。
