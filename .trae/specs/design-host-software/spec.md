# BJT 测试系统上位机软件 Spec

## Why
根据“26-4-3-BJT 测试系统方案”，系统需要一个功能完备的上位机软件（Host Software）来配置测试参数、调度自动化测试流程、实时可视化数据（参数和 Ic-VCE 曲线），并进行报告归档。为了实现极致的视觉体验和现代化的交互（响应 `frontend-design` 和 `frontend-skill` 的极简、工业感美学要求），我们采用前后端分离的现代化 Web 架构。

## What Changes
- **系统架构**：后端采用 Python (FastAPI + PySerial) 负责与 FPGA 硬件的 UART 通信与数据解析；前端采用 React + Tailwind CSS + ECharts 负责高性能数据可视化与用户交互。
- **界面美学 (Frontend Design & Skill)**：
  - **视觉主题**：采用 Linear 风格的克制设计（Linear-style restraint），以深色工业风（Dark Industrial/Lab Theme）为主色调，营造专业仪器的高级感。
  - **排版与色彩**：使用高对比度的无衬线字体，单点高亮色（如琥珀色或荧光绿）用于强调状态和动作；去除多余的卡片边框，利用空间留白和对齐构建清晰的视觉层次。
  - **核心布局**：
    - 侧边栏（Test Control）：串口配置、扫描参数设置、一键启停控制。
    - 顶部信息栏（Device Status）：NPN/PNP 识别结果、当前测试阶段、过流保护硬实时告警标志。
    - 主数据区（Parameter Display）：高密度且易读的 KPI 展板（Ib, Ic, β, VBE, VCE(sat)）。
    - 核心视界（Curve Display）：全幅展现的 Ic-VCE 输出特性曲线，支持多曲线平滑绘制。
    - 底部/导出（Data Export）：支持 CSV 原始数据及 PDF 图文报告一键导出。

## Impact
- Affected specs: BJT 上位机交互与数据流设计
- Affected code: 将在项目根目录下新建 `host-software/backend` 和 `host-software/frontend` 两个子工程。

## ADDED Requirements
### Requirement: 高性能串口与 WebSocket 通信
后端（FastAPI）需能够稳定连接 FPGA 串口，按照协议解析状态字、测试参数与曲线点阵数据，并通过 WebSocket 毫秒级推送至前端。

### Requirement: 现代仪器仪表看板 (Modern Instrument Dashboard)
前端需实现以下功能场景：
#### Scenario: 自动化测试闭环
- **WHEN** 用户在侧边栏配置基极/集电极偏置参数并点击“启动测试”
- **THEN** 后端通过串口下发指令，前端顶部状态栏依次切换“初始化 -> 类型识别 -> 偏置配置 -> 参数测量 -> 曲线扫描”状态。
- **THEN** 主数据区实时更新 BJT 的静态参数，核心视界逐点绘制 Ic-VCE 曲线。
- **THEN** 当接收到硬件级过流保护标志时，界面立即高亮警告，并终止数据扫描。

### Requirement: 报告导出归档
支持测试完毕后，将当前绘制的曲线快照与静态参数打包，导出为标准的 PDF 报告和 CSV 数据表。
