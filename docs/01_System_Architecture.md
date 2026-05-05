# BJT 自动化测试系统架构设计文档

## 1. 系统概述
本系统是一个全自动的双极性结型晶体管 (BJT) 测试与分析平台。通过集成高精度硬件采样、Python 自动化调度与 React 前端可视化，实现对 BJT 特性的精确提取与评估。

## 2. 系统架构 (三层架构)
### 2.1 硬件层 (Hardware Layer)
- **核心主控**：基于 Instruments Playground SDK (IP-SDK) 提供的高精度数模转换支持。
- **放大与采样电路**：由于原生 AWG 仅支持 ±5V，硬件层外挂高压大电流运放，实现 VCE 0-50V、Ic 0-10A 的输出与采样。采用高精度采样电阻 ($R_{b\_sense}$, $R_{c\_sense}$) 和差分放大器进行电流检测。
- **保护机制**：实现硬件级与软件级双重保护，包括过流、过压、过温及 ESD 防护。

### 2.2 核心逻辑层 (Software Backend)
- **框架**：FastAPI + Python 3
- **硬件抽象层 (HAL)**：`hardware_tester.py` 负责与底层 SDK 通信，解析 NPN/PNP 类型，计算 $\beta$ 线性度。
- **数据管理**：SQLite + SQLAlchemy (`database.py`)，负责测试序列保存与 ISO17025 历史数据归档。

### 2.3 表现层 (UI Frontend)
- **技术栈**：React + Vite + TailwindCSS + ECharts
- **实时通信**：通过 WebSocket 与后端建立全双工通信，确保波形 60fps 流畅渲染。

## 3. 核心计算模型
依据系统规范，所有参数计算均在后端 HAL 层完成：
- $Ib = Vb_{sense} / Rb_{sense}$
- $Ic = Vc_{sense} / Rc_{sense}$
- $\beta = Ic / Ib$
- $VBE = VB - VE$
- $VCE(sat) = VC - VE$
- $\beta_{linearity} = \frac{\beta_{max} - \beta_{min}}{\beta_{avg}} \times 100\%$
