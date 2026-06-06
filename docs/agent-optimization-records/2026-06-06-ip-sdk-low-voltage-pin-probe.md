# 2026-06-06 IP-SDK Low Voltage Pin Probe

## 阶段目标

把 unknown-device workflow 的第一步从纯 simulation 拓扑观察，推进为可替换真实硬件的低压三端探测工具。

目标链路：

```text
low_voltage_pin_probe
-> topology observations
-> topology hypotheses
-> autonomous unknown-device workflow
```

## 架构变化

新增 `low_voltage_pin_probe` 工具，封装 Rainfall/IP-SDK fixture path。

当前实现分两层：

- `measurement/pin_probe.py`
  - `run_low_voltage_three_pin_probe`
  - simulation 下返回完整三端拓扑观察
  - hardware 下通过现有 `build_runtime -> PyRDDriver` 路径进行低压 fixture 响应探测
- `app/services.py`
  - `run_low_voltage_pin_probe`
- `ai/tool_runtime.py`
  - tool schema: `low_voltage_pin_probe`
  - safety: `max_probe_voltage_v <= 1.2`
  - safety: `max_probe_current_a <= 0.001`
  - hardware mode requires `allow_hardware=true` and valid token
- `ai/unknown_device.py`
  - `topology_hypotheses_from_probe_result`

unknown-device workflow 现在优先调用：

```text
self.low_voltage_pin_probe(...)
```

而不是直接使用硬编码 topology observations。

## 核心文件

- `measurement/pin_probe.py`
- `app/services.py`
- `ai/tool_runtime.py`
- `ai/unknown_device.py`
- `tests/test_tool_call_agent.py`
- `tests/test_unknown_device_workflow.py`

## 量化数据

新增工具：

```text
low_voltage_pin_probe
```

simulation smoke:

```text
source: ip_sdk_low_voltage_pin_probe
observations: present
topology hypothesis: NPN_BJT
```

hardware safety:

```text
mode=hardware without allow_hardware -> blocked_reason=hardware_not_allowed
```

测试结果：

```text
337 passed in 13.57s
```

## API / Workflow 影响

unknown-device workflow 的 `topology_probe` 现在包含：

```text
probe_result.source == ip_sdk_low_voltage_pin_probe
```

这表示 agent 的拓扑判断入口已经从固定 simulation 文本迁移到了可替换的探测 API。

## 已知限制

- 当前硬件 path 使用现有 BJT fixture 的 V+ / W1 / W2 / scope 能力，不是任意三端 relay matrix
- arbitrary A/B/C permutation 仍需要后续 `relay_matrix_connect` 或夹具切换支持
- hardware 下真实三端 PN 结正反向矩阵扫描还未完成
- 当前工具已经具备安全门控、schema、postcondition 和 workflow 接入，可作为后续硬件能力落点

## 下一步建议

实现 relay-matrix 风格的 pin permutation 层：

```text
relay_matrix_connect(A, B, C)
pin_probe_pair(source_pin, sense_pin, polarity)
```

然后把 `low_voltage_pin_probe` 从 fixture response 升级为真正的三端矩阵扫描。
