# BJTagent 评估可见性增强设计

## 目标

在不大改 agent 核心逻辑、不过度提高 CI 失败风险的前提下，增强 BJTagent 的评估可见性，让回归报告更诚实地暴露当前能力强弱。

本轮重点：

- 统一默认数据集口径到 `数据/transistor_agent_samples.v3.jsonl`
- 扩展 evaluator 软统计能力
- 补少量 regression cases / 主线样本
- 输出一份面向 Codex 的后续 agent 能力改进清单

## 范围

允许修改：

- `scripts/evaluate_agent_samples.py`
- `scripts/run_agent_regression.py`
- `tests/test_agent_dataset.py`
- `数据/agent_regression_cases.jsonl`
- `数据/transistor_agent_samples.v3.jsonl`
- `docs/superpowers/status/*.md`

禁止修改：

- `frontend/src/App.jsx`
- `api_server.py`
- `ai/*.py`
- `app/*.py`
- `measurement/*.py`
- `core/*.py`
- `config/user_transistor_profiles.json`

## 设计决策

### 1. 默认数据集统一到 v3

统一以下默认口径：

- `scripts/evaluate_agent_samples.py`
- `tests/test_agent_dataset.py`

目标是避免：

- README / CI / 主回归脚本使用 v3
- evaluator 默认值和部分测试仍指向旧 `transistor_agent_samples.jsonl`

### 2. evaluator 只增强“软统计”，不新增硬门槛

新增统计维度，但不纳入 `run_agent_regression.py` 的失败判断：

- `expected_model` 的 checked / ok / mismatch
- `expected_diagnosis` 的 checked / ok / mismatch
- `expected_actions` 的 checked / ok / mismatch
- 按 category 汇总的薄弱项
- 报告中显式列出“样本里已写但当前未纳入硬门槛”的字段

原则：

- 可以让报告更诚实
- 不能让现有 `python3 scripts/run_agent_regression.py --json` 因新增软统计而失败

### 3. regression cases 只做少量高价值补充

补充方向：

- 复杂中文测试意图
- 多轮上下文
- 未知型号补全
- 结果解释
- 器件库命令

策略：

- 金样本 `agent_regression_cases.jsonl` 只补少量高价值场景
- 主线 `transistor_agent_samples.v3.jsonl` 可补少量代表性样本
- 不追求一次性把所有能力都拉进硬门槛

### 4. 用状态文档给 Codex 清单，而不是直接改核心

新增一份简短状态文档，说明：

- 当前哪些能力已有样本且已纳入硬评估
- 哪些能力已有样本但只做软统计
- 哪些能力样本仍稀薄
- 建议 Codex 的后续 agent 核心改进优先级

## 报告输出设计

evaluator 报告新增：

- `soft_metrics.model`
- `soft_metrics.diagnosis`
- `soft_metrics.actions`
- `category_breakdown`
- `non_gating_fields`

其中：

- `soft_metrics.*` 只提供 checked / ok / mismatch_count / mismatch_examples
- `category_breakdown` 用于显示各 category 下最常见薄弱项
- `non_gating_fields` 明确说明这些字段当前只是可见性增强，不参与主回归失败判定

## 验证

执行：

```bash
python3 scripts/run_agent_regression.py --json
python3 -m pytest tests/test_agent_dataset.py tests/test_ai_agent.py tests/test_ai_conversation.py tests/test_ai_safety_regression.py -q
```

通过标准：

- 默认口径已统一到 v3
- 回归脚本仍稳定通过
- 新增软统计字段可输出
- 不因 soft metrics 导致主回归失败

## 风险与控制

### 风险 1：软统计结构改动影响旧调用方

控制：

- 保留现有顶层字段与已有结构
- 只追加新字段，不删除旧字段

### 风险 2：补样本过多导致指标波动过大

控制：

- 仅补少量高价值 case
- 不把新增软统计接入失败门槛

### 风险 3：和 Codex 并行冲突

控制：

- 不改 `ai/*.py`
- 不改后端安全执行层
- 只在评估脚本、数据和状态文档层面推进
