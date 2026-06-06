# 2026-06-06 AIDE Active-Inference Core

## 背景

用户提供 `BJTAgent_Active_Inference_Architecture.md`，要求把 BJTagent 从“工具调用器”继续推进为“像测试工程师一样测试、判断、补测”的 AIDE（Active-Inference Device Engineer）模式。

本阶段选择落地 M1/L2-L4/L10 的最小闭环：

- 类型化实验目标：自然语言或测试计划 -> `ExperimentGoal`
- 主动推断布点：DUT belief -> 信息增益/成本/安全过滤后的下一批测点
- 执行溯源：工具调用、目标编译、布点、测量、belief 更新、模型提取写入 provenance DAG
- VM 侧运行监视：单点测量后独立检查 Ic、功耗、异常趋势；仿真记录，硬件阻断

## 新增/修改文件

- 新增 `ai/experiment_goal.py`
  - `ExperimentGoal`
  - `compile_experiment_goal`
  - `goal_from_plan`
- 新增 `ai/active_inference.py`
  - `ActiveInferenceCandidate`
  - `BatchDesign`
  - `design_next_measurement_batch`
- 新增 `ai/provenance.py`
  - `ProvenanceDAG`
  - `ProvenanceEvent`
- 修改 `ai/tool_runtime.py`
  - 新增工具：
    - `compile_experiment_goal`
    - `design_next_batch`
    - `read_experiment_provenance`
  - `run_adaptive_characterization` 改为使用主动推断 batch design
  - `run_static_point` 接入 runtime monitor
  - SPICE twin / residual follow-up / unknown-device report 输出 provenance
- 修改 `ai/spice_twin.py`
  - 残差补测候选去重后为空时，增加邻近判别点 recovery pass
- 修改 `ai/measurement_program.py`
  - critic 在饱和边界不确定时主动加入短/长脉冲判别
- 修改 `ai/experiment_summary.py`
  - 摘要显示 AIDE 目标和第一批主动布点信息
- 新增 `tests/test_active_inference_goal.py`

## 行为变化

以前自适应循环的下一步主要来自启发式候选排序。现在每个候选测点会被结构化评分：

| 字段 | 含义 |
| --- | --- |
| `uncertainty_target` | 该点主要减少哪类 belief 不确定性 |
| `prior_uncertainty` | 测量前该目标的不确定度 |
| `expected_information_gain` | 近似预期信息增益 |
| `estimated_cost` | 包含源重配、热预算等的代价估计 |
| `utility` | 信息增益 / 代价 |
| `safety_status` | 是否通过静态安全过滤 |
| `safety_reasons` | 通过或拒绝原因 |

`run_adaptive_characterization` 的 trace 现在包含：

- `aide_goal`
- `active_inference_design`
- `selected/rejected candidates`
- `total_expected_information_gain`
- `covered_uncertainty_targets`
- `provenance`

## 验证数据

局部回归：

```text
python3 -m pytest tests/test_active_inference_goal.py tests/test_unknown_device_workflow.py tests/test_tool_registry.py -q
13 passed in 0.11s
```

扩展相关回归：

```text
python3 -m pytest tests/test_dut_belief.py tests/test_unknown_device_workflow.py tests/test_tool_registry.py tests/test_tool_call_agent.py -q
36 passed in 0.15s
```

## 关键修复

主动布点变强后，残差补测阶段曾出现“原候选点已被前序自适应测过，去重后无新增点”的情况。已修复为：

1. 先按 residual diagnosis 生成候选；
2. 去重和 safety filter；
3. 若为空，自动生成 coverage / neighboring recovery candidates；
4. 再做 safety filter。

这让 agent 更像工程师：原计划测点被覆盖后，会临场换成邻近判别点，而不是停止。

## 当前局限

- 信息增益是可解释启发式近似，还不是完整 nested Monte Carlo BOED。
- `ExperimentGoal` 目前为 deterministic compiler；LLM 可在云模式参与语义边界，但内环仍保持确定性。
- Provenance DAG 已有事件结构，但还没有文件持久化和前端实验笔记视图。

## 下一步建议

1. 把 provenance DAG 持久化为每次实验的 JSONL/Markdown notebook。
2. 增加 compact-model posterior 的参数可信区间，不只给 MAP `.model`。
3. 做 resource lease / relay fixture lock，让硬件执行 VM 有真正的独占实验台语义。
