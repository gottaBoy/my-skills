# Worktree 隔离指南

> 两个 Agent 写同一个文件 = 两个工程师同时改同一行代码 = 冲突地狱。
> Git Worktree 给每个 Agent 独立的 checkout，互不干扰。

## 为什么需要 Worktree？

```
没有 Worktree:
  Agent A ──→ main 分支 ──→ 改 user.py
  Agent B ──→ main 分支 ──→ 改 user.py  ← 💥 冲突！

有 Worktree:
  Agent A ──→ feature/agent-a 分支 ──→ 自己的工作目录
  Agent B ──→ feature/agent-b 分支 ──→ 自己的工作目录
  互不干扰，各干各的
```

## 基本用法

```bash
# 为 CI 修复 Agent 创建隔离工作树
git worktree add ../autodrive-ci-fix feature/auto-ci-fix

# 为代码审查 Agent 创建隔离工作树
git worktree add ../autodrive-review feature/code-review

# 列出所有工作树
git worktree list

# 清理完成的工作树
git worktree remove ../autodrive-ci-fix
git branch -D feature/auto-ci-fix
```

## Claude Code 中的 Worktree

```bash
# 方式1：直接在隔离工作树中启动
claude-code --worktree feature/add-search

# 方式2：子Agent自动使用隔离工作树
claude-code --prompt "/subagent \"Build the search API\" --isolation worktree"
```

## Sub-agent 配置中的 Worktree

在 `.claude/agents/ci-fixer.toml` 中：
```toml
[isolation]
type = "worktree"
# Agent 自动获得独立 checkout，任务完成后自动清理
```

## 最佳实践

1. **一个 Agent，一个 Worktree** — 永远不要让两个 Agent 共享工作空间
2. **任务完成即清理** — `git worktree remove` + `git branch -D`
3. **命名规范** — `feature/agent-{name}-{task}` 便于追踪
4. **审查带宽是上限** — 你能审查多少代码，就开多少个并行 Agent
