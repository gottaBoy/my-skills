---
name: analyze-design
description: '先分析后设计 — 强制在编码前完成需求分析和设计文档。Analyze before design, design before code. Use when: any non-trivial feature request, architecture change, or when user says "先分析" / "出设计" / "出方案". Produces: analysis report + design doc + gap assessment.'
---

# Analyze-Design — 分析→设计→编码 铁律

> **强制门禁**: 任何超过 50 行代码的变更，必须先通过本 Skill 的分析和设计阶段。
> 不允许"边写边想"、"先写着看"、"直接改代码"。

## When to Use
- 接到新功能需求，且 > 50 行代码
- 用户说 "先分析" / "出方案" / "出设计" / "还缺什么"
- 架构变更、新增页面、新增 API
- AI 编码前需要方向确认的场景

## 三步法

### Step 1: 探索现状 (Explore Current State) → 分析报告

**输入**: 用户需求描述
**输出**: 简短分析（在对话中直接输出，不落文件）

```
分析报告模板：
1. 现状 — 当前代码/数据/API 能做什么，不能做什么
2. 差距 — 从"现状"到"用户期望"还缺什么
3. 可行性 — 技术上是否可行，需要多少改动
4. 风险 — 哪些地方容易出错
```

### Step 2: 设计方案 (Design Proposal) → 设计文档

**输入**: 分析报告
**输出**: 设计要点（对话中输出）

```
设计方案模板：
1. 改动清单 — 要改哪些文件，每个文件改什么
2. 数据流 — 新增/修改的 API 和数据模型
3. 优先级 — P0（必须）/ P1（应该）/ P2（锦上添花）
4. 不回滚策略 — 如果出问题怎么回退
```

### Step 3: 确认后执行 (Confirm & Execute)

**输入**: 用户对设计的确认
**输出**: 代码变更

```
确认清单：
[ ] 用户已确认设计方案
[ ] 明确 P0/P1/P2 优先级
[ ] 明确本次实现范围（只做 P0，还是全做）
```

## 与其他 Skill 的关系

```
analyze-design → spec-generator → execution-governor → verify-feedback
   (轻量分析)     (正式规格)        (TDD 执行)         (验证闭环)
```

- **analyze-design** 是轻量入口，适合日常迭代
- **spec-generator** 是重量入口，适合大功能、跨服务变更
- 如果用户需求很明确，可以从 `analyze-design` 直接跳到 `execution-governor`
- 如果需求模糊、范围大，从 `analyze-design` 跳转到 `spec-generator`

## 示例触发词

| 用户说 | AI 行为 |
|--------|---------|
| "先分析下还缺什么" | 执行 Step 1，输出分析报告 |
| "这个页面内容是不是太少了" | 执行 Step 1+2，分析 + 设计方案 |
| "出个方案再动手" | 执行 Step 1+2，等用户确认再写代码 |
| "直接改" | 如果 > 50 行，提示先执行 analyze-design |
