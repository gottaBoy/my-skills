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
│   ├── SKILLS_GUIDE.md            ← 完整使用指南
│   ├── SYNC_GUIDE.md              ← 跨电脑同步指南
│   └── WORKFLOWS.md               ← 标准工作流串联文档
└── .gitignore
```

## 快速开始

### 部署到 VS Code 工作空间（推荐）

```bash
# 在 workspace 根目录下
cd /path/to/your/workspace
git clone https://github.com/<your-username>/autodrive-skills.git .github
```

VS Code Copilot 会自动发现 `.github/skills/` 和 `.github/instructions/`。

### 安装到用户目录（跨所有项目生效）

```bash
# Windows PowerShell
Copy-Item -Recurse skills/* $env:APPDATA/Code/User/prompts/skills/
Copy-Item -Recurse instructions/* $env:APPDATA/Code/User/prompts/instructions/
```

### 更新

```bash
cd .github
git pull
```

## 使用方式

在 VS Code Copilot Chat 中：
- 输入 `/` 查看可用 Skills 列表
- 或直接用自然语言描述任务（如 "帮我 review 这段代码"），Agent 自动匹配对应 Skill

详细说明见 [SKILLS_GUIDE.md](skills/SKILLS_GUIDE.md)。

## Skill 清单 (9 个，按 Spec→Harness→Loop 三层)

| 层 | Skill | 触发方式 | 一句话描述 |
|---|-------|---------|-----------|
| **Spec** | `spec-generator` | `/spec-generator` | 模糊需求 → 结构化规格（proposal→specs→design→tasks） |
| **Spec** | `task-recipe` | `/task-recipe` | 把大任务拆成可执行的 INVEST 子任务 |
| **Harness** | `execution-governor` | `/execution-governor` | TDD 铁律 + Scope Fence + Review Gates |
| **Harness** | `code-review` | `/code-review` | 五维度代码审查（安全/正确/可维护/性能/测试） |
| **Harness** | `verify-feedback` | `/verify-feedback` | 给 AI 代码建立五层验证金字塔 |
| **Harness** | `bug-hunting` | `/bug-hunting` | 系统化 Bug 定位五步法 |
| **Loop** | `pr-checklist` | `/pr-checklist` | PR 提交前质量把关 + 自检清单 |
| **Loop** | `safe-refactor` | `/safe-refactor` | 安全重构（原子 commit + 行为不变） |
| **Loop** | `db-migration` | `/db-migration` | 数据库安全迁移（UP/DOWN 回滚） |
| `safe-refactor` | `/safe-refactor` | 安全重构五步法 |

## 核心理念

> 不是收藏别人的 Skills，而是把自己的经验写成 Skills。
> 每当你第三次手动做同一件事时，就是该写一个 Skill 的时候了。

— Inspired by Andrej Karpathy's AI coding philosophy
