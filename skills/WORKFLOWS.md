# Spec→Harness→Loop 标准工作流参考

> 本文档定义了 autodrive 项目中三层工作流的完整串联方式。
> 每个工作流都有明确的触发条件、参与的 Skill、输入输出和回退策略。

---

## 工作流概览

| 工作流 | 触发条件 | 参与 Skills | 预计耗时 |
|--------|---------|------------|---------|
| [新功能开发](#workflow-1-新功能开发) | 接到新需求 | analyze-design → spec-generator → design-patterns → task-recipe → execution-governor → code-review → verify-feedback → pr-checklist | 1-3 天 |
| [快速迭代](#workflow-8-快速迭代) | 日常小功能 / 增强 | analyze-design → execution-governor → verify-feedback → pr-checklist | 1-4 小时 |
| [新模块设计](#workflow-2-新模块设计) | 设计新模块/服务 | spec-generator → design-patterns → clean-code → execution-governor → pr-checklist | 4-8 小时 |
| [Bug 修复](#workflow-3-bug-修复) | 线上/测试发现 Bug | bug-hunting → execution-governor → verify-feedback → pr-checklist | 2-8 小时 |
| [代码审查（常规）](#workflow-4-代码审查) | PR review / 自检 | clean-code → code-review → verify-feedback | 30 分钟 |
| [数据库变更](#workflow-5-数据库变更) | 修改 schema | db-migration → execution-governor → verify-feedback → pr-checklist | 1-4 小时 |
| [安全重构](#workflow-6-安全重构) | 代码腐化需要整理 | safe-refactor → clean-code → code-review → verify-feedback → pr-checklist | 4-16 小时 |
| [CI/CD 部署](#workflow-7-cicd-部署) | 准备上线部署 | devops-engineer → execution-governor → pr-checklist | 2-4 小时 |

---

## 快捷能力矩阵（一句话触发）

> 在 Copilot Chat 中直接说这些短句，AI 会自动调用对应 skill。

### 🎨 设计阶段

| 你说 | AI 自动调用 | 输出 |
|------|-----------|------|
| "先分析下还缺什么" | `/analyze-design` | 分析报告 + 设计方案|
| "这个页面内容是不是太少了" | `/analyze-design` | 分析 + 设计 + 待确认|
| "帮我设计 XX 功能" | `/spec-generator` | proposal + specs + design + tasks |
| "这个模块怎么架构比较好" | `/design-patterns` + `@architect` | 推荐模式 + 代码骨架 |
| "拆解一下这个需求" | `/task-recipe` | INVEST 子任务 + 估时 |
| "分析下这个方案的风险" | `@architect` | 模块边界 + 反模式识别 |

### 💻 开发阶段

| 你说 | AI 自动调用 | 输出 |
|------|-----------|------|
| "实现 Task X" | `/execution-governor` | TDD 循环: RED→GREEN→REFACTOR |
| "这段代码写得怎么样" | `/code-review` | 五维度问题清单 |
| "代码写得不太对劲" | `/clean-code` + `/code-review` | 命名/函数/注释/错误处理建议 |
| "这个类太大了，拆一下" | `/safe-refactor` | 五步重构 + 行为不变 |
| "这个 SQL 怎么安全上线" | `/db-migration` | UP/DOWN 脚本 + 回滚方案 |
| "帮我写个 Dockerfile" | `/devops-engineer` | Dockerfile + compose + K8s |

### 🧪 测试阶段

| 你说 | AI 自动调用 | 输出 |
|------|-----------|------|
| "帮我设计测试用例" | `@test-strategist` | 测试矩阵 + GWT 用例 |
| "跑一下验证" | `/verify-feedback` | 类型→Lint→单元→集成→启动 |
| "这个 Bug 怎么回事" | `/bug-hunting` | 五步定位 + 根因分析 |

### 🚀 交付阶段

| 你说 | AI 自动调用 | 输出 |
|------|-----------|------|
| "准备提交了" | `/pr-checklist` | 质量门 + PR 模板 |
| "部署上线" | `/devops-engineer` + `/pr-checklist` | Pipeline + 蓝绿策略 |
| "服务挂了怎么办" | `/ops-playbook` | 监控 + 日志 + 灾备 |

---

---

## Workflow 1: 新功能开发

### 适用场景
- 接到新的功能需求
- 需要新增 API 接口
- 新增页面或组件
- 需要跨服务协作的变更

### 完整流程

```
Phase 1: Spec（规划）
  /spec-generator "需求描述"
    → 生成 proposal.md, specs.md, design.md, tasks.md
    → 人工审批：确认规格合理
    ↓
  /task-recipe "拆解 tasks.md 中的任务"
    → 每个子任务满足 INVEST 原则
    → 明确验证方式、依赖关系、估时
    ↓
Phase 2: Harness（执行）
  /execution-governor "开始执行 Task 1"
    → 生成 execution-contract.md
    → 人工审批契约
    → TDD 循环: RED → GREEN → REFACTOR
    → 每个 Task 完成后: Scope Fence 检查
    ↓
  /code-review "审查 Task 1 ~ N 的代码"
    → 五维度检查
    → 修复发现的问题
    ↓
  /verify-feedback "验证全部改动"
    → 类型检查 → Lint → 单元测试 → 集成测试 → 启动验证
    ↓
Phase 3: Loop（闭环）
  /pr-checklist "准备提交 PR"
    → 范围检查 → 质量门 → Commit 规范 → PR 描述
```

### 退出条件
- [ ] 所有 specs.md 中的 MUST/SHALL 需求已实现
- [ ] 测试覆盖率达到 Test Obligations 要求
- [ ] 所有 Review Gates 通过
- [ ] 无 Rewind Trigger 被触发
- [ ] PR 描述完整，已通过 pr-checklist

### 回退策略
- 如果发现 spec 有遗漏 → 回到 Phase 1，补充 Delta Spec
- 如果 Rewind Trigger 触发 → 暂停，人工评估后决定继续或回滚
- 如果 Review Gate 失败 → 修复后重新进入该 Gate

## Workflow 2: 新模块设计

### 适用场景
- 新建一个 Go package / Python module
- 需要设计 API 和数据模型
- 跨服务集成设计（如 zota-repo ↔ zota-server）

### 完整流程

```
Phase 1: 规格
  /spec-generator "新模块描述"
    → 明确输入输出、成功标准、边界条件
    ↓
Phase 2: 设计
  /design-patterns "选择合适的架构模式"
    → Repository? Adapter? Strategy?
    → 画依赖关系图
    ↓
Phase 3: 编码
  /clean-code "按整洁代码规范实现"
    → 命名清晰、函数短小
    → 接口隔离、依赖反转
    ↓
Phase 4: 验证
  /execution-governor "执行 TDD"
    → 先写测试 → 实现 → 重构
    ↓
Phase 5: 交付
  /pr-checklist "提交模块"
```

---

### 适用场景
- 线上用户报告的问题
- CI/CD 测试失败
- 开发过程中发现的缺陷

### 完整流程

```
Phase 1: 定位
  /bug-hunting "描述 Bug 现象"
    → Step 1: 收集证据（日志、堆栈、触发条件）
    → Step 2: 缩小范围（哪个服务？最近改了什么？）
    → Step 3: 形成假设
    ↓
Phase 2: 规划修复
  /spec-generator(delta) "为 Bug 修复创建 Delta Spec"
    → 用 ADDED/MODIFIED/REMOVED 描述变更
    → 明确修复范围和边界条件
    ↓
Phase 3: 执行修复
  /execution-governor "执行修复"
    → 先写失败测试捕获 Bug（TDD 铁律）
    → 最小修复 → 测试通过
    ↓
Phase 4: 验证
  /verify-feedback "验证修复"
    → 确认不引入回归
    → 手动验证原始 Bug 场景
    ↓
Phase 5: 交付
  /pr-checklist "提交修复"
```

### 退出条件
- [ ] 复现步骤 100% 修复
- [ ] 新增的测试通过
- [ ] 已有测试无回归
- [ ] 根因已记录在 commit message 中

---

## Workflow 5: 数据库变更

### 适用场景
- 新增表、修改列
- 数据迁移
- 索引优化
- ORM 模型变更

### 完整流程

```
Phase 1: 规划
  /spec-generator "数据库变更描述"
    → 评估影响范围（哪些服务读写这个表？）
    → 生成 design.md 含数据迁移方案
    ↓
Phase 2: 迁移
  /db-migration "创建迁移脚本"
    → UP 脚本（正向变更）
    → DOWN 脚本（回滚方案）
    → 大表操作评估锁表时间
    ↓
Phase 3: 执行
  /execution-governor "执行迁移"
    → Scope Fence: 只改 DB 相关代码
    → 同步更新 models.py / Entity 类
    ↓
Phase 4: 验证
  /verify-feedback "验证迁移"
    → 测试环境先执行
    → 数据完整性检查
    → API 兼容性验证
    ↓
Phase 5: 交付
  /pr-checklist "提交迁移"
```

### 退出条件
- [ ] UP/DOWN 脚本齐全且可逆
- [ ] 测试环境验证通过
- [ ] ORM 模型已同步
- [ ] 大表操作有锁表时间评估

---

## Workflow 6: 安全重构

### 适用场景
- 函数太长需要拆分
- 重复代码需要抽取
- 模块职责混乱
- 命名不够清晰

### 完整流程

```
Phase 1: 重构
  /safe-refactor "重构目标描述"
    → Step 1: 加测试护栏（先保证测试全绿）
    → Step 2: 做最小改动
    → Step 3: 立即验证
    → Step 4: 原子 commit
    → Step 5: 清理
    ↓
Phase 2: 验证
  /verify-feedback "验证重构后的代码"
    → 行为不变验证（同一组测试）
    → 类型检查和 lint
    ↓
Phase 3: 审查
  /code-review "审查重构"
    → 确认可维护性提升
    → 确认没有引入新问题
    ↓
Phase 4: 交付
  /pr-checklist "提交重构"
```

### 退出条件
- [ ] 所有原有测试通过（行为不变）
- [ ] 新结构清晰，命名准确
- [ ] 无死代码残留

---

## Workflow 8: 快速迭代（分析→设计→编码）

### 适用场景
- 日常小功能、页面增强、组件升级
- 用户说 "先分析下" / "还缺什么" / "内容太少了"
- 不涉及架构变更、不涉及数据库变更

### 完整流程

```
Phase 1: 分析
  /analyze-design "分析现状+差距"
    → 读现有代码、API、数据结构
    → 输出：现状 + 差距 + 可行性 + 风险
    ↓
Phase 2: 设计
  /analyze-design "设计方案"
    → 改动清单 + 数据流 + P0/P1/P2 优先级
    → 等用户确认
    ↓
Phase 3: 编码
  /execution-governor "执行实现"
    → 先写测试 → 实现 → 重构
    ↓
Phase 4: 验证
  /verify-feedback "验证改动"
    → 类型检查 → 测试 → 构建
    ↓
Phase 5: 交付
  /pr-checklist "提交"
```

### 退出条件
- [ ] 用户已确认设计方案
- [ ] P0 项全部完成
- [ ] 无类型错误、无测试回归
- [ ] 页面可正常交互

---

## 工作流选择决策树

```
收到任务
  │
  ├─ 是新功能？     → Workflow 1: 新功能开发
  ├─ 是新模块？     → Workflow 2: 新模块设计
  ├─ 是 Bug？      → Workflow 3: Bug 修复
  ├─ 是代码审查？    → Workflow 4: 代码审查
  ├─ 涉及数据库？    → Workflow 5: 数据库变更
  ├─ 是重构？       → Workflow 6: 安全重构
  ├─ 需要部署？     → Workflow 7: CI/CD 部署
  └─ 不确定？       → 先用 /spec-generator 理清需求
```

---

## 跨工作流衔接

```
Workflow 1 (新功能) 中发现需要设计模式指导:
  → 暂停当前 Task → 进入 Workflow 2 Phase 2 → 回原 Task

Workflow 1 (新功能) 中触发数据库变更:
  → 暂停当前 Task → 进入 Workflow 5 → 回原 Task

Workflow 3 (Bug修复) 中发现需要重构:
  → 先最小修复 → 提交 Bug PR → 另开分支 Workflow 6

Workflow 6 (重构) 中引入新功能诱惑:
  → 严格拒绝：重构就是重构，不改行为
  → 新功能单独走 Workflow 1
```

---

> 这些工作流是参考模板，根据实际项目情况调整。
> 关键原则不变：Spec → Harness → Loop，层层把关，不跳步。
