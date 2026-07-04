# Data Loop Failure Modes

> 每次线上问题修复后更新。每个 FM 必须包含：症状 → 一键检测 → 修复步骤。

## FM-001: 磁盘写满

| 严重度 | P0 — 录制停止，触发被拒 |
|--------|------------------------|
| **根因** | `disk_manager` 只扫描 `**/*.mcap`，ros2 bag session 目录（含 `.db3`）不可见 |
| **触发** | `cleanup_session_dirs: false` + 拔盘离线上传未及时取走 |
| **相关** | `disk_manager.py`, `snapshot_recorder.yaml` |

**一键检测**:
```bash
df -h /mnt/disk_main | awk 'NR==2{print $5}'   # > 95%？ → 紧急
du -sh /mnt/disk_main/ZSD-* 2>/dev/null | sort -rh | head -5
```

**修复**:
```bash
# 1. 暂停录制
kill -STOP $(cat /tmp/record_all.pid)
# 2. 清理 >2 天旧 session
find /mnt/disk_main -maxdepth 2 -name "metadata.yaml" -mmin +2880 -exec dirname {} \; | xargs rm -rf
# 3. 恢复录制
kill -CONT $(cat /tmp/record_all.pid)
```

**预防**: 开启 `cleanup_session_dirs: true` 或定期手动清理。

---

## FM-002: trigger_id 为空

| 严重度 | P2 — 数据上传但无法关联 trigger |
|--------|-------------------------------|
| **根因** | 云端 deactivate 后 `metadata.trigger_id` 设为 `""`。`dict.get(k, d)` 在 key 存在但值为 `""` 时不 fallthrough |
| **触发** | rule active→not_active 过渡窗口：API 仍返回 rule 但 trigger_id 已清空 |
| **相关** | `tag_rules_fetcher_node.py:139`, `rule_evaluator_node.py:217` |
| **修复日期** | 2026-07-03 |

**一键检测**:
```bash
for f in $(ls -t /mnt/disk_main/events/event_*/event_meta.json 2>/dev/null | head -5); do
    echo "$f: $(python3 -c "import json;t=json.load(open('$f')).get('triggers',[]);print([x.get('id','?') for x in t])")"
done
```

**状态**: ✅ 已修复 — `or` fallthrough + 双重过滤。新代码不会再产生空 trigger_id。

---

## FM-003: 上传队列积压

| 严重度 | P1 — event 堆积，磁盘压力增大 |
|--------|------------------------------|
| **根因** | 云端不可达 / 带宽不足 / token 过期 / 超时 |
| **触发** | 网络断开、云端 down、token 过期 |
| **相关** | `upload_handler.py`, `api_client.py` |

**一键检测**:
```bash
echo "Queue: $(ls /mnt/disk_main/events/.upload_queue/job_*.json 2>/dev/null | wc -l) pending"
curl -s -o /dev/null -w "Cloud: HTTP %{http_code}\n" http://10.8.250.23:32486/api/v1/vehicle
```

**缓解**:
```bash
# 队列 > 20 → 暂停录制
kill -STOP $(cat /tmp/record_all.pid)
# 云端恢复后
kill -CONT $(cat /tmp/record_all.pid)
```

**待改进**: 需要 circuit breaker，避免无限重试。

---

## FM-004: trigger 不触发

| 严重度 | P2 — 该采集的事件未采集 |
|--------|------------------------|
| **根因** | rule 条件不满足 / topic 无数据 / rule 未加载 / cooldown 期内 |
| **相关** | `tag_rules_fetcher_node.py`, `rule_evaluator_node.py` |

**一键检测**:
```bash
# Rule 是否下发？
ros2 topic echo /zeron/cloud/rules --once 2>/dev/null | python3 -c "import sys,json;[print(r['id']) for r in json.load(sys.stdin)['rules']]"
# 有没有触发？
ros2 topic echo /zeron/vehicle/trigger --once 2>/dev/null
```

---

## FM-005: clip 失败

| 严重度 | P1 — event 目录创建但无 mcap |
|--------|----------------------------|
| **根因** | `record_all_root` 路径错 / session 不存在 / 时间窗口不匹配 |
| **相关** | `record_all_clipper.py`, `snapshot_recorder_node.cpp` |

**一键检测**:
```bash
# 检查 mcap 源文件
ls /mnt/disk_main/*/all/all_*.mcap 2>/dev/null | head -3 || echo "NO MCAP SOURCES"
# 列出空的 event 目录
for d in /mnt/disk_main/events/event_*/; do
    ls "$d"*.mcap >/dev/null 2>&1 || echo "EMPTY: $(basename $d)"
done
# 检查最近的 clip 错误
grep "Failed to create microlog" /var/log/aura/snapshot_recorder.log | tail -3
```

**验证修复**: 手动触发 test rule → 确认 event 目录下有 `microlog.mcap` 且 > 0 bytes。

---

## FM-006: clipper 覆写丢失 triggers

| 严重度 | P2 — 缺 trigger 元数据，mcap 正常 |
|--------|--------------------------------|
| **根因** | clipper `meta = {}` 在 `event_meta.json` 未就绪时初始化为空，`meta.update()` 不含 `triggers` |
| **触发** | 极端竞态：C++ 创建目录但未刷盘时 clipper 已运行 |
| **相关** | `record_all_clipper.py:570-595` |
| **状态** | ⚠️ 待修复 |

**一键检测**:
```bash
# 检查最近 5 个 event 的 triggers 完整性
for f in $(ls -t /mnt/disk_main/events/event_*/event_meta.json 2>/dev/null | head -5); do
    has_triggers=$(python3 -c "import json;d=json.load(open('$f'));print('OK' if d.get('triggers') else 'MISSING')")
    echo "$(basename $(dirname $f)): triggers=$has_triggers"
done
```

**验证修复**: 检查 `record_all_clipper.py` 的 `meta.update()` 之后 `triggers` 键仍存在。

---

## 故障热力图

```
                    频率 ↑
                    │
         FM-001     │     FM-003
         (磁盘满)    │     (上传积压)
                    │
    ────────────────┼────────────────→ 严重度
                    │
         FM-002     │     FM-005    FM-006
      (trigger_id空) │     (clip失败)  (triggers丢失)
                    │
         FM-004     │
       (trigger不触发)│
```
