# BJTagent 动作建议结构化设计

## 目标

把 BJTagent 当前分散在：

- `next_action_items`
- `diagnosis_tags`
- `preflight_summary`
- safety / plan / modify 的中文建议文案

中的“动作建议”统一成一套稳定的后端结构化能力。

本轮目标不是做前端消费，而是让后端先稳定产出：

- 已完成动作
- 下一步动作
- 动作标签 taxonomy
- diagnosis 到动作建议的稳定映射

并让 evaluator 能基于这些结构做软统计。

## 范围

### 本轮会做

- 后端动作 taxonomy v1
- `completed_actions` / `next_action_items` 的统一结构
- `plan / modify / safety / diagnosis` 四类路径的动作标签收口
- evaluator 对结构化动作的读取与软统计联动
- 最小必要样本与回归更新

### 本轮不会做

- 不做前端建议卡片
- 不把 `expected_actions` 升级成硬门槛
- 不放宽安全策略
- 不做大规模 UI/协议重构

## 动作 taxonomy v1

本轮统一以下动作标签：

- `create_plan`
- `apply_conservative_defaults`
- `run_wiring_check`
- `modify_plan`
- `clamp_current`
- `clamp_power`
- `increase_points`
- `reject_unsafe`
- `explain_limit`
- `request_hardware_confirmation`
- `suggest_next_step`
- `check_wiring`
- `prompt_pinout_confirm`

这些标签要求：

- 语义单一
- 可复用
- 可评估
- 可展示

## 统一输出结构

后端动作输出分成两层：

### 1. `completed_actions`

表示当前这一轮 agent 已经完成了哪些动作。

示例：

```json
[
  "modify_plan",
  "clamp_current"
]
```

### 2. `next_action_items`

保留现有能力，但收敛成带标签的稳定结构。

建议结构：

```json
[
  {
    "action": "request_hardware_confirmation",
    "reason": "hardware execution still requires explicit confirmation",
    "priority": "high"
  }
]
```

本轮重点不是扩字段复杂度，而是保证：

- `action` 标签稳定
- `reason` 可读
- 不同路径输出风格一致

## 四类路径的动作收口

### 1. plan

典型动作：

- `create_plan`
- `apply_conservative_defaults`
- `run_wiring_check`
- `request_hardware_confirmation`

### 2. modify

典型动作：

- `modify_plan`
- `clamp_current`
- `clamp_power`
- `increase_points`

### 3. safety

典型动作：

- `reject_unsafe`
- `clamp_current`
- `clamp_power`
- `explain_limit`
- `request_hardware_confirmation`

### 4. diagnosis

典型动作：

- `suggest_next_step`
- `check_wiring`
- `prompt_pinout_confirm`
- 以及由 diagnosis tag 映射出来的具体后续动作

## diagnosis 到动作建议映射

`diagnosis_tags` 保持为状态/异常判断层。

在其上新增统一映射逻辑：

- `saturation_suspected` -> `suggest_next_step`
- `bce_reversed` -> `check_wiring`, `prompt_pinout_confirm`
- `overcurrent` -> `clamp_current`, `explain_limit`
- `open_circuit` -> `check_wiring`, `suggest_next_step`

要求：

- diagnosis 是“看见了什么”
- actions 是“下一步该做什么”
- 两层不要混淆

## evaluator 联动

evaluator 继续保持软统计，不进入硬门槛。

本轮要做到：

- 优先读取真实结构化动作输出
- 仅在没有结构化动作时才回退到启发式映射
- 报告继续输出：
  - `soft_metrics.actions`
  - `missing_expected_tags`
  - `missing_by_category`
  - `confusion_pairs`

并新增一项可见性：

- 哪些样本已经命中“真实结构化动作输出”
- 哪些样本仍靠 evaluator 回退映射

## 兼容性要求

- 不破坏现有 `run_agent_regression.py --json`
- 不让 CI 因新增动作结构而失败
- 不改变现有安全硬门槛
- 不要求前端立即适配

## 风险与控制

### 风险 1：和 Codex 当前改动冲突

控制：

- 优先做小而集中的收口
- 避免跨太多文件做大重构

### 风险 2：taxonomy 过大导致实现不稳

控制：

- 只做 v1 必需动作
- 先覆盖 plan / modify / safety / diagnosis 的高频动作

### 风险 3：evaluator 和运行时语义不一致

控制：

- evaluator 优先读取真实结构化输出
- 让回退映射显式可见，便于后续逐步淘汰

## 验证

至少验证：

```bash
python3 scripts/run_agent_regression.py --json
python3 -m pytest -q
cd frontend && npm run build
```

通过标准：

- `run_agent_regression.py --json` 仍为 `ok: true`
- 动作结构开始稳定输出
- `soft_metrics.actions` 报告可见性更强
- 不破坏现有安全与前端基线
