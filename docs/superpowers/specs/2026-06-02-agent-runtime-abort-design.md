# Agent Runtime Abort Design

## Goal

为 BJT Agent 增加执行中的安全中止机制，在 `hardware` 模式下根据实时测量结果决定是否提前停止后续测量，并将中止原因结构化返回给上层。

本阶段只做“检测到异常 -> 安全停机 -> 上报”，不做自动降参数重试，不改 `simulation` 路径，不改用户意图解析。

## Current Problem

当前执行链路在 [tools.py](file:///Users/helap/Documents/Project/雨骤/ai/tools.py) 中按计划逐点执行：

- 执行前有统一策略 gate
- 执行中每个点会经过 [static.py](file:///Users/helap/Documents/Project/雨骤/measurement/static.py) 的单点 `SafetyGuard`
- 但执行层本身没有“根据已经测到的结果决定中止整轮执行”的闭环能力

这意味着：

- 即使已经出现明显异常趋势，执行层仍会继续跑后续点
- Agent 只能在执行完成后做总结，不能在执行中给出“已安全停机”的结构化结果
- 后续若要做自动降参数或半自动决策，没有运行时判据层可以复用

## Design Choice

本阶段采用独立运行时判据层，而不是把执行中判据继续塞进 [safety.py](file:///Users/helap/Documents/Project/雨骤/ai/safety.py) 或 [tools.py](file:///Users/helap/Documents/Project/雨骤/ai/tools.py)。

推荐新增：

- `ai/runtime_guard.py`

原因：

- [safety.py](file:///Users/helap/Documents/Project/雨骤/ai/safety.py) 负责执行前策略和计划 clamp
- 执行中判据是另一类职责，和“执行前是否允许开始”不同
- 将它拆成独立模块，可以保持边界清晰，也便于后续扩展自动重试或半自动建议

## Scope

### In Scope

- 仅 `hardware` 模式启用运行时中止判据
- 单点电流超限中止
- 单点功耗超限中止
- 简单两点趋势异常中止
- 在执行结果中返回结构化 `aborted` 信息
- 保留已测点，并确保仍执行关断和资源释放

### Out Of Scope

- `simulation` 路径接入运行时中止
- 自动降参数
- 自动重试
- 复杂三点或更长窗口趋势分析
- 用户提示文案统一重构

## Runtime Guard API

新增两个轻量数据结构和一个纯函数：

- `RuntimeAbortDecision`
  - `should_abort: bool`
  - `reason: str`
  - `tags: list[str]`
- `check_abort_after_point(plan, point, history) -> RuntimeAbortDecision`

其中：

- `plan` 提供当前允许的 `ic_limit_a`、`power_limit_w`
- `point` 是刚测完的当前点
- `history` 是此前已经接受的测量点列表

这个接口不负责做设备动作，只返回判定。

## Abort Rules

### Rule 1: Ic Hard Limit

如果当前点满足：

- `point["Ic"] > plan.ic_limit_a`

则立即中止，标签为：

- `runtime_ic_limit_exceeded`

原因文本明确指出当前电流超过计划上限。

### Rule 2: Power Hard Limit

如果当前点满足：

- `point["Vce"] * point["Ic"] > plan.power_limit_w`

则立即中止，标签为：

- `runtime_power_limit_exceeded`

原因文本明确指出当前功耗超过计划上限。

### Rule 3: Two-Point Trend

仅当 `history` 非空时检查最近两点趋势。

如果当前点和前一测量点同时满足：

- `Ic` 明显上升
- `Vce` 明显下降

则判定为疑似失稳或热风险趋势，立即中止，标签为：

- `runtime_instability_trend`

第一版采用固定、保守阈值：

- `Ic` 增量至少 `0.002 A`
- `Vce` 降量至少 `0.5 V`

这样能覆盖明显异常，但尽量减少误停。

## Execution Flow Changes

在 [tools.py](file:///Users/helap/Documents/Project/雨骤/ai/tools.py) 的逐点循环中：

1. 测一个点
2. 将该点转成字典并追加到临时结果
3. 如果 `mode == "hardware"`，调用 `check_abort_after_point(...)`
4. 若需要中止：
   - 标记 `result["aborted"] = True`
   - 写入 `abort_reason`
   - 写入 `abort_tags`
   - 写入 `aborted_after_index`
   - 立即停止后续测量
5. 无论是否中止，`finally` 中仍执行 `disable_all()` / `emergency_off()` / `close()`

## Result Schema

执行结果新增可选字段：

- `aborted: bool`
- `abort_reason: str`
- `abort_tags: list[str]`
- `aborted_after_index: int`

语义如下：

- 未触发运行时中止时，这些字段可以不存在或 `aborted=False`
- 触发运行时中止时，必须存在并包含明确原因

已有字段 `skipped` 的语义保持不变：

- `skipped` 表示执行前就没有开始
- `aborted` 表示执行已经开始，但中途因安全判据被停止

## Agent Behavior

本阶段不让 [agent.py](file:///Users/helap/Documents/Project/雨骤/ai/agent.py) 自动重试。

Agent 对运行时中止结果只做两件事：

- 保留执行结果与已测点
- 把 `aborted` 信息交给现有摘要和后续诊断使用

如果后续需要自动降参数，这会成为阶段三后半或阶段四的工作，不在本次实现中完成。

## Testing Strategy

### New Tests

新增：

- `tests/test_ai_runtime_guard.py`

覆盖：

- `Ic` 超限触发中止
- 功耗超限触发中止
- 两点趋势异常触发中止
- 正常点不误判

### Updated Tests

更新 [test_execution_safety.py](file:///Users/helap/Documents/Project/雨骤/tests/test_execution_safety.py)：

- `hardware` 模式测到异常后中止
- 中止后保留已测点
- 返回 `aborted`、`abort_reason`、`abort_tags`
- 中止后仍执行驱动关断与关闭

### Regression

继续要求：

- `python3 -m pytest -q`
- `python3 scripts/run_agent_regression.py --json`

全部通过，且不能降低当前阶段二的安全基线。

## Risks

- 趋势阈值过严会导致误停
- 趋势阈值过松则只会少挡一部分风险，但不会突破现有硬上限
- 如果把 `aborted` 和 `skipped` 混用，会让上层难以判断“没开始”还是“中途停机”

因此第一版优先保证：

- 字段语义清晰
- 只拦截明显异常
- 不引入自动决策副作用

## Decision

本阶段采用“独立运行时判据层 + hardware only + 硬阈值加两点趋势”的方案。
