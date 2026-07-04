# Loop Engineering 实战指南

## 两大循环原语

### `/loop` — 定时循环
```
# 每5分钟检查一次
/loop 5m 检查 staging 部署是否完成

# 智能模式（AI自行决定间隔）
/loop 检查 CI 是否通过，失败就修复

# 维护模式（自动找活干）
/loop
```

### `/goal` — 跑到完成为止
```
# 跑到所有测试通过
/goal all tests in test/auth pass and lint is clean

# 跑到功能完成
/goal the user registration endpoint returns 201 on success
```

## 闭环 vs 开环

| | 闭环 (Closed Loop) | 开环 (Open Loop) |
|---|---|---|
| **停止条件** | 明确可验证 | 无自动停止 |
| **适用场景** | Bug修复、测试通过、CI绿灯 | 持续监控、探索性研究 |
| **风险** | 低，有明确出口 | 高，可能无限烧Token |
| **建议** | 从闭环开始 | 掌握闭环后再尝试 |

## 闭环五要素
1. **明确目标** — 精确定义"完成"的样子
2. **充足上下文** — VISION.md、ARCHITECTURE.md、RULES.md
3. **受限动作** — 只允许必要工具
4. **客观反馈** — 测试、lint、类型检查
5. **清晰停止条件** — 可验证的成功标准

## 成本控制

| 策略 | 节省 |
|------|------|
| 渐进式披露（元数据常驻，正文按需加载） | ~85% Token |
| 闭环有明确停止条件 | 避免无限循环 |
| 子Agent只在需要时创建 | 减少闲置消耗 |
| 外部状态存储（不依赖上下文窗口） | 每次重启不丢进度 |

## 最小可行 Loop (Ralph Loop)

```bash
# 最原始的无限循环——每次都是全新上下文
while :; do cat PROMPT.md | claude-code; done
```

每次循环重新读取 PROMPT.md 和当前代码库状态，彻底解决上下文漂移问题。

## 推荐：从闭环开始

1. 写一个明确目标 → `/goal all tests pass`
2. 准备好上下文文件 → ARCHITECTURE.md, RULES.md
3. 限制工具范围 → 只给必要的
4. 设置可验证停止条件 → lint clean + test pass
5. 观察 → 调整 → 再跑
