# Agent Current Status

## Purpose

这份文档记录 2026-06-02 时点 BJT 自动化测试 Agent 的当前实现状态，用于补充
`docs/superpowers/plans/` 与 `docs/superpowers/specs/` 中的阶段性设计文档。

说明：

- `plans/` 和 `specs/` 主要是设计与实施过程文档
- 当前事实以代码、测试、回归脚本和本状态文档为准

## Current Position

当前系统应准确表述为：

- 规则 + LLM 可选辅助 + 本地安全策略 + 数据驱动回归评估 的 BJT 自动化测试 Agent

不应将其描述为纯神经网络或纯机器学习系统。

## Verified Commands

当前推荐给用户的主命令：

```bash
python3 scripts/run_agent_regression.py --json
python3 -m pytest -q
```

说明：

- `scripts/run_agent_regression.py --json` 是当前推荐的统一回归入口
- `python3 -m pytest -q` 是当前推荐的全量测试入口

## Dataset Status

当前回归数据主线：

- 金样本：`数据/agent_regression_cases.jsonl`
- 主样本：`数据/transistor_agent_samples.v3.jsonl`

其中：

- `数据/transistor_agent_samples.v3.jsonl` 是当前主线数据集
- `scripts/run_agent_regression.py` 默认会加载该 v3 主数据集

## Unknown Model Guidance

当前未知型号行为：

- 未知型号先进入保守引导路径
- Agent 会追问：
  - `管型`
  - `Vceo`
  - `Ic 最大值`
  - `Ptot`
- 规格补齐后，系统使用会话级临时 profile 生成安全计划
- 未知型号不会直接进入自动硬件执行

实现要点：

- `AIConversationState` 保存 `pending_profile_model` 与 `pending_profile_fields`
- planner 支持 `profile_override`
- fallback profile 仍是安全兜底

## PNP Guidance

当前 `PNP` 行为：

- `PNP` 请求可以生成保守 / 引导计划
- 默认引导目标偏 `screening`
- 默认深度偏 `conservative`
- 响应会明确提示接线方向、datasheet 和引脚核对
- 自动硬件执行仍被阻断

这意味着：

- `PNP` 不再只是硬拒绝
- 但当前自动执行路径仍只开放 `NPN`

## Hardware Confirmation Semantics

需要区分 CLI 与 `TestAgent` 两条路径：

### `TestAgent`

程序内 `TestAgent.run_turn()` 的硬件执行需要同时满足：

- 调用方显式允许：`allow_hardware=True`
- 当前计划通过安全策略判定
- 提供有效的一次性硬件确认 token

如果缺少有效 token：

- Agent 会返回 `hardware_confirmation_required=True`
- 并签发一次性 token

### CLI

`ai_cli.py` 是较薄的封装层：

- `--mode hardware` + `--execute` + `--confirm-hardware` 会把显式确认直接传给执行层
- CLI 不走 `TestAgent` 的多轮 token 签发交互

因此文档描述时必须明确区分：

- CLI 的显式确认参数
- `TestAgent` 的 `allow_hardware + token` 组合语义

## Runtime Abort Guard

当前 runtime abort guard 的范围：

- 只用于 `hardware` 逐点执行
- 不用于 `simulation`

当前中止条件：

- `Ic` 超过计划上限
- 功耗超过计划上限
- 出现明显两点失稳趋势

中止后会返回结构化结果，例如：

- `aborted`
- `abort_reason`
- `abort_tags`
- `aborted_after_index`

## Regression And CI

当前 CI 工作流：

- `.github/workflows/agent-regression.yml`

当前应与 README 保持一致，执行：

```bash
python3 scripts/run_agent_regression.py --json
```

## Notes On Historical Docs

以下文档仍可作为设计参考，但应视为阶段性文档：

- `docs/superpowers/specs/2026-06-02-agent-safety-policy-design.md`
- `docs/superpowers/specs/2026-06-02-agent-runtime-abort-design.md`
- `docs/superpowers/specs/2026-06-02-unknown-model-guidance-design.md`
- `docs/superpowers/specs/2026-06-02-pnp-guidance-design.md`
- `docs/superpowers/plans/2026-06-02-agent-regression-baseline.md`
- `docs/superpowers/plans/2026-06-02-agent-runtime-abort.md`
- `docs/superpowers/plans/2026-06-02-unknown-model-guidance.md`
- `docs/superpowers/plans/2026-06-02-pnp-guidance.md`

这些文档的用途是说明“为什么这样做”和“当时打算怎么做”，不是替代当前实现状态。
