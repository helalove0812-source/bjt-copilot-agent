# Agent Safety Policy Design

## Goal

为 BJT Agent 新增一个统一安全策略层，集中管理两类逻辑：

- 计划层安全收口：对 `TestPlan` 的 `Ic / Pmax / Vcc` 上限做统一 clamp
- 执行层放行判定：统一判断 `allow / deny / require_confirm`

本阶段不修改业务目标识别，不改变硬件底线，不新增自动重试，也不统一改写用户提示文案。

## Current Problem

当前安全逻辑分散在三处：

- `ai/test_planner.py`
  - 计算基础上限
  - 将计划数值 clamp 到 `HwConfig`
  - 给 PNP / fallback profile 附带安全说明
- `ai/tools.py`
  - 执行前阻断未显式允许的 hardware 模式
  - 阻断非 NPN 自动执行
  - 运行时再次用计划值收缩 `HwConfig`
- `ai/agent.py`
  - 管理硬件确认 token
  - 决定何时 `require_confirm`

这样的问题是：

- 同一个安全规则的“来源”不唯一
- planner 和 executor 都在做限制，测试要分别覆盖
- 后续做闭环执行时，没有统一的策略判定入口

## Proposed Approach

新增 `ai/safety.py`，作为单一策略层，提供两个纯函数和两个轻量数据结构：

- `clamp_plan_to_policy(plan: TestPlan, cfg: HwConfig) -> TestPlan`
- `evaluate_execution_request(plan: TestPlan, mode: str, allow_hardware: bool, token_valid: bool) -> ExecutionPolicyDecision`

推荐配套数据结构：

- `PlanPolicyResult`
  - `plan: TestPlan`
  - `tags: list[str]`
  - `changed: bool`
- `ExecutionPolicyDecision`
  - `status: Literal["allow", "deny", "require_confirm"]`
  - `reasons: list[str]`
  - `tags: list[str]`

第一版先不强制所有调用方都消费 `tags`，但测试会用它们做断言。

## Responsibilities

### `ai/safety.py`

负责：

- 基于 `HwConfig` 对计划上限做统一 clamp
- 统一生成策略标签，例如：
  - `clamped_to_hardware_max`
  - `requires_hardware_confirmation`
  - `blocked_hardware_execution`
  - `pnp_auto_execution_blocked`
  - `unknown_model_fallback`
- 给执行层返回唯一的放行结论

不负责：

- 解释用户意图
- 生成测试目标与扫描点
- 真正执行硬件

### `ai/test_planner.py`

调整为：

- 仍负责生成“候选计划”
- 不再直接承担最终安全 clamp 的唯一职责
- 在 `build_test_plan()` 返回前调用 `clamp_plan_to_policy()`

这样 planner 输出的 plan 仍然天然安全，但 clamp 规则来源被挪到 `ai/safety.py`。

### `ai/tools.py`

调整为：

- 执行前调用 `evaluate_execution_request()`
- 根据 `status` 决定：
  - `allow`：继续执行
  - `deny`：返回 `skipped=True`
  - `require_confirm`：原则上不在这里发生；若发生，按 deny 处理并带理由
- `_config_from_plan()` 继续把 plan 值映射到运行时配置，但不再承担“策略定义”

### `ai/agent.py`

调整为：

- 继续保留 token 的生成和校验
- 在执行 hardware 前调用 `evaluate_execution_request()`
- 当返回 `require_confirm` 时，复用当前 token 机制
- `allow_hardware` 和 token 是否有效，只作为策略函数输入，不再在 `run_turn()` 中散落判断

## Safety Rules In Scope

第一版统一以下规则：

1. `Ic / Pmax / Vcc` 不能超过 `HwConfig` 硬上限
2. 未知型号允许生成计划，但需要带 `unknown_model_fallback`
3. PNP 可以生成计划，但自动执行必须 deny
4. hardware 执行必须同时满足：
   - `allow_hardware == True`
   - token 有效
   - `plan.bjt_type == "NPN"`
5. simulation 不需要 token，但仍受计划安全上限约束

## Out Of Scope

本阶段明确不做：

- 自动重试
- 运行中实时中止判据
- 用户提示文案统一化
- PNP 半自动引导路径
- 未知型号追问补全

## Testing Strategy

新增或更新测试时，优先验证策略层，而不是在高层重复断言。

### 新增测试

- `tests/test_ai_safety_policy.py`
  - 验证 `clamp_plan_to_policy()`
  - 验证 `evaluate_execution_request()`
  - 断言 `allow / deny / require_confirm` 和策略标签

### 更新现有测试

- `tests/test_ai_safety_regression.py`
  - 改为更多依赖 `ai/safety.py` 的结果
- `tests/test_execution_safety.py`
  - 保留执行层行为测试，但减少对分散判断细节的依赖

### 回归命令

继续使用：

- `python3 scripts/run_agent_regression.py`
- `python3 -m pytest -q`

目标是不降低当前回归基线，特别是：

- `plan.safety_and_policy_accuracy == 1.0`
- 金样本 safety 行为维持 100%

## Migration Plan

1. 新增 `ai/safety.py` 与策略层单测
2. 将 `build_test_plan()` 的最终 clamp 改为调用策略层
3. 将 `TestAgent.run_turn()` 的 hardware 放行判断改为策略层
4. 将 `execute_plan()` 的前置 gate 改为策略层
5. 运行回归与全量 pytest，确认行为不退化

## Risks

- 如果 planner 和 executor 同时做 clamp，但实现细节不一致，可能出现回归
- 如果策略层返回的 reason 改得太大，可能打断现有测试文案断言
- 如果一次性把提示文案和标签都统一，改动面会超出阶段二目标

## Decision

本阶段采用“判定 + clamp 一起收口”的方案，但只统一策略来源与判定流程，不扩大到用户消息文案层。
