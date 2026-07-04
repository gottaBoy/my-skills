---
name: safe-refactor
description: 'Safe refactoring workflow with behavioral preservation. Use when: restructuring code without changing behavior, extracting methods/classes, improving code organization, reducing technical debt, applying design patterns. Emphasizes small steps and constant verification.'
---

# Safe Refactor — 安全重构工作流

核心思想：重构不是重写。每一步改动都必须可验证、可回退、行为不变。

## When to Use
- 函数太长需要拆分
- 重复代码需要抽取
- 命名不够清晰需要改进
- 模块职责混乱需要重新组织
- 准备添加新功能前先整理代码

## 重构铁律

> **每次只改一件事，改完立刻验证。**

## 五步安全重构法

### Step 1: 加测试护栏 (Add Safety Net)
在改任何代码之前，先确保有测试覆盖：
```bash
# 先跑一遍现有测试，确保全绿
cd insight/trigger-server && python -m pytest -v

# 如果被改的代码没有测试，先补一个
# 只测行为，不测实现细节
```

### Step 2: 做最小改动 (Smallest Change)
```python
# ❌ 一次改太多
def process(order):  # 改了函数名 + 参数 + 内部逻辑
    ...

# ✅ 分步来
# Commit 1: 只改函数名
# Commit 2: 只拆参数
# Commit 3: 只优化内部逻辑
```

### Step 3: 立即验证 (Verify Immediately)
```bash
# 每改完一步，立刻跑测试
python -m pytest -v

# 如果有类型检查也跑一下
mypy .
```

### Step 4: 提交原子 commit (Atomic Commit)
```bash
git add -p  # 逐个确认改动
git commit -m "refactor: extract validate_input from process_order"
# 每个 commit 只包含一个逻辑改动
```

### Step 5: 清理 (Clean Up)
```bash
# 确认旧代码没有任何引用
grep -r "old_function_name" .

# 确认新代码符合项目规范
ruff check .
```

## 常见重构模式

### 提取函数 (Extract Function)
```python
# Before: 一个函数做太多事
def process_order(order):
    # 验证 (10 lines)
    # 计算价格 (15 lines)
    # 保存数据库 (8 lines)
    # 发送通知 (12 lines)
    ...

# After: 分步提取
def process_order(order):
    validate_order(order)
    price = calculate_price(order)
    save_order(order, price)
    notify_user(order)
```

### 提取类 (Extract Class)
```python
# Before: 上帝类
class OrderService:
    def validate(self): ...
    def calculate_price(self): ...
    def save(self): ...
    def notify(self): ...
    def generate_report(self): ...

# After: 职责分离
class OrderValidator: ...
class PriceCalculator: ...
class OrderRepository: ...
class NotificationService: ...
```

### 用 dataclass 替代字典
```python
# Before
trip = {"id": 1, "status": "active", "driver": "Zhang"}

# After
@dataclass
class Trip:
    id: int
    status: str
    driver: str
```

## 重构检查清单

- [ ] 所有现有测试仍然通过
- [ ] 没有引入新的类型错误
- [ ] 旧接口的调用方已全部更新（或保留了兼容层）
- [ ] 没有遗留的注释代码
- [ ] 新的命名比旧的更清晰（如果新命名没有更好，就不改）
- [ ] 改动范围可控（git diff 显示的改动集中在一两个文件）

## 什么时候不应该重构
- 没有测试覆盖的代码 → 先补测试
- 不理解的代码 → 先读懂
- 马上要发版的代码 → 等发版后
- "看着不爽"但没有实际问题的代码 → 忍住
