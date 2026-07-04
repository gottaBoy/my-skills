---
name: spec-generator
description: '结构化规格生成器 — 模糊需求→proposal→specs→design→tasks。Structured specification generator. Use when: starting a new feature, receiving vague requirements, need to produce verifiable specs before coding. Generates artifacts with SHALL/MUST language and GWT scenarios. Inspired by OpenSpec (57k stars) and Karpathy methodology.'
---

# Spec Generator — 把模糊想法变成可验证的规格

核心思想（来自 OpenSpec + Karpathy）：AI 编码助手在需求只存在于聊天记录时行为不可预测。
在写代码之前，先把"要做什么"和"不做什么"写下来，用 SHALL/MUST 这种确定性语言描述需求。

## When to Use
- 接到新功能需求，觉得"很模糊"
- AI 总是跑偏，需要更精确的输入
- 多人协作需要统一的规格标准
- 棕地项目（brownfield），需要精确描述增量变更
- 开始任何超过 100 行代码的变更

## 五阶段规格生成法

### Phase 1: 探索 (Explore) → `proposal.md`
**目标**：理解"为什么要做"，而非"怎么做"

```markdown
# Proposal: [变更名称]

## 动机 (Motivation)
- 当前痛点：[一句话描述现有问题]
- 预期收益：[一句话描述做完后的效果]

## 影响范围 (Impact)
- 涉及服务：[trigger-server / web / jetlinks / upload-hub]
- 涉及模块：[具体到目录或包名]
- 是否涉及数据库变更：是 / 否
- 是否涉及 API 变更：是 / 否

## 约束 (Constraints)
- [ ] 不改变现有 API 接口签名
- [ ] 不引入新的外部依赖
- [ ] 兼容现有数据
- [ ] [其他项目特定约束]
```

### Phase 2: 规格 (Specs) → `specs.md`
**目标**：用 SHALL / MUST / MUST NOT 描述可验证的需求

```markdown
# Specs: [变更名称]

## 功能需求
### REQ-001: [需求标题]
**优先级**: P0 (必须) / P1 (应该) / P2 (可选)

**描述**: 系统 SHALL [具体行为描述]

**场景**:
- **Given** [前置条件]
- **When** [触发动作]
- **Then** [预期结果]

### REQ-002: [需求标题]
...

## 非功能需求
### NFR-001: 性能
- 接口响应时间 MUST < 500ms (P95)
- 支持并发 MUST >= 100 QPS

### NFR-002: 兼容性
- MUST NOT 破坏现有 API 契约
- MUST 兼容已有的数据库 schema
```

**GWT 场景速查**：

| Given | When | Then |
|-------|------|------|
| 用户已登录 | 点击"导出"按钮 | 下载包含筛选条件的 CSV 文件 |
| 数据库为空 | 调用查询接口 | 返回空列表，状态码 200 |
| 传入非法参数 | 调用创建接口 | 返回 400 + 具体错误信息 |
| 网络超时 | 调用外部 API | 返回 503 + 重试建议 |

### Phase 3: 设计 (Design) → `design.md`
**目标**：技术方案，匹配 `safe-refactor` 和项目架构

```markdown
# Design: [变更名称]

## 架构决策
- **方案**: [选了哪个方案，为什么]
- **备选方案**: [考虑过但否决的方案，以及否决原因]

## 数据流
```
[输入] → [处理] → [输出]
   ↓        ↓        ↓
[DB读]  [逻辑层]  [DB写/缓存/消息]
```

## 模块变更
### 新增文件
- `insight/trigger-server/services/new_service.py` — [职责]
- `web/app/new-page/page.tsx` — [职责]

### 修改文件
- `insight/trigger-server/models.py` — 增加 NewModel
- `jetlinks-community/.../DeviceController.java` — 新增接口

### 不修改的文件（明确排除）
- `insight/trigger-server/app.py` — 路由不动
- `web/lib/api/` — API 层不改

## 数据模型变更（如有）
```sql
-- UP
ALTER TABLE trips ADD COLUMN new_field VARCHAR(100);

-- DOWN
ALTER TABLE trips DROP COLUMN new_field;
```

## 风险 & 回滚
- 最大风险：[描述]
- 回滚方式：git revert / feature flag / 数据库回滚
- 监控指标：[上线后看什么]
```

### Phase 4: 任务拆分 (Tasks) → `tasks.md`
**目标**：拆成半天内可完成的 INVEST 子任务，对齐 `task-recipe` 六步法

```markdown
# Tasks: [变更名称]

## 依赖图
```
Task 1 (数据层) ──→ Task 2 (逻辑层) ──→ Task 3 (API层)
                                      └──→ Task 4 (前端, 可并行)
```

## 任务列表
- [ ] **Task 1**: [简短描述]
  - 文件: `path/to/file.py`
  - 验证: `python -m pytest tests/test_xxx.py -v`
  - 估时: 2h

- [ ] **Task 2**: [简短描述]
  - 依赖: Task 1
  - 文件: `path/to/service.py`
  - 验证: `python -m pytest tests/test_yyy.py -v`
  - 估时: 3h

- [ ] **Task 3**: [简短描述]
  - 依赖: Task 2
  - 文件: `path/to/controller.java`
  - 验证: `./mvnw test -Dtest=XxxControllerTest`
  - 估时: 2h
```

### Phase 5: 增量适用 (Delta Spec) — 棕地项目专用
当修改已有功能时，不重写整份 spec，只描述差异：

```markdown
# Delta Spec: [变更名称]

## ADDED
- REQ-010: 系统 SHALL 支持分页查询用户列表

## MODIFIED
- REQ-003: 查询接口 MUST 增加可选的 `page` 和 `size` 参数
  - 旧行为: 返回全部结果
  - 新行为: 默认返回前 20 条

## REMOVED
- (无)
```

## 规格完成标准 (Spec Done)

在进入执行阶段前，必须确认：
- [ ] 所有 REQ 都有对应的 GWT 场景
- [ ] 所有 MUST / SHALL 需求都可测试
- [ ] design.md 覆盖了所有 specs.md 中提到的技术决策
- [ ] tasks.md 中每个任务都有明确的验证方式
- [ ] 已明确列出 Non-Goals（不做什么）
- [ ] 人工确认"这个规划值得执行"（对照 `execution-governor` 的执行契约）

## 与项目现有技能的衔接

| 输出工件 | 下游消费者 |
|---------|-----------|
| `proposal.md` | `task-recipe` (Step 1: 定义边界) |
| `specs.md` | `execution-governor` (Intent Lock, Scope Fence) |
| `design.md` | `safe-refactor` (重构范围参考) |
| `tasks.md` | `verify-feedback` (测试覆盖映射) |
| Delta Spec | `db-migration` (增量 schema 变更) |
