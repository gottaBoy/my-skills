# autodrive-skills

> 基于 Andrej Karpathy AI 编程哲学的 Agent Skills 集合，适用于 VS Code Copilot。

## 这是什么

这是一套可复用的 AI 编程工作流（Skills），将代码审查、Bug 定位、任务拆解、安全重构等高频操作的工程经验固化为结构化文件，让 AI 编程助手稳定、可预测地工作。

## 适用场景

本仓库原本服务于多项目工作空间 `autodrive`，包含 Python (Flask)、TypeScript (Next.js)、Java (Spring Boot) 等多种技术栈。Skills 大多语言无关，可跨项目复用。

## 文件结构

```
autodrive-skills/
├── README.md                      ← 你在这里
├── copilot-instructions.md        ← 全局项目规范（始终生效）
├── instructions/                  ← 按文件类型匹配的规范
│   ├── python.instructions.md     ← applyTo: **/*.py
│   ├── typescript.instructions.md ← applyTo: web/**/*.{ts,tsx}
│   └── java.instructions.md       ← applyTo: jetlinks-community/**/*.java
├── skills/                        ← 按需调用的工作流（Spec→Harness→Loop 三层）
│   ├── spec-generator/            ← ✨ 结构化规格生成器
│   ├── execution-governor/        ← ✨ 执行纪律框架
│   ├── task-recipe/               ← 任务拆解配方
│   ├── code-review/               ← 代码审查清单
│   ├── bug-hunting/               ← Bug 定位五步法
│   ├── db-migration/              ← 数据库迁移安全流程
│   ├── pr-checklist/              ← PR 提交前自检
│   ├── verify-feedback/           ← 验证与反馈闭环
│   ├── safe-refactor/             ← 安全重构工作流
│   ├── devops-engineer/           ← CI/CD Pipeline + Docker
│   ├── ops-playbook/              ← 运维排障 + 监控 + 灾备
│   ├── SKILLS_GUIDE.md            ← 完整使用指南
│   ├── SYNC_GUIDE.md              ← 跨电脑同步指南
│   ├── WORKFLOWS.md               ← 标准工作流串联文档
│   ├── PORTABILITY.md             ← 跨项目适配指南
│   └── SKILL_VERSIONING.md        ← 版本化策略
├── agents/                        ← 自定义 Agent（角色分工）
│   ├── architect.agent.md         ← 架构审查（只读）
│   ├── ui-designer.agent.md       ← UI 审查（只读）
│   └── test-strategist.agent.md   ← 测试策略（可运行测试）
└── instructions/                  ← 按文件类型匹配的规范
    ├── python.instructions.md
    ├── typescript.instructions.md
    └── java.instructions.md
```

## 快速开始

### 部署到 VS Code 工作空间

```bash
# 在 workspace 根目录下
cd /path/to/your/workspace
git clone git@github.com:gottaBoy/my-skills.git .github

# VS Code Copilot 自动发现，无需额外配置
```

### 更新

```bash
cd .github && git pull
```

### 使用

在 Copilot Chat 中:
- 输入 `/` 查看可用 Skills 列表 → 选择 `/spec-generator` 等
- 输入 `@` 调用 Agent → 选择 `@architect` 等
- 或自然语言触发（如 "帮我 review 这段代码"）

## 能力矩阵

### Skills（11 个，按 Spec→Harness→Loop 三层）

| 层 | Skill | 一句话 |
|---|-------|--------|
| Spec | `spec-generator` | 模糊需求 → 结构化规格（SHALL/MUST + GWT） |
| Spec | `task-recipe` | 大任务拆成 INVEST 子任务 |
| Harness | `execution-governor` | TDD 铁律 + Scope Fence + Rewind Triggers |
| Harness | `code-review` | 五维度代码审查 |
| Harness | `verify-feedback` | 五层验证金字塔 |
| Harness | `bug-hunting` | 系统化 Bug 定位五步法 |
| Harness | `devops-engineer` | CI/CD Pipeline + Docker + 部署策略 |
| Harness | `ops-playbook` | 监控告警 + 日志分析 + 灾备 |
| Loop | `pr-checklist` | PR 提交前质量把关 |
| Loop | `safe-refactor` | 安全重构（原子 commit） |
| Loop | `db-migration` | 数据库 UP/DOWN 安全迁移 |

### Agents（3 个，角色分工）

| Agent | 权限 | 职责 |
|-------|------|------|
| `@architect` | 只读 | 架构审查：模块边界、依赖方向、非功能需求 |
| `@ui-designer` | 只读 | UI 审查：a11y、响应式、组件一致性、状态覆盖 |
| `@test-strategist` | 可运行测试 | 测试策略：覆盖率分析、GWT 用例、测试矩阵 |

### DevOps 全链路覆盖

| 阶段 | 覆盖 | 工具 |
|------|------|------|
| 设计 | ✅ 80% | `spec-generator` + `@architect` |
| UI | ✅ 60% | `@ui-designer` + `typescript.instructions.md` |
| 开发 | ✅ 85% | `execution-governor` + `code-review` + `safe-refactor` |
| 测试 | ✅ 75% | `verify-feedback` + `@test-strategist` + `bug-hunting` |
| CI/CD | ✅ 70% | `devops-engineer` (Pipeline 模板 + Dockerfile) |
| 部署 | ✅ 50% | `devops-engineer` + `db-migration` |
| 运维 | ✅ 60% | `ops-playbook` (监控 + 告警 + 复盘模板) |
| AIops | ⚠️ 30% | 告警规则模板 + 5 Whys 复盘（自愈/预测需外部工具链） |

## 标准工作流

```
新功能:   /spec-generator → @architect → /execution-governor → @test-strategist → @ui-designer → /pr-checklist
Bug修复:  /bug-hunting → /execution-governor → /verify-feedback → /pr-checklist
数据库:   /db-migration → /verify-feedback → /pr-checklist
重构:     /safe-refactor → /code-review → /pr-checklist
CI/CD:    /devops-engineer → /verify-feedback → /pr-checklist
运维:     /ops-playbook → @architect (复盘)
```

## 核心理念

> 不是收藏别人的 Skills，而是把自己的经验写成 Skills。
> 每当你第三次手动做同一件事时，就是该写一个 Skill 的时候了。

— Inspired by Andrej Karpathy's AI coding philosophy + OpenSpec (57k⭐) + Superpowers (240k⭐)
