# Agent Evaluation Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提升 BJTagent 评估可见性，统一 v3 口径，增加软统计，补少量样本与状态文档，同时保持主回归门槛不变。

**Architecture:** 在 evaluator 侧追加非破坏性统计字段，保留现有 JSON 结构与硬门槛逻辑。数据层仅补少量高价值样本，状态文档负责向 Codex 输出后续 agent 核心改进优先级。

**Tech Stack:** Python, JSONL, pytest, Markdown

---

### Task 1: 统一默认数据集到 v3

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_agent_dataset.py`

- [ ] **Step 1: 写失败测试，锁定 evaluator 默认数据集和 dataset 测试默认口径都应指向 v3**
- [ ] **Step 2: 跑测试确认红灯**
- [ ] **Step 3: 最小修改脚本与测试默认路径**
- [ ] **Step 4: 跑测试确认转绿**

### Task 2: 增加 evaluator 软统计

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/scripts/evaluate_agent_samples.py`
- Modify: `/Users/helap/Documents/Project/雨骤/tests/test_agent_dataset.py`

- [ ] **Step 1: 写失败测试，锁定 soft_metrics、category_breakdown、non_gating_fields 输出**
- [ ] **Step 2: 跑测试确认红灯**
- [ ] **Step 3: 以追加字段方式实现软统计，不改主回归硬门槛**
- [ ] **Step 4: 跑测试确认转绿**

### Task 3: 补少量高价值样本

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/数据/agent_regression_cases.jsonl`
- Modify: `/Users/helap/Documents/Project/雨骤/数据/transistor_agent_samples.v3.jsonl`

- [ ] **Step 1: 增补少量 regression cases，覆盖复杂意图、多轮上下文、未知型号、结果解释、器件库命令**
- [ ] **Step 2: 仅补少量代表性 v3 样本，避免引入大幅波动**
- [ ] **Step 3: 用回归命令验证新样本不破坏现有硬门槛**

### Task 4: 输出状态文档并验证

**Files:**
- Create: `/Users/helap/Documents/Project/雨骤/docs/superpowers/status/2026-06-03-agent-evaluation-visibility-status.md`

- [ ] **Step 1: 写状态文档，列出已纳入硬门槛、仅软统计、样本稀薄区和 Codex 后续清单**
- [ ] **Step 2: 运行 `python3 scripts/run_agent_regression.py --json`**
- [ ] **Step 3: 运行 `python3 -m pytest tests/test_agent_dataset.py tests/test_ai_agent.py tests/test_ai_conversation.py tests/test_ai_safety_regression.py -q`**
