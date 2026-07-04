# Spec → Harness → Loop 完整操作指南

> 在 Copilot Chat 中逐步走完三阶段闭环，从需求到代码一气呵成。

---

## 三步总览

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1. Spec  │ ──→ │2. Harness│ ──→ │ 3. Loop  │
│ 写规格    │     │ 建验证    │     │ 跑循环    │
└──────────┘     └──────────┘     └──────────┘
  /spec-generator  /execution-    写代码→跑测试→
                   governor       修正→再跑
```

---

## 阶段 1: Spec — 写规格

### 操作

在 Copilot Chat 中输入：

```
/spec-generator 实现用户手机号+验证码登录
```

### AI 产出

```markdown
## 功能: 手机号验证码登录

### 目标
用户通过手机号 + 短信验证码登录系统

### 接口
POST /api/auth/login
输入: { phone: string, code: string }
输出: { token: string, user: { id, name, phone } }

### 成功标准
- [ ] 正确验证码 → 200 + 返回 token
- [ ] 错误验证码 → 401 + "验证码错误"
- [ ] 过期验证码 → 401 + "验证码已过期"
- [ ] 频繁请求 → 429 + "请60秒后重试"

### 边界条件
- 手机号不存在 → 404
- 手机号格式错误 → 400
- 验证码已使用 → 401
```

### 你做的事

看一眼规格，确认输入输出和边界条件没问题，说"OK"。

---

## 阶段 2: Harness — 建验证装置

### 操作

在 Copilot Chat 中输入：

```
/execution-governor 为上面的登录功能搭建测试
```

### AI 产出

```python
# test_login.py
def test_login_success():
    """正确验证码 → 200 + token"""
    resp = client.post("/api/auth/login", json={
        "phone": "13800138000",
        "code": "123456"
    })
    assert resp.status_code == 200
    assert "token" in resp.json

def test_login_wrong_code():
    """错误验证码 → 401"""
    ...

def test_login_expired_code():
    """过期验证码 → 401"""
    ...

def test_login_rate_limit():
    """频繁请求 → 429"""
    ...
```

### 你做的事

确认测试覆盖了所有成功标准。此时测试应该是 **红色（失败）**——因为还没写业务代码。

---

## 阶段 3: Loop — 跑循环

### 操作

现在开始写代码。每改一点就跑一遍测试：

```
写登录接口 → 跑 test_login_success → 通过 ✅
写验证码校验 → 跑 test_login_wrong_code → 通过 ✅
写过期检查 → 跑 test_login_expired_code → 失败 ❌ → 修正 → 通过 ✅
写限流   → 跑 test_login_rate_limit → 通过 ✅
```

### 一键验证命令

```bash
# Python
while true; do ruff check . && mypy src/ && pytest tests/test_login.py -x --cov && break; echo "❌ 修复中..."; done

# TypeScript
while true; do eslint . && tsc --noEmit && vitest run test_login && break; done

# Java
while true; do mvn checkstyle:check && mvn test -Dtest=LoginTest && break; done
```

### 全部通过后

```
/pr-checklist
```

检查提交清单 → 提交 PR。

---

## 完整对话示例

```
👤  /spec-generator 实现用户手机号验证码登录

🤖  [输出 spec.md 内容...]

👤  看起来没问题，继续

👤  /execution-governor 搭建测试

🤖  [创建 test_login.py...]
🤖  测试已创建。运行结果: 4 failed (expected — 业务代码还未实现)

👤  好的，开始写登录接口

🤖  [创建 login_handler.py...]
🤖  运行测试: 2 passed, 2 failed
🤖  test_login_success ✅
🤖  test_login_wrong_code ✅
🤖  test_login_expired_code ❌ — 缺少过期检查
🤖  test_login_rate_limit ❌ — 缺少限流

👤  补上过期检查

🤖  [修改 login_handler.py...]
🤖  运行测试: 3 passed, 1 failed

👤  补上限流

🤖  [添加 rate_limiter...]
🤖  运行测试: 4 passed ✅

👤  /pr-checklist

🤖  [检查清单...] 全部通过，可以提交！
```

---

## 遇到问题时的回退

```
情况: 测试连续失败 3 次以上
操作: git stash && git checkout .
      # 回到上一步，换思路重来

情况: 修改文件超过 3 个
操作: 拆成多个小任务，一个一个做

情况: 不确定问题在哪
操作: /bug-hunting 分析当前失败的原因
```
