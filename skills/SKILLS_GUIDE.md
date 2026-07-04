---
name: skills-guide
description: 'Complete guide for the autodrive project Agent Skills system — philosophy, usage, customization, cross-machine sharing, and best practices.'
---

# autodrive Agent Skills — 完整使用指南

> 基于 Andrej Karpathy 的 AI 编程哲学，结合 VS Code Copilot Agent Customization 框架的落地实践。

---

## 目录

1. [哲学基础](#1-哲学基础)
2. [体系架构](#2-体系架构)
3. [Skill 清单与使用场景](#3-skill-清单与使用场景)
4. [日常使用方式](#4-日常使用方式)
5. [如何创建新 Skill](#5-如何创建新-skill)
6. [跨电脑共享](#6-跨电脑共享)
7. [最佳工程实践](#7-最佳工程实践)
8. [FAQ](#8-faq)

---

## 1. 哲学基础

### Karpathy 式 AI 编程的三个核心原则

```
┌──────────────────────────────────────────────────┐
│  原则 1: 先训练自己，再训练 AI                      │
│  把任务拆清楚、边界定明确，AI 才会输出稳定           │
├──────────────────────────────────────────────────┤
│  原则 2: 给 AI 装上"眼睛"（反馈闭环）               │
│  测试、类型、lint、日志——每扇窗口都减少 AI 的猜测     │
├──────────────────────────────────────────────────┤
│  原则 3: 好流程沉淀为 Skill，不再靠记忆              │
│  反复做、反复错、反复解释的事情，写成 Skill           │
└──────────────────────────────────────────────────┘
```

### 核心理念对照

| Karpathy 理念 | 本体系实现 |
|---|---|
| "别急着生成，先把任务变干净" | `task-recipe` — 六步拆解法 |
| "AI 越强，工程纪律越重要" | `copilot-instructions.md` — 全局约束 |
| "把反馈变成机器可读的信号" | `verify-feedback` — 五层验证金字塔 |
| "不要让同一问题靠记忆解决" | SKILL.md 文件版本控制 |
| "生成成本下降，混乱成本上升" | `code-review` + `pr-checklist` 质量门 |
| "最小可理解单元" | `safe-refactor` — 每次只改一件事 |

---

## 2. 体系架构

### 部署架构（多项目工作空间）

本 Skills 是一个**独立的 Git 仓库**，部署在工作空间根目录下：

```
c:\d\autodrive\                    ← 工作空间根目录（非 git 仓库）
├── .github/                       ← [autodrive-skills 独立仓库] ← git clone 到此
│   ├── README.md
│   ├── copilot-instructions.md    ← 全局规范
│   ├── instructions/              ← 语言级规范
│   └── skills/                    ← 可复用工作流
├── insight/                       ← 独立 git 仓库
├── jetlinks-community/            ← 独立 git 仓库
├── web/                           ← 独立 git 仓库
└── ...
```

> **关键设计**：VS Code Copilot 扫描 `.github/skills/` 基于文件路径，不关心 `.github` 是不是 git 仓库。
> 所以 `.github` 作为独立仓库 clone 到工作空间根目录，既有版本控制又天然被 VS Code 发现。

### 文件结构

```
.github/
├── copilot-instructions.md          ← [始终生效] 全局项目规范
├── instructions/                    ← [按文件匹配] 语言/框架级规范
│   ├── python.instructions.md       ← applyTo: **/*.py
│   ├── typescript.instructions.md   ← applyTo: web/**/*.{ts,tsx}
│   └── java.instructions.md         ← applyTo: jetlinks-community/**/*.java
└── skills/                          ← [按需调用] 可复用工作流
    ├── task-recipe/SKILL.md         ← 任务拆解配方
    ├── code-review/SKILL.md         ← 代码审查清单
    ├── bug-hunting/SKILL.md         ← Bug 定位五步法
    ├── db-migration/SKILL.md        ← 数据库迁移安全流程
    ├── pr-checklist/SKILL.md        ← PR 提交前自检
    ├── verify-feedback/SKILL.md     ← 验证与反馈闭环
    └── safe-refactor/SKILL.md       ← 安全重构工作流
```

### 三层加载机制

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Agent Instructions (始终生效)              │
│  copilot-instructions.md → 每次对话自动加载           │
├─────────────────────────────────────────────────────┤
│  Layer 2: File Instructions (匹配文件时生效)          │
│  *.instructions.md → applyTo glob 匹配时自动附加      │
├─────────────────────────────────────────────────────┤
│  Layer 3: Skills (按需调用)                          │
│  SKILL.md → 输入 / 斜杠命令或 Agent 自动识别触发       │
└─────────────────────────────────────────────────────┘
```

### Skill vs Instruction vs Prompt 选择指南

| 场景 | 用什么 | 原因 |
|------|--------|------|
| 代码风格规范 | File Instruction | 匹配文件类型自动加载 |
| 项目架构约定 | Agent Instruction | 始终需要 |
| 多步骤工作流 | Skill | 包含过程、检查点、命令 |
| 一次性任务模板 | Prompt | 参数化输入，执行即完成 |
| 上下文隔离的子任务 | Custom Agent | 不污染主对话上下文 |

---

## 3. Skill 清单与使用场景

### 完整 Skill 矩阵

| Skill | 触发方式 | 适用场景 | 关键输出 |
|-------|---------|---------|---------|
| `/task-recipe` | 新功能开发前 | 模糊需求 → 可执行步骤 | 子任务列表 + 完成标准 |
| `/spec-generator` | 新功能开发前 | 需求 → proposal → specs → design → tasks | 结构化规格文档 |
| `/execution-governor` | 执行代码时 | TDD + Scope Fence + Gate 管控 | 执行契约 + 审查记录 |
| `/code-review` | 提交前 / PR review | 代码质量检查 | 五维度检查清单 |
| `/bug-hunting` | 遇到 Bug 时 | 系统化定位根因 | 五步定位法 + 验证方案 |
| `/db-migration` | 改数据库时 | 安全变更数据库 | 变更 + 回滚脚本 |
| `/pr-checklist` | 提 PR 前 | 最终质量把关 | 质量门 + PR 描述模板 |
| `/verify-feedback` | AI 生成代码后 | 建立验证闭环 | 五层验证金字塔 |
| `/safe-refactor` | 重构时 | 行为不变的结构优化 | 五步安全重构法 |

### 典型工作流组合

```
新功能开发全流程（Spec→Harness→Loop）：
  /spec-generator → /task-recipe → /execution-governor → /code-review → /verify-feedback → /pr-checklist

Bug 修复全流程：
  /bug-hunting → /spec-generator (delta) → /execution-governor → /verify-feedback → /pr-checklist

数据库变更全流程：
  /db-migration → /verify-feedback → /pr-checklist

重构全流程：
  /safe-refactor → /verify-feedback → /code-review → /pr-checklist
```

---

## 4. 日常使用方式

### 方式一：斜杠命令（显式调用）

在 Copilot Chat 中输入 `/`，从列表中选择 Skill：

```
/task-recipe 帮我拆解"用户上传视频后自动生成缩略图"这个需求
/code-review 检查我刚写的这段代码
/bug-hunting 分析这个错误：TypeError at app.py:42
/safe-refactor 重构 insight/trigger-server/services/analysis.py
```

### 方式二：自然语言触发（自动识别）

每个 Skill 的 `description` 字段包含触发关键词，Agent 会自动匹配：

```
你说："帮我 review 一下这段代码"
→ Agent 识别到 "review"、"代码" → 自动加载 code-review skill

你说："这个 bug 怎么定位"
→ Agent 识别到 "bug"、"定位" → 自动加载 bug-hunting skill

你说："我要加一个新表"
→ Agent 识别到 "表"、"数据库" → 自动加载 db-migration skill
```

### 方式三：手动附加（Add Context）

在 Chat 中点击 `Add Context` → `Instructions` → 选择对应的 Skill 文件。

---

## 5. 如何创建新 Skill

### 模板

```markdown
---
name: my-skill-name           # 必填：1-64 字符，小写字母+连字符，必须与文件夹名一致
description: '一句话描述这个 Skill 做什么以及什么时候用。包含触发关键词。'
argument-hint: '[可选] 斜杠命令后的参数提示'
---

# Skill 标题

## When to Use
- 场景 1
- 场景 2

## 核心流程

### Step 1: ...
### Step 2: ...
### Step 3: ...

## 检查清单
- [ ] ...
- [ ] ...

## 相关命令
\```bash
command here
\```
```

### 创建步骤

```bash
# 1. 创建文件夹
mkdir -p .github/skills/my-skill-name

# 2. 创建 SKILL.md
# 复制上面的模板，填入内容

# 3. （可选）添加资源文件
mkdir -p .github/skills/my-skill-name/scripts     # 可执行脚本
mkdir -p .github/skills/my-skill-name/references  # 参考文档
mkdir -p .github/skills/my-skill-name/assets      # 模板/样板代码
```

### description 关键词设计原则

```yaml
# ❌ 太模糊，Agent 无法自动匹配
description: '一个有用的技能'

# ✅ 关键词丰富，自动触发和手动搜索都能找到
description: 'Task decomposition recipe. Use when: starting a new feature, breaking down complex tasks, planning implementation steps.'
```

---

## 6. 跨电脑共享

> 本 Skills 是独立 Git 仓库（`autodrive-skills`），clone 到工作空间 `.github/` 目录即可。

### 核心方案：独立 Git 仓库 + Clone 到工作空间

```
┌──────────────────────────────────────────────────┐
│  GitHub:  autodrive-skills 仓库                   │
│  ├── skills/          ← git push/pull 同步       │
│  ├── instructions/                               │
│  └── copilot-instructions.md                     │
└──────────────┬───────────────────────────────────┘
               │ git clone
               ▼
┌──────────────────────────────────────────────────┐
│  本地工作空间                                      │
│  c:\d\autodrive\.github\   ← clone 到此           │
│  VS Code Copilot 自动发现 ← 无需额外配置            │
└──────────────────────────────────────────────────┘
```

### 新电脑初始化（一行命令）

```bash
# 1. 进入工作空间根目录
cd c:\d\autodrive

# 2. Clone Skills 仓库到 .github 目录
git clone https://github.com/<your-username>/autodrive-skills.git .github

# 3. 打开 VS Code — Skills 自动生效
code .
```

### 日常更新

```bash
cd c:\d\autodrive\.github
git pull    # 拉取最新 Skills
# 或修改后
git add -A && git commit -m "skill: update xxx" && git push
```

### 其他可选方案

| 方案 | 命令 | 适用场景 |
|------|------|---------|
| **独立仓库**（👈 默认） | `git clone <url> .github` | 团队共享 + 版本控制 |
| **用户目录 + Settings Sync** | 复制到 `%APPDATA%/Code/User/prompts/` | 个人跨项目 + 自动同步 |
| **直接下载 ZIP** | 解压到 `.github/` | 快速试用，无需 git |

---

## 7. 最佳工程实践

### 7.1 Skill 设计原则

```
✅ 一个好 Skill 的五个特征：
1. 单一职责 — 只解决一类问题
2. 可执行 — 包含具体命令，不是鸡汤
3. 有反馈 — 每步都有验证方式
4. 能沉淀 — 把经验固化，不是一次性提示词
5. 有边界 — 明确"做什么"和"不做什么"
```

### 7.2 渐进式加载（Keep It Lean）

```
SKILL.md 控制在 500 行以内：
  ├── SKILL.md (< 5000 tokens)  ← Agent 加载到上下文
  ├── references/   ← Agent 需要时才读取
  └── scripts/      ← Agent 需要时才执行
```

### 7.3 生命周期管理

```
创建 → 使用 → 反馈 → 迭代 → 退役

1. 创建：当你第三次手动做同一件事时，写成 Skill
2. 使用：在新任务中主动调用，验证是否好用
3. 反馈：发现缺失步骤或过时内容，立刻更新
4. 迭代：每次使用后花 1 分钟改进
5. 退役：不再适用的 Skill，删除不要留着
```

### 7.4 description 是发现入口

```yaml
# 好的 description 包含：
# - 这个 Skill 做什么
# - 什么时候用（触发词）
# - 适用范围（语言、框架、场景）

description: 'Code review checklist. Use when: reviewing PRs, pre-commit self-review, checking code quality. Covers Python, TypeScript, Java.'
```

### 7.5 Do's and Don'ts

| Do | Don't |
|----|-------|
| ✅ 一次只做一件事 | ❌ 一个 Skill 包罗万象 |
| ✅ 包含可执行的命令 | ❌ 只有抽象描述 |
| ✅ 每次使用后迭代改进 | ❌ 写了就不管 |
| ✅ 用 `applyTo` 精确匹配文件 | ❌ `applyTo: "**"` 烧上下文 |
| ✅ 团队 review Skills 变更 | ❌ 随意添加未经验证的 Skill |
| ✅ 把通用 Skill 提取到用户级 | ❌ 把个人偏好强加给团队 |
| ✅ description 包含触发关键词 | ❌ description 写 "A helpful skill" |

### 7.6 版本控制

```bash
# Skills 变更应该走正常的 PR 流程
git checkout -b skill/update-code-review
# 修改 .github/skills/code-review/SKILL.md
git add .github/skills/
git commit -m "skill(code-review): add security check for SQL injection"
git push
# 创建 PR，让团队 review
```

### 7.7 衡量效果

定期回顾：
- 这周哪个 Skill 用得最多？→ 值得继续投入
- 哪个 Skill 从来没触发过？→ description 关键词不够，或根本不需要
- AI 有没有在不需要的时候加载了 Skill？→ 调整 description 精确度
- 团队有没有反馈 Skill 过时或错误？→ 更新

---

## 8. FAQ

### Q: Skills 和 Prompt 有什么区别？
- **Skill**：多步骤工作流，可以附带脚本和参考文档，适合反复使用
- **Prompt**：一次性任务模板，有参数化输入，适合"生成某种特定格式的输出"

### Q: 为什么 AI 没有自动加载我的 Skill？
检查 `description` 字段是否包含足够的关键词。AI 只能根据 description 来判断是否加载。如果 description 太模糊（如 "A helpful skill"），AI 不知道什么时候用它。

### Q: 可以在 `.github/` 之外放 Skills 吗？
可以。除了 `.github/skills/`，还支持 `.agents/skills/` 和 `.claude/skills/`。用户级 Skills 放在 `~/.copilot/skills/`。

### Q: Skills 文件太大怎么办？
将详细内容拆分到 `references/` 子目录。Agent 只在需要时才读取 reference 文件，不会一次性加载所有内容。

### Q: 个人偏好（如 emoji 风格）应该放在哪里？
放在用户级 Instructions（`{{VSCODE_USER_PROMPTS_FOLDER}}/instructions/`），不要放在项目的 `.github/` 中。

---

> **最后记住 Karpathy 的话：不是收藏别人的 Skills，而是把自己的经验写成 Skills。**
>
> 每当你第三次手动做同一件事时，就是该写一个 Skill 的时候了。
