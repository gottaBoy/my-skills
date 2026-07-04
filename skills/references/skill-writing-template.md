# Skill 写作模板

> "不要让同一个问题第二次还靠记忆解决。" — Karpathy

## 判断：什么时候该写一个 Skill？

| 信号 | 行动 |
|------|------|
| 同一件事手动做了 3 次 | **立即写 Skill** |
| 团队新人反复问同一个问题 | 把答案写成 Skill |
| AI 在某类任务上总是跑偏 | 把约束写成 Skill |
| 每次 PR 都有人漏掉同样的检查 | 把检查写成 Skill |
| 某次排查花了 > 1 小时 | 把排查步骤写成 Skill |

## 模板

```markdown
---
name: my-skill-name
description: '[一句话中文 + Use when: 触发关键词 + 适用范围]'
---

# Skill 名称

## 一句话
[10 个字说清楚这个 Skill 做什么]

## When to Use
- 场景 1（含触发关键词）
- 场景 2
- 场景 3

## 核心流程

### Step 1: 步骤名
- [ ] 检查项
- [ ] 检查项

### Step 2: 步骤名
...

## 检查清单
- [ ] 关键检查 1
- [ ] 关键检查 2

## 常见错误
| 错误 | 正确做法 |
|------|---------|
| ... | ... |

## 命令速查
\```bash
command
\```
```

## 工程级示例

参考仓库中的：
- `skills/bug-hunting/SKILL.md` — 流程驱动型 Skill 范例
- `skills/code-review/SKILL.md` — 检查清单型 Skill 范例
- `skills/devops-engineer/SKILL.md` — 模板生成型 Skill 范例

## 反模式（不要这样做）

| ❌ 反模式 | ✅ 正确做法 |
|----------|-----------|
| 纯理论，无可执行步骤 | 每步都带 `[ ]` 可勾选的检查项 |
| description 写 "A helpful skill" | 包含 Use when + 触发关键词 |
| 5000 行的单一文件 | 拆到 `references/` 子目录 |
| 和已有 Skill 功能重复 | 先读 `SKILLS_GUIDE.md` 确认不重复 |
| 只有描述没有命令 | 给出可复制粘贴运行的命令 |
