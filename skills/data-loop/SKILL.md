---
name: data-loop
description: '数据闭环管道专家 — snapshot_recorder 全链路架构、故障排查、优化方案。Use when: debugging data loop issues (disk full, trigger_id empty, upload backlog), modifying snapshot_recorder pipeline, understanding DSL rule→clip→upload flow, doing data loop code review.'
---

# Data Loop — 数据闭环管道

## 一句话
掌握 snapshot_recorder 全链路（DSL 规则→触发→剪辑→上传→云端），快速排障。

## When to Use
- 调试：磁盘满、trigger_id 为空、上传积压、clip 失败
- 开发：修改 `snapshot_recorder/` 下任一组件的代码
- 审查：数据闭环 PR review
- 运维：日常巡检、应急响应

## 变更流程

> 大改先提案，小修直接干。改数据闭环代码前按此流程走。

| 步骤 | 做什么 | 产物 |
|------|--------|------|
| 1. **explore** | 读 SKILL.md + 相关代码 + 现有 FM，理解现状 | 方案思路 |
| 2. **propose** | 写清楚：改什么文件、为什么改、如何回滚 | 更新设计原则/关键文件 |
| 3. **apply** | 实现 + 验证：`ros2 topic echo` 确认管道正常 | 代码变更 |
| 4. **archive** | 沉淀：新故障模式 → FM；新约束 → loop-constraints | 更新 references/ |

**小修免提案**（typo、日志格式、配置调优）。**大改必提案**（新增组件、改 trigger_id 流转、改清理策略）。

## 管道全景

```mermaid
flowchart LR
    subgraph Cloud["☁️ Cloud"]
        API["DSL API<br/>/vehicle_triggers/dsl"]
    end

    subgraph Vehicle["🚗 Vehicle"]
        FETCH["tag_rules_fetcher<br/>30s poll"] -->|"/zeron/cloud/rules"| EVAL["rule_evaluator<br/>evaluate + fire"]
        EVAL -->|"/zeron/vehicle/trigger"| REC["snapshot_recorder (C++)<br/>clip + upload"]
        REC -->|"event_meta.json"| DISK[("💾 Disk")]
        REC -->|"microlog.mcap"| DISK
        DISK --> UPLOAD["upload_handler<br/>POST /tasks → upload TOS"]
        DM["disk_manager<br/>120s cleanup cycle"] -.->|"watermark control"| REC
        DM -.->|"event cleanup"| DISK
    end

    subgraph Hub["☁️ Hub"]
        TASKS["POST /tasks → PENDING<br/>PATCH → UPLOADING<br/>PATCH → UPLOADED"]
        DAG["trigger_convert_dag<br/>→ Argo/Airflow"]
    end

    API -->|"rules JSON"| FETCH
    UPLOAD -->|"POST /tasks"| TASKS
    UPLOAD -->|"PATCH status"| TASKS
    UPLOAD -->|"Upload"| S3["TOS/S3"]
    TASKS --> DAG
```

## 排障决策树

> **万能第一步**: `ros2 topic echo /rosout | grep -E "\[TRIGGER\]|\[UPLOAD\]|\[DiskManager\]|\[CLIP\]|\[RULE\]" | tail -20`

```mermaid
flowchart TD
    START["🚨 出问题了"] --> Q1{"什么症状？"}

    Q1 -->|"磁盘满了"| D1["du -sh /mnt/disk_main/* | sort -rh | head"]
    D1 --> D1A{"有大量 ZSD-DP007_* 目录？"}
    D1A -->|"是"| FM001["→ FM-001: session 未被清理<br/>disk_manager 不管理 session<br/>手动清理或开启 cleanup_session_dirs"]
    D1A -->|"否"| FM003["→ FM-003: events 积压<br/>上传队列堵塞"]

    Q1 -->|"trigger_id 为空"| Q2{"所有记录还是最后一条？"}
    Q2 -->|"最后一条"| FM002["→ FM-002: deactivate 过渡窗口<br/>已修复：or fallthrough + 双重过滤"]
    Q2 -->|"所有"| FM006["→ FM-006: clipper 覆写丢失<br/>event_meta.json 缺 triggers 数组"]

    Q1 -->|"上传积压"| Q3{"云端可达？"}
    Q3 -->|"否"| ACT1["暂停录制 kill -STOP<br/>等云端恢复"]
    Q3 -->|"是但慢"| ACT2["调分片上传参数<br/>MULTIPART_THRESHOLD_MB"]

    Q1 -->|"不触发"| FM004["→ FM-004: 检查 rule/topic/cooldown"]
    Q1 -->|"clip 失败"| FM005["→ FM-005: 检查 record_all_root"]
```

## 关键文件

| 文件 | 角色 | 易错点 |
|------|------|--------|
| `tag_rules_fetcher_node.py` | DSL API → ROS2 rules | `dict.get(k, d)` vs `dict.get(k) or d` |
| `rules_merger_node.py` | 合并 HTTP + Push 规则 | push 覆盖 http 同 id |
| `rule_evaluator_node.py` | 评估条件→发布 trigger | `_on_rules` 替换不影响进行中的 `_tick` 迭代 |
| `snapshot_recorder_node.cpp` | 接收 trigger→clip→upload | `rec_state_` 原子门，一次只处理一个 |
| `event_directory_manager.cpp` | 创建 event dir + metadata | 新格式 writes `triggers[]` 而非顶层 `id` |
| `record_all_clipper.py` | 从 session 剪辑 mcap | `meta.update()` 不覆盖 `triggers` |
| `upload_handler.py` | 注册任务→上传→PATCH | 从磁盘读，不依赖 DSL API |
| `api_client.py` | 云端 API 客户端 | token 过期、重试、热重载 |
| `disk_manager.py` | 磁盘清理+录制控制 | 只管理 `events/`，不管理 session（默认） |
| `config_loader.py` | 统一配置加载 | YAML + `SNAP_` env 覆盖 + 磁盘自适应 |

## 核心设计原则

1. **磁盘链路解耦**：trigger 发布后走 `event_meta.json` 磁盘链路，不依赖 DSL API 后续返回
2. **防御性 ID**：`tag_rules_fetcher`（`or` fallthrough）+ `rule_evaluator`（skip empty id）双重过滤
3. **默认安全**：session 目录不自动删（拔盘离线上传），上传队列超阈值自动节流
4. **渐进降级**：磁盘满→暂停录制→节流触发→丢弃低优先级→紧急清理
5. **可观测性**：`[DiskManager]` `[TRIGGER]` `[UPLOAD]` `[CLIP]` `[RULE]` 日志前缀 + Prometheus 指标

## 配置速查

> 完整配置在 `config/snapshot_recorder.yaml`。紧急覆盖用 `SNAP_` 环境变量。

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `disk.high_watermark_pct` | 80 | 暂停录制水位 |
| `disk.low_watermark_pct` | 60 | 恢复录制水位 |
| `disk.cleanup_session_dirs` | **false** | 自动删 session？默认关 |
| `queue.max_upload_queue` | 10 | >此值节流触发 |
| `queue.critical_upload_queue` | 20 | >此值丢弃低优先级 |
| `clip.rule_cooldown_s` | 10.0 | 同 rule 去重间隔 |

## 常用命令

```bash
# 管道状态一键检查
echo "Disk: $(df -h /mnt/disk_main | awk 'NR==2{print $5}')" && \
echo "Queue: $(ls /mnt/disk_main/events/.upload_queue/job_*.json 2>/dev/null | wc -l) jobs" && \
echo "Events: $(ls -d /mnt/disk_main/events/event_* 2>/dev/null | wc -l) dirs" && \
echo "Rules: $(ros2 topic echo /zeron/cloud/rules --once 2>/dev/null | python3 -c "import sys,json;print(len(json.load(sys.stdin)['rules']))") active"

# 查看日志
ros2 topic echo /rosout | grep -E "\[TRIGGER\]|\[UPLOAD\]|\[DiskManager\]|\[CLIP\]"

# 紧急降低水位
export SNAP_DISK_HIGH_WATERMARK_PCT=70
pkill -f disk_manager.py && python3 /path/to/disk_manager.py &

# 启动 recorder
ros2 launch snapshot_recorder recorder.launch.py --ros-args -p session_parent_dir:=/mnt/disk_main
```

## 参考文档

- [LOOP.md](LOOP.md) — 4 个并发 loop 的运行态 + 碰撞检测 + Intent Debt Map
- [failure-modes.md](references/failure-modes.md) — 6 个已知故障模式 + 一键检测 + 修复方案
- [ops-runbook.md](references/ops-runbook.md) — 日常巡检 + 应急响应 + 配置调优 + Run Log & Budget
- [pipeline-architecture.md](references/pipeline-architecture.md) — 系统边界 + LOOP 反模式对照 + 升级路径
- [loop-constraints.md](references/loop-constraints.md) — 机器可读约束（Pre-Flight + 重试上限 + 磁盘预算 + denylist + 紧急覆盖）
