# User Profile Library Management Design

## Goal

为当前 BJT Agent 增加“用户器件库管理”能力，让已经沉淀到 `config/user_transistor_profiles.json` 的型号资料可以被查看、搜索、新增、更新、删除、启用/禁用，并同时支持：

- 前端右侧面板中的完整管理界面
- `BJTagent` 对话里的快捷管理命令

本阶段目标是把“已能保存未知型号”的单点能力升级为“可维护、可审计、可继续使用”的长期资料管理能力，而不是改变现有硬件执行权限或安全门。

## Current Problem

当前系统已经具备：

- 未知型号补全
- 用户显式确认后写入独立 JSON 型号库
- 运行时查库优先命中用户库
- 前端聊天区显示“尚未保存 / 已保存到本地库”的提示

但器件库仍缺少管理能力：

- 用户无法在界面中查看已保存型号
- 无法搜索、编辑、删除或禁用条目
- 无法直观看到来源、更新时间、备注等元数据
- Agent 对话尚不能作为器件库管理快捷入口

这意味着型号沉淀虽然已经开始，但还不具备“长期维护”的基本能力。

## Design Choice

本阶段采用“双入口 + 统一管理层”方案：

- 前端右侧面板新增与 `BJTagent` 同尺寸的 `器件库` 面板
- 通过顶部标签在 `BJTagent` 和 `器件库` 之间切换
- `BJTagent` 对话支持器件库快捷命令
- 后端新增统一的用户型号库管理层，负责 CRUD、搜索、启用/禁用和关键字段变更确认
- 运行时查库只读取“启用”的用户条目

不采用以下方案：

- 只做前端面板，不做对话命令：会浪费 Agent 作为快捷入口的价值
- 只做对话命令，不做面板：不利于批量查看和长期维护
- 直接把资料管理逻辑堆进 `transistor_db.py`：边界会变得混乱

## Scope

### In Scope

- 用户型号库列表、搜索和详情查看
- 新增用户型号
- 更新用户型号
- 删除用户型号
- 启用/禁用用户型号
- 前端右侧 `器件库` 面板
- `BJTagent` 对话里的快捷命令入口
- 核心安全字段更新时的二次确认
- 运行时只读取启用的用户型号

### Out Of Scope

- 多用户协作
- 历史版本回滚
- 批量导入/导出
- 远程配置中心
- 自动从 datasheet 网页抓取并直接入库
- 绕过现有 `SafetyGuard`
- 放宽 `PNP` 自动硬件执行限制

## Architecture

本阶段将能力拆成 3 层，避免资料管理和执行控制耦合。

### 1. User Profile Manager

新增一层统一的用户型号库管理模块，负责：

- 读取 JSON 库
- 写入 JSON 库
- 列表和搜索
- 新增、更新、删除
- 启用/禁用
- 字段校验
- 判断本次更新是否触碰核心安全字段

它不负责：

- 生成测试计划
- 允许/阻止硬件执行
- 替代 `SafetyGuard`

### 2. Agent Command Layer

`BJTagent` 对话层负责：

- 理解用户是否在进行器件库管理
- 将命令路由到管理层
- 在涉及关键字段更新或删除时组织确认流
- 给前端返回结构化状态和自然语言反馈

示例命令：

- `列出已保存型号`
- `查看 XYZ123`
- `新增 XYZ123`
- `更新 XYZ123`
- `删除 XYZ123`
- `启用 XYZ123`
- `禁用 XYZ123`

### 3. Runtime Lookup Layer

执行查库层保持单一职责：

- 只读取“启用”的用户型号
- 用户库优先于内置库
- 即使命中用户库，也仍然服从现有 `SafetyGuard`

这保证：

- “资料存在”不等于“允许执行”
- “资料启用”也不等于“允许绕过安全门”

## Data Model

在现有用户型号库存储基础上，补充管理所需元数据：

- `model`
- `bjt_type`
- `vceo_max_v`
- `ic_max_a`
- `p_tot_w`
- `package`
- `pinout_hint`
- `description`
- `source`
- `notes`
- `enabled`
- `confirmed_by_user`
- `created_at`
- `updated_at`

建议语义：

- `enabled`: 是否参与运行时查库
- `source`: `user_confirmed` / `llm_plus_user_confirmation` / `manual_edit`
- `notes`: 管理备注，不参与计划和安全逻辑

第一版不做版本历史，仅保留当前值和更新时间。

## Core Safety Fields

以下字段定义为核心安全字段：

- `bjt_type`
- `vceo_max_v`
- `ic_max_a`
- `p_tot_w`

对这些字段的修改允许发生，但必须二次确认。

以下字段视为普通字段，可一次确认保存：

- `package`
- `pinout_hint`
- `description`
- `notes`

## Frontend Interaction

### Right Panel

右侧现有 `BJTagent` 面板扩展为两个一级标签：

- `BJTagent`
- `器件库`

两者共用同一块右侧区域：

- 尺寸一致
- 位置一致
- 只显示一个面板

切换行为：

- 点击 `器件库`，以同尺寸面板覆盖当前 AI 面板内容
- 点击 `BJTagent`，切回现有 Agent 工作流界面

### Device Library Panel

`器件库` 面板建议分为 3 块：

- 顶部工具栏
  - 搜索框
  - `新增器件`
  - `仅看启用`
- 中部列表
  - 型号
  - 管型
  - 来源
  - 是否启用
  - 更新时间
- 详情区
  - 完整字段展示
  - 编辑
  - 删除
  - 启用/禁用

### BJTagent Coordination

Agent 对话是快捷入口，不替代面板。

当用户通过聊天发出器件库相关命令时，前端应尽量：

- 自动切换到 `器件库` 面板
- 若命中特定型号，则高亮该型号或打开详情

## Conversation Flow

### List / View

- `列出已保存型号`：返回摘要列表，同时前端切到 `器件库`
- `查看 XYZ123`：返回单型号摘要，前端切到 `器件库` 并定位详情

### Create

- 允许从面板新增
- 允许通过对话为缺失型号发起新增
- 新增时必须通过统一校验层

### Update

普通字段更新：

1. 用户发起更新
2. 系统校验通过
3. 直接写入
4. 返回成功提示

核心安全字段更新：

1. 用户发起更新
2. 系统识别为关键字段变更
3. 进入“待确认更新”状态
4. 明确展示旧值和新值
5. 用户再次确认
6. 才真正落库

### Delete

删除必须显式确认：

1. 用户点击删除或发出 `删除 XYZ123`
2. 系统进入“待确认删除”
3. 用户再次确认
4. 才执行删除

### Enable / Disable

- 启用/禁用允许轻确认
- 禁用后不再参与运行时查库
- 启用后恢复参与查库
- 不影响 `SafetyGuard`
- 不影响 `PNP` 自动硬件执行限制

## Error Handling

必须对以下失败给出明确反馈：

- `型号不存在`
  - 返回未找到，并提示是否新增
- `JSON 文件损坏`
  - 不让整个系统崩溃
  - 器件库面板显示错误状态
  - Agent 回复“本地器件库不可读，请先修复配置文件”
- `字段非法`
  - 例如空型号、负数额定值、未知管型
  - 直接拦住，不进入保存
- `确认中断`
  - 不执行更新/删除
  - 清理待确认状态

## API Shape

建议新增独立接口，不复用 `ai-chat`：

- `GET /api/user-profiles`
  - 列表 / 搜索 / 仅看启用
- `GET /api/user-profiles/{model}`
  - 查看详情
- `POST /api/user-profiles`
  - 新增
- `PUT /api/user-profiles/{model}`
  - 更新
- `POST /api/user-profiles/{model}/confirm-update`
  - 确认关键字段更新
- `POST /api/user-profiles/{model}/delete`
  - 删除或确认删除
- `POST /api/user-profiles/{model}/toggle-enabled`
  - 启用/禁用

如果当前 `api_server.py` 更适合统一走 JSON body，也可以退而求其次采用单一路由 + `action` 字段，但语义上仍然应保持“管理接口”和“AI 对话接口”分离。

## Testing Strategy

至少补这 4 类测试：

### 1. Store / Manager Tests

- 列表
- 搜索
- 新增
- 更新
- 删除
- 启用/禁用
- 非法 JSON
- 非法字段

### 2. Agent Conversation Tests

- `列出已保存型号`
- `查看 XYZ123`
- `删除 XYZ123`
- `禁用 XYZ123`
- 核心字段更新触发确认流

### 3. API Tests

- 列表、详情、CRUD、启用/禁用
- 关键字段更新确认
- 删除确认

### 4. Frontend Smoke Tests

- 右侧标签切换
- `器件库` 面板列表和详情入口存在
- 通过聊天命令可切换到 `器件库`
- 不破坏现有 `BJTagent` 状态卡和行动日志

## Safety Invariants

以下规则在本阶段必须保持不变：

- 不恢复 `UNKNOWN -> NPN` 自动降级
- 不绕过现有 `SafetyGuard`
- 不绕过硬件确认
- 即使启用或更新了 `PNP` 型号，也不自动放开硬件执行
- 运行时查库只读取启用的用户条目

## Rollout Plan

推荐分 3 步落地：

1. 后端管理层 + API + 测试
2. 前端 `器件库` 面板 + smoke
3. `BJTagent` 对话快捷入口与前后联动

这样可以先把数据管理和安全边界做稳，再接入 UI 和 Agent 联动。
