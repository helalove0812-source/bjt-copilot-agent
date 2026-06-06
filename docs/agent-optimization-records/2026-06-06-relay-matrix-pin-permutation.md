# 2026-06-06 Relay Matrix Pin Permutation

## 阶段目标

把 unknown-device workflow 的拓扑探测入口从固定 BJT fixture response 继续推进到 relay-matrix 风格的 A/B/C 任意两端低压扫描抽象。

目标是让 agent 的第一步更接近真实测试工程师行为：

```text
任选两脚
-> 正反向低压探测
-> 判断公共端
-> 推断 BJT / diode array / FET 候选
```

## 架构变化

新增 relay matrix probe 抽象：

```text
relay_matrix_pin_probe
```

核心路径：

```text
measurement.pin_probe.run_relay_matrix_pin_permutation_probe
-> app.services.run_relay_matrix_pin_probe
-> ai.tool_runtime.relay_matrix_pin_probe
-> unknown-device workflow topology_probe
```

simulation 下支持完整有序 pair scan：

```text
A -> B
B -> A
C -> B
B -> C
A -> C
C -> A
```

hardware 下如果 driver 没有 `relay_matrix_connect`，明确返回：

```text
blocked_reason: relay_matrix_unavailable
```

并回退到已有 `low_voltage_pin_probe` fixture path。

## 核心文件

- `measurement/pin_probe.py`
- `app/services.py`
- `ai/tool_runtime.py`
- `ai/unknown_device.py`
- `tests/test_pin_probe.py`
- `tests/test_tool_call_agent.py`
- `tests/test_unknown_device_workflow.py`

## 量化数据

新增工具：

```text
relay_matrix_pin_probe
```

simulation relay scan:

```text
pair_results: 6
capability.relay_matrix_connect: true
source: relay_matrix_pin_probe
```

unknown-device workflow:

```text
topology_probe.probe_result.source: relay_matrix_pin_probe
topology hypothesis: NPN_BJT
topology confidence: >= 0.85
```

硬件 capability fallback:

```text
driver without relay_matrix_connect
-> ok: false
-> blocked_reason: relay_matrix_unavailable
-> fallback_tool: low_voltage_pin_probe
```

测试结果：

```text
340 passed in 17.05s
```

## API / Workflow 影响

unknown-device workflow 现在优先使用 relay matrix probe。

如果 relay matrix 不可用，则自动回退到 fixed fixture low-voltage probe。

这让上层 agent 判断接口稳定为：

```text
topology_probe -> observations -> topology_hypotheses
```

后续接真实继电矩阵时，不需要重写 agent reasoning/report 层。

## 已知限制

- 当前真实硬件 driver 还没有 `relay_matrix_connect`
- hardware pair permutation 仍未执行真实 A/B/C 交叉扫描
- simulation pair matrix 目前建模为典型 NPN 三脚器件

## 下一步建议

实现真实 relay matrix driver capability：

```text
driver.relay_matrix_connect(source_pin, sink_pin)
driver.relay_matrix_disconnect_all()
driver.pin_pair_probe(source_pin, sink_pin, voltage, current_limit)
```

然后让 `run_relay_matrix_pin_permutation_probe(..., mode="hardware")` 执行真实 pair matrix。
