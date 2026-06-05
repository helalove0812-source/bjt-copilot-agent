# BJT 共射极组态自动化测试系统 — 技术方案

> 历史参考：本文是早期完整技术方案，包含已经废弃的桌面 GUI 设想。当前实现主线以 Web UI + CLI 为准。
>
> 目标硬件：上海雨骤科技 Raindrop **Model S**（雨骤 S）
> 目标 SDK：Instruments Playground SDK — Python API (`pyRD`)
> 适用对象：国产 NPN / PNP 小信号双极型晶体管（典型代表：S8050、S8550、9013、9014、2N3904、2N3906 等）
> 文档版本：v1.0
> 文档用途：交付给实现 agent 作为开发蓝图

---

## 目录

1. 项目概述与设计目标
2. 系统总体架构
3. 硬件平台与测试电路
4. 核心测量原理与算法
   - 4.1 NPN/PNP 自动识别
   - 4.2 静态参数测量
   - 4.3 \(V_{CE(sat)}\) 测量
   - 4.4 \(I_C\)–\(V_{CE}\) 输出特性曲线扫描
   - 4.5 \(\beta\) 线性精度（β Linearity）
   - 4.6 数据预处理与拟合
5. 软件架构与模块划分
6. 关键类与接口设计
7. 异常检测与安全保护
8. GUI 设计
9. 数据存储与报告生成
10. 雨骤 SDK 关键 API 调用映射
11. 项目目录结构
12. 完整测试流程
13. 开发任务清单与里程碑
14. 验收标准
附录 A：典型 \(\beta\) 计算示例
附录 A2：\(\beta\) 线性精度计算示例
附录 B：易错点与排查

---

## 1. 项目概述与设计目标

### 1.1 功能目标

| 编号 | 功能 | 关键指标 |
|------|------|----------|
| F1 | 设备类型自动识别 | 在不指定 NPN/PNP 的情况下识别正确率 ≥ 99 % |
| F2 | 静态参数测量（\(I_B,\,I_C,\,V_{BE},\,V_{CE}\)） | \(I_B\) 分辨率 ≤ 1 μA，\(V_{BE}\) 分辨率 ≤ 5 mV |
| F3 | 电流增益 \(\beta\) (即 \(h_{FE}\)) 计算 | 至少给出 5 个 \(I_C\) 工作点下的 \(\beta\) |
| F4 | 饱和压降 \(V_{CE(sat)}\) 测量 | 确保 \(\beta_{forced} < \beta_{actual}/5\) |
| F5 | \(I_C\)–\(V_{CE}\) 输出特性曲线扫描 | 至少 4 条 \(I_B\) 等级曲线，每条 ≥ 50 点 |
| F6 | \(\beta\) 线性精度（β Linearity）计算 | 给出指定 \(I_C\) 区间内 \(\beta\) 的最大/最小/均值与归一化波动率 |
| F7 | 异常检测与硬保护 | 越限 50 ms 内切断输出 |
| F8 | 实时数据可视化 | GUI 刷新率 ≥ 5 Hz |
| F9 | 报告归档 | 自动生成 PDF/HTML 报告，含原始 CSV |

### 1.2 非功能性需求

- 全 Python 实现，单机运行，免编译；
- 跨 Windows / Raspberry Pi OS（依据 SDK 提供能力）；
- 模块化，硬件抽象层与业务逻辑解耦，便于后续替换为其他型号雨骤设备；
- 关键路径异常可恢复，不因单次测量失败而退出程序。

---

## 2. 系统总体架构

分层结构（自底向上）：

```
┌─────────────────────────────────────────────────────────┐
│   GUI 层 (PySide6)   主窗口 / 实时曲线 / 报告浏览       │
├─────────────────────────────────────────────────────────┤
│   编排与状态层  TestOrchestrator (QThread)              │
├─────────────────────────────────────────────────────────┤
│   测量逻辑层    Detector / StaticMeas / Sweep / Sat     │
├─────────────────────────────────────────────────────────┤
│   分析与报告层  DataProcessor / ReportBuilder           │
├─────────────────────────────────────────────────────────┤
│   硬件抽象层    PSU / Scope / AWG / DMM / Safety        │
├─────────────────────────────────────────────────────────┤
│   雨骤 pyRD SDK  (RD 类)                                │
└─────────────────────────────────────────────────────────┘
```

数据流：硬件采样 → 测量逻辑生成结构化数据 → 编排层通过 Qt Signal 推送给 GUI → DataProcessor 入库 → ReportBuilder 出报告。

---

## 3. 硬件平台与测试电路

### 3.1 雨骤 Model S 可用资源映射

| Model S 资源 | 在本系统中的角色 | 备注 |
|---|---|---|
| V+ (0 ~ +5 V 程控) | \(V_{CC}\) 主电源（NPN 集电极偏置） | `AnalogIOChannelNodeSet(ch=0, value)` |
| V- (-5 ~ 0 V 程控) | PNP 测试时的基极下拉电源 | `AnalogIOChannelNodeSet(ch=1, value)` |
| AWG W1 (DC 模式) | \(V_{BB}\) 基极偏置电源（程控） | 比直接用 V+ 灵活，可独立扫描 |
| AWG W2 (DC 模式) | PNP 测试时的发射极正偏置（设为 +5 V DC） | 或保留作扩展 |
| 示波器 CH1 | 测 \(V_B\) | `AnalogInRead(ch=0)` |
| 示波器 CH2 | 测 \(V_C\) | `AnalogInRead(ch=1)` |
| DMM | 校准 / 高精度电流复测 | DCA 挡测 \(I_C\)，DCV 挡测 \(V_{BE}\) |
| 数字 IO | （可选）控制外部继电器切换 NPN/PNP 接线 | 见 §3.5 |

> **关键澄清**：示波器通道单端对地测量，所以 \(V_{BE} = V_B - V_E\)，\(V_{CE} = V_C - V_E\)。NPN 测试时把 E 接 GND，则 \(V_{BE} = V_B\)、\(V_{CE} = V_C\)。PNP 详见 §3.4。

### 3.2 NPN 测试电路（共射极）

```
   V+ (Model S)  ──┐
                   │
                  [R_C]          ← 限流，选 220 Ω ~ 1 kΩ
                   │
                   ●── CH2 (测 V_C)
                   │
                  ┌C┐
   AWG W1 ─[R_B]──● B ┤      NPN BJT
                  └E┘
                   │
                   ●── CH1 实际上接 V_B 也可挪到 R_B 前端
                   │
                  GND
```

测得：
- \(V_B\) = CH1 实测电压
- \(V_C\) = CH2 实测电压
- \(V_{BB}\) = W1 设定电压（已知）
- \(V_{CC}\) = V+ 设定电压（已知）

推得：
\[
I_B = \frac{V_{BB} - V_B}{R_B},\qquad
I_C = \frac{V_{CC} - V_C}{R_C},\qquad
V_{BE} = V_B,\qquad
V_{CE} = V_C
\]

### 3.3 元器件与限流电阻选型

| 元件 | 推荐值 | 选型理由 |
|---|---|---|
| \(R_B\) | **22 kΩ**（默认）；可切 4.7 kΩ / 47 kΩ / 100 kΩ | \(V_{BB}\) 范围 0.7–5 V 对应 \(I_B\) 约 0 ~ 200 μA，覆盖小信号管常用区 |
| \(R_C\) | **220 Ω**（默认）；可切 100 Ω / 1 kΩ | \(V_{CC}\) = 5 V 时最大 \(I_C ≈ 23\,\text{mA}\)，安全且足以观察饱和 |
| 钳位二极管 1N4148 ×2 | 基极对地反向并联，防误接 PNP 烧 BJT | 可选 |
| 备用 TVS / PTC | 集电极线串 PTC 用于二次保护 | 可选 |

可在 GUI 中让用户从下拉框选择实际焊接的 \(R_B / R_C\) 阻值，软件据此计算电流。

### 3.4 PNP 测试电路（共射极）

PNP 推荐采用「发射极接 +5 V，基极通过 \(R_B\) 接 W1（W1 取低电平使 B-E 正向偏置），集电极通过 \(R_C\) 接地」：

```
   AWG W2 = +5 V DC ──── ●── (CH? 可选监测 V_E)
                          │
                         ┌E┐
   AWG W1 ──[R_B]────────● B ┤    PNP BJT
                         └C┘
                          ●── CH2 (测 V_C)
                          │
                         [R_C]
                          │
                         GND
```

\(V_E\) 已知（W2 = 5 V），不必再用一个 ADC 通道。CH1 测 \(V_B\)。

\[
I_B = \frac{V_B - V_{BB}}{R_B},\qquad
I_C = \frac{V_C - 0}{R_C} = \frac{V_C}{R_C}
\]
\[
V_{BE} = V_B - V_E\ (\text{负值}),\qquad
V_{CE} = V_C - V_E\ (\text{负值})
\]

记录时保留符号，画图时按绝对值显示；以"PNP"标记图例。

### 3.5（可选）继电器接线切换

若希望被测管插一个插座就能自动处理 NPN / PNP，可在硬件上用 2 ~ 4 个 SPDT 继电器：
- 由 Model S 数字 IO（`DigitalIOOutputSet`）驱动；
- IO0 控制 E 端（接 GND or 接 +5V）；
- IO1 控制 \(R_C\) 另一端（接 V+ or 接 GND）；
- IO2 控制 \(R_B\) 馈源（W1 单端）。

本方案默认 **不依赖继电器**，由用户在 GUI 中点击 "NPN 配线" / "PNP 配线" 后插管再开始测试。

---

## 4. 核心测量原理与算法

### 4.1 NPN / PNP 自动识别

#### 思路
分别尝试 NPN 偏置假设与 PNP 偏置假设，观察集电极电流是否出现"明显"流动。"明显"定义为：在基极注入 ≈ 50 μA 时 \(I_C\) ≥ 0.5 mA，且 \(I_C \gg I_B\)（\(\beta \ge 10\)）。

#### 伪代码

```python
def detect_bjt_type(hw) -> Literal["NPN", "PNP", "UNKNOWN"]:
    # ---- 试 NPN ----
    hw.psu.set_v_pos(3.0)        # V_CC = 3 V
    hw.awg.set_w1_dc(2.0)        # V_BB = 2 V  →  I_B ≈ (2 - 0.7) / 22 kΩ ≈ 59 μA
    hw.scope.acquire_and_average(samples=2000)
    Vb, Vc = hw.scope.last_means
    Ib_npn = (2.0 - Vb) / R_B
    Ic_npn = (3.0 - Vc) / R_C
    hw.psu.disable_all()

    # ---- 试 PNP ----
    hw.awg.set_w2_dc(5.0)        # V_E = 5 V
    hw.awg.set_w1_dc(3.0)        # V_BB = 3 V  → I_B ≈ (V_B - 3) / R_B
    hw.psu.set_v_pos(0)          # 不用 V+
    hw.scope.acquire_and_average(samples=2000)
    Vb, Vc = hw.scope.last_means
    Ib_pnp = (Vb - 3.0) / R_B
    Ic_pnp = Vc / R_C
    hw.psu.disable_all(); hw.awg.disable_all()

    beta_npn = Ic_npn / Ib_npn if Ib_npn > 1e-6 else 0
    beta_pnp = Ic_pnp / Ib_pnp if Ib_pnp > 1e-6 else 0

    if beta_npn > 10 and beta_npn > 3 * beta_pnp:
        return "NPN"
    if beta_pnp > 10 and beta_pnp > 3 * beta_npn:
        return "PNP"
    return "UNKNOWN"  # 触发 GUI 报错：检查接线 / 管子是否损坏
```

#### 安全保护
两次试探之间必须 `disable_all()`，并 `time.sleep(0.05)`，防止电源切换瞬间产生过流尖峰。

#### 备选方案：DMM 二极管挡
将红表笔接基极、黑表笔接集电极，用 `DMMSet(RDDMMDiode, 0)` + `DMMReadSingle()` 读返回字节串；正向压降 ≈ 0.6 V 即可推断 PN 结方向。该方案不需要程控供电，但要求测试夹具线序固定，目前只作为辅助校验。

### 4.2 静态参数测量

测量流程（NPN 情况，PNP 对称）：

1. 设 `V_CC = 5 V`，`V_BB` 从 0 V 起，以 0.05 V 为步长上升。
2. 每个步进点：
   - 等待 PSU 稳定（建议 ≥ 20 ms）；
   - 用示波器以 100 kHz 采样率、缓冲区 2048 点采集 \(V_B\) / \(V_C\)（10 个完整周期的平均，剔除外部 50 Hz 工频干扰）；
   - 求均值得到 \(\overline{V_B},\,\overline{V_C}\)；
   - 计算 \(I_B,\,I_C,\,\beta\)。
3. 跳出条件：
   - \(I_C\) ≥ 软件电流上限 \(I_{C,\max}\)（默认 30 mA）；
   - \(V_{CE}\) ≤ 0.3 V（进入饱和）；
   - \(V_{BB}\) ≥ 5 V（W1 上限）。

输出数据结构：

```python
@dataclass
class StaticPoint:
    Vbb: float
    Vcc: float
    Vb: float
    Vc: float
    Ib: float          # A
    Ic: float          # A
    Vbe: float         # V
    Vce: float         # V
    beta: float        # 量纲一
    region: Literal["cutoff", "active", "saturation"]
```

`region` 判定：
- \(V_{BE} < 0.5\,\text{V}\)：cutoff
- \(V_{CE} < 0.3\,\text{V}\)：saturation
- 其余：active

\(\beta\) 取活动区中点（\(I_C\) 约 1 ~ 10 mA）的多次平均，作为该器件的代表 \(\beta\)。

### 4.3 \(V_{CE(sat)}\) 测量

通过强制基极过驱动使 BJT 进入饱和：

1. 给定预期 \(I_C\) 目标值（默认 10 mA）；
2. 据当前 \(\beta\) 估计 \(I_B^{\text{normal}} = I_C / \beta\)；
3. 设 \(I_B^{\text{forced}} = 10 \times I_B^{\text{normal}}\)，即"强迫 \(\beta\)" \(\beta_F = 10\)，远小于实际 \(\beta\)；
4. 设置对应 \(V_{BB}\)，读取 \(V_{CE}\)，即 \(V_{CE(sat)}\)。
5. 典型值 0.1 ~ 0.3 V。

```python
def measure_vce_sat(target_ic=10e-3, beta_forced=10) -> float:
    Ib_force = target_ic / beta_forced
    Vbb_target = Vbe_typ + Ib_force * R_B   # Vbe_typ 取 0.7
    hw.awg.set_w1_dc(Vbb_target)
    hw.psu.set_v_pos(5.0)
    Vb, Vc = hw.scope.average(2000)
    return Vc  # = Vce_sat for NPN with E grounded
```

### 4.4 \(I_C\)–\(V_{CE}\) 输出特性曲线扫描

对 \(N\) 条等基极电流曲线，分别在固定 \(I_B\) 下扫描 \(V_{CC}\) 来得到 \(V_{CE}\) 与 \(I_C\)。

```python
def sweep_output_curves(
    Ib_levels=(10e-6, 25e-6, 50e-6, 100e-6, 200e-6),
    Vcc_range=(0.0, 5.0),
    Vcc_steps=60,
):
    results: dict[float, list[StaticPoint]] = {}
    for Ib in Ib_levels:
        # 反推 V_BB
        Vbb = 0.7 + Ib * R_B
        hw.awg.set_w1_dc(Vbb)

        curve = []
        for Vcc in np.linspace(*Vcc_range, Vcc_steps):
            hw.psu.set_v_pos(Vcc)
            time.sleep(0.020)            # PSU 建立时间
            check_safety()               # ← 见 §7
            point = read_static_point()
            curve.append(point)
        results[Ib] = curve
    return results
```

每条曲线得到点序列，存入 `pandas.DataFrame`，主键 `(Ib_level, Vcc_step)`。

### 4.5 \(\beta\) 线性精度（β Linearity）

#### 4.5.1 定义

\(\beta\) 线性精度刻画的是器件 \(\beta\) 在一段集电极电流 \(I_C\) 工作区间内的相对波动。本系统采用如下归一化指标：

\[
\eta_\beta \;=\; \frac{\beta_{\max} - \beta_{\min}}{\beta_{\mathrm{avg}}}
\]

其中 \(\beta_{\max}\)、\(\beta_{\min}\)、\(\beta_{\mathrm{avg}}\) 均在所设定的"线性度评估区间" \(I_C \in [I_{C,\mathrm{lo}},\,I_{C,\mathrm{hi}}]\) 内统计得到。\(\eta_\beta\) 越小，说明器件在该区间内 \(\beta\) 越平坦，越适合做线性放大；反之，若器件在低/高电流区都出现明显 \(\beta\) 下降（低电流区受复合电流影响、高电流区受高注入效应、基区调制与载流子输运受限等机制影响），\(\eta_\beta\) 将明显增大。

#### 4.5.2 评估区间选取

默认评估区间设为 \([0.5\,\mathrm{mA},\,20\,\mathrm{mA}]\)，覆盖典型小信号 NPN/PNP 的中等电流工作带。可由 GUI 让用户改写，但需满足：
- \(I_{C,\mathrm{lo}}\) 不低于本机噪声底（建议 ≥ 0.2 mA）；
- \(I_{C,\mathrm{hi}}\) 不超过 \(I_{C,\max}\)；
- 评估区间内至少有 8 个有效 active 点。

#### 4.5.3 数据来源

线性精度需要在 **固定 \(V_{CE}\)** 下，扫描 \(I_B\)（进而扫描 \(I_C\)）得到一组 \(\beta(I_C)\)。具体做法：

1. 设 \(V_{CC}\) = 5 V，但通过 \(R_C\) 限流后实际 \(V_{CE}\) 会随 \(I_C\) 变化；为消除 Early 效应对 \(\beta\) 的污染，**推荐另开一次专用扫描**：固定 \(V_{CE} = 3\) V（取中点），通过 \(V_{CC}\) 软件闭环逐点调节。
2. 简化做法（默认）：直接复用 §4.2 静态扫描的 active 区域点，但仅取 \(V_{CE} \in [2,\,4]\,\mathrm{V}\) 的子集，以减小 Early 效应影响。
3. 推荐做法：在 §4.4 输出曲线扫描的副产品中，每条 \(I_B\) 等级曲线插值得到 \(V_{CE} = 3\) V 处的 \(\beta\)，再以多个 \(I_B\) 等级合成 \(\beta\)–\(I_C\) 关系。

#### 4.5.4 算法

```python
def beta_linearity(
    points: list[StaticPoint],
    ic_range: tuple[float, float] = (0.5e-3, 20e-3),
    vce_window: tuple[float, float] | None = (2.0, 4.0),
) -> "BetaLinearity":
    """
    返回 BetaLinearity dataclass。若有效点数不足，eta=None 并附 reason。
    """
    candidates = [
        p for p in points
        if p.region == "active"
        and ic_range[0] <= abs(p.Ic) <= ic_range[1]
        and (vce_window is None
             or vce_window[0] <= abs(p.Vce) <= vce_window[1])
    ]
    if len(candidates) < 8:
        return BetaLinearity(eta=None, n=len(candidates),
                             reason="有效点不足 8 个")

    betas = np.array([p.beta for p in candidates])
    ics   = np.array([abs(p.Ic) for p in candidates])

    b_max, b_min, b_avg = betas.max(), betas.min(), betas.mean()
    eta = (b_max - b_min) / b_avg

    # 取 β_max / β_min 出现的 I_C，便于报告标注
    ic_at_max = float(ics[betas.argmax()])
    ic_at_min = float(ics[betas.argmin()])

    return BetaLinearity(
        eta=float(eta),
        beta_max=float(b_max), beta_min=float(b_min), beta_avg=float(b_avg),
        ic_at_max=ic_at_max, ic_at_min=ic_at_min,
        ic_range=ic_range, n=len(candidates),
        beta_vs_ic=list(zip(ics.tolist(), betas.tolist())),
    )
```

对应的数据类：

```python
@dataclass
class BetaLinearity:
    eta: float | None              # (β_max - β_min) / β_avg
    beta_max: float = 0.0
    beta_min: float = 0.0
    beta_avg: float = 0.0
    ic_at_max: float = 0.0         # A，β_max 出现处的 I_C
    ic_at_min: float = 0.0         # A，β_min 出现处的 I_C
    ic_range: tuple[float, float] = (0.5e-3, 20e-3)
    n: int = 0                     # 参与统计的有效点数
    beta_vs_ic: list[tuple[float, float]] = field(default_factory=list)
    reason: str = ""               # 计算失败时给出原因
```

#### 4.5.5 评级（可选，用于报告显示）

| \(\eta_\beta\) | 评级 | 释义 |
|---|---|---|
| < 0.10 | A — 优秀 | 在 0.5 ~ 20 mA 区间 \(\beta\) 波动 < 10 %，适合大动态范围线性放大 |
| 0.10 ~ 0.25 | B — 良好 | 典型量产小信号管水平 |
| 0.25 ~ 0.50 | C — 一般 | 仅适合窄工作点放大或开关用途 |
| > 0.50 | D — 较差 | 强非线性，仅建议作开关或代换排查 |

> 说明：上述阈值仅为工程经验值，具体应结合数据手册与电路设计需求。

#### 4.5.6 输出物

- GUI："\(\beta\)–\(I_C\)" 半对数图（\(I_C\) 取 log 轴），叠加 \(\beta_{\mathrm{avg}}\) 水平参考线与评估区间阴影；
- 报告：\(\eta_\beta\) 数值 + 评级 + 上图；
- CSV：`beta_linearity.csv`，列 `Ic_A, Vce_V, beta`。

### 4.6 数据预处理与拟合

- **去噪**：示波器每点取 2048 个采样的算术平均；可选：去除前 5 % / 后 5 % 后再均值。
- **\(\beta\) 中位数**：避免 cutoff/saturation 附近大量异常点拉高均值，使用 active 区域内 \(\beta\) 的 **中位数** 作为器件代表值。
- **早期效应（Early voltage）拟合**：对每条 \(I_B\) 曲线在饱和区之后取线性段，外推到 \(I_C = 0\) 处的 \(V_{CE}\)（绝对值），得 \(V_A\)；多条曲线 \(V_A\) 取均值即可。
- **\(\beta\) 线性精度**：见 §4.5；对线性度评估专用数据集做单独筛选，避免与器件代表 \(\beta\) 的统计混淆。

---

## 5. 软件架构与模块划分

### 5.1 层次结构

| 层 | 主要类 / 文件 | 职责 |
|---|---|---|
| GUI | `gui.main_window.MainWindow` | 整合各功能 Tab，事件分发 |
| GUI | `gui.live_plot.LivePlotWidget` | 嵌入 matplotlib FigureCanvas |
| GUI | `gui.panels.*` | 各功能面板 |
| 编排 | `app.orchestrator.TestOrchestrator(QThread)` | 串行执行流程，发 Signal 给 GUI |
| 测量 | `measurement.detector.BJTDetector` | NPN/PNP 识别 |
| 测量 | `measurement.static.StaticMeasurer` | \(I_B,I_C,V_{BE},V_{CE},\beta\) |
| 测量 | `measurement.vce_sat.SatMeasurer` | \(V_{CE(sat)}\) |
| 测量 | `measurement.curves.CurveSweeper` | 输出特性曲线 |
| 测量 | `measurement.linearity.LinearityAnalyzer` | \(\beta\) 线性精度评估 |
| 分析 | `analysis.data_processor.DataProcessor` | 滤波、\(\beta\) 统计、Early 拟合、\(\eta_\beta\) 计算 |
| 分析 | `analysis.report.ReportBuilder` | HTML/PDF 报告 |
| 硬件 | `core.device.DeviceManager` | RD 实例生命周期、单例 |
| 硬件 | `core.psu.PSU` | V+、V-、AWG DC 输出 |
| 硬件 | `core.scope.Scope` | 配置 + 采集 + 均值 |
| 硬件 | `core.awg.AWG` | DC 与函数输出 |
| 硬件 | `core.dmm.DMM` | 万用表 |
| 硬件 | `core.safety.SafetyGuard` | 实时越限监测 |
| 工具 | `utils.logger`、`utils.config` | logging、YAML 配置 |

### 5.2 主要数据类型

```python
# core/types.py
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime

BJTType = Literal["NPN", "PNP", "UNKNOWN"]
Region  = Literal["cutoff", "active", "saturation"]

@dataclass
class HwConfig:
    R_B: float = 22e3
    R_C: float = 220.0
    Vbe_typ: float = 0.7
    Ic_max_A: float = 30e-3
    Pmax_W: float = 0.30          # 软功率限
    Vcc_max: float = 5.0
    # β 线性度评估区间
    lin_ic_lo_A: float = 0.5e-3
    lin_ic_hi_A: float = 20e-3
    lin_vce_window: tuple[float, float] = (2.0, 4.0)

@dataclass
class StaticPoint:
    Vbb: float; Vcc: float
    Vb: float;  Vc: float
    Ib: float;  Ic: float
    Vbe: float; Vce: float
    beta: float
    region: Region
    timestamp: datetime = field(default_factory=datetime.now)

# BetaLinearity 定义见 §4.5.4，此处略

@dataclass
class DeviceReport:
    bjt_type: BJTType
    serial: str                   # 雨骤设备序列号
    dut_label: str                # 用户输入的样品名
    beta_median: float
    beta_active_curve: list[StaticPoint]
    vce_sat: float
    Ic_at_sat: float
    output_curves: dict[float, list[StaticPoint]]
    early_voltage: float | None
    beta_linearity: "BetaLinearity"   # ← 新增：η_β 及其统计
    hw_config: HwConfig
    started_at: datetime
    finished_at: datetime
```

---

## 6. 关键类与接口设计

### 6.1 `DeviceManager`

```python
class DeviceManager:
    """RD 单例，封装枚举/打开/关闭"""
    _instance: "DeviceManager | None" = None
    rd: "RD"
    sn: str

    @classmethod
    def get(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = cls._connect_first()
        return cls._instance

    @classmethod
    def _connect_first(cls) -> "DeviceManager":
        from pyRD import RD
        rd = RD()
        rd.DeviceEnumLists()
        if not rd.devicelist:
            raise RuntimeError("未找到雨骤设备")
        # 优先取序列号包含 'YZ' 的
        idx = next((i for i, d in enumerate(rd.devicelist)
                    if b"YZ" in d[1]), 0)
        rd.DeviceOpen(idx)
        obj = cls.__new__(cls)
        obj.rd = rd
        obj.sn = rd.devicelist[idx][1].decode()
        return obj

    def close(self):
        self.rd.DeviceClose()
        DeviceManager._instance = None
```

### 6.2 `PSU` / `AWG` / `Scope`

```python
class PSU:
    def __init__(self, dm: DeviceManager):
        self.rd = dm.rd

    def set_v_pos(self, volts: float):
        volts = max(0.0, min(5.0, volts))
        self.rd.AnalogIOChannelEnableSet(0, True)
        self.rd.AnalogIOChannelNodeSet(0, volts)

    def set_v_neg(self, volts: float):
        volts = max(-5.0, min(0.0, volts))
        self.rd.AnalogIOChannelEnableSet(1, True)
        self.rd.AnalogIOChannelNodeSet(1, volts)

    def disable_all(self):
        self.rd.AnalogIOChannelEnableSet(0, False)
        self.rd.AnalogIOChannelEnableSet(1, False)


class AWG:
    """用 W1/W2 输出 DC 充当扩展程控电源"""
    def set_dc(self, ch: int, volts: float):
        # ch: 0=W1, 1=W2
        rd = self.rd
        rd.AnalogOutNodeEnableSet(ch, RDAnalogOutNodeCarrier, True)
        rd.AnalogOutNodeFunctionSet(ch, RDAnalogOutNodeCarrier, RDFUNCDC)
        rd.AnalogOutNodeOffsetAmpSet(
            ch, RDAnalogOutNodeCarrier,
            vOffset=volts, amp=0.0)
        rd.AnalogOutConfigure(ch, True)

    def disable(self, ch: int):
        self.rd.AnalogOutConfigure(ch, False)


class Scope:
    """单次双通道平均采集"""
    def configure(self, fs=100_000, buffersize=2048,
                  vrange_ch1=5, vrange_ch2=5):
        rd = self.rd
        for ch, rng in ((0, vrange_ch1), (1, vrange_ch2)):
            rd.AnalogInCHEnable(ch, True)
            rd.AnalogInCHRangeSet(ch, rng)
        rd.AnalogInFrequencySet(fs)
        rd.AnalogInBufferSizeSet(buffersize)
        rd.AnalogInTriggerSourceSet(RDTRIGSRCNone)   # 无触发：连续采
        rd.AnalogInTriggerAutoTimeoutSet(1)          # 1 s 超时兜底
        self.buffersize = buffersize

    def acquire(self, timeout_s=1.0) -> tuple[float, float]:
        rd = self.rd
        rd.AnalogInRun(True)
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rd.AnalogInStatus()
            if rd.analoginstatus == RDStateDone:
                break
            time.sleep(0.005)
        else:
            raise TimeoutError("Scope acquire timeout")

        rd.AnalogInRead(self.buffersize, 0)
        rd.AnalogInRead(self.buffersize, 1)
        v1 = float(np.mean(list(rd.aidatach1)))
        v2 = float(np.mean(list(rd.aidatach2)))
        return v1, v2
```

### 6.3 `SafetyGuard`

```python
class SafetyGuard:
    def __init__(self, cfg: HwConfig, psu: PSU, awg: AWG):
        self.cfg, self.psu, self.awg = cfg, psu, awg

    def check(self, point: StaticPoint):
        if abs(point.Ic) > self.cfg.Ic_max_A:
            self.emergency_off("Ic 过流")
        P = abs(point.Vce * point.Ic)
        if P > self.cfg.Pmax_W:
            self.emergency_off(f"功耗 {P*1000:.1f} mW 超限")

    def emergency_off(self, reason: str):
        self.psu.disable_all()
        self.awg.disable(0); self.awg.disable(1)
        raise SafetyAbort(reason)
```

---

## 7. 异常检测与安全保护

### 7.1 三级保护

| 等级 | 实现 | 响应时间 |
|---|---|---|
| L1：硬件 | \(R_C\) 串联限流 + 1N4148 反向钳位 | 即时 |
| L2：测量循环内软件 | `SafetyGuard.check()`，越限 raise `SafetyAbort` | < 20 ms |
| L3：独立监测线程 | 1 kHz 轮询 \(V_C\)，若 \(V_C\) 接近 0（\(I_C\) 满量程）立即调用 emergency_off | < 50 ms |

### 7.2 触发条件

- \(I_C > I_{C,\max}\)（默认 30 mA）；
- 功耗 \(P = |V_{CE} \cdot I_C| > P_{\max}\)（默认 300 mW）；
- 示波器超时（设备掉线）；
- DUT 短路：\(V_C ≈ 0\) 而 \(I_B ≈ 0\)；
- DUT 击穿：\(V_{CE}\) 异常变化超过 ±0.5 V 之内的步进；
- 用户点击 GUI 上的 **STOP** 按钮。

### 7.3 程序退出 / 异常路径

- 任意 `SafetyAbort` 被捕获后：
  1. 立即关闭所有电源/AWG/示波器；
  2. 在 GUI 状态栏弹出红色提示；
  3. 写日志（`utils.logger`）；
  4. 测试线程退出，主线程仍可重新启动测试。
- `KeyboardInterrupt` / 窗口关闭 / `atexit` 钩子统一调用 `DeviceManager.close()` 与 `psu.disable_all()`。

---

## 8. GUI 设计

### 8.1 框架与依赖

- **PySide6**（LGPL，兼容性好）
- **matplotlib** 嵌入：`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
- **pyqtgraph**（可选，用于实时曲线刷新更高帧率）

### 8.2 主窗口布局

```
┌──────────────────────────────────────────────────────────────┐
│ ⚙ Raindrop Model S | SN: YZD12345 | ● Connected | [断开]     │
├───── 左：控制面板 ─────┬────────── 右：图表区 ────────────────┤
│ ▣ 硬件配置             │ ┌──────── Ic-Vce 曲线 ────────┐    │
│   R_B [22 kΩ ▾]        │ │                              │    │
│   R_C [220 Ω ▾]        │ │     (matplotlib canvas)      │    │
│   I_c 上限 [30 mA]     │ │                              │    │
│   P_max  [300 mW]      │ └──────────────────────────────┘    │
│   线性区间             │ ┌──────── β-Ic 曲线 (log x) ──┐    │
│   I_c [0.5–20 mA]      │ │                              │    │
│                        │ │  η_β = 0.18  评级 B          │    │
│ ▣ 测试动作             │ └──────────────────────────────┘    │
│   [识别 NPN/PNP]       │ ┌──────── 实时数值 ────────────┐    │
│   [测静态参数]         │ │ Vbe = 0.683 V   Ib = 56.0 μA│    │
│   [测 Vce(sat)]        │ │ Vce = 2.41 V    Ic = 11.8 mA│    │
│   [扫描输出曲线]       │ │ β   = 211       Region: ACT │    │
│   [β 线性度评估]       │ └──────────────────────────────┘    │
│   [一键全套]           │ ┌──────── 日志 ────────────────┐    │
│                        │ │ 12:01:33 设备就绪…           │    │
│ ▣ 报告                 │ │ 12:01:41 识别结果：NPN       │    │
│   DUT 标签 [_______]   │ │ 12:01:55 β中位 = 207         │    │
│   [生成 PDF 报告]      │ │ 12:02:10 η_β = 0.18 (B)      │    │
│   [导出 CSV]           │ └──────────────────────────────┘    │
│                        │                                      │
│ 🛑  停止 / 紧急停止    │                                      │
└────────────────────────┴──────────────────────────────────────┘
```

### 8.3 Qt Signal 流

```
TestOrchestrator (QThread)
  ├─ progress(int)             → 进度条
  ├─ point_ready(StaticPoint)  → 实时数值 + 实时点画图
  ├─ curve_ready(dict)         → 全部曲线绘制
  ├─ linearity_ready(BetaLinearity) → β-Ic 子图 + η_β 显示
  ├─ status(str)               → 状态栏 / 日志
  ├─ finished(DeviceReport)    → 跳到报告 Tab
  └─ error(str)                → 弹红色 toast
```

### 8.4 线程模型

- GUI 永远在主线程；
- `TestOrchestrator` 继承自 `QThread`，调用各 measurement 模块；
- 设备访问 **只在 orchestrator 线程**，禁止 GUI 直接读 RD；
- 紧急停止：GUI 点按钮 → `orchestrator.requestInterruption()` → 测量循环检查 `isInterruptionRequested()` 后退出。

---

## 9. 数据存储与报告生成

### 9.1 目录约定

```
./data/<YYYYMMDD-HHMMSS>__<DUT_label>/
    ├─ raw_static.csv          # 静态扫描全部点
    ├─ raw_curves.csv          # 输出特性扫描，列：Ib_level, Vcc, Vb, Vc, Ib, Ic, Vce
    ├─ beta_linearity.csv      # β 线性度评估专用数据集
    ├─ summary.json            # DeviceReport dataclass 序列化（含 BetaLinearity）
    ├─ curves.png              # Ic-Vce 曲线图
    ├─ beta_vs_ic.png          # β-Ic 图（标注 η_β、评估区间、β_avg）
    └─ report.pdf              # 最终报告
```

### 9.2 CSV 列规范

```
raw_static.csv
timestamp, Vbb_V, Vcc_V, Vb_V, Vc_V, Ib_uA, Ic_mA, Vbe_V, Vce_V, beta, region

beta_linearity.csv
Ic_A, Vce_V, beta, in_window     # in_window=1 表示落在评估区间内并参与统计
```

### 9.3 报告内容（PDF）

使用 **reportlab** 或 **weasyprint** + Jinja2 模板生成：

1. 标题页：DUT 标签、雨骤设备 SN、测试时间；
2. 摘要：识别结果（NPN/PNP）、\(\beta_\text{median}\)、\(V_{CE(sat)}\)、Early 电压 \(V_A\)、\(\beta\) 线性精度 \(\eta_\beta\) 及评级；
3. 测试条件：\(R_B,\,R_C,\,I_{C,\max}\)、\(\beta\) 线性度评估区间 \([I_{C,\mathrm{lo}},\,I_{C,\mathrm{hi}}]\) 与 \(V_{CE}\) 窗，环境温度（可手填）；
4. 图：\(I_C\)–\(V_{CE}\) 曲线族；
5. 图：\(\beta\)–\(I_C\) 曲线（log 横轴，附 \(\beta_{\max},\,\beta_{\min},\,\beta_{\mathrm{avg}}\) 水平线、评估区间阴影、\(\eta_\beta\) 标注）；
6. 表：每个 \(I_B\) 等级下的若干特征点；
7. \(\beta\) 线性精度统计表：\(\beta_{\max} / I_{C}@\beta_{\max},\,\beta_{\min} / I_{C}@\beta_{\min},\,\beta_{\mathrm{avg}},\,\eta_\beta,\) 参与点数 \(n\)，评级；
8. 异常 / 警告记录；
9. 原始数据文件清单。

---

## 10. 雨骤 SDK 关键 API 调用映射速查

| 目标 | API | 关键参数 |
|---|---|---|
| 枚举设备 | `DeviceEnumLists()` | 结果存 `rd.devicelist` |
| 打开 | `DeviceOpen(idx)` | 返回 0 表示成功 |
| 关闭 | `DeviceClose()` | — |
| V+ 输出 | `AnalogIOChannelEnableSet(0, True)`<br>`AnalogIOChannelNodeSet(0, V)` | V ∈ [0, 5] |
| V- 输出 | `AnalogIOChannelEnableSet(1, True)`<br>`AnalogIOChannelNodeSet(1, V)` | V ∈ [-5, 0] |
| AWG DC | `AnalogOutNodeEnableSet(ch, RDAnalogOutNodeCarrier, True)`<br>`AnalogOutNodeFunctionSet(ch, RDAnalogOutNodeCarrier, RDFUNCDC)`<br>`AnalogOutNodeOffsetAmpSet(ch, RDAnalogOutNodeCarrier, V, 0)`<br>`AnalogOutConfigure(ch, True)` | ch=0 (W1) / 1 (W2)；amp 设 0，仅用 offset 当 DC |
| 示波器使能 + 量程 | `AnalogInCHEnable(ch, True)`<br>`AnalogInCHRangeSet(ch, 5)` | Model S 量程 5V / 25V |
| 采样率 | `AnalogInFrequencySet(100000)` | 100 kHz 即可 |
| 缓冲区 | `AnalogInBufferSizeSet(2048)` | 2048 点 |
| 无触发模式 | `AnalogInTriggerSourceSet(RDTRIGSRCNone)` | 持续扫描 |
| 启动一次采集 | `AnalogInRun(True)` | 跑到 `RDStateDone` 停 |
| 查询状态 | `AnalogInStatus()` → `rd.analoginstatus` | 2 = 完成 |
| 读数据 | `AnalogInRead(2048, ch)` → `rd.aidatach1/2/...` | 返回长度 = buffersize |
| DMM 打开 | `DMMOpen(True)` | — |
| DMM 设挡 | `DMMSet(RDDMMDCV, idx)` 等 | idx 见快速入门表 |
| DMM 读 | `DMMReadSingle()` → `rd.DMMData.value` | 返回 byte 字符串如 `b"0.687V"` |

### 10.1 注意点

1. **DC 模式输出**：AWG `RDFUNCDC` 时，最终输出 = `vOffset + amp * 0` = `vOffset`。把 `amp` 设为 0 即可获得纯直流。
2. **PSU 与 AWG 切换延时**：实测 PSU 改变后 V+ 稳定到 ±10 mV 大约需要 15 ~ 30 ms，软件中统一 `sleep(0.02)`。
3. **状态机超时**：`AnalogInRun` 之后必须轮询 `AnalogInStatus`，不能阻塞死，建议每次循环 `sleep(0.005)`，整体超时 1 s。
4. **DMM 与示波器互斥**：不要同时开启 DMM 与示波器读取同一节点，避免相互干扰，按需切换。
5. **关闭顺序**：先关 AWG → 关 PSU → 关示波器 → `DeviceClose`；异常路径下仍按此顺序。

---

## 11. 项目目录结构

```
bjt_test_system/
├── main.py                       # 程序入口（启动 QApplication）
├── requirements.txt
├── README.md
├── pyproject.toml                # 可选：用 Poetry 管理
│
├── config/
│   ├── default.yaml              # R_B, R_C, Ic_max 等可调参数
│   └── logging.yaml
│
├── core/                         # 硬件抽象层
│   ├── __init__.py
│   ├── device.py                 # DeviceManager
│   ├── psu.py
│   ├── awg.py
│   ├── scope.py
│   ├── dmm.py
│   ├── safety.py
│   └── types.py                  # 全部 dataclass / TypedDict
│
├── measurement/                  # 测量逻辑层
│   ├── __init__.py
│   ├── detector.py               # BJTDetector
│   ├── static.py                 # StaticMeasurer
│   ├── vce_sat.py                # SatMeasurer
│   ├── curves.py                 # CurveSweeper
│   └── linearity.py              # LinearityAnalyzer  ← β 线性精度
│
├── analysis/
│   ├── __init__.py
│   ├── data_processor.py
│   └── report.py                 # ReportBuilder
│
├── app/
│   ├── __init__.py
│   └── orchestrator.py           # TestOrchestrator (QThread)
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── live_plot.py
│   ├── panels/
│   │   ├── connection_panel.py
│   │   ├── hw_config_panel.py
│   │   ├── action_panel.py
│   │   └── live_value_panel.py
│   └── resources/                # 图标 / qss
│
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── config_loader.py
│
├── tests/
│   ├── test_static_math.py       # 静态点计算单元测试
│   ├── test_detector_logic.py    # 用 mock RD 测识别逻辑
│   ├── test_linearity.py         # 注入合成 β-Ic 数据验证 η_β 计算
│   └── test_safety.py
│
├── data/                          # 测试结果存档（运行时创建）
└── reports/                       # 报告归档（运行时创建）
```

### 11.1 requirements.txt（建议）

```
numpy>=1.26
pandas>=2.1
matplotlib>=3.8
PySide6>=6.6
pyqtgraph>=0.13            # 可选
reportlab>=4.0
jinja2>=3.1
pyyaml>=6.0
loguru>=0.7
# pyRD 来自雨骤 IP-SDK，无 PyPI 包，sys.path 引入
```

---

## 12. 完整测试流程（"一键全套" 模式）

```
                ┌───────────────┐
                │ 启动 GUI       │
                └──────┬────────┘
                       ▼
                ┌───────────────┐
                │ 连接 Model S  │ DeviceManager.get()
                └──────┬────────┘
                       ▼
                ┌───────────────┐
                │ 加载硬件配置  │ R_B, R_C, 阈值
                └──────┬────────┘
                       ▼
                ┌───────────────┐
                │ 用户插管 + 点 ▶│
                └──────┬────────┘
                       ▼
        ┌──────────────────────────────┐
        │ Step 1: 识别 NPN/PNP        │  ── BJTDetector.detect()
        │   ↓ 成功 / UNKNOWN→报错退出 │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 2: 静态参数扫描         │  ── StaticMeasurer.sweep()
        │   产出 active 区 β 序列      │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 3: Vce(sat) 测量        │  ── SatMeasurer.run()
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 4: 输出特性曲线扫描     │  ── CurveSweeper.sweep()
        │   GUI 实时更新 4 条曲线      │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 5: β 线性精度评估       │  ── LinearityAnalyzer.run()
        │   从 Step 2/4 数据中筛选     │  产出 BetaLinearity(η_β …)
        │   GUI 出 β-Ic 子图           │
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 6: DataProcessor 分析   │  β 中位数 / Early 电压 / 评级
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ Step 7: ReportBuilder 出报告 │  PDF + CSV + JSON
        └──────┬───────────────────────┘
               ▼
        ┌──────────────────────────────┐
        │ 关闭电源 / AWG / 示波器       │  finally 块
        └──────────────────────────────┘
```

每一步在 orchestrator 线程内执行，每步开始/结束 `emit status(...)` 给 GUI 显示。

---

## 13. 开发任务清单与里程碑

### 阶段 0：环境准备
- [ ] 安装 Anaconda + Python 3.13；`pip install -r requirements.txt`
- [ ] 安装 IP-SDK，在 `sys.path` 中追加 `…\IP-SDK\Python\src`
- [ ] 焊接测试夹具：22 kΩ + 220 Ω + 8 脚插座 + 钳位二极管
- [ ] 跑通 SDK 快速入门示例（W1 输出 1 kHz 正弦，示波器抓回波形）

### 阶段 1：硬件抽象层（2 天）
- [ ] `DeviceManager` 单例，含 sn 解析与关闭钩子
- [ ] `PSU`、`AWG`（DC 输出）、`Scope`（双通道平均采集）实现并打通
- [ ] `Scope.acquire()` 用 RDStateDone 等待，含超时
- [ ] 单元测试：用真机做"V+ 输出 X V → 示波器测回 X V"闭环

### 阶段 2：测量逻辑层（3 天）
- [ ] `BJTDetector` 两套偏置试探 + 退化结果处理
- [ ] `StaticMeasurer` 扫描 \(V_{BB}\)、判区域、输出 `list[StaticPoint]`
- [ ] `SatMeasurer` 实现强迫 \(\beta\) 思路
- [ ] `CurveSweeper` 实现外双重循环（\(I_B\) 等级 × \(V_{CC}\) 步进）
- [ ] `LinearityAnalyzer` 实现 \(\eta_\beta\) 计算与评级
- [ ] PNP 通路完整测试

### 阶段 3：安全 & 分析（1 天）
- [ ] `SafetyGuard` + `SafetyAbort` 异常路径
- [ ] L3 独立监测线程
- [ ] `DataProcessor`：β 中位数、Early 拟合、合成 β-Ic 数据集供 LinearityAnalyzer

### 阶段 4：GUI（3 天）
- [ ] PySide6 主窗口骨架
- [ ] 各 panel（硬件配置 / 动作 / 实时值 / 日志）
- [ ] `LivePlotWidget` 嵌入 matplotlib，支持多曲线动态更新
- [ ] β-Ic 子图（log 横轴）与 \(\eta_\beta\)、评级文字标注
- [ ] `TestOrchestrator` 与 Signal 接线
- [ ] 紧急停止按钮 + interruption 检查点

### 阶段 5：报告与归档（1 天）
- [ ] CSV 落盘（含 `beta_linearity.csv`）
- [ ] PDF 报告（reportlab + Jinja2 模板，含 \(\eta_\beta\) 模块）
- [ ] DeviceReport JSON 序列化（pydantic 或 dataclasses.asdict）

### 阶段 6：联调与测试样本（2 天）
- [ ] 用 S8050（NPN）、S8550（PNP）各 5 颗实测
- [ ] 标定 \(\beta\) 与 \(V_{CE(sat)}\)，与万用表读数对比，误差应 < 5 %
- [ ] 同一颗管子重复评估 \(\eta_\beta\) 5 次，离散度 < 10 %
- [ ] 各类异常注入：短路 / 开路 / 反插，验证保护逻辑

---

## 14. 验收标准

| 项 | 标准 |
|---|---|
| 识别正确率 | 30 颗样本（NPN/PNP 各半）100 % 正确 |
| \(\beta\) 测量重复性 | 同一颗管子 10 次测量，相对偏差 < 3 % |
| \(V_{BE}\) 测量绝对误差 | 与高精度桌面万用表比对，< 10 mV |
| \(V_{CE(sat)}\) 测量绝对误差 | < 30 mV |
| 输出曲线总时长 | 5 条曲线 × 60 点 ≤ 60 s |
| \(\eta_\beta\) 计算正确性 | 合成数据集注入测试中，与解析解差 < 0.5 % |
| \(\eta_\beta\) 重复性 | 同一颗管子重复评估 5 次，相对偏差 < 10 % |
| 安全响应 | 故意短路 C-E，软件须在 100 ms 内切断 V+ |
| GUI 刷新 | "实时数值" 区每秒 ≥ 5 次更新，曲线无阻塞卡顿 |
| 报告完整性 | PDF 含 §9.3 所有要素（包括 \(\eta_\beta\) 模块），原始 CSV 可二次分析 |

---

## 附录 A：典型 \(\beta\) 计算示例

设当前测得：
- 设定 \(V_{BB} = 1.50\ \text{V}\)，\(V_{CC} = 5.00\ \text{V}\)
- 示波器实测 \(V_B = 0.681\ \text{V}\)，\(V_C = 2.93\ \text{V}\)
- \(R_B = 22\ \text{k}\Omega\)，\(R_C = 220\ \Omega\)

则：
\[
I_B = \frac{1.50 - 0.681}{22\,000} = 37.2\ \mu\text{A}
\]
\[
I_C = \frac{5.00 - 2.93}{220} = 9.41\ \text{mA}
\]
\[
V_{BE} = 0.681\ \text{V},\quad V_{CE} = 2.93\ \text{V}
\]
\[
\beta = \frac{I_C}{I_B} = \frac{9.41 \times 10^{-3}}{37.2 \times 10^{-6}} \approx 253
\]
\[
P_{\text{diss}} = V_{CE} \cdot I_C = 2.93 \times 9.41\ \text{mW} \approx 27.6\ \text{mW}\quad\checkmark
\]

工作区域：\(V_{BE} > 0.5\ \text{V}\) 且 \(V_{CE} > 0.3\ \text{V}\) → **active**。

---

## 附录 A2：\(\beta\) 线性精度计算示例

假设在评估区间 \([0.5\,\mathrm{mA},\,20\,\mathrm{mA}]\) 内、\(V_{CE} \in [2,4]\,\mathrm{V}\) 范围内筛得 10 个 active 点，得到如下 \(\beta\)–\(I_C\) 数据：

| \(I_C\) / mA | 0.6 | 1.2 | 2.0 | 3.5 | 5.0 | 8.0 | 12.0 | 16.0 | 18.0 | 19.5 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| \(\beta\) | 178 | 205 | 224 | 241 | 248 | 253 | 246 | 228 | 210 | 192 |

统计量：

\[
\beta_{\max} = 253\ (\text{at } I_C = 8.0\,\text{mA}),\qquad
\beta_{\min} = 178\ (\text{at } I_C = 0.6\,\text{mA})
\]
\[
\beta_{\mathrm{avg}} = \frac{1}{10}\sum_{i=1}^{10}\beta_i = 222.5
\]
\[
\eta_\beta = \frac{\beta_{\max} - \beta_{\min}}{\beta_{\mathrm{avg}}}
          = \frac{253 - 178}{222.5}
          \approx 0.337
\]

按 §4.5.5 评级表，\(\eta_\beta = 0.337\) 落在 C 级（一般），说明该器件在所选区间内 \(\beta\) 波动接近 1/3，低电流侧（0.6 mA）与高电流侧（19.5 mA）均出现明显下降——典型的复合电流主导（低端）与高注入效应（高端）特征。报告中应在 \(\beta\)–\(I_C\) 图上把 \(I_C = 8\) mA 标为 "peak β"。

---

## 附录 B：易错点与排查

1. **AWG DC 输出实际幅值偏移**：W1 输出 0 V 时实测可能存在 ±20 mV 偏置，建议程序启动时做一次"零位标定"——把 W1 设 0 V，示波器测对应通道电压，记录偏置值并在后续计算中扣除。

2. **示波器 5 V 量程下分辨率**：12 bit ADC → \(5/4096 \approx 1.2\ \text{mV}\)。\(V_{BE}\) 应有 5 mV 级别精度，但 \(V_C\) 在小 \(I_C\) 时变化小（\(\Delta V_C = R_C \cdot \Delta I_C\)），220 Ω 下 1 mA 对应 220 mV，足够；但若 \(R_C\) 改为 100 Ω，则 1 mA 仅 100 mV，需配合多次平均提高 SNR。

3. **饱和判别错位**：实测中可能出现 \(V_{CE}\) ≈ 0.4 ~ 0.6 V 的"准饱和"区，建议把饱和阈值放宽到 0.5 V，并配合 "\(I_C\) 随 \(I_B\) 增长是否还成比例" 二级判据。

4. **PNP 测试 W2 = 5 V 时电流方向**：因为 W2 与 V+ 都是单端对地，W2 输出 5 V 时拉电流能力较 V+ 弱（AWG 驱动能力较小），若 \(I_C\) > 20 mA 可能出现"塌陷"。务必在 GUI 中显示 \(V_E\) 实测值并与设定比较；偏差 > 100 mV 给出警告。

5. **数据帧解析**：`rd.aidatach1` 是 ctypes 数组，必须 `list(rd.aidatach1)` 或 `np.frombuffer` 转 numpy，否则 `np.mean` 会很慢。

6. **\(\eta_\beta\) 受 Early 效应污染**：若评估时混入了 \(V_{CE}\) 跨度过大的点（如同时包含 \(V_{CE} = 1\) V 与 \(V_{CE} = 4\) V），Early 效应会让"同 \(I_C\)、不同 \(V_{CE}\)"对应不同 \(\beta\)，从而虚高 \(\eta_\beta\)。务必通过 `vce_window` 参数限制 \(V_{CE}\) 范围，或者按 §4.5.3 中"推荐做法"在固定 \(V_{CE}\) 处插值，再计算 \(\eta_\beta\)。

7. **低电流端噪声放大 \(\eta_\beta\)**：当 \(I_C\) 接近 0.2 ~ 0.5 mA 时，\(V_C\) 测量噪声会显著影响 \(I_C\) 进而影响 \(\beta\)。建议在低电流端用 DMM 复测一次 \(I_C\) 做校正，或者增大 \(R_C\)（如 1 kΩ）提高低电流分辨率。

---

文档结束。Agent 可据此文档逐阶段实施。
