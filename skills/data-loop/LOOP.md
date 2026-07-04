# LOOP.md — Data Loop 运行态

> Harness = 单次会话配置。Loop = Harness + Schedule + State + Verification。
> 本文件描述 data-loop 内部 4 个并发 loop 的协调规则。

## 运行的 Loop

| Loop | 角色 | Harness | Schedule | State | 风险 |
|------|------|---------|----------|-------|------|
| **rules-sync** | DSL API → ROS2 rules | `tag_rules_fetcher_node.py` | 30s poll | `/zeron/cloud/rules` topic | L1: 只读 |
| **rule-eval** | 评估条件→发布 trigger | `rule_evaluator_node.py` | 100ms tick | `self.rules` dict | L1: 只读 |
| **disk-guard** | 磁盘清理+录制控制 | `disk_manager.py` | 120s cycle | Prometheus + `.upload_queue/` | L2: 会删文件 |
| **event-pipe** | trigger→clip→upload | C++ + `record_all_clipper.py` + `upload_handler.py` | 事件驱动 | `event_meta.json` + hub DB | L3: 无人值守 |

## 碰撞检测

```
disk-guard 删除 event 目录 ←→ event-pipe 正在上传该 event   ← 碰撞！
rule-eval 发布 trigger   ←→ event-pipe 正忙（rec_state_）   ← 已防护（原子门）
rules-sync 更新 rules    ←→ rule-eval 正在 _tick() 迭代    ← 已防护（dict 迭代器）
```

### 碰撞优先级

| 优先级 | Loop | 规则 |
|--------|------|------|
| 1 | **event-pipe** | 正在处理的 event 不可被 disk-guard 删除 |
| 2 | **disk-guard** | 紧急清理（磁盘 > 95%）覆盖所有 |
| 3 | **rule-eval** | 等待 event-pipe 空闲（rec_state_ 原子门） |
| 4 | **rules-sync** | 不影响进行中的 _tick() 迭代 |

### 碰撞防护

| 碰撞 | 当前防护 | 是否足够 |
|------|---------|---------|
| disk-guard ↔ event-pipe | `_cleanup_uploaded_events()` 检查 `.upload_queue/` job 状态 | ✅ 已足够 |
| rule-eval ↔ event-pipe | `rec_state_` atomic CAS | ✅ 已足够 |
| rules-sync ↔ rule-eval | Python dict.items() 迭代器 | ✅ 已足够 |
| 多个 event-pipe 并发 | `rec_state_` atomic CAS | ✅ 一次只处理一个 |

## Schedule 协调

```
rules-sync:     每 30s ────────────────────────────────────────
rule-eval:      每 100ms ─────────────────────────────────────
disk-guard:     每 120s ────────────┬──────────────────────────
event-pipe:     事件驱动 ───────────┴── 单线程，不重叠 ──────────
```

## 升级路径（L0→L3）

```
L1 — Report (全部达成)              L2 — Assisted (2/4 达成)
  ✅ rules-sync: 只读无副作用          ✅ disk-guard: 只删已上传
  ✅ rule-eval: 只读无副作用           ⚠️ disk-guard: 缺 circuit breaker
  ✅ disk-guard: Prometheus 指标       ⚠️ event-pipe: 缺 attempt cap
  ✅ event-pipe: 结构化日志

L3 — Unattended (当前 4/4)
  ✅ event-pipe: 无人值守 + circuit breaker
  ✅ disk-guard: 水位线自控 + run log
  ✅ rule-eval: 自动触发
  ✅ rules-sync: 30s poll
```

## Intent Debt Map（没有此文档 AI 会犯的错）

| 如果不写下来 | AI 会怎么做 | 正确做法 |
|------------|-----------|---------|
| trigger_id 流转走磁盘 | 以为可以实时从 DSL API 获取 | `event_meta.json` 磁盘链路 |
| session 目录不自动删 | 加自动清理逻辑 | 默认 `cleanup_session_dirs: false` |
| `dict.get(k,d)` vs `or` | 用 `dict.get` 导致空字符串不 fallthrough | 用 `or` |
| 4 个并发 loop 的碰撞风险 | 以为没有碰撞 | 本文件记载的优先级和防护 |

## 云端 Hub Loop（zeron-upload-hub）

| Loop | 角色 | Harness | State | 风险 |
|------|------|---------|------|------|
| **hub-register** | POST /tasks → 创建 UploadTask | `routes/tasks.py::register_task` | MySQL `upload_task` 表 | L1: 只写 |
| **hub-status** | PATCH /tasks/{id}/status → 状态流转 | `routes/tasks.py::update_status` | MySQL + `trigger_convert_dag` | L2: 触发 DAG |

### hub-register 防护

| 防护 | 状态 |
|------|------|
| trigger_id 空字符串 fallthrough (`or` 替代 `dict.get`) | ✅ 2026-07-04 |
| 重复 task 友好 409（替代 500） | ✅ 2026-07-04 |
| 结构化 run log（JSONL） | ✅ 2026-07-04 |

### hub-status 防护

| 防护 | 状态 |
|------|------|
| 状态流转白名单 (`UPLOAD_TRANSITIONS`) | ✅ 已有 |
| DAG 触发结果记录到 run log | ✅ 2026-07-04 |

## 车云协同约束

| 约束 | 车端 | 云端 |
|------|------|------|
| trigger_id 空字符串处理 | `or` fallthrough (tag_rules_fetcher + rule_evaluator) | `or` fallthrough (register_task) |
| 重复任务 | 不重复 POST（事件级唯一 task_name） | 409 友好返回 |
| 重试上限 | 3 次 → DISCARDED (upload_handler) | 无限制（信任车端） |
| run log | Prometheus metrics + `[DiskManager]` `[UploadHandler]` 日志前缀 | `upload_task` 表字段 (report_time/upload_started_at/upload_completed_at/status) |
