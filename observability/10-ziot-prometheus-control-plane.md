# ziot Prometheus 与控制面埋点方案

更新时间：`2026-08-29`

状态：`implemented/unverified`

本文记录当前 `ziot` 云端代码改动、Prometheus 暴露方式，以及它和
ZLMediaKit/DeepFlow/DataBuff 的关联边界。`operator` 不在本文范围内。

## 1. 当前运行基线

现场 Java 进程为：

```text
java -Xms512m -Xmx2g -XX:+UseG1GC ... -jar application.jar
```

当前代码已经存在 `ParallelDrivingLatencyMetrics`，覆盖：

```text
remotejoystick 平台延迟
latest-only mailbox 合并和丢弃
设备发送完成/错误/取消耗时
WebSocket 会话、EventBus、队列和发送延迟
```

原有缺口是 standalone 没有明确启用 Actuator/Prometheus 暴露，且
`MeterRegistryManager` 的 JetLinks 时序 registry 不等价于
`/actuator/prometheus`。

## 1.1 2026-08-29 现场核对结论

用户提供的现场信息确认存在如下 Java 启动形态：

```text
java -Xms512m -Xmx2g ... -jar application.jar
```

用户随后提供的 `/actuator/prometheus` 返回结果已经确认当前运行进程能够暴露
Prometheus 指标，并且已经注册自定义 `parallel_driving_*` 指标。

当前结论：

| 范围 | 状态 |
|---|---|
| `ParallelDrivingLatencyMetrics` 源码 | `implemented` |
| Actuator/Prometheus 依赖和配置 | `implemented` |
| 运行进程是否使用包含最新埋点的构建 | `verified`（以已提供指标输出为运行证据） |
| `/actuator/prometheus` 是否可访问 | `verified` |
| 自定义 `parallel_driving_*` 指标是否注册 | `verified` |
| 控制操作后指标是否增长 | `unverified` |
| ziot -> Collector -> DataBuff | `unverified` |
| 原有 JetLinks 时序链路未受影响 | `unverified` |

因此，ziot 当前不能称为“已完全埋点并验收完成”；准确表述是：
**ziot 指标代码、暴露配置和 Prometheus 运行端点已确认；实际业务操作增长以及
Collector/DataBuff 采集闭环仍待验证。**

## 1.2 当前阶段：ziot 进入后到车端

本阶段暂不依赖驾驶仓发送埋点，只观察指令进入 ziot 之后的下行链路：

```text
ziot cloud_receive
  -> latest-only mailbox enter/leave
  -> device send start/completion
  -> vehicle TCP body receive
  -> decrypt/parse/dispatch
  -> remotejoystick handler
  -> ROS publish
```

云端可用的指标和日志主要回答云端是否接收、合并、丢弃、在途过慢或发送完成；
车端结构化日志回答消息是否到达，以及 body 接收、解密、解析、handler 和
ROS publish 各阶段是否变慢。`socket.write` 或设备发送器完成只表示云端写调用
完成，不表示车端已经收到完整消息。

当前阶段的单条消息关联键为：

```text
messageId + source_seq + correlationId
```

DeepFlow/eBPF Agent 只补充 TCP/进程/容器层事实，例如 RTT、重传、RTO、socket
队列、连接代际和调度；它不替代 ziot 或车端业务事件，也不能单独确认某条指令
已经执行。

## 2. 已落地的 ziot 改动

### 2.1 依赖和端点

`jetlinks-standalone/pom.xml` 已增加：

```text
spring-boot-starter-actuator
micrometer-registry-prometheus
```

`application.yml` 已增加可配置项：

```yaml
management:
  server:
    address: ${MANAGEMENT_SERVER_ADDRESS:127.0.0.1}
    # 管理端口必须与业务端口分离，避免配置 management.server.address 时因同端口启动失败。
    port: ${MANAGEMENT_SERVER_PORT:8850}
  endpoints:
    web:
      exposure:
        include: ${MANAGEMENT_ENDPOINTS_WEB_EXPOSURE:health,info,prometheus}
  metrics:
    export:
      prometheus:
        enabled: ${MANAGEMENT_METRICS_EXPORT_PROMETHEUS_ENABLED:false}
```

默认关闭 Prometheus exporter，避免未经过网络和安全评审就暴露指标。目标环境
启用时建议单独使用管理端口：

```bash
export MANAGEMENT_METRICS_EXPORT_PROMETHEUS_ENABLED=true
export MANAGEMENT_SERVER_ADDRESS=0.0.0.0
export MANAGEMENT_SERVER_PORT=8850
```

然后由 Prometheus 或 OTel Collector 抓取：

```text
http://<ziot-host>:8850/actuator/prometheus
```

管理端口必须由防火墙、安全组或内网 ACL 限制。不要把该端点直接暴露到公网。

### 2.2 原有时序行为不替换

本次没有关闭或替换 JetLinks 的 `TimeSeriesMeterRegistry`。Prometheus 是额外的
registry/导出面，只有设置
`MANAGEMENT_METRICS_EXPORT_PROMETHEUS_ENABLED=true` 时才启用。

上线前要确认：

```text
原有 device_metrics/JetLinks 时序数据仍正常写入
Prometheus endpoint 返回 200
应用启动没有 MeterRegistry bean 冲突
指标没有因为管理端点关闭而影响业务链
```

## 3. 控制面指标

新增指标均使用固定低基数标签：

```text
parallel_driving_control_requests_total
  operation=bind|unbind|takeover|release|control
  result=success|failure|cancel|other

parallel_driving_control_duration_seconds
  operation=bind|unbind|takeover|release|control
  result=success|failure|cancel|other

parallel_driving_control_stage_duration_seconds
  operation=takeover|release|control
  stage=redis_lock|device_lookup|remove_old_sessions|delete_stale_session|
        create_session|create_room|notify_devices|update_session_state|
        wait_active|close_room|delete_session|session_room_lookup|forward
  result=success|failure|cancel|other

parallel_driving_control_redis_lock_total
  operation=takeover
  result=acquired|busy
```

Micrometer 会把点号名称转换为 Prometheus 的下划线名称。真实名称以 endpoint
输出为准。

以下字段不作为 Prometheus label：

```text
vehicleDeviceId
cockpitDeviceId
messageId
sessionId
functionId
stream
```

这些值如果需要排障，应进入限频结构化日志或抽样事件；不应创建无界时间序列。

### 3.1 响应式计时边界

控制面使用 `Mono.defer`/`doFinally`：

```text
开始时间：响应式链真正订阅时
本机耗时：System.nanoTime()
结束状态：success/failure/cancel/other
```

这样不会把创建冷 `Mono` 的时间误当作业务执行时间，也不会把 wall clock
调整造成的时间跳变写入耗时指标。

### 3.2 对 takeover 400 的观测

此前出现的：

```text
io.lettuce.core.output.ValueOutput does not support set(long)
```

属于 Redis/Reactive Redis 控制面兼容或调用链问题，不是媒体链路问题。新增指标
可以确认请求是否到达 `redis_lock` 阶段，但不会吞掉或改写该异常。

应同时查看：

```text
parallel_driving_control_requests_total{operation="takeover",result="failure"}
parallel_driving_control_stage_duration_seconds{operation="takeover",stage="redis_lock",...}
parallel_driving_control_redis_lock_total
```

如果 Redis 锁阶段失败，继续检查完整 ziot 异常堆栈和 Redis 客户端依赖版本；
不能用“埋点成功”作为 takeover 成功的判断。

## 4. 采集到 DeepFlow/DataBuff

推荐链路：

```text
ziot /actuator/prometheus
  -> OTel Collector prometheus receiver
  -> memory_limiter + batch
  -> DataBuff OTLP metrics
```

示例：

```yaml
receivers:
  prometheus/ziot:
    config:
      scrape_configs:
        - job_name: ziot
          scrape_interval: 5s
          metrics_path: /actuator/prometheus
          static_configs:
            - targets: ["ziot-host:8850"]

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
  batch:
    timeout: 1s
    send_batch_size: 512

exporters:
  otlphttp/databuff:
    endpoint: http://<databuff-host>:4318
    compression: gzip
    retry_on_failure:
      enabled: true
    sending_queue:
      enabled: true
      queue_size: 2048

service:
  pipelines:
    metrics/ziot:
      receivers: [prometheus/ziot]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/databuff]
```

真实环境必须补上 DataBuff 的 TLS、认证、租户 header、证书和网络 ACL。Collector
不可达时，ziot 的控制、远控消息、WebSocket 和媒体相关业务必须继续运行。

DeepFlow Agent 不负责读取 Java heap 或直接解析 Micrometer。DeepFlow 负责宿主机
网络、进程、容器、TCP/UDP 和服务拓扑；ziot 指标通过 Prometheus receiver 进入
Collector。两者使用以下资源字段进行关联：

```text
service.name=ziot
service.instance.id=<stable ziot node id>
deployment.environment=<env>
host.name=<approved host id>
```

## 5. ZLMediaKit 侧落地顺序

ZLMediaKit 当前部署：

```text
zlmediakit_polaris-media_1
  harbor.intra.zeron.ai/library/zlmediakit:2025-12-17

zlmediakit_zlmexporter_1
  harbor.intra.zeron.ai/library/zlmexporter:2025-09-11
  host port 9091
```

现场按以下顺序执行：

1. 检查容器的 network mode、PID mode、配置挂载、ZLM API secret 来源和真实端口用途。
2. 访问 `http://127.0.0.1:9091/metrics`，记录 exporter 的实际指标名称和 labels。
3. 通过 `getApiList` 确认该 ZLM 镜像实际支持的 API，再低频采集流状态、线程负载和会话。
4. 在 ZLM 宿主机部署 DeepFlow Agent，观察容器、veth、TCP/UDP、RTT、重传、reset、
   socket queue、网卡 drop/error 和进程资源。
5. 让 DeepFlow Server 只选择性导出 ZLM 相关 L7 flow log 到 Collector；
   Agent 原始 eBPF buffer 不直接写入 DataBuff。
6. 由 Collector 分开接收 ziot、ZLM exporter 和选定 DeepFlow 事件，再批量上传 DataBuff。

ZLMediaKit 媒体数据面不增加逐 RTP 日志、不修改 RTP 包、不等待 Collector。

## 6. 验收清单

### ziot

```bash
curl -fsS http://127.0.0.1:8849/actuator/health
curl -fsS http://127.0.0.1:8850/actuator/prometheus \
  | rg 'parallel_driving_(control|remotejoystick|status_websocket)'
```

验收条件：

```text
endpoint 200
control requests/duration 在 takeover、release、bind、unbind、control 后增长
Redis busy 和 failure 能区分
车辆/驾驶舱/消息 ID 未出现在 metric label
Collector/DataBuff 不可用时业务仍可用
```

### ZLMediaKit/DeepFlow

```bash
curl -fsS http://127.0.0.1:9091/metrics
docker inspect zlmediakit_polaris-media_1
docker inspect zlmediakit_zlmexporter_1
```

验收条件：

```text
exporter 能访问 ZLM API
ZLM 输入/输出流、FPS、码率和会话可查询
DeepFlow 能把网络流量归属到 ZLM 容器
车端上行与浏览器 WebRTC 下行能按五元组/容器/时间窗区分
选定数据能经过 Collector 到达 DataBuff
```

未验证项必须保留为 `unverified`，不能仅凭代码或配置改动标记为已部署。
