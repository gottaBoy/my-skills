---
name: ops-playbook
description: 'Operations playbook for incident response, monitoring setup, log analysis, capacity planning, and disaster recovery. Use when: setting up monitoring/alerting, responding to production incidents, doing post-mortem analysis, planning capacity. Tools: read-only + terminal for diagnostic commands.'
---

# Ops Playbook — 运维排障手册

## When to Use
- 生产环境出现异常需要快速响应
- 设置监控和告警规则
- 日志分析和问题定位
- 容量规划和灾备方案

---

## 1. 故障响应流程 (Incident Response)

```
发现告警 → 确认影响范围 → 止损（回滚/降级/限流）→ 定位根因 → 修复 → 复盘
  │            │               │                    │          │        │
  └─ 5min      └─ 10min        └─ 15min             └─ 调查     └─ 修复   └─ 24h后
```

### 故障级别

| 级别 | 定义 | 响应时间 | 升级条件 |
|------|------|---------|---------|
| **P0 紧急** | 核心功能不可用、数据丢失 | 15 min | 全员告警 |
| **P1 严重** | 部分用户不可用、性能严重下降 | 30 min | 通知 Tech Lead |
| **P2 一般** | 非核心功能异常 | 2 h | 加入 sprint |
| **P3 轻微** | UI 小问题、不影响使用 | 下一迭代 | 无需升级 |

---

## 2. 监控指标体系

### 黄金指标 (Four Golden Signals)

| 指标 | 含义 | 告警阈值建议 | 工具 |
|------|------|------------|------|
| **延迟 (Latency)** | P95 响应时间 | > 500ms (API) | Prometheus + Grafana |
| **流量 (Traffic)** | QPS / RPM | 偏离基线 ±50% | Nginx/ALB metrics |
| **错误 (Errors)** | 4xx/5xx 比率 | > 5% | Sentry / ELK |
| **饱和度 (Saturation)** | CPU/内存/连接数 | > 80% | Prometheus |

### 应用级指标

```yaml
# 关键业务指标
- 登录成功率
- 任务提交成功率
- 数据库连接池使用率
- 消息队列积压数量
- API 调用耗时分布 (P50/P95/P99)
```

### 告警规则模板

```yaml
# prometheus-alerts.yml
groups:
  - name: application
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High 5xx error rate: {{ $value }}"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 latency > 500ms"

      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"
```

---

## 3. 日志分析

### 日志级别使用规范

```python
# ✅ 正确使用日志级别
logger.debug("详细调试信息，生产环境关闭")
logger.info("业务流程关键节点：事件处理完成, event_id={}", event_id)
logger.warning("预期内的异常：重试第3次, error={}", err)
logger.error("非预期错误：数据库连接失败", exc_info=True)  # 带堆栈
logger.critical("系统级灾难：内存不足", exc_info=True)
```

### 日志搜索模式

```bash
# 统计错误频率
grep -c "ERROR" /var/log/app.log | sort | uniq -c | sort -rn | head -20

# 追踪单个请求（通过 trace_id）
grep "trace_id=abc123" /var/log/app.log

# 查看最近 100 条错误前后的上下文
grep -B 5 -A 10 "ERROR" /var/log/app.log | tail -200

# 统计 API 响应时间分布
awk '{print $NF}' /var/log/access.log | sort -n | awk '{all[NR]=$0} END{print "P50:", all[int(NR*0.5)]; print "P95:", all[int(NR*0.95)]; print "P99:", all[int(NR*0.99)]}'
```

---

## 4. 容量规划

### 资源预估公式

```
QPS × (单个请求 CPU 时间 + IO 等待) × 安全系数(1.5~2.0) = 所需 CPU 核心数
QPS × 平均请求内存占用 × 安全系数 = 所需内存
并发连接数 / 单实例最大连接 = 所需实例数
```

### 扩容信号

| 信号 | 阈值 | 动作 |
|------|------|------|
| CPU 持续 > 70% | 15 min | 水平扩容 |
| 内存持续 > 80% | 15 min | 扩容 / 查内存泄漏 |
| DB 连接池耗尽 | 即时 | 扩容连接池 / 加实例 |
| 消息队列积压 > 1000 | 10 min | 增加消费者 |

---

## 5. 灾备方案

### 备份策略

| 数据 | 频率 | 保留期 | 恢复时间目标 (RTO) |
|------|------|--------|-------------------|
| MySQL 全量 | 每天 | 30 天 | < 4 h |
| MySQL 增量 (binlog) | 实时 | 7 天 | < 1 h |
| 文件存储 (S3/OSS) | 实时同步 | 永久 | 秒级 |
| 配置文件 | 每次变更 | 永久 | 分钟级 |

### 灾难恢复 Checklist

- [ ] 数据库备份可用且最新
- [ ] 备份恢复已在测试环境验证过
- [ ] 服务启动依赖清单（DB → Redis → 应用）
- [ ] 应急预案文档（谁负责什么）
- [ ] 回滚到上一个稳定版本的步骤明确

---

## 6. 诊断命令速查

```bash
# 容器诊断
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"  # 容器列表
docker stats --no-stream  # 实时资源使用
docker logs <container> --tail 100 -f  # 跟踪日志

# 网络诊断
curl -o /dev/null -s -w "%{http_code} %{time_total}s\n" http://localhost:5000/health
ss -tlnp  # 监听端口
netstat -an | grep ESTABLISHED | wc -l  # 活跃连接数

# 系统诊断
free -h  # 内存使用
df -h    # 磁盘使用
top -b -n 1 | head -20  # CPU 使用
```

---

## 7. 复盘模板 (Post-Mortem)

```markdown
# 故障复盘: [标题]

## 时间线
- [时间] 告警触发
- [时间] 确认影响范围
- [时间] 执行止损操作
- [时间] 服务恢复
- [时间] 根因确认

## 影响范围
- 影响时长: [N 分钟]
- 影响用户: [N 人 / N%]
- 影响功能: [描述]

## 根因分析 (5 Whys)
1. 为什么服务挂了？→ ...
2. 为什么...？→ ...
3. 为什么...？→ ...
4. 为什么...？→ ...
5. 为什么...？→ 根因

## 改进措施
| 优先级 | 行动 | 负责人 | 期限 |
|--------|------|--------|------|
| P0 | ... | ... | ... |

## 预防措施
- [ ] 添加监控告警
- [ ] 增加测试覆盖
- [ ] 更新运维文档
```
