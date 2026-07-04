---
name: pr-checklist
description: 'Pre-PR self-check workflow to ensure quality before submitting pull requests. Use when: preparing to create a PR, about to push code, doing final checks before merge, self-reviewing changes.'
---

# PR 自检 Skill

## When to Use
- 准备提交 PR 之前
- 准备 push 代码之前
- 合并前最终检查

## 自检清单

### 1. 改动范围检查
- [ ] `git diff main` 确认改动都在预期范围内
- [ ] 无意外改动的文件（调试代码、临时文件）
- [ ] 无注释掉的代码残留
- [ ] 无 `console.log` / `print()` 调试语句

### 2. 质量门 (Quality Gates)
```bash
# Python 服务
cd insight/trigger-server && ruff check . && python -m pytest

# 前端
cd web && npm run lint && npm run build

# Java
cd jetlinks-community && ./mvnw clean verify -DskipTests=false
```

### 3. Commit 规范
- [ ] Commit message 格式：`<type>: <description>`
  - `feat:` 新功能
  - `fix:` Bug 修复
  - `refactor:` 重构
  - `docs:` 文档
  - `test:` 测试
- [ ] 每个 commit 只做一件事
- [ ] 无 "WIP" 或 "fix typo" 类垃圾 commit（已 squash）

### 4. PR 描述模板
```markdown
## 改动内容
- 简要说明做了什么

## 测试方式
- [ ] 单元测试通过
- [ ] 手动测试步骤和结果

## 影响范围
- 影响的服务/模块
- 是否需要数据库迁移
- 是否需要更新文档

## 截图（如有 UI 变更）
```

### 5. 最终确认
- [ ] 已在本地完整运行通过
- [ ] 无新增 linter 警告
- [ ] 敏感信息已移除
- [ ] 相关文档已更新
