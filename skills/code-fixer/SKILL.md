---
name: code-fixer
description: 'Fix code issues based on CI triage results. Use when: CI failure is auto-fixable, tests need fixing, lint errors need resolution, build errors after dependency change.'
---

# Code Fixer Skill

## 目的
根据 CI 失败信息修复代码问题。

## 输入
- CI triage 输出的 JSON（issue_type, root_cause, file_path, line_number）
- 目标文件的完整内容
- 相关测试文件

## 修复原则

### 🔴 必须遵守
1. **只修复与 CI 失败直接相关的问题** — 不要顺手重构
2. **保持代码风格一致** — 匹配现有文件格式、命名、结构
3. **所有修复必须通过 lint 和类型检查**
4. **如果修复涉及测试，确保测试仍然通过**

### 🟡 建议
5. 如果测试失败是因为测试本身有 bug，修复测试而非业务代码
6. 如果修复需要新增 import，放在文件头部已有 import 之后
7. 涉及多个文件的修复，按依赖顺序处理

### 🔵 输出
- 修改后的代码（使用 `replace_in_file`）
- 修复说明（为什么这样修复）
- 运行测试的结果（pass/fail）

## 修复后验证清单

- [ ] 运行受影响的测试套件：`pytest tests/affected_test.py` 或 `npm test -- affected.test`
- [ ] 运行 lint：`ruff check` 或 `eslint`
- [ ] 运行类型检查：`mypy` 或 `tsc --noEmit`
- [ ] 确认没有引入新的 lint 错误

## 常见修复模式

### Python
```
问题: "TypeError: 'NoneType' object is not subscriptable"
修复: 在访问前添加 `if x is not None:` 守卫
```

### TypeScript
```
问题: "Property 'x' does not exist on type 'Y'"
修复: 检查类型定义，添加可选链 `?.` 或类型守卫
```

### Java
```
问题: "NullPointerException at line 42"
修复: 添加 `Objects.requireNonNull()` 或 `Optional.ofNullable()`
```

## 回滚规则
如果修复后出现以下情况，立即回滚：
1. 修复引入新的测试失败
2. 修复导致 lint error 增加
3. 修复涉及超过 3 个文件（重新评估是否应该标记为 needs_human）
