# 2026-06-06 Agentic Measurement Program Loop

## 阶段目标

把 BJTagent 从“调用固定工具的执行器”推进到“围绕 DUT belief 做实验判断的 agent”。

本阶段重点是建立：

- DUT belief 驱动的测量循环
- typed measurement program
- critic review
- program refinement
- program optimizer
- refined program execution
- sweep / pulse 原语
- pulse 结果诊断并回写 anomaly hypotheses

## 架构变化

新增或强化了以下链路：

```text
DUT belief
-> measurement program
-> critic review
-> program refinement
-> optimizer
-> execute refined primitives
-> update belief
-> extract SPICE twin
-> diagnose residual / pulse signature
```

核心变化：

- `measure` 原语扩展为可执行 `sweep` 和 `pulse`
- critic 不再只给建议，而是能把建议变成 typed primitives
- refined program 不再只输出计划，而是会执行新增测点并更新 belief
- pulse 短/长脉冲对照会生成结构化异常假设

## 核心文件

- `ai/measurement_program.py`
- `ai/pulse_diagnosis.py`
- `ai/tool_runtime.py`
- `ai/unknown_device.py`
- `ai/experiment_summary.py`
- `tests/test_measurement_program.py`
- `tests/test_pulse_diagnosis.py`
- `tests/test_unknown_device_workflow.py`

## 量化数据

本阶段 smoke 任务：

```text
这有个不知道型号的三脚器件，你自己搞清楚它是什么，并给我一份表征报告
```

关键输出数据：

```text
topology hypothesis: NPN_BJT
pinout candidate: A=emitter, B=base, C=collector
topology confidence: 0.78
SPICE twin confidence: 0.76
```

refined program 数据：

```text
added primitives:
- sweep: critic_same_base_drive_vce_sweep
- pulse: critic_short_long_pulse_vce_sat_check

executed primitives: 2
executed points: 5
```

残差改善：

```text
before refined execution overall residual: 0.9751
after refined execution overall residual: 0.6319
delta: 0.3433
```

pulse 诊断：

```text
hypothesis: self_heating_or_thermal_saturation_drift
confidence: 0.55
short pulse width: 100 us
long pulse width: 5000 us
short Vce: 0.1744 V
long Vce: 0.17876 V
Vce delta: 0.00436 V
Vce delta ratio: 0.025
Ic delta ratio: 0.0
```

belief 回写：

```text
anomaly_hypotheses includes:
- name: self_heating_or_thermal_saturation_drift
  source: pulse_diagnosis
  confidence: 0.55
```

## 测试结果

```text
336 passed in 5.23s
```

## API Smoke

API health:

```json
{"ok": true, "service": "bjt-api"}
```

`/api/ai-chat` smoke 确认：

- response 中包含 `pulse 诊断`
- `refined_program_execution.pulse_diagnosis.ok == true`
- `belief.anomaly_hypotheses` 中包含 `source == pulse_diagnosis`

## 已知限制

- 当前 pulse 在 simulation 下使用等效静态点加热漂移近似，不等价于真实硬件脉冲采样
- topology probe 仍是 simulation 结果，尚未接真实 IP-SDK 三端低压探测
- optimizer 当前只做基础重排，还没有基于仪器真实切换代价建模
- SPICE twin 仍是简化模型，未做完整 Gummel-Poon 拟合

## 下一步建议

优先做真实硬件三端低压探测工具：

```text
ip_sdk_low_voltage_pin_probe
```

目标是把 unknown-device workflow 的第一步从 simulation 观察换成真实硬件观察，让 agent 的判断真正来自 DUT。
