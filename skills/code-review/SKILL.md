---
name: code-review
description: '代码审查清单（五维度：安全/正确/可维护/性能/测试）。Code review checklist and workflow. Use when: reviewing PRs, doing pre-commit self-review, checking code quality. Covers Python, TypeScript, Java.'
---

# Code Review Skill

## When to Use
- Before committing or pushing code
- Reviewing a teammate's PR
- After AI generates code — verify correctness
- Preparing for a release

## Review Checklist

### 1. 安全性 (Security)
- [ ] 无硬编码密钥、Token、密码
- [ ] SQL 使用参数化查询，无拼接
- [ ] 用户输入有校验和清理
- [ ] API 接口有认证/授权检查

### 2. 正确性 (Correctness)
- [ ] 边界条件已处理（null、空列表、零值）
- [ ] 错误处理完整，不吞异常
- [ ] 类型标注完整（Python type hints, TypeScript types）
- [ ] 数据库迁移脚本可逆（有 down/rollback）

### 3. 可维护性 (Maintainability)
- [ ] 函数/方法不超过 50 行
- [ ] 无魔法数字，使用命名常量
- [ ] 复杂逻辑有注释说明
- [ ] 命名清晰，见名知义

### 4. 性能 (Performance)
- [ ] 无 N+1 查询
- [ ] 大数据量操作有分页
- [ ] 避免不必要的循环嵌套

### 5. 测试 (Testing)
- [ ] 新功能有对应测试
- [ ] 边界条件有测试覆盖
- [ ] 运行 `python -m pytest` / `npm test` / `./mvnw test` 通过

## Review Command Reference

```bash
# Python: lint + type check
cd insight/trigger-server && ruff check . && mypy .

# Web: lint
cd web && npm run lint

# Java: build with tests
cd jetlinks-community && ./mvnw clean verify
```

## Anti-patterns to Watch
- 过大的 try/except 块
- 在循环中执行数据库查询
- 使用 `Any` 类型代替具体类型
- 复制粘贴代码（应抽取公共方法）
