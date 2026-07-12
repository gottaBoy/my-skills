---
name: clean-code
description: '代码整洁之道 — 命名、函数、注释、格式、错误处理、边界六个维度的实用规则。Use when: writing new code, reviewing PRs, refactoring, setting coding standards. Covers Go, Python, TypeScript.'
---

# Clean Code — 代码整洁之道

> 代码是写给人看的，只是顺便让机器执行。
> 核心原则：**每次只做好一件事。每个函数只做一件事。每个模块只做一件事。**

## When to Use
- 写新代码：不确定怎么写"好"
- 代码审查：感觉代码"不好"但说不出理由
- 重构：代码能工作但难读/难改
- 制定规范：团队需要统一的编码标准

## 六大维度

### 1. 命名 (Naming) — 见名知义

```go
// ❌ 差：需要注释才能懂
var d int // elapsed time in days
var theList [][]string // list of list of strings

// ✅ 好：名字即文档
var elapsedTimeInDays int
var gameBoard [][]string
```

**规则**：
- 用能读出来的名字（`customer` 而非 `cust`，`generateReport` 而非 `genRpt`）
- 类/结构体用名词（`Vehicle`, `CompatibilityRule`）
- 方法/函数用动词（`ListModules`, `CreateVersion`, `findTarget`）
- 布尔用 `is`/`has`/`can` 前缀（`isActive`, `hasDrift`）
- 避免魔法缩写（`hbClient` → `zsClient`，`recHandler` → `reconcilerHandler`）
- 同一概念用同一词（不要 `get`/`fetch`/`retrieve` 混用）

### 2. 函数 (Functions) — 短小精悍

```go
// ❌ 一个函数做太多事 (50+ 行)
func handleOrder(order Order) error {
    // 验证 (10 lines)
    // 计算价格 (15 lines)
    // 保存 (10 lines)
    // 通知 (10 lines)
    return nil
}

// ✅ 拆成小函数，每个只做一件事
func handleOrder(order Order) error {
    if err := validateOrder(order); err != nil { return err }
    price := calculateTotal(order)
    if err := saveOrder(order, price); err != nil { return err }
    notifyUser(order)
    return nil
}
```

**规则**：
- 每个函数不超过 20 行（理想）
- 每个函数只做一件事（单一抽象层级）
- 参数不超过 3 个，多了用结构体
- 无副作用：查询和命令分离
- 用异常/error 代替返回错误码

### 3. 注释 (Comments) — 解释意图，不重复代码

```go
// ❌ 差：重复代码
// Set port to 8080
port := 8080

// ❌ 差：注释掉的死代码
// oldImplementation()
// oldFunction()

// ✅ 好：解释为什么
// Match HawkBit MGMT API 'controllerId' field (VIN string, not numeric ID)
type Target struct {
    ControllerID string `json:"controllerId"`
}

// ✅ 好：TODO 带上下文
// TODO(zota): add semver range parsing with github.com/Masterminds/semver/v3
```

**规则**：
- 好代码自注释，只在必要时加注释
- 注释解释 **意图**（为什么），不重复 **代码**（是什么）
- 删除注释掉的死代码，不要留着
- Javadoc/GoDoc 只写公开 API 的行为契约

### 4. 格式 (Formatting) — 统一风格

```go
// ✅ 团队统一风格（gofmt / prettier / ruff format）
type Rule struct {
    ID                   int64     `json:"id"`
    ModuleName           string    `json:"module"`
    VersionRange         string    `json:"version_range"`
    RequiresModuleName   string    `json:"requires_module"`
    RequiresVersionRange string    `json:"requires_version_range"`
    Compatible           bool      `json:"compatible"`
}
```

**规则**：
- 用团队统一的 formatter（`gofmt`, `prettier`, `ruff format`）
- 一个文件不超过 500 行
- 横向不超过 120 字符
- 相关代码靠近，用空行分隔不同概念

### 5. 错误处理 (Error Handling) — 不吞异常

```go
// ❌ 差：静默吞掉错误
actual, _ := client.GetActualVersions(vin)
h.db.Exec(query, args...)

// ❌ 差：返回 nil 掩盖问题
if err := decode(); err != nil {
    return nil, nil  // 调用方不知道出错了
}

// ✅ 好：区分场景处理
if err != nil {
    if errors.Is(err, sql.ErrNoRows) {
        return nil, nil  // 空结果是正常的
    }
    return nil, fmt.Errorf("get versions: %w", err)  // 包装上下文
}
```

**规则**：
- 永远不要忽略 error 返回值（Go）/ 不要空 catch（Java/Python）
- 错误消息包含上下文：`fmt.Errorf("sync vehicle %s: %w", vin, err)`
- 区分"正常空"和"异常空"（`nil, nil` vs `nil, err`）
- 使用自定义错误类型传递额外信息

### 6. 边界 (Boundaries) — 隔离外部依赖

```go
// ✅ 接口隔离：依赖抽象而非具体实现
type Repository interface {
    ListModules() ([]Module, error)
    CreateModule(m *Module) error
}

// Handler 依赖接口，不依赖 *Store
type Handler struct {
    store Repository  // 可 mock，可测试
}
```

**规则**：
- 第三方库/API 调用封装在独立模块中（如 `zotaserver.Client`）
- 使用接口解耦（Repository, Service, Client）
- 不让外部 API 的类型污染业务代码
- 对第三方依赖做适配层（Anti-Corruption Layer）

---

## 快速检查清单

写完代码后自问：

- [ ] 命名能否让新人一眼看懂？
- [ ] 有没有超过 30 行的函数？
- [ ] 有没有无意义的注释或注释掉的代码？
- [ ] 所有 error 都处理了吗？
- [ ] 有没有硬编码的魔法数字？
- [ ] 函数参数超过 3 个了吗？
- [ ] 依赖的是接口还是具体实现？

## 对应本项目

| 原则 | zota-repo 示例 |
|------|---------------|
| 见名知义 | `requires_module_id` 比 `module_b_id` 清晰 |
| 单一职责 | `catalog.Handler` 只做 HTTP，`catalog.Store` 只做 SQL |
| 接口隔离 | `catalog.Repository` 接口定义契约，`Store` 是实现 |
| 错误包装 | `fmt.Errorf("find target %s: %w", vin, err)` |
| 注释意图 | `// Prod safety: warn if using SQLite` |
