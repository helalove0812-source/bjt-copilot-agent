# BJT Test System Host Software Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`-[x]`) syntax for tracking.

**Goal:** 构建一个基于 Python (FastAPI) 和 React 的现代化高颜值 BJT 测试系统上位机软件。

**Architecture:** 前后端分离架构。Python 后端通过 PySerial 读取 FPGA 串口数据流，通过 WebSocket 推送至前端。前端基于 React、Tailwind CSS 构建极简深色工业风 UI，采用 ECharts 渲染高性能 Ic-VCE 曲线。

**Tech Stack:** Python, FastAPI, PySerial, React, Vite, Tailwind CSS, shadcn/ui, ECharts

---

# Tasks

-[x] Task 1: 初始化项目结构 (Project Scaffolding)
  -[x] SubTask 1.1: 创建 FastAPI 后端结构与虚拟环境（包含 fastapi, uvicorn, pyserial, websockets）。
  -[x] SubTask 1.2: 使用 Vite 初始化 React 前端工程，并安装 Tailwind CSS 和 shadcn/ui 基础组件。

-[x] Task 2: 后端串口通信与协议解析 (Backend UART & Protocol)
  -[x] SubTask 2.1: 编写 `serial_manager.py` 实现基于 `pyserial` 的串口连接与断开。
  -[x] SubTask 2.2: 实现数据帧解析逻辑（状态字、测试参数、点阵数据）。
  -[x] SubTask 2.3: 编写 FastAPI WebSocket 路由实现实时数据广播。

-[x] Task 3: 前端主题与全局布局 (Frontend Theme & Layout)
  -[x] SubTask 3.1: 在 Tailwind 中配置深色工业风主题变量（背景色、高亮色）。
  -[x] SubTask 3.2: 构建左侧控制栏（Test Control）、顶部状态栏（Device Status）与右侧主视图区。

-[x] Task 4: 前端测试控制与状态展示 (Test Control & Status UI)
  -[x] SubTask 4.1: 编写串口选择与参数配置表单（扫描步进、保护阈值等）。
  -[x] SubTask 4.2: 编写状态栏组件，实时展示当前测试阶段（NPN/PNP类型、阶段、过流保护红色警报）。

-[x] Task 5: 核心参数与实时曲线可视化 (Data Viz & Curves)
  -[x] SubTask 5.1: 编写 WebSocket 订阅 Hook 并管理前端全局状态流。
  -[x] SubTask 5.2: 实现高对比度 KPI 看板展示 Ib, Ic, β, VBE, VCE(sat) 数据。
  -[x] SubTask 5.3: 引入 ECharts 实现支持多条 Ic-VCE 曲线动态追加的图表组件。

-[x] Task 6: 数据导出归档 (Data Export)
  -[x] SubTask 6.1: 实现 CSV 格式原始数据表导出。
  -[x] SubTask 6.2: 集成 HTML 转 PDF 功能，实现一键生成测试报告及曲线快照下载。

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 3 and Task 2
- Task 5 depends on Task 4 and Task 2
- Task 6 depends on Task 5
