# BJTagent 评估可见性状态

## 本轮完成

- evaluator 默认数据集已统一到 `数据/transistor_agent_samples.v3.jsonl`
- `tests/test_agent_dataset.py` 默认口径已统一到 v3
- evaluator 新增软统计：
  - `soft_metrics.model`
  - `soft_metrics.diagnosis`
  - `soft_metrics.actions`
  - `category_breakdown`
  - `non_gating_fields`
- evaluator 继续增强的 breakdown：
  - `soft_metrics.actions.missing_expected_tags`
  - `soft_metrics.actions.missing_by_category`
  - `soft_metrics.diagnosis.missing_expected_tags`
  - `soft_metrics.diagnosis.missing_by_category`
  - `soft_metrics.diagnosis.confusion_pairs`
- 已补少量 regression cases 与主线 v3 样本，用于暴露复杂意图、多轮上下文、未知型号、结果解释、器件库命令的现状

## 当前硬门槛

仍由主回归脚本判定：

- `intent_accuracy`
- `parser.explicit_constraint_accuracy`
- `plan.safety_and_policy_accuracy`
- `safety.behavior_accuracy`
- 既有 pytest 子集

这些门槛没有因为本轮软统计增强而收紧。

## 当前仅做软统计的字段

- `expected_model`
- `expected_diagnosis`
- `expected_actions`

说明：

- 这些字段现在会进入报告
- 会显示 checked / ok / mismatch / mismatch_examples
- 但不会让 `python3 scripts/run_agent_regression.py --json` 直接失败
- 现在还会显示缺失标签排行、按 category 的缺失分布，以及 diagnosis 的常见误判映射

## 当前暴露出的薄弱方向

### 1. 复杂意图链式理解

典型样本：

- “先保守扫一下 S8050，如果 beta 正常再加深”
- “不要超过 10mA，重点看饱和压降”

问题特征：

- 现有 agent 更擅长识别“首个动作”，不擅长把条件性后续步骤纳入计划层表达

### 2. 多轮上下文承接

典型样本：

- “电流再小一点”
- “下一步你自己调整”

问题特征：

- 当前 modify 能力主要覆盖显式参数收紧
- 对“让 agent 自己调整”的自主优化意图承接较弱

### 3. 结果解释质量

典型样本：

- “为什么这个点像饱和了”
- “执行中止了，为什么”

问题特征：

- intent 可能能进 diagnose
- 但 diagnosis tag 和下一步建议动作未被稳定显式表达

### 4. 未知型号补全与保守引导

典型样本：

- “我不确定型号，先按低风险筛查”

问题特征：

- 安全方向是对的
- 但 goal / guidance / follow-up prompts 的细粒度质量仍值得继续打磨

### 5. 器件库命令路由

典型样本：

- “禁用 XYZ123”

问题特征：

- 当前已经有基础路由
- 但多轮确认、字段变更确认、命令覆盖密度仍不足

## 建议 Codex 后续优先级

### P0

- 结构化 `next_actions / completed_actions` 输出
- 诊断 tag 输出或可映射的诊断结构
- 复杂意图拆解与阶段式计划表达
- 多轮上下文下的 modify / autonomous-adjust 路由

### P1

- 危险请求的结构化安全动作，例如 `reject_unsafe / clamp_current / explain_limit`
- aborted / low_beta / open_circuit / short-like / saturation 的下一步建议模板化
- 多轮上下文下的 autonomous-adjust 质量打磨

### P2

- 未知型号补全过程的追问质量与字段完整性判断
- 器件库命令的多轮确认状态机覆盖

## 建议开发顺序

1. 先改 `复杂意图 + 多轮上下文`
2. 再改 `结果解释 + 自动优化计划`
3. 最后补 `未知型号补全 + 器件库命令细化`

这样能最快提升“agent 含金量”，同时保持当前安全门不被扰动。
