---
description: "Use when writing Python code, Flask routes, data models, or database access. Covers type hints, dataclass patterns, and MySQL best practices for the autodrive project."
applyTo: "**/*.py"
---

# Python Coding Standards — autodrive

## Type Hints
```python
# ✅ Always use type hints
def get_trip(trip_id: int) -> dict[str, Any] | None:
    ...

# ❌ Don't skip hints
def get_trip(trip_id):
    ...
```

## Data Models
```python
from dataclasses import dataclass

@dataclass
class TripEvent:
    trip_id: int
    event_type: str
    timestamp: datetime
```

## Flask Patterns
- Blueprint 用于组织路由模块
- 使用 `flask.jsonify` 返回 JSON 响应
- 数据库连接从 `mysql.py` 获取，不要自己创建连接
- 错误处理统一用 `try/except` + 返回标准错误格式

## Database (MySQL via PyMySQL)
```python
# ✅ 参数化查询
cursor.execute("SELECT * FROM trips WHERE id = %s", (trip_id,))

# ❌ 字符串拼接（SQL 注入风险）
cursor.execute(f"SELECT * FROM trips WHERE id = {trip_id}")
```

## Testing
- 测试文件放在 `tests/` 目录
- 使用 pytest 框架
- 每个服务函数至少有一个 happy-path 测试
