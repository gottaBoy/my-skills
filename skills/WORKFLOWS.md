# Spec→Harness→Loop 标准工作流参考

> 本文档定义了 autodrive 项目中三层工作流的完整串联方式。
> 每个工作流都有明确的触发条件、参与的 Skill、输入输出和回退策略。

---

## 工作流概览

| 工作流 | 触发条件 | 参与 Skills | 预计耗时 |
|--------|---------|------------|---------|
| [新功能开发](#workflow-1-新功能开发) | 接到新需求 | spec-generator → task-recipe → execution-governor → code-review → verify-feedback → pr-checklist | 1-3 天 |
| [Bug 修复](#workflow-2-bug-修复) | 线上/测试发现 Bug | bug-hunting → spec-generator(delta) → execution-governor → verify-feedback → pr-checklist | 2-8 小时 |
| [数据库变更](#workflow-3-数据库变更) | 修改 schema | spec-generator → db-migration → execution-governor → verify-feedback → pr-checklist | 1-4 小时 |
| [安全重构](#workflow-4-安全重构) | 代码腐化需要整理 | safe-refactor → verify-feedback → code-review → pr-checklist | 4-16 小时 |
| [依赖升级](#workflow-5-依赖升级) | 升级框架/库 | spec-generator(delta) → execution-governor → verify-feedback → pr-checklist | 2-8 小时 |

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

---

## Workflow 2: Bug 修复

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

## Workflow 3: 数据库变更

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

## Workflow 4: 安全重构

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

## Workflow 5: 依赖升级

### 适用场景
- Python 包升级
- npm 包升级
- Maven 依赖升级
- Spring Boot 版本升级

### 完整流程

```
Phase 1: 规划
  /spec-generator(delta) "升级 <包名> 从 <旧版> 到 <新版>"
    → 查 CHANGELOG，列 Breaking Changes
    → Delta Spec: MODIFIED 记录 API 变更
    ↓
Phase 2: 执行
  /execution-governor "执行升级"
    → 更新 requirements.txt / package.json / pom.xml
    → TDD: 先跑现有测试
    → 逐个修复 Breaking Changes
    ↓
Phase 3: 验证
  /verify-feedback "验证升级"
    → 全量测试
    → 启动验证
    ↓
Phase 4: 交付
  /pr-checklist "提交升级"
```

---

## 工作流选择决策树

```
收到任务
  │
  ├─ 是新功能？
  │   └─ 是 → Workflow 1: 新功能开发
  │
  ├─ 是 Bug？
  │   └─ 是 → Workflow 2: Bug 修复
  │
  ├─ 涉及数据库？
  │   └─ 是 → Workflow 3: 数据库变更
  │
  ├─ 是重构（不改行为）？
  │   └─ 是 → Workflow 4: 安全重构
  │
  ├─ 是升级依赖？
  │   └─ 是 → Workflow 5: 依赖升级
  │
  └─ 不确定？
      └─ 先用 /spec-generator 理清需求
```

---

## 跨工作流衔接

### 当一个工作流触发另一个时

```
Workflow 1 (新功能) 中触发数据库变更:
  → 暂停当前 Task
  → 进入 Workflow 3 (数据库变更)
  → 完成后回到原 Task 继续

Workflow 2 (Bug修复) 中发现需要重构:
  → 先完成最小修复
  → 提交 Bug 修复 PR
  → 另开分支进入 Workflow 4 (安全重构)

Workflow 4 (重构) 中引入新功能诱惑:
  → 严格拒绝：重构就是重构，不改行为
  → 新功能单独走 Workflow 1
```

---

> 这些工作流是参考模板，根据实际项目情况调整。
> 关键原则不变：Spec → Harness → Loop，层层把关，不跳步。
