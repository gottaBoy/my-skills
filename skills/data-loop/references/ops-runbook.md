# Data Loop Ops Runbook

> 所有命令可直接复制执行。`BAG_FOLDER=/mnt/disk_main`。

## 健康检查（一键）

```bash
# 粘贴即运行
echo "=== Data Loop Health @ $(date) ==="
echo "Disk:   $(df -h /mnt/disk_main | awk 'NR==2{print $5 " used, " $4 " free"}')"
echo "Queue:  $(ls /mnt/disk_main/events/.upload_queue/job_*.json 2>/dev/null | wc -l) pending uploads"
echo "Events: $(ls -d /mnt/disk_main/events/event_* 2>/dev/null | wc -l) event dirs"
echo "Rules:  $(ros2 topic echo /zeron/cloud/rules --once 2>/dev/null | python3 -c "import sys,json;print(len(json.load(sys.stdin)['rules']))") active"
echo "DM:     $(ps aux | grep -c '[d]isk_manager.py') running"
echo "Record: $(ps aux | grep -c '[r]os2 bag record') running"
echo "Triggers today: $(grep -c '\[TRIGGER\]' /var/log/aura/snapshot_recorder.log 2>/dev/null || echo 0)"
echo "Uploaded today: $(grep -c 'UPLOADED' /var/log/aura/upload_handler.log 2>/dev/null || echo 0)"

# 磁盘消耗速率（GB/h）— 对比两次 df 输出
FREE1=$(df /mnt/disk_main | awk 'NR==2{print $4}')
sleep 3600
FREE2=$(df /mnt/disk_main | awk 'NR==2{print $4}')
echo "Consumption rate: $(python3 -c "print(f'{($FREE1-$FREE2)/1024/1024:.1f} GB/h')")"

# 预估磁盘满时间
USED=$(df /mnt/disk_main | awk 'NR==2{print $3}')
TOTAL=$(df /mnt/disk_main | awk 'NR==2{print $2}')
echo "Estimated full in: $(python3 -c "h=($TOTAL-$USED)/(($FREE1-$FREE2) or 1);print(f'{h:.0f}h' if h>0 else 'N/A')")"
```

## 应急响应

### 🚨 磁盘满

| Step | 命令 | 说明 |
|------|------|------|
| 1. 确认 | `df -h /mnt/disk_main; du -sh /mnt/disk_main/* \| sort -rh \| head -5` | 看谁占空间 |
| 2. 暂停 | `kill -STOP $(cat /tmp/record_all.pid)` | 停止产生新数据 |
| 3. 清旧 session | `find /mnt/disk_main -maxdepth 2 -name "metadata.yaml" -mmin +2880 -exec dirname {} \; \| xargs rm -rf` | >48h 的 rosbag session |
| 4. 清已上传 event | 见下方脚本 | job 不在 queue 的 event |
| 5. 确认恢复 | `df -h /mnt/disk_main` | 水位是否降了 |
| 6. 恢复录制 | `kill -CONT $(cat /tmp/record_all.pid)` | 仅水位 < low_watermark |

**清已上传 event 脚本**:
```bash
python3 -c "
import os, glob, shutil, json
events = '/mnt/disk_main/events'
queue_ids = {os.path.basename(os.path.dirname(json.load(open(j))['meta_path']))
             for j in glob.glob(f'{events}/.upload_queue/job_*.json')
             if os.path.exists(j)}
for d in os.listdir(events):
    if d.startswith('.') or d in queue_ids: continue
    p = os.path.join(events, d)
    if os.path.isdir(p):
        shutil.rmtree(p)
        print(f'Deleted {d}')
"
```

### 🚨 上传中断

```bash
# 1. 测试连通性
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://10.8.250.23:32486/api/v1/vehicle

# 2. 队列深度
ls /mnt/disk_main/events/.upload_queue/job_*.json 2>/dev/null | wc -l

# 3. 最新错误
grep -E "failed|error|timeout" /var/log/aura/upload_handler.log | tail -10

# 4. 如果云端不可用 → 暂停录制，减少积压
kill -STOP $(cat /tmp/record_all.pid)

# 5. 云端恢复 → 恢复录制
kill -CONT $(cat /tmp/record_all.pid)
```

### 🚨 trigger_id 为空

```bash
# 确诊
for f in $(ls -t /mnt/disk_main/events/event_*/event_meta.json 2>/dev/null | head -5); do
    echo "$(basename $(dirname $f)): $(python3 -c "import json;t=json.load(open('$f')).get('triggers',[]);print([x.get('id','EMPTY') for x in t])")"
done

# 如果确认是 deactivate 过渡窗口 → 重启拉取最新 rules
pkill -f tag_rules_fetcher_node
```

## 配置调优

### 磁盘自适应（自动，无需手动）

| 磁盘 | max_age_hours | max_total_gb |
|------|--------------|-------------|
| 512G | 2h | 450 GB |
| 1T | 4h | 950 GB |
| 2T | 8h | 1800 GB |
| 3T+ | 12h | 3060 GB |

### 紧急覆盖

```bash
export SNAP_DISK_HIGH_WATERMARK_PCT=70   # 降低水位
export SNAP_DISK_MAX_TOTAL_GB=2000       # 降低容量上限
pkill -f disk_manager.py && python3 /path/to/disk_manager.py &
```

### 上传性能

```bash
# 大文件分片上传
export UPLOAD_MULTIPART_THRESHOLD_MB=100
export UPLOAD_MULTIPART_CHUNK_SIZE_MB=50
export UPLOAD_MAX_CONCURRENT_PARTS=4

# 弱网降低超时
export UPLOAD_TIMEOUT_MAX_S=600
```

## 监控告警

```yaml
# prometheus-alerts.yml
groups:
  - name: data_loop
    rules:
      - alert: DiskNearFull
        expr: snapshot_recorder_disk_usage_pct > 85
        for: 5m
        labels: {severity: critical}
      - alert: UploadBacklog
        expr: snapshot_recorder_queue_depth > 15
        for: 30m
        labels: {severity: warning}
      - alert: RecordingPaused
        expr: snapshot_recorder_recording_paused == 1
        for: 1h
        labels: {severity: warning}
```

## Run Log & Budget

> Run log schema 定义见 [loop-constraints.md](loop-constraints.md) §6。

### 查看今日运行统计

```bash
# disk_manager 清理次数
grep -c "Cleaned uploaded event" /var/log/aura/disk_manager.log 2>/dev/null || echo 0

# upload 成功/失败/丢弃
echo "Uploaded:  $(grep -c 'UPLOADED' /var/log/aura/upload_handler.log 2>/dev/null || echo 0)"
echo "Failed:    $(grep -c 'UPLOAD_FAILED' /var/log/aura/upload_handler.log 2>/dev/null || echo 0)"
echo "Discarded: $(grep -c 'DISCARDED' /var/log/aura/upload_handler.log 2>/dev/null || echo 0)"

# 磁盘趋势（需两次采样，间隔 > 1h）
tail -1 /var/log/aura/disk_manager.log 2>/dev/null | grep -oP 'Disk: \K[0-9.]+'
```

### Budget 状态

```bash
# 磁盘预算
DISK_PCT=$(df /mnt/disk_main | awk 'NR==2{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 95 ]; then echo "CRITICAL: disk > 95%"; 
elif [ "$DISK_PCT" -gt 80 ]; then echo "WARNING: disk > 80% (high watermark)";
else echo "OK: disk ${DISK_PCT}%"; fi

# 上传预算
QUEUE=$(ls /mnt/disk_main/events/.upload_queue/job_*.json 2>/dev/null | wc -l)
if [ "$QUEUE" -gt 20 ]; then echo "CRITICAL: queue $QUEUE > 20";
elif [ "$QUEUE" -gt 10 ]; then echo "WARNING: queue $QUEUE > 10 (throttle)";
else echo "OK: queue $QUEUE"; fi

# 触发率（今日）
TRIGGERS=$(grep -c '\[TRIGGER\]' /var/log/aura/snapshot_recorder.log 2>/dev/null || echo 0)
echo "Triggers today: $TRIGGERS"
```
