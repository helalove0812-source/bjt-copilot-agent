# Agent Optimization Records

这个目录用于保存 BJTagent 每个阶段性优化的数据记录。

每次做出架构级或能力级突破后，都要新增一份记录，至少包含：

- 优化阶段名称
- 目标和动机
- 架构变化
- 新增/修改的核心文件
- 可量化数据
- 测试结果
- API smoke 结果
- 已知限制
- 下一步建议

推荐命名：

```text
YYYY-MM-DD-short-topic.md
```

当前记录口径：

- 测试结果以本地 `pytest` 输出为准
- smoke 数据以 `/api/ai-chat` 的真实返回为准
- 不把候选 pinout、模型参数或异常判断当作正式器件库事实，除非用户确认
