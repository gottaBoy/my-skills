---
name: sdd-spec
description: 'SDD 规范 — 标准化软件设计文档工作流。Use when: 开始新功能、做架构变更、需要输出设计文档、写 proposal/specs/design/tasks。集成 spec-generator + task-recipe + execution-governor，提供统一模板和质检门。'
argument-hint: '功能名称或模糊需求描述'
---

# SDD 规范 — 标准化软件设计文档

## 概述

SDD (Software Design Document) 是本项目的标准化设计文档规范，覆盖从需求到实现的完整链路。

```
模糊需求 → Proposal → Specs → Design → Tasks → 执行
               ↑          ↑       ↑        ↑       ↑
           5WHY分析    GWT场景  架构图   INVEST   质检门
```

## When to Use

| 场景 | 必需度 | 产物 |
|------|:------:|------|
| 新功能 > 100 行代码变更 | ✅ **必须** | proposal + specs + design + tasks |
| 架构重构、模块新增 | ✅ **必须** | proposal + design + tasks |
| 数据库 schema 变更 | ✅ **必须** | design (含 UP/DOWN) + tasks |
| API 接口变更 | ✅ **必须** | specs (含 GWT) + design |
| Bug 修复、简单优化 | ⬜ **可选** | 直接 coding，无需 SDD |
| 跨部门/跨模块变更 | ✅ **必须** | 全量 4 文档 |

## 工作流

### Step 1: 澄清 (Clarify)

开始写文档前，先澄清以下问题：

```
┌─ 要解决什么问题？（现状 vs 目标）
├─ 怎么算"做完"？（验收标准）
├─ 涉及哪些模块/服务？
├─ 有前置依赖吗？
├─ 不做的是什么？（明确排除）
└─ 有历史背景或之前的决策吗？
```

输出：确认后的需求要点，进入 Step 2。

### Step 2: Proposal → `docs/proposal.md`

**目标**：说清楚"为什么做"，获得立项决策。

```markdown
# Proposal: [项目名称]

## 动机
- **当前痛点**：[一句话描述]
- **预期收益**：[一句话描述]

## 影响范围
| 组件 | 动作 | 说明 |
|------|------|------|
| `path/to/module/` | ✅ 新增 / 🔄 增强 / 🔧 重构 | 做什么 |
| 涉及数据库变更 | 是 / 否 |
| 涉及 API 变更 | 是 / 否 |
| 涉及配置变更 | 是 / 否 |

## 约束
- [ ] 不破坏现有 API 兼容性
- [ ] 不引入新的外部依赖（除非论证）
- [ ] 兼容现有数据
- [ ] 向下兼容 / 允许不兼容（需说明）

## 确认
- [ ] 问题定义清晰
- [ ] 影响范围明确
- [ ] Non-Goals 已列出
- [ ] 值得投入资源去做
```

**质检门**：
- [ ] 动机有数据或用户反馈支撑
- [ ] Non-Goals 已列出
- [ ] 团队 review 确认方向 OK

---

### Step 3: Specs → `docs/specs.md`

**目标**：用 SHALL/MUST 描述可验证的需求，GWT 场景覆盖边界。

```markdown
# Specs: [项目名称]

## 功能需求
### REQ-001: [标题]
**优先级**: P0 (必须) / P1 (应该) / P2 (可选)

**描述**: 系统 SHALL [具体行为]

**场景**:
- **Given** [前置条件]
- **When** [触发动作]
- **Then** [预期结果]

### REQ-002: [标题]
...

## 非功能需求
### NFR-001: 性能
- P95 响应时间 MUST < 500ms
- 并发 MUST >= 100 QPS

### NFR-002: 兼容性
- MUST NOT 破坏现有 API 契约
- MUST 兼容已有数据库 schema
```

**GWT 场景模板**：

| Given | When | Then |
|-------|------|------|
| 正常输入 | 调用接口 | 返回预期结果 |
| 输入为空 | 调用接口 | 返回 400 + 明确错误信息 |
| 输入非法 | 调用接口 | 返回 400 + 具体校验失败原因 |
| 依赖服务超时 | 调用接口 | 返回 503 + 合理重试建议 |
| 数据不存在 | 查询 | 返回空结果，状态码 200 |
| 并发请求 | 同时写入 | 最终一致 / 幂等 |
| 权限不足 | 调用接口 | 返回 403 |

**质检门**：
- [ ] 每个 REQ 都有 GWT 场景
- [ ] 所有 MUST/SHALL 可测试
- [ ] 边界条件已覆盖（空/异常/超时/并发）
- [ ] Non-Goals 已列出

---

### Step 4: Design → `docs/design.md`

**目标**：技术方案，数据流，模块变更，风险回滚。

```markdown
# Design: [项目名称]

## 架构决策
- **选型方案**: [方案名] — [为什么选它]
- **备选方案**: [方案A] — [否决原因], [方案B] — [否决原因]

## 系统架构
```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ 组件 A    │───→│ 组件 B    │───→│ 组件 C    │
└──────────┘    └──────────┘    └──────────┘
```

## 数据流
```
[触发条件] → [模块1处理] → [模块2处理] → [输出/持久化]
                ↓
           [副作用/消息]
```

## 模块变更
### 新增
- `path/to/new/file.go` — 职责说明

### 增强
- `path/to/existing/file.go` — 改动说明

### 不修改（明确排除）
- `path/to/not-touched/file.go` — 理由

## 数据模型变更
```sql
-- UP
ALTER TABLE xxx ADD COLUMN yyy VARCHAR(100);

-- DOWN
ALTER TABLE xxx DROP COLUMN yyy;
```

## 风险 & 回滚
| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| [风险描述] | 高/中/低 | 严重/中等/轻微 | [缓解措施] |

- **最大风险**: [一句话]
- **回滚方式**: git revert / feature flag / DB rollback
- **监控指标**: [上线后关注什么]
```

**质检门**：
- [ ] 方案选择有明确理由（含否决方案）
- [ ] 数据流图覆盖正常路径 + 异常路径
- [ ] 数据模型变更含 UP + DOWN
- [ ] 风险分析完整
- [ ] 回滚方案可执行

---

### Step 5: Tasks → `docs/tasks.md`

**目标**：拆成 INVEST 子任务，半天内可完成。

```markdown
# Tasks: [项目名称]

## 依赖图
```
T1 (数据层) ──→ T2 (逻辑层) ──→ T3 (API层)
                                   └──→ T4 (前端, 可并行)
```

## 任务列表
- [ ] **T1**: [一句话描述]
  - 文件: `path/to/file`
  - 验证: `go test ./... -run TestXxx -v`
  - 估时: 2h

- [ ] **T2**: [描述]
  - 依赖: T1
  - 文件: `path/to/service.go`
  - 验证: `curl http://localhost:8080/api/xxx`
  - 估时: 3h

## 完成标准
- [ ] 所有任务闭环
- [ ] `go test ./...` 通过
- [ ] Code Review 通过
- [ ] 文档更新完毕
```

**质检门**：
- [ ] 每个任务独立可交付
- [ ] 有明确的验证方式
- [ ] 总估时 < 2 周（否则拆成多个 Phase）
- [ ] 依赖关系正确

---

### Step 6: 执行 (Execute)

任务拆分完成后，进入编码执行阶段，调用下游技能：

```
SDD 完成
  │
  ├──→ @execution-governor  (TDD + Scope Fence + Quality Gates)
  ├──→ @test-strategist     (测试策略 + 覆盖分析)
  ├──→ @architect           (架构审查, 只读)
  ├──→ @ui-designer         (UI审查, 前端变更时)
  └──→ @code-reviewer       (PR审查)
```

---

## 文档放置规范

```
<project>/docs/
├── proposal.md    ← 提案
├── specs.md       ← 规格
├── design.md      ← 设计
└── tasks.md       ← 任务

<project>/doc/specs-my/   ← 旧格式兼容（按需迁移）
```

---

## 模式速查

| 变更类型 | 需要哪些文档 | 重点关注 |
|---------|-------------|---------|
| 新增微服务/模块 | proposal + specs + design + tasks | 架构图、部署、监控 |
| 新增 API | specs + design + tasks | GWT 场景、兼容性 |
| 数据库变更 | design + tasks | UP/DOWN 脚本、数据迁移 |
| 前端页面/组件 | specs + tasks | 状态覆盖 (loading/empty/error/edge) |
| Bug 修复 | (无) | 直接修复，必要时补测试 |
| 重构（行为不变） | design + tasks | 加测试护栏、原子提交 |
| 第三方集成 | proposal + specs + design + tasks | 熔断、重试、降级 |

---

## 与现有技能的衔接

| SDD 阶段 | 上游/输入 | 下游/输出 |
|---------|----------|----------|
| Clarify | 用户需求 / 产品需求文档 | 清晰的 scope + Non-Goals |
| Proposal | Clarify 输出 | `proposal.md` → 团队确认 |
| Specs | proposal.md | `specs.md` → 测试用例 |
| Design | specs.md | `design.md` → 实现参考 |
| Tasks | design.md | `tasks.md` → `execution-governor` |
| Execute | tasks.md | 代码 → PR → Review → Merge |
