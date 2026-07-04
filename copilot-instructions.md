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
This project uses a Karpathy-inspired Skills system. Type `/` in Copilot Chat to see available skills. See `.github/skills/SKILLS_GUIDE.md` for the complete guide.

Available skills: `task-recipe`, `code-review`, `bug-hunting`, `db-migration`, `pr-checklist`, `verify-feedback`, `safe-refactor`
