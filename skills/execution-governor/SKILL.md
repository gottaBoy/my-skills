---
name: execution-governor
description: 'Execution governance with TDD enforcement, scope fencing, and quality gates. Use when: implementing tasks from a spec, need to ensure AI does not drift from requirements, want to enforce test-before-code discipline. Inspired by Superpowers (240k⭐) TDD iron-law, Review Gates, and Subagent-Driven Development.'
---

# Execution Governor — 执行不漂移的纪律框架

核心思想（来自 Superpowers）：规划写得再好，执行时没有纪律照样漂移。
TDD 是铁律，Review Gate 层层设卡，Scope Fence 圈定边界。AI 最容易"顺手"做 spec 之外的事情，Governor 把这扇门焊死。

## When to Use
- 从 `spec-generator` 生成了规格，准备开始执行
- 让 AI 实现代码，需要确保不超出 scope
- 重构复杂模块，需要逐步验证
- 多人协作，需要统一的执行纪律

## 执行契约 (Execution Contract)

在执行任何代码之前，先从 spec 工件中提取以下六大约束，形成 `execution-contract.md`：

```markdown
# Execution Contract: [变更名称]
# 自动提取自: proposal.md + specs.md + design.md + tasks.md
# 此文件是执行锚点——所有实现行为必须对标此契约

## 1. Intent Lock（意图锁定）
# 从 proposal.md 提取
实现 [核心目标]。
防止目标漂移：如果发现正在做的不再是上述目标，立即暂停。

## 2. Scope Fence（范围围栏）
### In Scope
- `src/module/file1.py` — 新增 XX 功能
- `src/module/file2.tsx` — 修改 YY 组件

### Out of Scope
- 不修改 API 层
- 不动数据库 schema
- 不碰认证模块

## 3. Non-Goals（明确不做）
- 不引入新依赖
- 不重构无关模块
- 不做性能优化（除非 spec 明确要求）

## 4. Test Obligations（测试义务）
- [ ] 单元测试: [模块] — 覆盖 happy path
- [ ] 单元测试: [模块] — 覆盖边界条件
- [ ] 集成测试: [场景] — 验证端到端流程

## 5. Review Gates（审查门禁）
- Gate 1: 数据层完成后 → Review 数据模型和查询
- Gate 2: 业务逻辑完成后 → Review 核心算法
- Gate 3: API 层完成后 → Review 接口契约
- Gate 4: 全部完成后 → `pr-checklist` 最终检查

## 6. Rewind Triggers（回滚触发条件）
出现以下任一情况，MUST 暂停并重新评估：
- 需要改动 Out of Scope 的文件 → 评估是否需要调整 scope
- 新代码导致已有测试失败 → 先修复，再继续
- 发现 spec 中未覆盖的边界情况 → 回 spec-generator 补充
- 实现复杂度远超预估 (>2x) → 暂停，讨论是否拆分
- 外部依赖不可用 → 先 mock，标记为待验证
```

## 五步执行纪律

### Step 1: 契约审批 (Contract Approval)
- 生成 `execution-contract.md` 后，**必须**人工审批
- 人是唯一的审批节点：机器可规划，机器可执行，但"确认值得做"的判断必须人做
- 审批通过前，不写一行生产代码

### Step 2: TDD 铁律 (Test-Driven Discipline)
```
规则（不可绕过）:
  - 没有失败测试 → 不准写生产代码
  - 先写测试 → 看到红灯 → 写最少代码 → 看到绿灯 → 重构
  - 如果 AI 跳过了测试步骤 → 要求它删除已写代码，从测试重新开始

Red Flags（AI 可能用的借口——全部无效）:
  ✗ "这个改动太小了不需要测试"
  ✗ "用户赶时间先跳过测试"
  ✗ "我来先写个大概能跑的版本再补测试"
  ✗ "这段代码太简单不会出错"
```

**TDD 三步循环**:
```
  RED   → 写一个失败的测试（验证测试确实能失败）
  GREEN → 写最少代码让测试通过
  REFACTOR → 优化代码结构，保持测试绿
```

项目测试命令：
```bash
# Python
cd insight/trigger-server && python -m pytest tests/test_<module>.py -v

# TypeScript
cd web && npx jest <test-file> --watch

# Java
cd jetlinks-community && ./mvnw test -Dtest=<TestClass>
```

### Step 3: Scope Fence 检查 (Boundary Enforcement)

每完成一个 task，自动对照 Scope Fence：

```markdown
## Scope Check（每个 task 完成后必须回答）:
- [ ] 是否修改了 Out of Scope 文件？ → 如果是，立即回滚
- [ ] 是否"顺手"做了 Non-Goals 中的事情？ → 如果是，回退多余改动
- [ ] 是否新增了未在 design.md 中声明的文件？ → 如果是，评估必要性
```

### Step 4: Review Gate 推进 (Gate Progression)

```
Gate 1 ──通过──→ Gate 2 ──通过──→ Gate 3 ──通过──→ Gate 4
  │               │               │               │
  └─失败→修复     └─失败→修复     └─失败→修复     └─失败→修复
```

每个 Gate 的检查内容：
- **Quality**: 代码是否符合项目规范（对照 `.instructions.md`）
- **Spec Compliance**: 实现是否满足 specs.md 中的 SHALL/MUST
- **Test Coverage**: 测试是否覆盖了 Test Obligations
- **No Drift**: 是否有 scope 之外的改动

### Step 5: Rewind 处理 (Exception Handling)

当 Rewind Trigger 触发时：

```markdown
## Rewind Protocol
1. 立即暂停当前 task
2. 记录触发原因和当前进展
3. 评估：
   - 是否需要调整 scope？（更新 execution-contract.md）
   - 是否需要补充 spec？（回到 spec-generator）
   - 是否需要拆分 task？（回到 task-recipe）
4. 人工决策后再继续
```

## 子代理驱动开发 (SDD - Subagent-Driven Development)

对于复杂的多任务变更，每个 task 可以分发给独立的子代理：

```
优势:
  - 上下文隔离：子代理不会被其他 task 的上下文污染
  - 文件交接：子代理完成后交付工件，主代理审查
  - 双裁决审查：合规性裁决 + 代码质量裁决

裁决流程:
  1. 子代理执行 task → 产出代码 + 测试报告
  2. 合规性裁决：逐条对照 execution-contract.md 检查
  3. 代码质量裁决：运行 code-review skill 检查项
  4. 两项都通过 → 合并；任一失败 → 退回修正
```

## Token 预算意识

执行治理是有成本的。经验法则：
- < 100 行的小改动 → 不需要 Governor，直接用 `code-review` + `verify-feedback`
- 100~500 行的中等改动 → 使用 Governor 的 Step 1-4（契约 + TDD + Scope + Gate）
- 500+ 行的大改动 → 完整流程（含 SDD 子代理分发）

## 与项目现有技能的衔接

| Governor 阶段 | 调用技能 |
|--------------|---------|
| 契约审批前 | `spec-generator` (确保 spec 完整) |
| TDD 实施 | `verify-feedback` (测试反馈窗口) |
| Gate 检查 | `code-review` (安全检查清单) |
| Gate 4 最终检查 | `pr-checklist` (PR 自检清单) |
| 重构遵守 | `safe-refactor` (五步安全重构法) |
| 异常定位 | `bug-hunting` (五步定位法) |
| 数据库变更 | `db-migration` (迁移安全检查) |
