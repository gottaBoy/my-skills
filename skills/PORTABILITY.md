# Skills 跨项目可移植指南

> 本文档说明如何将 autodrive-skills 适配到不同的技术栈和工作空间结构。

---

## 适配清单

### 1. 必须修改的文件

| 文件 | 修改内容 | 原因 |
|------|---------|------|
| `copilot-instructions.md` | 更新项目架构、Build 命令 | 每个项目的技术栈不同 |
| `instructions/python.instructions.md` | 调整 `applyTo` glob、更新框架约定 | 不同项目用不同框架 |
| `instructions/typescript.instructions.md` | 同上 | React vs Vue vs Angular 写法不同 |
| `instructions/java.instructions.md` | 调整模块结构、依赖规则 | 每个 Java 项目结构不同 |

### 2. 可保留不动的文件

| 文件 | 原因 |
|------|------|
| `skills/*/SKILL.md` (所有 9 个) | 语言无关，纯方法论 |
| `skills/SKILLS_GUIDE.md` | 体系说明，跨项目通用 |
| `skills/SYNC_GUIDE.md` | 同步方案，与项目无关 |
| `skills/WORKFLOWS.md` | 工作流参考，通用 |
| `skills/SKILL_VERSIONING.md` | 版本化策略，通用 |

---

## 适配步骤

### Step 1: Fork 仓库

```bash
# Fork gottaBoy/my-skills → <your-org>/my-skills
# 或直接 clone 后修改 remote
git clone git@github.com:gottaBoy/my-skills.git my-project-skills
cd my-project-skills
git remote set-url origin git@github.com:<your-org>/my-project-skills.git
```

### Step 2: 修改项目特定文件

```bash
# 1. 更新全局规范
vim copilot-instructions.md
# 改: 项目名、架构、Build 命令、技术栈

# 2. 更新或删除不适用的语言 instructions
vim instructions/python.instructions.md  # 改框架约定
vim instructions/typescript.instructions.md  # 改组件模式
vim instructions/java.instructions.md  # 改模块结构

# 如果项目不用某种语言，直接删除对应文件
rm instructions/java.instructions.md   # 纯 Python 项目不需要
```

### Step 3: 更新仓库说明

```bash
vim README.md
# 改仓库名、适配的项目名、技术栈
```

### Step 4: 推送到新仓库

```bash
git add -A
git commit -m "adapt: customize for <project-name>"
git push
```

---

## 跨项目差异对照

### autodrive (原版) → 你的项目

| 维度 | autodrive | 你的项目 |
|------|-----------|---------|
| Python 框架 | Flask | Django / FastAPI / Flask |
| 前端框架 | Next.js (App Router) | Next.js / Vue / Svelte |
| Java 框架 | Spring Boot + JPA | Spring Boot / Quarkus |
| 数据库 | MySQL | MySQL / PostgreSQL / MongoDB |
| 构建工具 | Maven | Maven / Gradle / npm / poetry |
| 工作空间结构 | 多仓库 flat layout | 单仓库 / monorepo / 多仓库 |

### 需要调整的位置

```markdown
# copilot-instructions.md 需要改:
- Architecture 段: 你的服务/模块名称和职责
- Build & Test 段: 你的构建命令
- Conventions 段: 你的项目约定

# instructions/*.instructions.md 需要改:
- applyTo glob: 匹配你的文件路径
- 框架特定写法: 用你的框架模式替换

# 不需要改:
- skills/*/SKILL.md: 全部保留
```

---

## 多语言项目适配矩阵

### 纯 Python 项目

```
保留:
  ✅ skills/*/SKILL.md (全部)
  ✅ instructions/python.instructions.md (修改框架部分)
删除:
  ❌ instructions/typescript.instructions.md
  ❌ instructions/java.instructions.md
```

### 纯 TypeScript/Node.js 项目

```
保留:
  ✅ skills/*/SKILL.md (全部)
  ✅ instructions/typescript.instructions.md (修改框架部分)
删除:
  ❌ instructions/python.instructions.md
  ❌ instructions/java.instructions.md
```

### 纯 Java 项目

```
保留:
  ✅ skills/*/SKILL.md (全部)
  ✅ instructions/java.instructions.md (修改框架部分)
删除:
  ❌ instructions/python.instructions.md
  ❌ instructions/typescript.instructions.md
```

### 新增语言（Go / Rust / Kotlin 等）

```bash
# 新增 instructions 文件
mkdir -p instructions
cat > instructions/go.instructions.md << 'EOF'
---
description: "Use when writing Go code. Covers conventions, error handling, and testing."
applyTo: "**/*.go"
---

# Go Coding Standards

## Patterns
- Use `context.Context` as first parameter
- Return errors, don't panic
- Use `testing` package + table-driven tests
EOF
```

---

## 跨项目 Skill 继承

如果多个项目共享同一套 Skills，使用 **Git 分支策略**：

```
main (基础 Skills)
├── project-autodrive (autodrive 特有配置)
├── project-xxx (另一个项目特有配置)
└── project-yyy (再一个项目特有配置)
```

```bash
# 创建项目分支
git checkout -b project-autodrive
# 修改 instructions + copilot-instructions.md 适配 autodrive
git push --set-upstream origin project-autodrive

# 另一个项目
git checkout main
git checkout -b project-xxx
# 修改...
git push
```

### 同步基础 Skills 到项目分支

```bash
# 在 main 上更新了 Skills 后，合并到各项目分支
git checkout project-autodrive
git merge main    # 只合并 skills/，如果冲突只影响 instructions/ 则很安全
git push
```

---

> **核心原则**: Skills（方法论）跨项目通用，Instructions（语言约定）随项目定制。
> 分离这两层是保持 Skills 可移植的关键。
