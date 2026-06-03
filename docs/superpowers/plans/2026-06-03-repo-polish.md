# Repo Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成仓库展示层整理，补齐 `.gitignore`、重写中文 `README` 首页，并同步 GitHub 仓库 About。

**Architecture:** 只改仓库展示层，不改业务代码。`.gitignore` 负责忽略本地产物，`README.md` 负责对外展示当前系统全貌，GitHub About 与 README 首段保持同一口径。

**Tech Stack:** Git, Markdown, Mermaid, GitHub repository settings

---

### Task 1: 补齐忽略规则

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/.gitignore`

- [ ] **Step 1: 扩展忽略项**
- [ ] **Step 2: 检查不会误伤已跟踪的重要文件**
- [ ] **Step 3: 运行 `git status --short` 确认工作树只显示预期改动**

### Task 2: 重写中文 README 首页

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/README.md`

- [ ] **Step 1: 用中文首页替换旧脚手架说明**
- [ ] **Step 2: 增加能力概览表格和 Mermaid 结构图**
- [ ] **Step 3: 保留当前真实命令与安全边界描述**

### Task 3: 同步 GitHub 仓库 About

**Files:**
- Modify: `GitHub repository settings (About / Description)`

- [ ] **Step 1: 用与 README 一致的英文短描述更新仓库 About**
- [ ] **Step 2: 校验本地远端配置和推送状态**

### Task 4: 验证与提交

**Files:**
- Modify: `/Users/helap/Documents/Project/雨骤/.gitignore`
- Modify: `/Users/helap/Documents/Project/雨骤/README.md`

- [ ] **Step 1: 运行 `git diff --stat` 检查变更规模**
- [ ] **Step 2: 提交整理结果**
- [ ] **Step 3: 推送到 `origin/main`**
