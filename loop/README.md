# Loop Engineering — 自主 AI 循环系统

> 你不应该再亲自给 Agent 发 prompt 了。你应该设计一个循环系统，让系统替你去 prompt Agent。
> —— Peter Steinberger & Boris Cherny

## 核心理念

Loop Engineering 是 AI 辅助开发的第三次范式转移：

```
Prompt Engineering → Harness Engineering → Loop Engineering
(怎么问)              (什么环境)              (自动循环)
```

**你不再是拿着工具的人，你是设计系统的人。**

## 四层架构

```
┌─────────────────────────────────────────────────────┐
│  Loop 层    ← 自动发现→执行→验证→迭代               │
├─────────────────────────────────────────────────────┤
│  Harness 层 ← Skills + Agents + 工具调用            │
├─────────────────────────────────────────────────────┤
│  Context 层 ← RAG + 记忆管理 + 文件检索             │
├─────────────────────────────────────────────────────┤
│  Prompt 层  ← 角色设定 + 输出格式 + 示例            │
└─────────────────────────────────────────────────────┘
```

## 五阶段循环 (Discover→Plan→Execute→Verify→Iterate)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Discover │───→│   Plan   │───→│ Execute  │───→│  Verify  │───→│ Iterate  │
│ 发现问题  │    │ 制定计划  │    │ 执行任务  │    │ 验证结果  │    │ 改进迭代  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
      ↑                                                              │
      └──────────────── 不满足停止条件 ←────────────────────────────┘
```

## 六大核心要素

### 1. Automations (定时心跳)
`/loop`、`/goal`、GitHub Actions——让 AI 按计划自动运行

### 2. Worktrees (并行隔离)
`git worktree`——多个 Agent 并行工作，互不踩文件

### 3. Skills (知识编码)
`SKILL.md`——项目约定写一次，所有 Agent 共享

### 4. Plugins/Connectors (连接现实)
MCP 协议——让 Agent 读到 Issue、操作数据库、发 Slack 消息

### 5. Sub-agents (分工协作)
`.claude/agents/`——一个人写，另一个人审查

### 6. State (外部记忆)
`STATE.md`、`AGENTS.md`——模型会忘，文件不会
