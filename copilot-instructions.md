# Project Guidelines — autodrive

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

### Spec 层（规划）
- `spec-generator` — 模糊需求 → proposal → specs → design → tasks（结构化规格）
- `task-recipe` — 六步拆解法，把大任务变成可执行的 INVEST 子任务

### Harness 层（执行）
- `execution-governor` — TDD 铁律 + Scope Fence + Review Gates + Rewind Triggers
- `code-review` — 五维度代码审查（安全/正确/可维护/性能/测试）
- `verify-feedback` — 五层验证金字塔（类型→Lint→单元→集成→E2E）
- `bug-hunting` — 五步系统化 Bug 定位

### Loop 层（闭环）
- `pr-checklist` — PR 提交前自检 + 质量门
- `safe-refactor` — 五步安全重构（原子 commit + 行为不变）
- `db-migration` — 数据库安全迁移（UP/DOWN 脚本 + 回滚）

### 标准工作流
```
新功能:   /spec-generator → /execution-governor → /code-review → /pr-checklist
Bug修复:  /bug-hunting → /execution-governor → /verify-feedback → /pr-checklist
数据库:   /db-migration → /verify-feedback → /pr-checklist
重构:     /safe-refactor → /code-review → /pr-checklist
```
