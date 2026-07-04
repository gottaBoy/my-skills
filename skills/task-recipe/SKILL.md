---
name: task-recipe
description: '任务拆解配方（六步法：边界→输入输出→拆INVEST子任务→排序→完成标准→回滚方案）。Task decomposition recipe inspired by Karpathy. Use when: starting a new feature, breaking down complex tasks, organizing work before coding.'
---

# Task Recipe — 把模糊需求变成可执行步骤

灵感来源：Andrej Karpathy "A Recipe for Training Neural Networks" 的思维方式——把复杂过程拆成最小可验证步骤。

## When to Use
- 接到一个新功能需求，感觉"很大很模糊"
- AI 生成的代码总是跑偏，需要更清晰的输入
- 多人协作时需要统一的拆解标准
- 重构前需要评估范围

## 六步拆解法

### Step 1: 定义边界 (Define Scope)
```markdown
## 要做什么（一句话）
[用一句话说清楚目标]

## 不做什么（明确排除）
- [ ] 不涉及 XX 模块
- [ ] 不修改数据库 schema
- [ ] 不改变现有 API 接口签名
```

### Step 2: 列出输入输出 (I/O Contract)
```markdown
## 输入
- 函数参数 / API request body 格式
- 依赖的外部服务/数据库表

## 输出
- 返回值 / API response 格式
- 副作用（写数据库、发消息、写文件）
```

### Step 3: 拆分子任务 (Decompose)
每个子任务必须满足 **INVEST 原则**：
- **I**ndependent — 可独立完成
- **N**egotiable — 实现方式可调整
- **V**aluable — 对用户有价值
- **E**stimable — 可估算工作量
- **S**mall — 不超过半天
- **T**estable — 可独立测试

```markdown
## 子任务列表
- [ ] Task 1: [描述] → 验证方式: [怎么确认完成]
- [ ] Task 2: [描述] → 验证方式: [怎么确认完成]
- [ ] Task 3: [描述] → 验证方式: [怎么确认完成]
```

### Step 4: 确定执行顺序 (Order)
```markdown
## 执行顺序
1. Task 1 (无依赖，先做)
2. Task 2 (依赖 Task 1)
3. Task 3 (可与 Task 2 并行)
```

### Step 5: 定义完成标准 (Definition of Done)
```markdown
## 完成标准
- [ ] 所有测试通过
- [ ] 类型检查无错误
- [ ] 代码已 review
- [ ] 相关文档已更新
- [ ] 已在本地完整运行验证
```

### Step 6: 预设回滚方案 (Rollback Plan)
```markdown
## 如果出问题
- 回滚方式: [git revert / feature flag 关闭 / 数据库回滚]
- 影响范围: [哪些用户/功能会受影响]
- 监控指标: [看什么指标判断是否正常]
```

## 反模式
- ❌ "帮我实现登录功能" — 太模糊
- ✅ 先用这个 recipe 拆成 5-8 个子任务，再逐个让 AI 实现

## 与本项目其他 Skills 配合
1. 先用 `task-recipe` 拆解任务
2. 用 `code-review` 检查每个子任务的代码
3. 用 `pr-checklist` 做最终检查
4. 出问题用 `bug-hunting` 定位
