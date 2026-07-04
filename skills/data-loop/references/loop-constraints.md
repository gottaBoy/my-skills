# Data Loop — Machine-Readable Constraints

> 每次 loop 运行前读取此文件，强制执行所有约束。
> 基于 [loop-engineering safety.md](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/safety.md)。

## 0. Pre-Flight Checklist（变更前必检）

> 每次修改数据闭环代码后、提交前，逐项确认。

- [ ] 管道健康：`df -h /mnt/disk_main | awk 'NR==2{print $5}'` < 90%
- [ ] 上传队列：< 10 pending（`ls .upload_queue/job_*.json | wc -l`）
- [ ] event_meta.json 完整性：`triggers` 数组存在且非空
- [ ] 日志无异常：`grep -c "ERROR" /var/log/aura/snapshot_recorder.log` 未增长
- [ ] 已更新 failure-modes.md（如有新故障模式）
- [ ] 已更新 SKILL.md §关键文件（如有新组件）
- [ ] 已更新 loop-constraints.md（如有新约束）
- [ ] `cleanup_session_dirs` 保持 `false`（除非明确需要）

## 1. Attempt Caps（重试上限）

| 操作 | 最大重试 | 超限行为 |
|------|---------|---------|
| upload 单个 event | 3 次 | → DISCARDED，记录到 run log |
| clip 重试 | 1 次 | → 标记 event 目录为空，disk_manager 清理 |
| disk_manager 清理周期 | 120s 固定 | 每个周期内操作不可重试 > 1 次 |
| PATCH status 调用 | 2 次 | → 标记 UPLOAD_FAILED |

**规则**: 任何操作重试超过上限 → 进入 `Escalation` 状态 → 暂停该 event 处理 → 写 run log → 不阻塞后续 event。

## 2. Disk Budget（磁盘预算）

```
- 总磁盘: 自动检测
- 高水位: 80% (暂停录制)
- 低水位: 60% (恢复录制)
- 紧急水位: 95% (暂停所有写入 + 告警)
- Session 目录: 默认不自动删除 (cleanup_session_dirs: false)
```

**规则**: 磁盘 > 95% → 暂停 ros2 bag + 拒绝所有新 trigger + 发送 Prometheus critical alert。

## 3. Upload Budget（上传预算）

```
- 队列上限: 20 个 job (critical_upload_queue)
- 节流线: 10 个 job (max_upload_queue)
- 单 event 超时: 1800s (30 min)
- 最小上传速度: 0.3 MB/s (大文件)
```

**规则**: 队列 > 20 → 丢弃 MEDIUM/LOW 优先级 event，保留 CRITICAL/HIGH。

## 4. Denylist（禁止操作）

```
磁盘操作:
  - 禁止: rm -rf /mnt/disk_main (无确认)
  - 禁止: 删除 .upload_queue/ 目录
  - 禁止: 删除正在上传的 event 目录

API 操作:
  - 禁止: POST /tasks 时发送空 triggers 数组
  - 禁止: event_meta.json 缺少 vehicle_id / vehicle_vin

录制操作:
  - 禁止: ros2 bag record 写入超过磁盘 98%
  - 禁止: 同时运行多个 recorder 实例
```

## 5. Required Human Gates（必须人工确认）

```
- Session 目录批量删除 (> 1 个)
- 修改 snapshot_recorder.yaml 中的 high_watermark 低于 50%
- 手动丢弃 CRITICAL 优先级 event
- 恢复已暂停的录制 (ros2 bag SIGCONT)
- 修改 DSL rule 的 clip 窗口 (pre_s / post_s)
```

## 6. Run Log Schema（运行日志格式）

```json
{
  "run_id": "2026-07-04T10:15:00Z",
  "component": "disk_manager",
  "duration_s": 2.3,
  "disk_pct": 72.5,
  "events_cleaned": 3,
  "sessions_cleaned": 0,
  "queue_depth": 5,
  "recording_paused": false,
  "escalations": 0
}
```

## 7. Escalation Protocol

| 条件 | 动作 |
|------|------|
| 磁盘 > 95% 持续 5min | Prometheus critical → 人工介入 |
| 队列 > 20 持续 30min | Prometheus warning → 检查网络 |
| upload 失败 3 次同一 event | → DISCARDED → 写 run log |
| 录制暂停 > 1h | Prometheus warning → 人工检查 |
| 连续 2h 无 trigger | Prometheus info → 检查 rules |

## 8. Emergency Override（紧急覆盖条件）

以下情况允许绕过约束，但必须记录到 run log：

| 条件 | 允许操作 | 记录要求 |
|------|---------|---------|
| 磁盘 > 98% 且无已上传 event 可清理 | 可删除 < 24h 的 session 目录 | 写 run log + Prometheus annotation |
| 云端不可达 > 2h | 可临时禁用上传，event 仅写磁盘 | 标记 `upload_deferred: true` |
| 录制因磁盘满暂停 > 4h | 可降低 high_watermark 到 95% | 记录原值和覆盖值 |
| CRITICAL 优先级 event 积压 > 50 | 可临时丢弃 MEDIUM 优先级 | 记录丢弃数量 |
