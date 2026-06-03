# BJTagent 平台化演进路线设计

## 目标

把当前以 BJT 测试任务为中心的 `BJTagent`，从“具备基本规划、执行、安全门和前端交互的领域 agent”，演进成一套更接近工程化 Hermes 风格的专用智能体系统。

这份路线设计关注的是未来 1-2 个开发阶段的架构方向，而不是单次功能点实现。核心目标是：

- 提升 agent 行为的稳定性
- 提升多轮任务的可解释性
- 提升前后端与 evaluator 的结构一致性
- 提升运行时、评估与自动化之间的复用能力
- 在不放宽硬件安全边界的前提下，持续提高 agent 智能表现

## 当前基础

当前项目已经具备以下重要基础：

- 规则优先、LLM 可选辅助的 agent 主链
- BJT 测试计划生成、计划修改、仿真执行、硬件执行、结果解释能力
- 硬件确认、NPN gate、runtime abort、preflight 等安全门
- 未知型号补全过程、用户器件库管理、本地 profile 记忆
- Web UI、API、本地 agent 三条主入口
- `run_agent_regression.py` 与 `evaluate_agent_samples.py` 驱动的数据集回归
- `diagnosis_tags`、`next_action_items`、`preflight_summary` 等结构化能力的雏形

这些基础说明：

- 项目已经不是从零开始设计 agent
- 当前主要矛盾不再是“有没有功能”
- 而是“结构是否稳定、模块是否清晰、输出是否可评估、行为是否能跨入口复用”

## 核心演进原则

### 1. 安全门优先

任何架构演进都不能削弱以下边界：

- `UNKNOWN` 不得自动降级为 `NPN`
- `PNP` 不得自动进入硬件执行
- 硬件执行必须显式确认
- preflight / runtime abort / safety clamp 不能被前端或 LLM 绕过

### 2. 结构优先于文案

后续能力升级优先产出稳定结构，而不是继续增加自然语言文案分支。

要让 agent 能稳定产出：

- 做了什么
- 为什么这么做
- 下一步建议做什么
- 哪一步被安全层阻断

这些都应该优先用结构表达，再由前端或文案层消费。

### 3. evaluator 优先消费真实输出

评估系统的目标不是继续“猜 agent 可能在想什么”，而是尽量评估运行时真实结构化输出。启发式回退仍保留，但应该逐步边缘化。

### 4. 渐进式平台化

本项目的目标不是转成 Hermes 那样的通用多平台总线，而是吸收其：

- 分层
- 工具优先
- 状态管理
- 评估环境
- 结构化动作

这些最有价值的工程方法，服务于 BJT 垂直领域。

## 五条主线

### 主线一：统一动作结构

这是当前最优先的主线。

目标是把当前分散在：

- `next_action_items`
- `completed_actions`
- `diagnosis_tags`
- `preflight_summary`
- safety / plan / modify / diagnose 的中文建议

中的动作建议，统一成稳定 taxonomy 和输出契约。

最终要求：

- `plan / modify / safety / diagnosis / autonomy` 都能产出稳定动作标签
- evaluator 能优先读取真实动作输出
- 前端和 API 可以直接消费动作结构
- 文案不再承担动作语义本体

这一主线解决的问题是：

- agent 会做什么，不再靠文案猜
- 前后端对齐更容易
- soft metrics 更诚实
- 后续自动优化与建议卡片有统一基础

### 主线二：模块化认知层

当前项目的核心认知能力主要集中在少数关键文件中，后续如果继续叠加复杂意图、多轮上下文、自主优化和结果解释，很容易继续膨胀。

需要逐步拆清以下责任：

- `intent interpretation`
- `plan shaping`
- `diagnosis classification`
- `action recommendation`
- `autonomous refinement`
- `profile completion guidance`

要求是：

- diagnosis 负责“看见了什么”
- action recommendation 负责“下一步做什么”
- safety 负责“能不能做”
- autonomy 负责“什么时候自动收紧/加深/继续”

这一主线解决的问题是：

- 复杂意图不再全压到 conversation/agent 主分支
- 多轮上下文更容易维护
- diagnosis 和 next actions 的语义边界更清晰
- 后续引入更多能力时，不必继续扩大主循环复杂度

### 主线三：运行与评估解耦

现在项目已经具备了回归和样本评估基础，但运行时真实结构输出与 evaluator 之间仍然存在一部分“后解释”。

目标是形成更清晰的链路：

- 运行时输出结构化结果
- API 透传结构
- evaluator 直接消费结构
- regression dataset 对这些结构做软统计与逐步增强

后续需要让 evaluator 更明确回答：

- 哪些字段已经由真实运行时结构支持
- 哪些字段仍然靠回退映射
- 哪些 category 的行为稳定
- 哪些 category 只是 intent 对了，但动作和解释还弱

这一主线解决的问题是：

- 评估不再失真
- agent 能力改进能被更快感知
- soft/hard 指标边界更清晰
- 后续做自动优化时，可以用结构化行为做反馈信号

### 主线四：状态与错误标准化

当前项目已经有：

- agent_state
- execution.aborted / skipped
- preflight summary
- pending profile fields
- pending library action

但这些状态与错误仍然分布在不同路径和字段中。

后续应统一成标准状态/错误体系，覆盖：

- 对话状态
- 计划状态
- 执行状态
- 阻断状态
- 补全状态
- 器件库确认状态

建议统一几类状态：

- `idle`
- `plan_ready`
- `simulation_ready`
- `awaiting_profile_fields`
- `awaiting_hardware_confirmation`
- `executing`
- `aborted`
- `completed`
- `profile_library_ready`

建议统一几类错误或阻断原因：

- `unsafe_request`
- `hardware_confirmation_required`
- `unknown_model_incomplete`
- `pnp_execution_blocked`
- `runtime_abort`
- `preflight_blocked`

这一主线解决的问题是：

- 前端状态展示更稳
- API 响应更统一
- evaluator 能更清楚分类失败原因
- 后续日志与审计更容易结构化

### 主线五：工具优先的 agent 闭环

Hermes 最值得借鉴的一点是：工具调用不是附属品，而是主循环核心。

对 `BJTagent` 来说，后续最值得演进的是把领域能力进一步抽象为稳定工具或动作单元，例如：

- `plan tool`
- `modify tool`
- `diagnosis tool`
- `preflight tool`
- `library tool`
- `autonomy refine tool`

并让 agent 主循环更像：

- 理解任务
- 选择动作/工具
- 执行
- 更新状态
- 返回结构化结果

而不是：

- 直接拼一段解释文案
- 再由调用方猜 agent 可能做了什么

这一主线解决的问题是：

- 跨 Web/API/本地 agent 的行为更一致
- 结构化输出更自然
- 后续自动化、cron、自检、批处理能力更容易接入

## 推荐阶段拆分

### 阶段 A：动作与状态标准化

优先级：`P0`

目标：

- 完成动作 taxonomy v2
- 完成 `completed_action_items / next_action_items / safety_action_items`
- 统一 agent state / execution state / blocked reason taxonomy

产出：

- 稳定动作 schema
- 稳定状态 schema
- API 与 evaluator 对真实结构的优先消费

这是最关键的底座阶段，没有这一层，后续前端卡片、自动优化、可解释性都会继续靠文案。

### 阶段 B：认知层解耦

优先级：`P0`

目标：

- 拆出复杂意图处理与阶段式计划表达
- 拆出 diagnosis 到 next actions 的稳定映射
- 拆出 autonomous-adjust 的专用策略逻辑

重点覆盖：

- 复杂条件式意图
- 多轮 modify
- “下一步你自己调整”
- 执行后 refine

### 阶段 C：运行时与评估直连

优先级：`P1`

目标：

- evaluator 直接基于运行时真实结构打软分
- 补充“真实结构命中率”“回退映射占比”等可见性
- 增强 regression dataset 对复杂意图、结果解释、动作结构的覆盖

### 阶段 D：错误与安全状态系统

优先级：`P1`

目标：

- 统一安全动作标签
- 统一 preflight / runtime abort / skipped / blocked 的结构化说明
- 让前端、日志、评估对这些状态理解一致

### 阶段 E：工具化与平台化闭环

优先级：`P2`

目标：

- 把若干稳定领域能力沉淀为工具化接口
- 为未来的前端建议卡片、自动化自检、批量回归、自主操作建立统一接口

这阶段不是做“大而全平台”，而是让 `BJTagent` 的 BJT 专用能力具备平台化底座。

## 推荐优先级

### P0

- 动作结构彻底统一
- 状态/错误 taxonomy 统一
- 复杂意图拆解与阶段式计划表达
- 多轮上下文下的 modify / autonomous-adjust 解耦

### P1

- 结果解释标签化与 diagnosis 到动作的稳定映射
- 危险请求的结构化安全动作
- evaluator 与运行时结构的进一步直连

### P2

- 未知型号补全过程优化
- 器件库命令多轮确认细化
- 前端消费结构化字段
- dry-run / selftest / 自动化自检接入

## 对现有系统的影响

这份路线图不会要求：

- 立即重写所有核心文件
- 立即把 `expected_actions` 升级成硬门槛
- 立即重做前端
- 立即做 Hermes 那种多平台网关能力

它要求的是：

- 后续开发优先顺序更明确
- 每轮改动都优先补结构、状态、评估，而不是只补文案
- 把现有“能跑”的能力，逐步变成“能解释、能评估、能复用”的能力

## 风险与控制

### 风险 1：并行开发时核心文件冲突

控制：

- 优先做小步、边界清晰的模块落地
- 对核心大文件采用“只抽一层、不整文件重写”的策略
- 每一轮先以 evaluator 和状态文档锁定预期，再动运行时

### 风险 2：taxonomy 设计过快膨胀

控制：

- 先做高频动作、状态、错误
- taxonomy 按 v1 / v2 演进，不一次性追求完备

### 风险 3：前后端、评估与运行时字段脱节

控制：

- 明确规定 evaluator 优先读真实运行时结构
- API 优先透传结构
- 前端只消费已稳定字段，不抢跑

### 风险 4：为了“更聪明”误伤安全边界

控制：

- 安全层与动作层分离
- 所有自动优化都必须在 safety policy 之下运行
- 不允许 LLM 文案直接决定硬件执行权限

## 成功标准

当这份路线推进到中期完成时，应至少看到以下结果：

- `BJTagent` 的核心动作、状态、阻断原因都能稳定结构化输出
- evaluator 能更真实评估 agent 行为，而不是靠文案启发式猜测
- 多轮 modify / autonomous-adjust 行为更稳定
- 结果解释和下一步建议不再只是自然语言，而是可消费的结构
- 前端、API、回归系统可以围绕同一套字段协同演进

## 不在本路线内的内容

以下内容不是当前大规划的优先核心：

- 扩成 Hermes 式多平台消息网关
- 大规模重做前端视觉
- 引入复杂通用插件生态
- 把项目转成纯通用 agent 平台

当前路线仍然坚持：

- BJT 垂直领域
- 安全优先
- 评估驱动
- 渐进式平台化
