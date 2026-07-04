---
name: workflow-orchestrator
description: '七状态机编排 Spec→Harness→Loop 完整闭环。orchestrates tasks through 7 state-machine phases: init→clarify→spec→harness→impl→review→done. Use when: executing multi-step workflows, implementing features from spec, orchestrating agent teams, managing complex task pipelines. Inspired by spec-superflow bridge pattern.'
---

# Workflow Orchestrator — 七状态闭环编排器

> Bridges OpenSpec (planning) + Superpowers (execution) with a state machine.
> 把 Spec → Harness → Loop 串成一条自动化流水线。

## 七状态机

```
┌──────┐   ┌─────────┐   ┌──────┐   ┌─────────┐   ┌──────┐   ┌────────┐   ┌──────┐
│ INIT │──→│ CLARIFY │──→│ SPEC │──→│ HARNESS │──→│ IMPL │──→│ REVIEW │──→│ DONE │
└──────┘   └─────────┘   └──────┘   └─────────┘   └──────┘   └────────┘   └──────┘
 开始        需求澄清      规格制定      建立验证装置    编码实现      审查验证      验收完成

 每个状态都可以 ← 回退到上一个状态
```

| 状态 | 含义 | 产出物 | 用到的 Skill |
|------|------|--------|-------------|
| **INIT** | 收到需求，开始分析 | 无 | — |
| **CLARIFY** | 澄清模糊点，确认边界 | `clarification.md` | — |
| **SPEC** | 制定结构化规格 | `spec.md` | `spec-generator` |
| **HARNESS** | 搭建验证装置 | 测试框架 + 初始测试 | `execution-governor` |
| **IMPL** | 编码实现 | 代码 + 通过的测试 | `task-recipe` |
| **REVIEW** | 审查验证 | `review-report.md` | `code-review` |
| **DONE** | 验收完成 | 合并的 PR | `pr-checklist` |

## 执行契约

每个状态在进入下一个状态之前，必须满足条件：

### INIT → CLARIFY
- [ ] 需求已记录（文字、截图、issue链接均可）
- [ ] 知道改动范围（哪个项目、哪个模块）

### CLARIFY → SPEC
- [ ] 所有 `[NEEDS CLARIFICATION]` 标记已解决
- [ ] 输入输出边界已确认
- [ ] 成功标准可自动化验证

### SPEC → HARNESS
- [ ] spec.md 包含完整的四要素（目标、输入输出、成功标准、边界条件）
- [ ] 所有成功标准都是可自动化验证的

### HARNESS → IMPL
- [ ] 测试框架已就绪
- [ ] 每个成功标准都有对应的测试（初始为失败——RED）
- [ ] Lint 和类型检查已配置

### IMPL → REVIEW
- [ ] 所有测试通过（GREEN）
- [ ] Scope Fence 未被打破（修改文件数 ≤ 3/任务）
- [ ] 无 Rewind Trigger 触发

### REVIEW → DONE
- [ ] 五维度代码审查通过
- [ ] PR 描述完整
- [ ] 无未解决的 TODO/FIXME

## 状态文件格式

在每个任务目录下维护 `STATE.md`:

```markdown
# Task: [任务名]

## 当前状态: IMPL

## 状态历史
- 2026-07-04 10:00 → INIT
- 2026-07-04 10:15 → CLARIFY (澄清了接口格式)
- 2026-07-04 10:30 → SPEC (spec.md 已创建)
- 2026-07-04 11:00 → HARNESS (测试框架已搭建)
- 2026-07-04 11:30 → IMPL (正在编码...)

## 阻塞项
- 无

## 下一步
- 完成单元测试 → 进入 REVIEW
```

## 工具链映射

| 语言 | SPEC 工具 | HARNESS 工具 | LOOP 工具 |
|------|----------|-------------|----------|
| Python | spec-generator skill | pytest + mypy + ruff | `pytest -x --lf` |
| TypeScript | spec-generator skill | vitest + tsc + eslint | `vitest --run` |
| Java | spec-generator skill | JUnit + mvn + checkstyle | `mvn test` |

## 完整编排示例

```
用户: "实现用户手机号登录"

AI 按 WORKFLOW 执行:

INIT    → 收到需求，记下概要
CLARIFY → "确认：1.用验证码还是密码？2.需要注册流程吗？"
SPEC    → 调用 /spec-generator 输出 spec.md:
          - POST /api/auth/login {phone, code} → {token}
          - 成功: 201 + token 不为空
          - 边界: 验证码过期→401, 频繁请求→429
HARNESS → 调用 /execution-governor 搭建测试:
          - test_login_success.py
          - test_login_expired_code.py
          - test_login_rate_limit.py
IMPL    → TDD Loop: 写代码→跑测试→修正→通过
REVIEW  → 调用 /code-review 五维度审查
DONE    → 调用 /pr-checklist 检查 → 提交 PR
```

## 与其他 Skill 的关系

```
workflow-orchestrator (编排者)
  ├── spec-generator     → SPEC 状态
  ├── execution-governor → HARNESS + IMPL 状态
  ├── task-recipe        → IMPL 状态（任务拆解）
  ├── code-review        → REVIEW 状态
  ├── pr-checklist       → DONE 状态
  └── bug-hunting        → 任意状态出错时的回退
```
