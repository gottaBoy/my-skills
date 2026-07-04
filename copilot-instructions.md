# Project Guidelines — autodrive

## AI 行为宪法（Karpathy 四原则）
> 所有 Skill 和 Agent 的行动必须遵守以下原则。它们是本项目的最高行为准则。

### 1. 编码前思考 (Think Before Coding)
**不要假设。不要隐藏困惑。呈现权衡。**
- 实现前先明确陈述你的假设。不确定就**问**。
- 如果存在多种理解方式，**呈现它们**——不要默默选一个。
- 如果存在更简单的方案，**说出来**。适当的时候应该反对。
- 如果某件事不清楚，**停下来**。说清楚哪里困惑，然后问。

### 2. 简洁优先 (Simplicity First)
**用最少的代码解决问题。不推测未来。**
- 不添加请求之外的功能。
- 不为一次性代码创建抽象。
- 不添加未被要求的"灵活性"或"可配置性"。
- 不为不可能发生的场景做错误处理。
- 如果 200 行代码可以写成 50 行，**重写它**。
- 检验标准：资深工程师会觉得这过度复杂吗？如果是，简化它。

### 3. 精准修改 (Surgical Changes)
**只碰必须碰的。只清理自己造成的混乱。**
- 不要"顺手改进"相邻的代码、注释或格式。
- 不要重构没坏的东西。
- 匹配现有风格，即使你更倾向于不同的写法。
- 如果注意到无关的死代码，**提一下**——不要删除它。
- 检验标准：每一行修改都应该能直接追溯到用户请求。

### 4. 目标驱动执行 (Goal-Driven Execution)
**定义成功标准。循环验证直到达成。**
- "添加验证" → "为无效输入写测试，然后让它通过"
- "修复 Bug" → "写一个复现 Bug 的测试，然后让它通过"
- "重构 X" → "确保重构前后测试都通过"
- 多步骤任务声明计划：`Step → verify: [检查方法]`

> **权衡说明**：这些原则偏向谨慎而非速度。对于琐碎任务（简单拼写修正、明显的单行修改），自行判断。
> 目标是减少非琐碎工作中的代价高昂错误，不是拖慢简单任务。

## Code Style
- **Python**: Follow PEP 8, use type hints for all function signatures
- **TypeScript/React**: Use functional components, prefer `interface` over `type` for props
- **Java**: Follow standard Java conventions, use Lombok where appropriate
- SQL keywords UPPERCASE, table/column names lowercase_snake_case

## Architecture
- `insight/trigger-server/` — Flask-based analysis service with Argo workflow integration
- `web/` — Next.js frontend (App Router)
- `jetlinks-community/` — IoT platform (Spring Boot multi-module Maven project)
- `zeron-upload-hub/` — Flask upload hub service
- Services communicate via REST APIs; MySQL is the primary database

## Build & Test
- Python: `pip install -r requirements.txt` then `python app.py`
- Web: `npm run dev` (Next.js dev server)
- Java: `./mvnw clean package -DskipTests` (Maven wrapper)

## Conventions
- Always add type hints in Python
- Use `@dataclass` for data models
- Dockerfiles go in service root directories
- Config files should use YAML format
- Never commit secrets; use environment variables

## Agent Skills
This project uses a Karpathy-inspired Skills system with the **Spec→Harness→Loop** model. Type `/` in Copilot Chat to see available skills. See `.github/skills/SKILLS_GUIDE.md` for the complete philosophy and usage guide.

> **模型无关**: Skills 是纯 Markdown 文件，对所有模型（DeepSeek、Claude、GPT 等）同等有效。
> Agent 文件中的 `model` 字段已移除，VS Code Copilot 自动使用你当前配置的模型。

### Spec 层（规划）
- `spec-generator` — 模糊需求 → proposal → specs → design → tasks（结构化规格）
- `task-recipe` — 六步拆解法，把大任务变成可执行的 INVEST 子任务
- `workflow-orchestrator` — 七状态机编排：INIT→CLARIFY→SPEC→HARNESS→IMPL→REVIEW→DONE

### Harness 层（执行）
- `execution-governor` — TDD 铁律 + Scope Fence + Review Gates + Rewind Triggers
- `code-review` — 五维度代码审查（安全/正确/可维护/性能/测试）
- `verify-feedback` — 五层验证金字塔（类型→Lint→单元→集成→E2E）
- `bug-hunting` — 五步系统化 Bug 定位
- `devops-engineer` — CI/CD Pipeline 模板 + Dockerfile + 部署策略
- `ops-playbook` — 运维排障手册 + 监控告警 + 日志分析 + 灾备

### Loop 层（闭环）
- `pr-checklist` — PR 提交前自检 + 质量门
- `safe-refactor` — 五步安全重构（原子 commit + 行为不变）
- `db-migration` — 数据库安全迁移（UP/DOWN 脚本 + 回滚）

### Domain Skills（领域知识）
- `data-loop` — 数据闭环管道专家：snapshot_recorder 全链路架构、故障排查、优化方案

### Custom Agents（角色分工）
- `@architect` — 架构审查（只读）：模块边界、依赖方向、非功能需求
- `@ui-designer` — UI 审查（只读）：a11y、响应式、组件一致性、状态覆盖
- `@test-strategist` — 测试策略（可运行测试）：覆盖率分析、测试矩阵、GWT 用例

### Hooks（自动执行）
- `auto-lint.json` — 写入 Python 文件后自动 ruff lint + format
- `block-dangerous.json` — 阻止危险终端命令 (rm -rf 等)

### Memory（项目记忆）
- `/memories/repo/` — 仓库级记忆（架构、已知问题、Skills 配置）
- 每次 AI 发现新的项目约定或陷阱时，会自动更新记忆文件

### Loop Engineering（自主循环）
- `.github/loop/` — Loop Engineering 基础设施（STATE.md, GUIDE.md, WORKTREES.md）
- `.claude/agents/` — 自动循环 Agent（ci-fixer, code-reviewer）
- `.github/workflows/ci-triage.yml` — 每日 CI 分诊 Automation
- `.github/mcp/` — MCP Connectors 配置指南
- 详见 `.github/loop/README.md`

### 标准工作流
```
新功能:   /spec-generator → @architect → /execution-governor → @test-strategist → @ui-designer → /pr-checklist
Bug修复:  /bug-hunting → /execution-governor → /verify-feedback → /pr-checklist
数据库:   /db-migration → /verify-feedback → /pr-checklist
重构:     /safe-refactor → /code-review → /pr-checklist
CI/CD:    /devops-engineer → /verify-feedback → /pr-checklist
运维:     /ops-playbook → @architect (复盘)
数据闭环:  /data-loop → /bug-hunting（排障）→ /pr-checklist
自动循环:  CI Triage (/loop) → ci-fixer → code-reviewer → PR → STATE.md
```
