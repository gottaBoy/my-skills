---
name: bug-hunting
description: '系统化Bug定位工作流（五步法）。Systematic bug hunting workflow. Use when: debugging errors, investigating production incidents, fixing test failures, tracing root causes, analyzing stack traces or error logs.'
---

# Bug Hunting Skill

## When to Use
- 遇到运行时错误或异常
- 测试失败需要定位原因
- 生产环境问题排查
- 用户报告 Bug 需要复现

## 定位流程 (5 步法)

### Step 1: 收集证据 (Gather Evidence)
- [ ] 完整错误信息和堆栈跟踪
- [ ] 相关日志（前后 50 行上下文）
- [ ] 触发条件：什么操作导致的问题？
- [ ] 环境信息：Python 版本、Node 版本、Java 版本
- [ ] 是否可以稳定复现？

### Step 2: 缩小范围 (Narrow Scope)
- [ ] 确认问题出现在哪个服务？（trigger-server / web / jetlinks / upload-hub）
- [ ] 是前端还是后端？
- [ ] 最近改了什么？（`git log --oneline -10`）
- [ ] 回退最近的改动是否消失？

### Step 3: 形成假设 (Form Hypothesis)
- [ ] 写出你认为的原因（不超过 3 句话）
- [ ] 设计一个最小验证方法
- [ ] 先读相关代码，不要急着改

### Step 4: 验证修复 (Verify Fix)
- [ ] 先写一个失败的测试来捕获 Bug
- [ ] 实施最小改动
- [ ] 测试通过 + 不引入新问题
- [ ] 确认修复后，原有场景不受影响

### Step 5: 沉淀经验 (Document)
- [ ] 在修复 commit 中写清楚根因
- [ ] 如果是典型问题，更新 code-review skill 的检查项
- [ ] 是否需要加监控/告警？

## 调试命令速查

```bash
# Python: 进入调试模式
python -m pdb app.py

# Java: 远程调试
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005"

# 查看最近改动
git log --oneline -20
git diff HEAD~3

# 查看服务日志
docker logs <container-name> --tail 100
```
