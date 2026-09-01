# ZLMediaKit Docker、eBPF/DeepFlow 与 DataBuff 监控方案

更新时间：`2026-08-29`

状态：`approved/unverified`

说明：本文基于用户提供的 Docker 部署信息和公开组件能力整理方案。当前没有目标主机的
`docker inspect`、ZLMediaKit API、`zlmexporter /metrics`、DeepFlow Server 或 DataBuff
现场结果，因此本文不是“已部署”或“已验收”结论。

## 1. 当前部署基线

```text
zlmexporter:
  image: harbor.intra.zeron.ai/library/zlmexporter:2025-09-11
  container: zlmediakit_zlmexporter_1
  host port: 9091/tcp

ZLMediaKit:
  image: harbor.intra.zeron.ai/library/zlmediakit:2025-12-17
  container: zlmediakit_polaris-media_1
  host ports:
    80/tcp
    8000/tcp+udp
    10001-10003/tcp+udp
```

端口的实际用途必须以容器配置和启动日志为准。不能只根据宿主机映射推断
`10001-10003` 一定是 WebRTC 媒体端口，也不能把 `8000` 自动当成单一协议端口。

当前已知事实：

| 组件 | 现状 | 可观测价值 |
|---|---|---|
| `zlmediakit_polaris-media_1` | 运行中，镜像为 `2025-12-17` | ZLM 进程、容器网络、HTTP API、媒体连接 |
| `zlmediakit_zlmexporter_1` | 运行中且 healthy，宿主机暴露 `9091` | ZLM 核心指标的 Prometheus 抓取入口 |
| DeepFlow Agent | 未提供现场状态 | eBPF、网络、进程、容器和服务拓扑 |
| OTel Collector | 未提供现场状态 | 统一接收、过滤、批处理和路由 |
| DataBuff | 未提供现场状态 | OTLP Trace/Metric/Log 接收和查询 |

## 1.1 2026-08-29 现场核对结论

用户提供的 `docker ps` 只能证明 ZLMediaKit 和 `zlmexporter` 容器正在运行，
其中 `zlmexporter` 状态为 `healthy`。这不能直接证明 exporter 指标内容完整，
也不能证明 DeepFlow Agent、OTel Collector 或 DataBuff 已部署并形成数据闭环。

当前结论：

| 范围 | 状态 |
|---|---|
| ZLMediaKit 容器运行 | `observed` |
| `zlmexporter` 容器运行且 healthy | `observed` |
| `zlmexporter /metrics` 实际内容 | `unverified` |
| exporter 访问 ZLMediaKit API | `unverified` |
| ZLMediaKit 宿主机 DeepFlow Agent | `unverified` |
| eBPF 对 ZLM 容器和媒体连接的可见性 | `unverified` |
| DeepFlow -> Collector -> DataBuff | `unverified` |
| 车端上行、ZLM 入站、WebRTC 下行三段关联 | `unverified` |

因此，ZLMediaKit 当前不能称为“已完全埋点并验收完成”；准确表述是：
**ZLMediaKit 和 exporter 基础已运行，旁路 eBPF/DeepFlow/DataBuff 监控方案已记录，
但现场部署和闭环验证尚未完成。**

## 2. 推荐拓扑

首期采用“DeepFlow 采集系统事实，ZLM exporter/API 补充应用语义，OTel Collector
统一发送，DataBuff 异步接收”的拓扑：

```text
                         ┌────────────────────────────┐
                         │ DeepFlow Server             │
                         │ eBPF flow / process / map   │
                         └─────────────┬──────────────┘
                                       │ selected L7 flow logs -> OTLP
                                       v
┌──────────────────────────────────────────────────────────────────────┐
│ Docker host                                                          │
│                                                                      │
│  DeepFlow Agent                                                       │
│  host network + host pid + BPF/debugfs + Docker metadata             │
│       │                                                              │
│       ├── TCP/UDP/RTT/retransmit/reset/socket/process/container       │
│       │                                                              │
│  zlmexporter :9091 ── Prometheus scrape ──┐                          │
│  ZLMediaKit :80/:8000/:10001-10003        ├─> OTel Collector          │
│  ZLM API / logs / hooks ───────────────────┘       │                  │
│                                                     │ OTLP            │
└─────────────────────────────────────────────────────┼────────────────┘
                                                      v
                                      ┌──────────────────────────────┐
                                      │ DataBuff Ingest :4317/:4318  │
                                      │ Trace / Metric / Log / AI    │
                                      └──────────────────────────────┘
```

这里有两类不同数据：

1. DeepFlow Agent 产生的 eBPF 网络和进程观测，先进入 DeepFlow Server。
2. ZLM exporter、ZLM API、结构化日志和业务事件进入 OTel Collector，再送入
   DataBuff；需要时再把 DeepFlow Server 选定的 L7 flow log 通过其
   OpenTelemetry exporter 送到 Collector/DataBuff。

不能把 DeepFlow Agent 的原始 eBPF buffer 直接挂接到视频进程，也不能假定所有
DeepFlow 内部指标都能自动出现在 DataBuff。DeepFlow Server 的 OTLP 导出范围、
字段映射和版本配置必须单独验收。

## 3. DeepFlow Agent 部署位置

### 3.1 部署原则

DeepFlow Agent 应部署在运行 ZLMediaKit 的 Docker 宿主机，或者部署为具备等价
主机可见性的独立 Agent 容器。不要把 Agent 放入 `zlmediakit_polaris-media_1`
容器内部，原因是：

- Agent 需要观察宿主机网卡、Docker veth、容器 socket 和进程关系。
- ZLM 容器内部通常看不到完整的 host PID、宿主机网络命名空间和其他容器。
- 监控 Agent 生命周期不应跟随媒体 pipeline 或视频容器重启。

### 3.2 Docker 权限基线

DeepFlow 官方 Docker 示例使用以下能力和挂载：

```yaml
services:
  deepflow-agent:
    image: <approved-deepflow-agent-image>
    container_name: deepflow-agent
    restart: always
    cap_add:
      - SYS_ADMIN
      - SYS_RESOURCE
      - SYS_PTRACE
      - NET_ADMIN
      - NET_RAW
      - IPC_LOCK
      - SYSLOG
    volumes:
      - /etc/deepflow-agent.yaml:/etc/deepflow-agent/deepflow-agent.yaml:ro
      - /sys/kernel/debug:/sys/kernel/debug:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    network_mode: host
    pid: host
```

`privileged: true` 不应作为默认方案。只有在目标 Docker/内核环境验证
capabilities 仍不足时，才按 DeepFlow 和平台安全评审结果启用。

现场还必须检查：

```text
CONFIG_BPF_SYSCALL
BTF
BPF JIT
cgroup v1/v2
SELinux 状态
/sys/kernel/debug 可读
BPF/PERFMON 或 SYS_ADMIN 权限
SYS_RESOURCE、SYSLOG、NET_ADMIN、NET_RAW、IPC_LOCK
```

DeepFlow 文档说明，AF_PACKET 抓包至少需要 host network、`NET_RAW`、
`NET_ADMIN`，建议 `IPC_LOCK`；eBPF 探针需要 debugfs 只读访问、`SYS_RESOURCE`
和 `SYSLOG`，Linux 5.8 以上可评估用 `BPF`/`PERFMON` 替代 `SYS_ADMIN`。
最终权限以目标内核和安全策略实测为准。

### 3.3 采集范围

首期只采集与前端重拉诊断直接相关的事实：

| 类别 | 首期字段 | 用途 |
|---|---|---|
| TCP | connect/accept/close、RTT、RTO、重传、reset | 判断车端上行或 WebRTC/HTTP 连接是否异常 |
| UDP | 收发字节、包计数、丢包旁证、socket queue | 判断 RTP/RTCP/ICE 媒体路径 |
| 进程 | CPU、RSS、线程数、FD、调度和 off-CPU | 判断 ZLM 是否被资源或线程调度拖住 |
| 容器 | container ID/name、cgroup、PID、网络 namespace | 将流量归属到 ZLM 或 exporter |
| 网卡 | RX/TX、drop、error、队列和带宽 | 判断宿主机或网卡拥塞 |
| L7 | HTTP 请求、状态码、耗时、reset | 关联 `/index/api/webrtc` 和其他 API |

默认不采集完整 RTP/H.264 payload、SDP、ICE credential、认证 token 和控制
消息正文。逐包事件只在短时诊断窗口启用，并设置明确的限额。

## 4. ZLMediaKit 应用层采集

### 4.1 exporter

现有 `zlmexporter` 是 Prometheus exporter，下一步先确认它真实暴露的指标：

```bash
curl -sS http://127.0.0.1:9091/metrics | sed -n '1,240p'
```

如果 exporter 只在容器网络内监听：

```bash
docker exec zlmediakit_zlmexporter_1 sh -lc \
  'wget -qO- http://127.0.0.1:9091/metrics || curl -fsS http://127.0.0.1:9091/metrics'
```

必须记录指标名称、labels、抓取耗时、空值行为和错误码。尤其要确认是否已经
包含以下字段：

```text
stream/app/vhost
input/output bitrate
input/output fps
reader/client count
input packet age
RTSP/WebRTC session count
thread load
HTTP API error
```

未知指标名称不得直接写入告警规则或 DataBuff schema。若 exporter 不包含
`input packet age`，通过 ZLM API 定时补采。

### 4.2 ZLM HTTP API

先调用 API 列表确认镜像版本实际支持的接口，然后以低频、只读方式采集：

```bash
docker exec zlmediakit_polaris-media_1 sh -lc \
  'wget -qO- "http://127.0.0.1/index/api/getApiList?secret=$ZLM_SECRET"'
```

如果容器没有 `wget`/`curl`，从宿主机执行：

```bash
curl -sS -G 'http://127.0.0.1/index/api/getApiList' \
  --data-urlencode "secret=${ZLM_SECRET}"
```

首批候选接口：

| API | 采集内容 | 频率 |
|---|---|---:|
| `getThreadsLoad` | 网络线程负载 | 5-10 秒 |
| `getWorkThreadsLoad` | 工作线程负载 | 5-10 秒 |
| `getMediaList` | app/stream/vhost、轨道和流状态 | 5 秒 |
| `getAllSession` 或等价接口 | TCP/UDP 会话和读者 | 5-10 秒 |
| `listWebrtcRooms` | WebRTC peer 会话（若版本支持） | 5-10 秒 |
| `webrtc` | 信令请求结果，不主动轮询 | 按请求事件 |

ZLM 官方 API 的返回通常包含 `code` 和 `msg`。应把 API 成功和业务成功分开：

```text
HTTP 200 + code != 0  !=  HTTP failure
```

敏感的 `secret` 只放在 Collector/exporter 的 secret store 或环境变量中，不进入
metric label、日志、Trace attribute 或 DataBuff 事件正文。

### 4.3 日志与 Hook

ZLM 日志中至少关联：

```text
timestamp
zlm_node
container_id
app
stream
protocol
session_id
event
code
msg
remote_addr
```

优先使用结构化 Hook 或 exporter 采集业务事件；如果只能解析文本日志，先用
明确的版本化 parser，并保留 `parser_version`。解析失败只能增加
`zlm_log_parse_error_total`，不能影响 ZLM。

## 5. 统一关联键

### 5.1 资源级关联

所有从同一主机来的数据统一补充：

```text
service.name=zlm-mediakit
service.instance.id=<zlm container id>
container.name=zlmediakit_polaris-media_1
container.image.name=harbor.intra.zeron.ai/library/zlmediakit
container.image.tag=2025-12-17
zlm.node=<stable node id>
deployment.environment=<env>
host.name=<redacted or approved host id>
```

exporter 使用：

```text
service.name=zlmexporter
service.instance.id=<exporter container id>
container.name=zlmediakit_zlmexporter_1
container.image.tag=2025-09-11
```

### 5.2 视频链路关联

推荐使用以下业务关联键：

```text
vehicle_id
video_session_id
app
stream
vhost
protocol
zlm_node
time_window
```

网络侧再使用：

```text
container_id
pid/process
netns
src_addr/src_port
dst_addr/dst_port
protocol
socket cookie
five-tuple
```

`stream` 和 `vehicle_id` 可以作为事件属性，但不应无控制地作为高频网络 metric
label。查询关联优先使用 `video_session_id + app + stream + 时间窗`，网络证据
再用五元组和容器/cgroup 过滤。

### 5.3 重拉问题的证据判断

```text
车端 push_ok 停止
  + 车端到 ZLM TCP 重传/断开
  -> 优先车端推流或上行网络

ZLM input packet age 增大
  + ZLM 输入码率降为 0
  -> 车端上行、ZLM 输入连接或媒体端口

ZLM 输入稳定
  + WebRTC HTTP/ICE/UDP 会话反复创建
  -> ZLM WebRTC、云端信令或浏览器恢复逻辑

ZLM CPU/线程负载饱和
  + socket recv queue/drop 增长
  -> ZLM 宿主机资源或网络处理能力

ZLM 和 DeepFlow 稳定
  + 浏览器 inbound bytes/framesDecoded 停止
  -> 浏览器、WebRTC 下行或前端状态机
```

这里的 eBPF 证据只能说明系统和网络事实，不能单独证明浏览器是否解码、渲染
或主动执行了重拉；前端 RUM/WebRTC stats 仍然是必要数据。

## 6. DeepFlow 到 DataBuff 的上传方式

### 6.1 推荐路径

推荐使用两个相互隔离的 OTel pipeline：

```text
pipeline/zlm-business:
  Prometheus receiver <- zlmexporter
  HTTP/log receiver  <- ZLM API/Hooks/log adapter
  OTLP exporter      -> DataBuff

pipeline/deepflow-selected:
  DeepFlow Server OpenTelemetry exporter
  selected flow_log.l7_flow_log
  OTLP exporter      -> OTel Collector -> DataBuff
```

DeepFlow 官方配置支持 `opentelemetry` exporter，当前公开示例主要针对选定的
`flow_log.l7_flow_log` 数据源，并通过 gRPC OTLP endpoint 发送。由此可见的
可行路径是“DeepFlow Server 选择性导出 -> Collector -> DataBuff”，而不是
“DeepFlow Agent 原始 eBPF -> DataBuff”。

### 6.2 DataBuff 接收

DataBuff 官方 OTLP 接收端口为：

```text
4317  OTLP/gRPC
4318  OTLP/HTTP
```

HTTP 单信号 endpoint：

```text
http://<databuff-host>:4318/v1/traces
http://<databuff-host>:4318/v1/metrics
http://<databuff-host>:4318/v1/logs
```

Collector 示例：

```yaml
receivers:
  prometheus/zlm:
    config:
      scrape_configs:
        - job_name: zlmexporter
          scrape_interval: 5s
          static_configs:
            - targets: ["127.0.0.1:9091"]

  otlp/deepflow:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
  batch:
    timeout: 1s
    send_batch_size: 512
  resource/zlm:
    attributes:
      - key: service.name
        value: zlm-mediakit
        action: upsert

exporters:
  otlphttp/databuff:
    endpoint: http://<databuff-host>:4318
    compression: gzip
    sending_queue:
      enabled: true
      queue_size: 2048
    retry_on_failure:
      enabled: true

service:
  pipelines:
    metrics/zlm:
      receivers: [prometheus/zlm]
      processors: [memory_limiter, resource/zlm, batch]
      exporters: [otlphttp/databuff]
    traces/deepflow:
      receivers: [otlp/deepflow]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/databuff]
```

上面是拓扑示例，不是可直接上线的配置。必须补充 TLS、认证、目标地址、队列
磁盘持久化、租户 header 和实际 Collector 版本。若 DataBuff 只开放 gRPC，则改用
`otlp` exporter 指向 `:4317`。

### 6.3 微批字段

业务指标和事件建议统一携带：

```text
schema_version
event_time_unix_nano
observed_time_unix_nano
trace_id
span_id
vehicle_id
video_session_id
zlm_node
container_id
container_name
app
stream
vhost
protocol
metric_or_event_name
value
status
error_code
sampling_priority
```

不把完整视频帧、RTP payload、SDP、ICE credential、ZLM secret 或用户标识原文
放入 DataBuff。DataBuff/Collector 只负责观测数据的缓存、批量、压缩、重试和
传输，不得进入：

```text
GStreamer push-buffer
RTSP send loop
WebRTC reconnect decision
ROS/CAN/control acknowledgement
```

## 7. 采样与资源保护

建议首期策略：

| 数据 | 默认策略 |
|---|---|
| ZLM exporter 指标 | 5 秒抓取，按 app/stream 聚合 |
| ZLM API 流状态 | 5 秒抓取，异常时临时提升到 1 秒 |
| HTTP/WebRTC 信令 | 错误 100%，成功按 1%-10% |
| DeepFlow L7 flow log | 只选 ZLM 端口和相关上下游，先 100% 小窗口验证 |
| TCP/UDP 网络事实 | DeepFlow 默认采集，按端口/namespace 过滤 |
| 逐包/完整 payload | 默认关闭，仅批准的短时诊断窗口 |
| ZLM 日志 | 错误和连接生命周期 100%，普通 debug 限流 |

每个采集组件必须有：

```text
queue depth
send failure
retry count
drop count
last successful export time
disk/memory waterline
```

观测系统不可达时，ZLM、车端推流、前端播放和控制链路必须继续运行。Collector
或 DataBuff 积压达到上限时优先丢弃低优先级普通样本，保留重拉、断流、flow
error、输入码率变为零和版本变更事件。

## 8. 现场核验步骤

### 8.1 容器和网络

```bash
docker inspect zlmediakit_polaris-media_1 \
  | jq '.[0] | {
      Id,
      Name,
      State,
      NetworkSettings: {
        Networks,
        Ports
      },
      HostConfig: {
        NetworkMode,
        PidMode,
        Privileged,
        CapAdd,
        Binds
      },
      Config: {
        Image,
        Env,
        Cmd,
        Entrypoint
      }
    }'

docker inspect zlmediakit_zlmexporter_1 \
  | jq '.[0] | {
      Id,
      Name,
      State,
      NetworkSettings: {
        Networks,
        Ports
      },
      HostConfig: {
        NetworkMode,
        PidMode,
        Binds
      },
      Config: {
        Image,
        Env,
        Cmd,
        Entrypoint
      }
    }'
```

确认：

```text
network mode、PID mode、cgroup、容器 IP、veth、配置挂载和 ZLM secret 来源
exporter 是否访问到 ZLM API
ZLM API listen address、HTTP secret、日志路径
80/8000/10001-10003 的实际协议用途
```

### 8.2 ZLM 和 exporter

```bash
curl -sS http://127.0.0.1:9091/metrics > /tmp/zlmexporter.metrics
rg -n 'stream|media|bitrate|fps|reader|session|thread|packet|error' \
  /tmp/zlmexporter.metrics

docker logs --since 10m zlmediakit_polaris-media_1 \
  | rg -n 'webrtc|rtsp|stream|reader|session|error|close|publish|play'

ss -lntup | rg ':(80|8000|10001|10002|10003)\b'
```

然后选一路，例如 `app/stream=live/cam_f_12`，固定 10 分钟时间窗，记录：

```text
ZLM 流是否存在
输入包年龄、输入码率、FPS、reader 数
HTTP WebRTC 请求的 code/msg 和耗时
ZLM 线程负载
容器 CPU/RSS/FD
```

### 8.3 DeepFlow Agent

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' \
  | rg 'deepflow|otel|databuff'

docker logs --since 10m deepflow-agent \
  | rg -n 'error|warn|ebpf|bpf|btf|permission|capture|drop'

uname -a
test -r /sys/kernel/btf/vmlinux && echo btf=present || echo btf=missing
test -r /sys/kernel/debug && echo debugfs=readable || echo debugfs=unreadable
grep -E 'CONFIG_BPF_SYSCALL|CONFIG_DEBUG_INFO_BTF|CONFIG_BPF_JIT' \
  /boot/config-$(uname -r)
```

验收时确认 DeepFlow 中能按 `container.name` 或 container ID 查询
`zlm-mediakit` 的 TCP/UDP、进程和网络指标，而不是只看到宿主机总流量。

### 8.4 DataBuff OTLP

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  http://<databuff-host>:4318/v1/metrics

docker logs --since 10m <otel-collector-container> \
  | rg -n 'export|retry|queue|drop|databuff|4317|4318'
```

用一条带 `service.name=zlm-mediakit` 的测试 metric 和一条测试 span 验证：

```text
Collector accepted
DataBuff accepted
DataBuff UI/query visible
resource attributes preserved
no secret/token/payload leakage
Collector/DataBuff down 时 ZLM 仍可持续收流
```

## 9. 验收标准

### 必须通过

1. DeepFlow Agent 运行在宿主机可见性范围内，BPF/BTF/debugfs 权限检查通过。
2. DeepFlow 能识别 ZLM 容器、PID/cgroup 和至少一条 ZLM 媒体连接。
3. exporter 指标可抓取，且能和 ZLM API 的流状态对照。
4. DataBuff 能看到 `zlm-mediakit` 的测试 metric、Trace 或 Log。
5. 一次前端重拉可以用同一时间窗关联到车端 push、ZLM 输入状态、网络事实和
   浏览器事件。
6. 关闭 Collector 或 DataBuff 后，ZLM 和前端媒体链路不发生额外重拉。
7. 采集 CPU、RSS、网络带宽和队列在目标负载下处于批准预算内。

### 当前不能宣称

```text
DeepFlow Agent 已部署
DeepFlow eBPF 已覆盖 ZLM 容器
DeepFlow 数据已自动进入 DataBuff
zlmexporter 已包含所有需要的 ZLM 指标
DataBuff 已成为生产唯一观测后端
```

## 10. 待确认项

| 项目 | 责任方 | 结果 |
|---|---|---|
| `docker inspect` 的 network/PID/cgroup/mount | ZLM 运维 | 待现场 |
| `zlmexporter /metrics` 实际指标和 labels | ZLM 运维/可观测性 | 待现场 |
| 80/8000/10001-10003 的实际协议用途 | ZLM 运维 | 待现场 |
| DeepFlow Agent 版本、Server 地址和 agent group | 网络/可观测性 | 待现场 |
| 目标 Linux 内核、BTF、cgroup 和 BPF 权限 | 主机平台 | 待现场 |
| DeepFlow Server OpenTelemetry exporter 是否启用 | DeepFlow 管理员 | 待现场 |
| DataBuff 版本、TLS、认证和 OTLP endpoint | DataBuff 管理员 | 待现场 |
| Collector 是否允许从 DeepFlow 接收 OTLP | 可观测性 | 待现场 |
| DataBuff retention、限流、查询和告警 | 数据平台 | 待现场 |

## 11. 公开资料依据

- [DeepFlow Agent cloud host Docker deployment](https://docs.deepflow.io/docs/ee-install/saas/cloud-host/)
- [DeepFlow required permissions](https://deepflow.io/docs/ce-install/overview/)
- [DeepFlow Agent configuration](https://deepflow.io/docs/configuration/agent/)
- [DeepFlow OpenTelemetry input](https://www.deepflow.io/docs/integration/input/tracing/opentelemetry/)
- [DeepFlow OpenTelemetry exporter](https://www.deepflow.io/docs/integration/output/export/opentelemetry-exporter/)
- [ZLMediaKit HTTP API](https://github.com/ZLMediaKit/ZLMediaKit/wiki/MediaServer支持的HTTP-API)
- [ZLMediaKit source API registration](https://github.com/ZLMediaKit/ZLMediaKit/blob/master/server/WebApi.cpp)
- [DataBuff OTLP ingestion](https://databuff.ai/docs/en/guide/otel-otlp-ingestion)
- [DataBuff eBPF/OBI ingestion](https://databuff.ai/docs/en/manual/ebpf-ingestion)
