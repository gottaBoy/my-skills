---
name: design-patterns
description: '设计模式参考手册 — 创建型/结构型/行为型经典模式的 Go 实现+实战案例。Use when: designing new modules, choosing architecture patterns, refactoring to patterns, code review.'
---

# Design Patterns — 设计模式参考

> 模式是已知问题的已知解决方案。不是为了炫技，是为了降低认知负担。
> 原则：**Don't design for the future you don't have. 只在确实需要时才引入模式。**

## When to Use
- 设计新模块：不确定怎么组织代码
- 重构：发现代码在朝着某个模式演化
- 代码审查：识别出模式可以加速理解
- 需要灵活扩展：但不能过早抽象

---

## 创建型 (Creational)

### 工厂函数 (Factory Function)

```go
// ✅ 封装复杂初始化
func NewServer(configPath string) (*Server, error) {
    cfg, err := loadConfig(configPath)
    // ... validation, DB setup, migrations ...
    return &Server{db: db, config: cfg}, nil
}

// ❌ 反模式：让调用方自己拼装
db, _ := sql.Open(...)
s := &Server{db: db}
```

**Go 习惯**：优先用 `NewXxx(...) (*Xxx, error)` 而非构造器重载。

### 单例 (Singleton) — 慎用

```go
// ✅ 仅在确实需要全局唯一状态时用（如连接池）
var migrationFor = map[string]string{
    "sqlite3":  sqliteMigration,
    "postgres": pgMigration,
    "mysql":    mysqlMigration,
}
```

> ⚠️ 避免全局可变单例——它让测试变得困难和不可靠。

---

## 结构型 (Structural)

### Repository 模式 (数据访问抽象)

```go
// 接口定义"做什么"
type Repository interface {
    ListModules() ([]Module, error)
    CreateModule(m *Module) error
    GetModuleByName(name string) (*Module, error)
}

// 具体实现定义"怎么做"
type Store struct {
    db *sql.DB
}
// Store 隐式实现 Repository（Go 鸭子类型）

// Handler 依赖接口
type Handler struct {
    store Repository  // 可注入 mock 进行测试
}
```

**收益**：
- Handler 可独立于数据库测试
- 切换数据库只需换实现（`*Store` → `*PostgresStore`）
- 接口即文档，一看就知道支持哪些操作

### 适配器 (Adapter) — 隔离外部 API

```go
// zotaserver.Client 是对 HawkBit MGMT API 的适配器
// 将 "GET /rest/v1/targets/VIN001/assignedDS" 封装为
func (c *Client) GetExpectedVersions(vin string) (map[string]string, error)

// 业务代码不直接拼 HTTP 请求，不依赖 HawkBit 的类型
```

**收益**：
- HawkBit API 变化时只改 Client
- 测试时可用 mock HTTP server 替代真实 HawkBit
- 业务代码用 `map[string]string`，简单通用

### 中间件链 (Middleware Chain)

```go
// 职责链模式：每个中间件只做一件事
handler := corsMiddleware(withLogging(mux))
//        ↑ CORS 头      ↑ 请求日志    ↑ 路由分发

// 每个中间件是独立的、可组合的
func corsMiddleware(next http.Handler) http.Handler { ... }
func withLogging(next http.Handler) http.Handler  { ... }
```

**收益**：添加新中间件不影响已有逻辑（Open-Closed 原则）。

---

## 行为型 (Behavioral)

### 策略模式 (Strategy) — 算法可替换

```go
// 数据库迁移按驱动选择策略
var migrationFor = map[string]string{
    "sqlite3":  sqliteMigration,   // SQLite DDL
    "postgres": pgMigration,       // PostgreSQL DDL
    "mysql":    mysqlMigration,    // MySQL DDL
}

func runMigrations(db *sql.DB, driver string) error {
    migration := migrationFor[driver]
    if migration == "" {
        migration = migrationFor["sqlite3"]  // 默认策略
    }
    _, err := db.Exec(migration)
    return err
}
```

**收益**：新增数据库只需加一个新的 DDL 常量，不改业务逻辑。

### 模板方法 (Template Method) — 框架定义流程

```go
// writeJSON 是"模板"——它定义了 HTTP 响应的通用流程
func WriteJSON(w http.ResponseWriter, status int, data interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(data)
}

// WriteError 复用了这个模板，只改变"数据"部分
func WriteError(w http.ResponseWriter, status int, message string) {
    WriteJSON(w, status, map[string]string{"error": message})
}
```

### 依赖注入 (Dependency Injection)

```go
// ❌ 反模式：Handler 自己创建依赖
func NewHandler(db *sql.DB) *Handler {
    store := catalog.NewStore(db)     // 硬编码依赖
    return &Handler{store: store}
}

// ✅ 依赖注入：从外部传入
func NewHandler(store catalog.Repository) *Handler {
    return &Handler{store: store}     // 遵循接口，不关心实现
}
```

**收益**：测试时注入 mock，生产注入真实 Store。

---

## 反模式警示 (Anti-patterns to Avoid)

### 上帝对象 (God Object)
```go
// ❌ 一个 struct 做所有事
type Service struct {
    db *sql.DB
    // validation logic
    // business rules
    // HTTP handling
    // caching
}

// ✅ 职责分离
type Handler struct { store Repository }    // HTTP only
type Store struct   { db *sql.DB }          // SQL only
```

### 过早抽象 (Premature Abstraction)
```go
// ❌ 为一个具体实现创建过度设计的接口
type ModuleDataAccessor interface { ... }
type ModulePersistor interface    { ... }
type ModuleRetriever interface    { ... }

// ✅ 一个接口足够，等有第二个实现时再拆分
type Repository interface {
    ListModules() ([]Module, error)
    CreateModule(m *Module) error
    GetModuleByName(name string) (*Module, error)
}
```

### 功能嫉妒 (Feature Envy)
```go
// ❌ 函数大量访问另一个对象的字段
func formatDriftAlert(state *VersionState) string {
    return state.VIN + ":" + state.ModuleName  // 全是 state 的字段
}

// ✅ 方法应该放在数据所在的结构体上
func (v VersionState) Alert() string {
    return v.VIN + ":" + v.ModuleName + " drift detected"
}
```

---

## zota-repo 模式地图

| 模式 | 位置 | 场景 |
|------|------|------|
| **Repository** | `catalog/store.go:14` | 数据访问抽象 |
| **Adapter** | `zotaserver/client.go` | 封装 HawkBit MGMT API |
| **Factory** | `api/router.go:NewServer()` | 服务器初始化 |
| **Middleware Chain** | `api/middleware.go` | CORS → Logging → Router |
| **Strategy** | `api/migration.go` | 多数据库 DDL 选择 |
| **Template Method** | `httputil/httputil.go` | JSON 响应模板 |
| **Dependency Injection** | `api/router.go:registerRoutes()` | 组装依赖图 |

## 决策指南

| 场景 | 推荐模式 | 不推荐 |
|------|---------|--------|
| 切换数据库 | Repository + Strategy | 到处 if/switch |
| 封装外部 API | Adapter (Client) | 直接调 HTTP |
| 需要多种变体 | Strategy | 大量 if/else |
| 组装复杂对象 | Factory Function | 调用方自己拼 |
| 跨切面功能 | Middleware Chain | 在每个 handler 里复制代码 |
| 测试困难 | Dependency Injection | 全局变量 / 单例 |
