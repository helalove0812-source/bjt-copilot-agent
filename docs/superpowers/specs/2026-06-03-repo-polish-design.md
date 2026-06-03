# 仓库展示层整理设计

## 目标

把当前项目的仓库展示层整理到“可直接给别人看”的状态，包括：

- 补齐根目录 `.gitignore`
- 将 `README.md` 重写为中文首页文档
- 更新 GitHub 仓库 `About / Description`

本次整理不修改核心业务逻辑，不改变现有测试、Agent、安全策略或 API 行为。

## 范围

### 1. `.gitignore`

保留现有规则，并补充项目实际需要的忽略项：

- Python 缓存与测试产物
- 虚拟环境目录
- 日志与覆盖率文件
- 前端构建产物与依赖目录
- 常见 IDE / 编辑器目录
- macOS 本地文件

约束：

- 不误伤当前已纳入版本控制的重要资产
- 不忽略 `数据/*.jsonl`
- 不忽略 `IPSDK3.2/` 中当前项目需要保留的 SDK / 示例文件

### 2. `README.md`

将当前偏“早期脚手架说明”的 README 整理为中文首页，面向第一次打开仓库的读者。

首页结构：

1. 项目简介
2. 系统能力概览
3. 系统组成图
4. Agent 工作流图
5. 快速开始
6. 常用命令
7. 仓库结构
8. 安全边界
9. 当前状态与回归方式

内容要求：

- 明确项目是“规则 + LLM 可选辅助 + 本地安全策略 + 数据驱动回归评估”的 BJT 自动化测试系统
- 明确 `BJTagent`、Web UI、CLI、回归脚本、硬件安全门、未知型号沉淀、器件库管理
- README 使用中文
- 增加轻量图表提升可读性，优先使用 Mermaid 或 Markdown 表格，不引入外部图片依赖
- 兼顾 GitHub 渲染效果，避免复杂 HTML

### 3. GitHub 仓库 About

更新 GitHub 仓库网页上的描述，使其与 README 首页口径一致。

策略：

- 使用简洁英文描述，便于 GitHub 列表页展示
- 不额外改 Topics，避免超出本次整理范围

建议文案：

`Rule-first BJT automated test system with optional LLM assistance, local safety guards, web UI, and regression-driven evaluation.`

## 不做的事

- 不改 Agent 核心逻辑
- 不改测试数据集
- 不新增截图素材
- 不调整 GitHub Release、Topics、Pages 等仓库设置

## 验证

完成后验证：

- `README.md` 无冲突标记、结构清晰
- `.gitignore` 生效且不影响当前已跟踪文件
- GitHub 仓库 `About` 已更新
- `git status` 干净

## 风险与处理

### 风险 1：`.gitignore` 误忽略重要文件

处理：

- 仅新增常规忽略项
- 对当前仓库中的数据集、SDK、文档目录保持显式保守

### 风险 2：README 过度宣传，偏离真实实现

处理：

- 所有能力描述以当前仓库已实现内容为准
- 不使用“神经网络系统”“自主学习系统”这类夸大表述

### 风险 3：GitHub About 与 README 表述不一致

处理：

- 先统一 README 首段口径，再同步到仓库 About
