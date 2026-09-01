# K8s 部署 DeepFlow、OTel Collector 与 DataBuff 方案

更新时间：`2026-08-30`

状态：`implemented/verified-poc`

本文是部署方案、实施边界和当前落地记录。当前仅 DeepFlow 单节点 POC 已部署验证，
OTel Collector、DataBuff 和全链路验收仍按阶段推进。部署模板位于：

```text
/Users/minyi/workspace/autodrive/my-otel
```

## 1. 目标和范围

本阶段只建设旁路可观测性链路：

```text
ziot /actuator/prometheus:8850
ZLMediaKit exporter:9091
K8s/节点网络与进程事实
        |
        v
OTel Collector Gateway
        |
        +--> 现有指标/日志/Trace 后端（按环境配置）
        |
        +--> DataBuff OTLP 接入（受控副本或指定生产流量）
```

DeepFlow 负责 K8s 节点、容器、进程、网络和 eBPF 事实；OTel Collector 负责
Prometheus/OTLP 接收、认证、脱敏、限流、批处理和路由；DataBuff 负责接收并查询
被批准的 OTLP 数据。三者不进入 ziot、ZLMediaKit、车端 TCP、RTSP 或 WebRTC
同步处理路径。

本阶段不做：

```text
修改业务控制逻辑
修改 RTP/RTSP 包
把 DeepFlow 原始 eBPF buffer 直接写入 DataBuff
把 DataBuff 作为唯一生产告警和故障事实源
在 K8s 中假设能够自动观测 K8s 外部 Docker 宿主机
```

### 1.1 Namespace 布局

生产环境不建议把所有组件放入现有业务 namespace `zota`。当前落地包固定使用：

| Namespace | 组件 |
|---|---|
| `zota` | 现有 ziot、`ziot-metrics` Service、单副本 OTel Collector |
| `databuff` | DataBuff ingest/web、Doris、ZooKeeper、PVC |
| `deepflow` | DeepFlow Server/App/Grafana、ClickHouse/MySQL、Agent |

Collector 靠近 ziot 便于抓取 `8850`，但不进入指令路径。DataBuff 是重型有状态
系统，DeepFlow Agent 包含集群级 RBAC、DaemonSet、hostPID、debugfs 和 eBPF 权限，
两者独立 namespace 可以缩小配额、权限、升级和误操作的影响范围。

节点放置也必须显式控制：

```text
DataBuff:        observability.zeron.ai/databuff=enabled
DeepFlow 后端:  observability.zeron.ai/deepflow-server=enabled
DeepFlow Agent: observability.zeron.ai/deepflow-agent=enabled
```

没有对应标签时 Pod 保持 Pending，不允许重型观测组件随机调度到业务节点。三个标签
都禁止添加到 VCI/virtual-kubelet 节点。

## 2. 关键部署边界

### 2.1 DeepFlow Server 与 Agent

DeepFlow Server 部署在 K8s 中，使用官方 Helm chart。DeepFlow 官方文档提供单 K8s
集群和 All-in-One Helm 部署方式；官方示例包含 `global.storageClass`、
`global.replicas` 和 `global.allInOneLocalStorage` 等配置项。实际生产部署前必须
锁定已批准的 chart 版本，并通过 `helm show values` 对照该版本的字段，不能直接
复制旧版本 values。

DeepFlow Agent 以 DaemonSet 覆盖需要观测的 K8s 节点。Agent 需要按目标内核和安全
策略配置 host network、host PID、BPF/cgroup/debugfs 可见性及最小必要 capability。
不要把 Agent 放进 ZLMediaKit 业务容器内部。

ZLMediaKit 当前是 Docker 容器。如果 ZLMediaKit 宿主机不属于该 K8s 集群，K8s 中
部署的 DeepFlow Agent 看不到该 Docker 宿主机，必须在 ZLMediaKit 宿主机额外部署
一个 DeepFlow Agent，并把它注册到同一个 DeepFlow Server。若 ZLMediaKit Docker
运行在 K8s 节点上，则先通过节点级验证确认 Agent 能看到 Docker namespace、veth、
容器 PID 和 ZLM 进程，再决定是否需要额外 Agent。

本项目需要区分两套 ziot 实例：ECS `10.7.20.145` 上的外部 jar ziot，
以及 K8s `zota` Namespace 内的 ziot。两套实例可以共用同一个 DeepFlow
Server/ClickHouse、OTel Collector 和 DataBuff，但各自使用所在环境的 Agent、
Prometheus target、`instance` 标签和验收记录。ECS Agent 的文件统一放在
`my-otel/external/deepflow-agent`，K8s Agent 继续由 Helm 管理。

注意：ZLMediaKit 不在 `10.7.20.145`，而是独立部署在 ECS
`10.7.30.44`。`10.7.20.145:8850` 只代表外部 ziot；ZLMediaKit exporter
使用独立的 `10.7.30.44:9091` target。若需要观测 ZLMediaKit 所在主机的
网络、进程和容器，还需要在 `10.7.30.44` 单独部署 DeepFlow Agent，不能
用 `10.7.20.145` 上的 Agent 代替。

### 2.2 OTel Collector

OTel Collector 使用 Deployment 和 ClusterIP Service。首期固定单副本，因为内置
Prometheus receiver 多副本会重复抓取 ziot 和 zlmexporter。需要高可用时先引入
Target Allocator，或拆分 scrape gateway 与 OTLP gateway，再扩容。Collector 只做
接收和路由：

```text
Prometheus receiver:
  ziot:8850
  zlmexporter:9091

OTLP receiver:
  4317/gRPC
  4318/HTTP

processors:
  memory_limiter
  batch
  attributes/filter（脱敏和固定资源属性）

exporters:
  生产后端（按环境）
  DataBuff OTLP（默认先受控副本）
```

Collector 不读取车端控制正文、RTP payload、ICE credential、JWT、ZLM secret 或
数据库密码。Prometheus label 必须保持低基数，`vehicleId`、`cockpitId`、
`messageId`、`sessionId` 等关联字段进入抽样日志/Trace 事件，不进入长期高基数
指标 label。

### 2.3 DataBuff

已经锁定 DataBuff OSS `0.1.8` 和官方提交
`cdbabc80f6f40ba367e9fe578bb58bc74616a9f1`。`my-otel` 基于官方 K8s manifests
适配了 VKE：

```text
namespace: databuff
ingest/web: ClusterIP
Doris FE metadata: ebs-ssd 20Gi
Doris BE storage: ebs-ssd 100Gi
ZooKeeper data: ebs-ssd 10Gi
OTLP/HTTP: ai-apm-ingest.databuff.svc.cluster.local:4318
```

当前是单副本 POC 拓扑，不是生产 HA。官方 SQL 和 AGPL-3.0 根许可证已随部署包保留；
二次开发和托管分发前需要法务确认。Web 管理员密码只通过 Secret 注入。

DataBuff 不可用时，Collector 必须通过队列上限、超时、重试和丢弃策略隔离，不能
阻塞 ziot 指令链路或 ZLMediaKit 媒体链路。

## 3. 推荐拓扑

```text
                           ┌─────────────────────────┐
                           │ DeepFlow Server          │
                           │ K8s / storage / query    │
                           └────────────┬────────────┘
                                        │
                  ┌─────────────────────┴─────────────────────┐
                  │                                           │
        K8s node DeepFlow Agent                    ZLM host Agent
        DaemonSet                                  Docker host
                  │                                           │
                  └─────────────── flow/eBPF facts ───────────┘

ziot:8850 ───────────────┐
zlmexporter:9091 ────────┼──> OTel Collector Gateway ──> DataBuff OTLP
OTLP application events ─┘             │
                                       └──> Prometheus/Tempo/Loki 等后端
```

DeepFlow 的网络事实和 OTel 的业务指标必须通过统一资源属性、时间窗以及
`messageId + source_seq + correlationId` 关联。DeepFlow 单独不能确认 ziot
业务 handler、车端解密/解析或 ROS publish 的耗时；这些仍由现有业务埋点和结构化
日志提供。

## 4. 分阶段实施

### Phase 0：环境盘点

部署前必须收集以下信息：

```text
Kubernetes 版本、节点架构和 Linux 内核版本
CNI、NetworkPolicy、Ingress、StorageClass
节点是否启用 BTF、BPF syscall、BPF JIT、cgroup v1/v2
是否允许 hostNetwork、hostPID、debugfs、BPF capability
ZLMediaKit Docker 宿主机是否属于 K8s 集群
ziot Service/namespace 与 8850 可达性
zlmexporter Service/namespace 或外部地址与 9091 可达性
DataBuff OTLP endpoint、协议、TLS、认证、租户和限额
现有 Prometheus/Tempo/Loki/DataBuff 是否已有重复采集
```

盘点不通过时只部署 Collector 配置校验，不部署生产 Agent。

### Phase 1：DeepFlow POC（已完成）

1. 在 `deepflow` 安装锁定的 DeepFlow chart `7.1.002`。
2. 为批准的后端物理节点添加 `observability.zeron.ai/deepflow-server=enabled`。
3. 使用独立 StorageClass/PVC；All-in-One 只用于 POC，不作为生产容量结论。
4. 部署 DeepFlow Agent DaemonSet，先覆盖一个可回滚的测试节点池。
5. 已验证 K8s Pod、Service、容器、节点网卡和进程事实同步。
6. 若 ZLM 在 K8s 外部 Docker 主机，单独安装 ZLM 主机 Agent。
7. 已验证 Agent 注册、平台同步和 Server 接收状态；Agent CPU、内存、BPF map、
   丢弃、发送队列仍需按目标流量持续观察。

### Phase 2：Collector 到 DataBuff 联调

1. 为批准的物理节点添加 `observability.zeron.ai/databuff=enabled`。
2. 在 `databuff` 部署 DataBuff `0.1.8` POC，并初始化锁定 SQL。
3. 先只抓取 ziot `8850` 的低频 Prometheus 指标和 zlmexporter `9091` 指标。
4. Collector 先使用 `debug` 或测试 OTLP exporter 验证数据结构。
5. 只发送已批准的指标/Trace 到 DataBuff。
6. 验证 DataBuff 收到数据、时间戳、资源属性、错误重试和断开恢复。
7. DataBuff 不可用时验证业务数据面仍正常。

### Phase 3：控制链路关联

对一条真实云端下发指令，按以下键对齐：

```text
ziot:
  messageId/source_seq/correlationId
  latest-only mailbox
  send start/completion

车端:
  messageId/source_seq/correlationId
  body receive
  decrypt/parse/dispatch
  handler
  ROS publish

DeepFlow:
  source/destination
  connection generation
  RTT/retransmission/RTO/reset
  socket queue
  process/container/node
```

该阶段只做观测和关联，不根据观测结果修改指令重试、latest-only、TCP 或 ROS
控制逻辑。

### Phase 4：生产扩大

只有以下条件全部通过，才扩大到全部节点和全部允许的数据类型：

```text
Agent 节点覆盖率达到目标
Collector 单 scrape 副本、滚动升级和资源上限有效
DataBuff TLS/认证/租户隔离有效
Collector backlog、丢弃、重试和 429/5xx 可观测
DeepFlow 与 ZLM Docker 宿主机归属正确
ziot 指令和 ZLMediaKit RTP/WebRTC 性能无显著回归
采集系统故障不影响业务链路
```

## 5. K8s 安全和资源基线

### DeepFlow Agent

```text
仅部署到批准的节点池
ServiceAccount 和 RBAC 使用锁定 chart 生成并经审计的权限
chart 的 privileged sysctl initContainer 和 Agent capabilities 必须经安全评审
hostPath 仅挂载必要的 debugfs、cgroup、容器运行时元数据
NetworkPolicy 不阻断 Agent 到 DeepFlow Server 的上报
禁止采集认证 token、RTP/H.264 payload 和控制消息正文
```

### OTel Collector

```text
Prometheus scrape 首期 1 副本，禁止直接扩容造成重复采集
requests/limits 必须固定
memory_limiter 必须启用
batch 必须启用
队列有硬上限，禁止无限制 retry
Secret 只通过 Secret/env 注入
Service 只在集群内暴露
```

### DataBuff

```text
优先使用 TLS
认证信息不进入 Git、label、日志或 Trace attribute
明确租户、保留期、配额和删除策略
按指标、Trace、Log 分开配置采样和路由
先副本/灰度，后扩大生产流量
```

## 6. 通过标准

### 配置级

```bash
kubectl apply --dry-run=server -k /Users/minyi/workspace/autodrive/my-otel/k8s
kubectl -n zota get deploy/otel-collector svc/otel-collector svc/ziot-metrics
```

要求：K8s schema 校验通过，Collector 配置可以启动，所有 placeholder 已在部署
前替换。

### 运行级

```bash
curl -fsS http://127.0.0.1:8850/actuator/prometheus
curl -fsS http://127.0.0.1:9091/metrics
kubectl -n zota logs deploy/otel-collector
```

要求：

```text
ziot Prometheus endpoint 返回 200
parallel_driving_* 指标在真实指令后增长
zlmexporter 指标可抓取
DeepFlow 能看到目标节点/容器/进程/网络流
Collector 无持续发送失败、无限队列或高丢弃
DataBuff 能查询到批准的数据
DataBuff/Collector 故障不影响 ziot、ZLM 和车端链路
```

## 7. 当前未验证项

```text
目标物理节点的 BTF、BPF 权限、debugfs 和 CNI 兼容性
ZLMediaKit Docker 宿主机是否在 K8s 节点范围内
zlmexporter 在 K8s 内外的真实访问地址
DataBuff `0.1.8` 在 VKE 上的实际启动、SQL 初始化和 PVC 性能
Collector 到 DataBuff 的数据闭环、保留期和容量
DeepFlow Server 到 Collector 的选定 L7 flow 导出方式
DeepFlow 查询页面/API 中真实业务流量记录和云端到车端指令关联
ECS 或外部 Docker 主机的 Agent 接入
全量节点 Agent 对 CPU、内存、网络和媒体性能的影响
```

截至 `2026-08-30 23:10`，DeepFlow `7.1.002` 已通过 Helm 部署到 `deepflow` Namespace：
Server、App、ClickHouse、MySQL、Grafana 和单节点 Agent 均为 `Running/Ready`，
PVC 已绑定到 `ebs-ssd`，时区为 `Asia/Shanghai`。Server 健康接口返回 HTTP 200
和 `OPT_STATUS=SUCCESS`，Server 日志持续显示 `vtap count: 1`，Agent 持续完成
Kubernetes/eBPF 平台同步。

受控验收中，从 DeepFlow App Pod 向 Server `20417` 健康接口发送 10 次请求，
请求全部成功；ClickHouse 中 `server_port=20417` 的记录从 `1333` 增至 `1343`。
L7 流量总记录从 `1,338,263` 增至 `1,340,885`。Grafana `/api/health` 返回
HTTP 200、数据库状态为 `ok`，认证后可查询 DeepFlow System 和 Agent 仪表盘。

当前结论是“单节点 POC 已部署并验证”，不是生产 HA 或全链路验收。此次验证证明
Kubernetes 内部 Agent -> Server -> ClickHouse -> Grafana 流量闭环；查询
`10.7.20.145` 或端口 `8850` 的 DeepFlow L7 记录为 `0`，外部 ECS jar ziot
主机尚未部署 Agent，因此不能据此判断该主机的网络流量。仍未覆盖 ECS/外部
Docker 主机 Agent、真实云端到车端指令关联，以及 DeepFlow flow 自动导出到 DataBuff。

当前外部 ECS jar ziot 的 `http://10.7.20.145:8850/actuator/prometheus` 已返回
指标内容；Collector 是否持续采集和 DataBuff 是否持续落库，按 Phase 2 单独验收。
