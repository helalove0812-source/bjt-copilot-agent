# BJTagent 3-Pin DUT Relay Fixture v1 PCB 板绘图指南

## 目标

这块板子的目标是让雨骤 Model S 通过软件自动把未知三脚器件 A/B/C 接到 `V+ / W1 / GND / CH1 / CH2`，实现自动摸引脚、低压拓扑判断、BJT 表征。

它不是普通三极管测试板，而是 **3 个 DUT pin 到 6 个测试节点的 18 路默认断开继电器矩阵板**。雨骤负责输出和测量，板子负责安全限流、保护和自动换线。

## 总体结构

```text
雨骤 Model S 接口
    |
    |-- V+
    |-- W1
    |-- W2 预留
    |-- CH1
    |-- CH2
    |-- GND
    |
保护/限流网络
    |
继电器矩阵
    |
DUT 插座 A / B / C
```

PCB 建议分 5 个区域：

```text
[雨骤接口区]  [限流保护区]  [继电器矩阵区]  [DUT插座区]
                         [MCU/USB控制区]
```

## 雨骤 Model S 接口

PCB 上做一个 8 到 10 pin 接线端子或排针：

```text
J1_RAINDROP
1  VPLUS        接雨骤 V+
2  W1           接雨骤 W1
3  W2           接雨骤 W2，预留
4  CH1          接雨骤 Scope CH1
5  CH2          接雨骤 Scope CH2
6  GND          接雨骤 GND
7  USB_5V_EXT   可选，给继电器/MCU供电
8  GND
```

继电器和 MCU 供电不要直接从雨骤模拟输出取电。建议用独立 USB 5V 给继电器板供电，GND 和雨骤 GND 共地。

## DUT 插座

```text
J2_DUT
1  DUT_A
2  DUT_B
3  DUT_C
```

建议同时放：

```text
1. 三孔直插座 TO-92
2. 3pin 排针
3. 弹簧夹/接线端子焊盘
```

这样以后既能插三极管，也能夹未知器件。

## 核心测试节点

板内定义这些 net：

```text
FORCE_VPLUS_RC     = V+ 经 R_C 后的集电极偏置
FORCE_W1_RB        = W1 经 R_B 后的基极/探测偏置
FORCE_W1_PROBE     = W1 经大电阻后的低压探测源
FORCE_GND          = GND
SENSE_CH1          = CH1 经保护后的测量输入
SENSE_CH2          = CH2 经保护后的测量输入
OPEN               = 不连接
```

推荐阻值：

```text
R_C          220 ohm，0.25W 或 0.5W
R_B          22k ohm
R_PROBE      47k ohm 或 100k ohm
R_CH1        10k ohm，串在 CH1 前
R_CH2        10k ohm，串在 CH2 前
R_PIN_A/B/C  100~330 ohm，每个 DUT pin 串一个小保护电阻
```

## 继电器矩阵

每个 DUT pin 都要能切到这些节点：

```text
DUT_A -> FORCE_VPLUS_RC
DUT_A -> FORCE_W1_RB
DUT_A -> FORCE_W1_PROBE
DUT_A -> FORCE_GND
DUT_A -> SENSE_CH1
DUT_A -> SENSE_CH2

DUT_B -> 同上
DUT_C -> 同上
```

完整矩阵是 `3 x 6 = 18` 路开关。建议第一版一步到位直接做 18 路继电器矩阵。

```text
K_A_VP      DUT_A <-> FORCE_VPLUS_RC
K_A_W1RB    DUT_A <-> FORCE_W1_RB
K_A_W1P     DUT_A <-> FORCE_W1_PROBE
K_A_GND     DUT_A <-> FORCE_GND
K_A_CH1     DUT_A <-> SENSE_CH1
K_A_CH2     DUT_A <-> SENSE_CH2

K_B_VP      DUT_B <-> FORCE_VPLUS_RC
K_B_W1RB    DUT_B <-> FORCE_W1_RB
K_B_W1P     DUT_B <-> FORCE_W1_PROBE
K_B_GND     DUT_B <-> FORCE_GND
K_B_CH1     DUT_B <-> SENSE_CH1
K_B_CH2     DUT_B <-> SENSE_CH2

K_C_VP      DUT_C <-> FORCE_VPLUS_RC
K_C_W1RB    DUT_C <-> FORCE_W1_RB
K_C_W1P     DUT_C <-> FORCE_W1_PROBE
K_C_GND     DUT_C <-> FORCE_GND
K_C_CH1     DUT_C <-> SENSE_CH1
K_C_CH2     DUT_C <-> SENSE_CH2
```

继电器选择：

```text
信号继电器：Omron G6K / Panasonic TQ2 / HFD4 类似
线圈：5V
触点：SPST-NO 优先，默认断开
```

如果想省面积，也可以用 ADG 系列模拟开关，但第一版更建议机械继电器，漏电小、直观、安全。

## 继电器驱动

不要用 MCU 直接驱继电器。用驱动阵列：

```text
MCU GPIO -> ULN2803A -> 继电器线圈 -> +5V
```

每个继电器线圈：

```text
+5V ---- Relay Coil ---- ULN2803A OUT
ULN2803A COM 接 +5V，用内部续流二极管
ULN2803A GND 接系统 GND
```

MCU 可选：

```text
方案 A：Arduino Nano / CH340 USB
方案 B：RP2040 Zero
方案 C：ESP32-S3，USB CDC
```

第一版建议用 RP2040 Zero 或 Arduino Nano，串口协议最简单。

## MCU 串口协议

固件至少支持：

```text
ID?
RESET
OPEN ALL
CLOSE K_A_W1P
CLOSE K_B_GND
CLOSE K_A_CH1
STATE?
```

更适合 agent 的抽象命令：

```text
PAIR A B PROBE_FORWARD
CONNECT A FORCE_W1_PROBE
CONNECT B FORCE_GND
CONNECT A SENSE_CH1
MEASURE_READY?
OPEN ALL
```

PCB 不关心最终协议细节，只要每个继电器线圈能由 MCU GPIO 控制即可。

## 保护电路

每个 DUT pin 串一个小电阻：

```text
DUT_A_RAW -- RPA 220R -- DUT_A_MATRIX
DUT_B_RAW -- RPB 220R -- DUT_B_MATRIX
DUT_C_RAW -- RPC 220R -- DUT_C_MATRIX
```

CH 输入保护：

```text
SENSE_CH1_MATRIX -- 10k -- CH1_TO_RAINDROP
                         |
                         +-- 双向 TVS 或钳位到 0~5V，谨慎使用
```

如果不确定雨骤 CH 输入内部保护，至少串 10k。

FORCE 保护：

```text
V+ -- R_C 220R -- FORCE_VPLUS_RC
W1 -- R_B 22k -- FORCE_W1_RB
W1 -- R_PROBE 47k/100k -- FORCE_W1_PROBE
```

低压摸引脚优先用 `FORCE_W1_PROBE`，不要一开始用 `V+`。

## 典型 NPN 静态测试连接

```text
V+ -- R_C -- C
W1 -- R_B -- B
GND ------- E
CH1 ------- B
CH2 ------- C
```

继电器矩阵需要能自动尝试：

```text
A=E, B=B, C=C
A=C, B=B, C=E
A=B, B=E, C=C
...
```

## PCB 布局建议

KiCad 里建议这样布局：

```text
左侧：J1_RAINDROP
中左：R_C / R_B / R_PROBE / CH保护电阻
中间：18路继电器矩阵
右侧：J2_DUT 插座
下方：MCU + ULN2803A + USB/5V
```

走线规则：

```text
模拟信号线短、直、远离继电器线圈
CH1/CH2 走线远离 MCU 时钟和 USB
继电器线圈电源单独粗线
GND 做整面铺铜
模拟 GND 和数字 GND 可单点汇合
每个继电器旁边丝印 K_A_W1P 这种名字
DUT A/B/C 丝印必须清楚
```

建议板子尺寸：

```text
80mm x 60mm
2层板
1oz 铜
信号线宽 0.2~0.3mm
继电器电源线宽 0.5~1.0mm
GND 大面积铺铜
```

## 安全默认态

所有继电器必须是：

```text
默认断开
MCU 复位时断开
USB 掉线时断开
程序启动第一件事 OPEN ALL
```

建议加一个物理急停/总断开：

```text
SW_ESTOP 切断继电器线圈 5V
```

## 推荐原理图页

KiCad 工程建议分 5 页：

```text
1_power_and_interfaces.kicad_sch
2_force_sense_protection.kicad_sch
3_relay_matrix_A.kicad_sch
4_relay_matrix_BC.kicad_sch
5_mcu_relay_driver.kicad_sch
```

## 第一版 BOM

```text
RP2040 Zero 或 Arduino Nano x1
ULN2803A x3
5V 信号继电器 x18
R_C 220R x1
R_B 22k x1
R_PROBE 47k/100k x1
R_PIN 220R x3
R_CH 10k x2
接线端子/排针 若干
DUT 三孔插座 x1
USB 5V 输入 x1
电源指示 LED x1
急停/总断开开关 x1
```

## 和 BJTagent 的对应关系

PCB 上的继电器名字最好直接按软件命名：

```text
K_A_VPLUS_RC
K_A_W1_RB
K_A_W1_PROBE
K_A_GND
K_A_CH1
K_A_CH2
...
```

后端配置可直接写成：

```json
{
  "pins": ["A", "B", "C"],
  "nodes": ["VPLUS_RC", "W1_RB", "W1_PROBE", "GND", "CH1", "CH2"],
  "relays": {
    "A:W1_PROBE": "K_A_W1_PROBE",
    "A:GND": "K_A_GND",
    "A:CH1": "K_A_CH1"
  }
}
```

## 最小 bring-up 流程

1. 不插 DUT，只接 USB 5V，确认 MCU 上电。
2. 发送 `ID?`，确认固件响应。
3. 发送 `OPEN ALL`，确认所有继电器断开。
4. 单独闭合每一路继电器，用万用表确认对应路径导通。
5. 接雨骤 GND，不开任何输出，确认共地正常。
6. 只使用 `FORCE_W1_PROBE` 低压路径做空载测试。
7. 插入已知 2N3904 或 S8050，跑低压 pin probe。
8. 确认 A/B/C 判定正确后，再进入 V+ / R_C 静态测试。

## 关键原则

- 所有地必须共地。
- 所有 FORCE 输出都要先过限流电阻。
- CH1/CH2 前面至少串 10k。
- 继电器默认断开。
- 先只支持低压探测，再扩展到完整表征。
- 软件命名和 PCB 丝印保持一致。
