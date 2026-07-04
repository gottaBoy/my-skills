---
name: verify-feedback
description: '验证与反馈闭环（六层金字塔：类型→Lint→单元→集成→E2E→浏览器）。Verification and feedback loop for AI-generated code. Use when: AI generates code that needs validation, setting up test harness, establishing quality gates.'
---

# Verify & Feedback — 给 AI 装上"眼睛"

核心思想（来自 Karpathy）：AI 的生成能力很强，但它对真实世界的感知取决于你给它开了多少窗口。
测试、日志、类型系统、lint、CI —— 每一扇窗口都让 AI 少猜，系统就更稳定。

## When to Use
- AI 生成了代码，需要验证是否正确
- 新功能开发完成后需要建立验证体系
- 重构后需要确保行为不变
- 建立 CI/CD 质量门

## 验证金字塔（六层）

```
           ┌──────────────┐
           │  浏览器反馈   │ ← ✨ 新增：read_page + screenshot + Playwright
           ├──────────────┤
           │    E2E      │ ← 关键用户流程的手动/自动验证
           ├──────────────┤
           │  集成测试     │ ← 服务间交互、数据库读写
           ├──────────────┤
           │  单元测试     │ ← 每个函数/方法的正确性
           ├──────────────┤
           │  Lint & 格式  │ ← 代码风格、安全规则
           ├──────────────┤
           │  类型系统     │ ← 编译时错误（最便宜）
           └──────────────┘
```

## 反馈窗口清单

### 窗口 0: 浏览器反馈 ✨ 新增

> Karpathy 原则："窗口越多，模型越少靠猜。" 浏览器是最强的视觉反馈窗口。

```bash
# 启动服务后在 VS Code Copilot 中告诉 AI:
"用 open_browser_page 打开 http://localhost:3000"
"用 read_page 检查页面上的按钮和文案"
"用 screenshot_page 截图确认布局"
"用 run_playwright_code 执行复杂交互"
```

| 工具 | 用途 | 优先级 |
|------|------|--------|
| `read_page` | 返回 DOM 文本快照，AI 可直接读取组件树 | ⭐ 首选 |
| `screenshot_page` | 视觉确认布局、颜色、响应式效果 | ⭐ 兜底 |
| `run_playwright_code` | 复杂多步交互（表单填写、跨页面流程） | ⭐ 攻坚 |
| `open_browser_page` | 启动页面 + 获取初始快照 | ⭐ 入口 |

### 窗口 1: 类型系统 (最便宜，最高效)
```bash
# Python
cd insight/trigger-server && mypy . --strict

# TypeScript
cd web && npx tsc --noEmit

# Java (编译即类型检查)
cd jetlinks-community && ./mvnw compile
```

### 窗口 2: Lint & 格式
```bash
# Python
cd insight/trigger-server && ruff check . && ruff format --check .

# TypeScript/React
cd web && npm run lint

# Java
cd jetlinks-community && ./mvnw checkstyle:check
```

### 窗口 3: 单元测试
```bash
# Python
cd insight/trigger-server && python -m pytest -v

# Web
cd web && npm test

# Java
cd jetlinks-community && ./mvnw test
```

### 窗口 4: 启动验证
```bash
# 确保服务能启动
cd insight/trigger-server && timeout 10 python app.py
cd web && timeout 10 npm run dev
```

### 窗口 5: 集成测试
```bash
# 数据库连接验证
python -c "from mysql import get_connection; conn = get_connection(); print('OK')"
```

## AI 代码验证流程

```
AI 生成代码
    │
    ├─→ 0. 浏览器反馈 (前端专用)  ← 新增
    │       ├─ open_browser_page → read_page 读取 DOM
    │       ├─ 组件渲染正确？→ 下一步
    │       └─ 缺失/错误 → 告诉 AI 具体哪里不对
    │
    ├─→ 1. 静态检查 (类型 + lint)  ← 先跑这个，最快
    │       ├─ 通过 → 下一步
    │       └─ 失败 → 把错误信息喂回给 AI
    │
    ├─→ 2. 单元测试
    │       ├─ 通过 → 下一步
    │       └─ 失败 → 把失败日志喂回给 AI
    │
    ├─→ 3. 启动验证
    │       ├─ 能启动 → 下一步
    │       └─ 启动失败 → 把启动日志喂回给 AI
    │
    ├─→ 4. 集成测试
    │       ├─ 通过 → 下一步
    │       └─ 失败 → 把失败日志喂回给 AI
    │
    └─→ 5. 人工 Review
            ├─ 逻辑正确 → 合并
            └─ 有问题 → 具体指出哪里不对
```

## 给 AI 提供反馈的正确方式

```markdown
❌ 坏的反馈：
"代码报错了，帮我修一下"

✅ 好的反馈：
"运行 mypy 报以下错误：
app.py:42: error: Argument 1 to "get_trip" has incompatible type "str"; expected "int"
请修复类型错误，同时检查是否有其他地方也存在类似问题。"
```

## 项目验证命令速查

| 服务 | 类型检查 | Lint | 测试 | 启动 |
|------|---------|------|------|------|
| trigger-server | `mypy .` | `ruff check .` | `pytest` | `python app.py` |
| web | `tsc --noEmit` | `npm run lint` | `npm test` | `npm run dev` |
| jetlinks | `mvnw compile` | `mvnw checkstyle:check` | `mvnw test` | `mvnw spring-boot:run` |
| upload-hub | `mypy .` | `ruff check .` | `pytest` | `python app.py` |
