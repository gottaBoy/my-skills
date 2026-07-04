---
name: ci-triage
description: 'Analyze CI failures, classify root causes, determine auto-fixability. Use when: CI fails, test failures, build errors, lint errors after push, daily CI triage.'
---

# CI Triage Skill

## 目的
分析 CI 失败日志，确定根因和修复优先级。

## 输入
- GitHub Actions CI 运行日志
- 失败的测试名称和错误信息
- 最近的 commit diff

## 输出
- 问题分类：测试失败 / lint 错误 / 构建错误 / 依赖问题 / 其他
- 根本原因分析
- 估计修复难度：简单 / 中等 / 困难
- 是否可以自动修复：是 / 否

## 分类规则

### 简单（auto_fixable: true）
- 语法错误、拼写错误
- 简单的 lint 警告
- 缺少 import / 未使用的 import
- 格式化问题（prettier/black/ruff）

### 中等（auto_fixable: maybe）
- 测试失败但错误信息明确
- 依赖版本冲突
- Type mismatch（类型推断问题）

### 困难（auto_fixable: false）
- 间歇性测试失败（flaky tests）
- 复杂的逻辑错误
- 性能问题
- 需要架构层面修改

## 输出格式

```json
{
  "issue_type": "test_failure",
  "root_cause": "The user service returns null when user not found, but the handler expects a non-null response",
  "difficulty": "medium",
  "auto_fixable": true,
  "file_path": "src/services/user.ts",
  "line_number": 42,
  "suggestion": "Add null check in the handler before accessing user properties"
}
```

## 多问题输出

```json
{
  "total_issues": 3,
  "auto_fixable_count": 2,
  "needs_human_count": 1,
  "issues": [
    { "id": 1, "auto_fixable": true, ... },
    { "id": 2, "auto_fixable": true, ... },
    { "id": 3, "auto_fixable": false, "reason": "flaky test, needs investigation" }
  ]
}
```

## 原则
1. 宁可标记为 needs_human，也不要冒险自动修复
2. 每个判断都要有明确的理由
3. 输出 JSON 格式便于后续 Agent 处理
