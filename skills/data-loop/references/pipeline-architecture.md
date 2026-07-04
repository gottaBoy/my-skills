# Pipeline Architecture — Data Loop

## 系统边界

```
┌──────────────────────────────────────────────────────────── Vehicle (车端) ───┐
│                                                                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐                 │
│  │ tag_rules_   │    │ rules_merger │    │ rule_evaluator   │                 │
│  │ fetcher_node │───>│ _node        │───>│ _node            │                 │
│  │ (30s poll)   │    │ (merge HTTP  │    │ (evaluate +      │                 │
│  │              │    │  + push)     │    │  fire triggers)  │                 │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘                 │
│                                                    │ /zeron/vehicle/trigger    │
│                                                    ▼                          │
│  ┌──────────────────────────────────────────────────────────┐                 │
│  │ snapshot_recorder_node (C++)                              │                 │
│  │  ├─ trigger_callback                                     │                 │
│  │  │   ├─ rule_deduplicator (10s cooldown)                 │                 │
│  │  │   ├─ rec_state_ atomic gate                           │                 │
│  │  │   └─ recording_thread_func (detached)                 │                 │
│  │  ├─ process_clip_from_record_all                         │                 │
│  │  │   ├─ event_directory_manager::create_event_directory  │                 │
│  │  │   ├─ event_directory_manager::write_metadata          │                 │
│  │  │   ├─ clipper_executor::execute                        │                 │
│  │  │   │   └─ record_all_clipper.py                        │                 │
│  │  │   └─ upload_executor::execute_async                   │                 │
│  │  │       └─ upload_handler.py                            │                 │
│  │  └─ process_ring_buffer_mode                             │                 │
│  │      └─ rosbag2_cpp::Writer (buffer dump)                │                 │
│  └──────────────────────────────────────────────────────────┘                 │
│                                                                                │
│  ┌──────────────────┐                                                         │
│  │ disk_manager.py  │  120s cycle                                             │
│  │  ├─ event cleanup│                                                         │
│  │  ├─ upload queue │                                                         │
│  │  ├─ session dirs │  (opt-in)                                               │
│  │  └─ watermark    │  pause/resume ros2 bag                                  │
│  └──────────────────┘                                                         │
│                                                                                │
│  ┌──────────────────┐                                                         │
│  │ metrics_exporter │  Prometheus textfile                                    │
│  │  .py             │                                                         │
│  └──────────────────┘                                                         │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
         │                              │
         │ POST /tasks                   │ Upload to TOS/S3
         │ PATCH /tasks/{id}/status      │
         ▼                              ▼
┌────────────────────┐    ┌──────────────────────┐
│ zeron-upload-hub   │    │ TOS / S3 Storage     │
│  ├─ POST /tasks    │    │                      │
│  ├─ PATCH status   │    │ datasets/in-house/   │
│  └─ trigger DAG    │───>│   data_loop/{vin}/   │
└────────────────────┘    │   {event_id}/        │
         │                │     event_meta.json  │
         │                │     microlog.mcap    │
         ▼                └──────────────────────┘
┌────────────────────┐
│ Argo / Airflow DAG │
│  dataloop_bag_     │
│  convert           │
└────────────────────┘
```

## 数据流

```
DSL API ──→ tag_rules_fetcher ──→ /zeron/cloud/rules ──→ rule_evaluator
                                                              │
                                    /zeron/vehicle/trigger ◄──┘
                                           │
                                           ▼
                              snapshot_recorder_node
                                   │          │
                            event_meta.json   microlog.mcap
                              (metadata)      (data)
                                   │          │
                                   └────┬─────┘
                                        │
                                  upload_handler.py
                                        │
                                ┌───────┼───────┐
                                │       │       │
                           POST /tasks  PATCH   TOS Upload
                                │    UPLOADING      │
                                │       │           │
                                ▼       ▼           ▼
                              Hub DB   Hub DB    S3 Bucket
                             (PENDING) (UPLOADING)
                                        │
                                   PATCH UPLOADED
                                        │
                                        ▼
                              trigger_convert_dag
                                        │
                                        ▼
                              Argo/Airflow DAG
```

## 组件职责

| 组件 | 语言 | 输入 | 输出 | 故障域 |
|------|------|------|------|--------|
| tag_rules_fetcher | Python | DSL API HTTP | `/zeron/cloud/rules` ROS2 | API 不可达 → 空 rules |
| rules_merger | Python | `/zeron/cloud/rules_http`, `_push` | `/zeron/cloud/rules` | merge 冲突 |
| rule_evaluator | Python | `/zeron/cloud/rules` + sensor topics | `/zeron/vehicle/trigger` | 评估延迟、误触发 |
| snapshot_recorder | C++ | `/zeron/vehicle/trigger` + all topics | `event_meta.json` + `microlog.mcap` | clip 失败、磁盘满 |
| upload_handler | Python | `event_meta.json` + `microlog.mcap` | Hub tasks + S3 objects | 网络中断、token 过期 |
| disk_manager | Python | 磁盘状态 + 上传队列 | 清理动作 + 录制控制 | 误删未上传数据 |

## LOOP 基元映射

| 基元 | 实现 | 成熟度 |
|------|------|--------|
| ⏱ Scheduling | `tag_rules_fetcher` 30s poll, `disk_manager` 120s cycle, `rule_evaluator` timer | L2 |
| 🌲 Worktrees | `rec_state_` atomic gate, `recording_thread_func` detached thread | L1 |
| 📚 Skills | `data-loop/SKILL.md` + references/ | L2 |
| 🔌 Connectors | `api_client.py` (REST), ROS2 pub/sub, TOS/S3 SDK | L2 |
| 🔀 Sub-agents | C++→Python (clip, upload), `@architect` review | L1 |
| 💾 State | `event_meta.json`, `.upload_queue/`, Prometheus metrics | L1 |
| 🛡 Safety | 水位线 pause/resume, trigger throttle, queue discard | L2 |
| 📊 Observability | `metrics_exporter.py`, structured logging prefixes | L1 |

**Loop Readiness Score**: ~65/100 (L1→L2)
- ✅ 有 scheduling、connectors、safety
- ⚠️ 缺 circuit breaker、run log/budget tracking、formal STATE.md
- ⚠️ Worktrees 和 sub-agents 是隐式的，未形式化

## LOOP 反模式对照

> 基于 [loop-engineering anti-patterns](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/anti-patterns.md)

| # | 反模式 | 命中？ | 当前状态 | 改进方向 |
|---|--------|--------|---------|---------|
| 1 | 同一 agent 实现+验证 | ⚠️ | C++ clip→Python upload 有拆分，但无 formal verifier | 考虑在 upload 前加文件校验 step |
| 2 | 无重试上限 | ❌ **命中** | upload_handler 无限重试 | 已加 3 次上限约束（FM-003），待实现 circuit breaker |
| 3 | 模糊 triage 输出 | ✅ | 结构化日志 `[TRIGGER]` `[UPLOAD]` 前缀 | 足够清晰 |
| 4 | L3 之前无 L1 质量 | ⚠️ | 直接 L3 生产运行 | 已创建 failure-modes 文档，run log 待实现 |
| 5 | 无 schema 共享状态 | ✅ | `event_meta.json` 有固定结构，`.upload_queue/` job 有 schema | 足够 |
| 6 | MCP 写权限过大 | ✅ | 车端无 MCP，api_client 只 POST/PATCH 特定端点 | 足够 |
| 7 | 无 kill switch | ⚠️ | `kill -STOP` 可用但不正式 | 已文档化 pause/resume/discard 协议 |
| 8 | 用代码修复 flaky test | N/A | 无测试框架 | N/A |
| 9 | 无 allowlist 自动合并 | N/A | 车端无 PR/merge 概念 | N/A |
| 10 | 无 run log | ❌ **命中** | 只有 Prometheus 指标 | 已在 loop-constraints.md 定义 schema，待实现 |

## 升级路径 (L0→L3)

```
L0 — Draft (已完成)               L1 — Report (已完成)
  ✅ 设计文档                        ✅ Prometheus 指标
  ✅ 管道全景图                      ✅ 结构化日志前缀
                                    ✅ 健康检查一行命令
       ↓
L2 — Assisted (部分完成)           L3 — Unattended (当前)
  ✅ 渐进式降级                      ✅ 无人值守运行
  ✅ 水位线 pause/resume             ⚠️ 缺 run log
  ⚠️ 缺 circuit breaker             ⚠️ 缺 attempt cap 强制执行
  ⚠️ 缺 run log                     ⚠️ 缺 loop-budget 资源追踪
```

### L2→L3 改进优先级

| 优先级 | 项目 | 文件 |
|--------|------|------|
| P0 | upload circuit breaker（3 次重试→熔断） | `upload_handler.py` |
| P0 | run log 实现（append JSON 到 `/var/log/aura/loop-run.jsonl`） | `disk_manager.py`, `upload_handler.py` |
| P1 | attempt cap 强制执行（非文档约束） | 各组件 |
| P2 | loop-budget 资源追踪 | 新建 |

## 参考

- [loop-constraints.md](loop-constraints.md) — 机器可读约束
- [failure-modes.md](failure-modes.md) — 故障模式目录
- [ops-runbook.md](ops-runbook.md) — 运维手册
- [loop-engineering anti-patterns](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/anti-patterns.md)
- [loop-engineering safety](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/safety.md)
