# 车云端全链路监控方案

> 文档管理：本文件是完整设计基线。按实际实施边界拆分的专题入口见
> [`.github/observability/README.md`](observability/README.md)；专题文档只做分域管理，
> 详细字段、代码挂点和历史决策仍以本文为准。
>
> GreptimeDB Edge、Apache Arrow、Parquet、OTel/OTAP 与 DataBuff/WAL 的车云数据平面设计见
> [专题文档 06](observability/06-greptime-edge-and-arrow.md)。

> 2026-09-12 数据库选型补充见[专题 23](observability/23-vehicle-data-platform-selection-20260912.md)：
> 区分 SQLite 事务状态、DuckDB 离线分析与 GreptimeDB 云端/Edge 候选，
> 并记录分阶段方案与升级门槛；不变更既有运行状态或安全边界。

## 1. 目标与边界

本方案用于建立从车端采集、车云网络、云端服务到用户端的统一可观测链路，优先解决两类问题：

- 视频链路：摄像头采集 -> 编码 -> RTSP 上行 -> ZLMediaKit -> WebRTC 下行 -> 用户端渲染。
- 指令链路：手柄 -> 云端 API -> MQTT/TCP -> 车端接收 -> ROS 2 执行 -> CAN 下发。

目标不是一次性部署所有 APM、日志和 AI 产品，而是先统一以下事实：

1. 所有关键事件都能关联到 `trace_id`、车辆和会话。
2. 每个链路阶段都能回答“何时进入、何时离开、耗时多少、在哪里失败”。
3. AI 只基于可查询的证据分析，不能凭模型记忆推断生产状态。
4. 自动化动作必须经过权限、审批和可回滚检查。

本方案中的硬件支持结论必须以现场镜像和内核检查结果为准。CPU 架构支持 eBPF 不等于当前车载系统已经开放 BPF syscall、BTF、JIT、必要 capability 或内核探针权限。

## 2. 组件职责

| 组件 | 职责 | 不负责的事情 |
|---|---|---|
| eBPF | 在内核侧采集系统调用、进程、网络和部分协议事实 | 不能自动理解业务语义，也不是 Trace 存储 |
| DeepFlow Agent | 运行在节点侧，利用 eBPF 生成网络、服务、拓扑和自动 Trace 数据 | 不替代业务关键点的领域语义 |
| OpenTelemetry | 统一 Trace、Metric、Log 的 API、上下文、语义属性和 OTLP 传输 | 不规定后端存储和告警策略 |
| OTel Collector | 本地或云端接收、过滤、脱敏、批处理、采样和路由 | 不承担根因分析 |
| 浏览器 RUM/OTel Adapter | 将页面生命周期、WebRTC、解码和渲染领域事件转换为 OTel Trace/Event/Log | 不能依赖 eBPF 自动采集，也不能直接暴露生产采集凭证 |
| DataBuff | 接收 OTLP，提供 Trace/Metric/Log 查询、拓扑和 AI 分析 PoC | 首期不作为唯一生产后端或唯一告警事实源 |
| Grafana | 统一展示指标、日志、Trace、拓扑和告警 | 不作为事故状态、审批或发布事实库 |
| DSH | 基于插件和 Skills 编排查询、证据关联、假设验证、优化建议与受控执行 | 不替代采集和存储，不进入实时控制链路，不自主做车辆安全决策 |

生产基线建议沿用仓库现有判断：

```text
OTel Collector
  -> Metrics: Prometheus/VictoriaMetrics
  -> Logs: Loki/OpenSearch
  -> Traces: Tempo
  -> Dashboard/Explore: Grafana

受控 Trace 副本 -> DataBuff PoC
告警/证据包 -> DSH 分析编排
```

DataBuff 只有在规模、可靠性、权限、审计、升级回退和 AI 证据准确性验证通过后，才考虑扩大生产范围。

## 3. 总体架构

```text
业务数据面（不经过 DSH）
用户端/手柄 <-> 云端 API、MQTT、ZLMediaKit <-> 车端网关、ROS 2、CAN、视频进程

可观测面
浏览器 parallel-driving-observation
  -> 浏览器 RUM/OTel Adapter
  -> 同源 Telemetry Gateway
  -> OTel Collector

车端/云端 DeepFlow Agent + OTel SDK
  -> OTel Collector（认证、脱敏、采样、路由）
  -> Tempo + Prometheus/VM + Loki/OpenSearch + Grafana
  -> DataBuff PoC（受控 Trace 副本）

DSH 优化控制面
告警/巡检/发布事件
  -> DSH Coordinator
  -> 只读工具插件 + 领域 Skills + 专项 Agent
  -> 证据化 RCA、容量/配置/发布建议
  -> 审批工作流
  -> 受控执行器
  -> 指标复查、回滚和事故知识沉淀
```

三个平面必须故障隔离：

1. DSH 停止、模型超时或插件失败，不能影响视频、指令、OTA 和车辆安全功能。
2. 可观测后端不可用时，业务继续运行，车端按资源预算执行 WAL、降采样和丢弃策略。
3. DSH 只能通过受控 API 查询观测面；禁止将 DSH、DataBuff 或 Grafana 放入手柄到 CAN 的同步调用路径。

### 3.1 车端平台

| 平台 | 典型系统 | eBPF 部署判断 | 现场验收重点 |
|---|---|---|---|
| 联想 AD1 域控制器 | NVIDIA DRIVE OS，Linux 5.15 系列 | 具备较好的内核基础，但受 DRIVE OS 安全策略和厂商内核配置约束 | `CONFIG_BPF_SYSCALL`、BTF、CO-RE、capability、探针白名单 |
| 天准 Jetson 星智系列 | Jetson AGX Orin 或 Jetson Thor，DRIVE OS/定制 Linux | 需按具体 BSP、内核和安全策略验证 | 内核配置、BPF JIT、BTF、功耗和 CPU 占用、升级兼容性 |
| x86 主机 | x86_64 Linux | 通常最容易部署和调试 | 内核版本、权限、容器 host access、性能基线 |

车端不应默认启用所有探针。建议按优先级逐步开启：

1. 进程、TCP/UDP、连接建立、重传、RTT、丢包和 socket 队列。
2. HTTP/gRPC、MQTT、TLS 连接等已验证协议解析。
3. ROS 2/DDS 和 CAN 相关的业务补充埋点。
4. 只在 POC 或专项问题期间开启更高开销的 profile。

### 3.2 云端部署

云端至少部署以下组件：

- DeepFlow Agent：覆盖 ZLMediaKit、API 网关、MQTT 网关、业务服务和宿主机网络。
- OTel Collector Gateway：接收车端和服务端 OTLP，执行认证、限流、脱敏、采样和路由。
- Prometheus/VictoriaMetrics：保存黄金指标、Agent 健康和 SLO。
- Loki/OpenSearch：保存结构化日志，并保留 `trace_id`、`span_id`。
- Tempo：保存生产 Trace。
- Grafana：统一查询入口和业务看板。
- DataBuff：以隔离环境或受控副本方式验证 AI 查询和根因分析。

## 4. 统一数据模型

### 4.1 必选资源属性

所有车端和云端信号都必须尽量携带以下属性：

```text
service.name
service.version
deployment.environment
host.id
vehicle.id
vehicle.platform
vehicle.vin_hash
device.id
session.id
route.type              # video / command / ota / telemetry
trace_id
span_id
```

敏感字段使用哈希或受控映射。VIN、手机号、Token、MQTT 密码、原始控制 payload 不得直接写入 Trace 属性、日志或 DSH Prompt。

浏览器视频链路还需要以下关联属性：

```text
session.id                 # 整个远控会话，允许长时间存在
video.session.id           # 单路视频在当前远控会话中的逻辑会话
player.instance.id         # 具体前端播放器组件实例
webrtc.shared_session.id   # 同流共享 PeerConnection 会话
correlation.id             # Trace Context 无法传播时的补偿关联键
camera
stream.app
stream.name
```

`trace_id` 不代替 `session.id`。远控会话、播放器实例和共享 WebRTC 会话用于长期关联；
`trace_id` 只覆盖一次有限操作，例如首次拉流、一次信令协商、一次重连或一次黑屏恢复。
不得把持续数小时的整个远控会话建成单一超长 Trace。

### 4.2 领域事件

eBPF 只能提供系统和网络事实，以下事件建议通过 OTel SDK 或结构化事件补充：

| 领域 | 事件示例 |
|---|---|
| 视频 | `camera.capture`, `video.encode`, `rtsp.publish`, `zlm.ingest`, `webrtc.offer`, `client.render` |
| 指令 | `controller.input`, `api.receive`, `mqtt.publish`, `vehicle.receive`, `ros.execute`, `can.send` |
| 车辆 | `vehicle.online`, `vehicle.network_switch`, `vehicle.process_restart`, `vehicle.safety_gate` |
| 诊断 | `config.reload`, `mqtt.connect`, `mqtt.subscribe`, `gateway.start`, `gateway.error` |

推荐用一个父 Trace 串联阶段，用 Messaging Span 表示 MQTT/TCP 边界，并在无法传播上下文时通过以下关联键补偿：

```text
command.id
video.session.id
vehicle.id
gateway.id
message.id
sequence
```

## 5. 两条核心链路

### 5.1 视频流链路

```text
camera.capture
  -> video.encode
  -> rtsp.publish
  -> network.up
  -> zlm.ingest
  -> zlm.transcode_or_relay
  -> webrtc.signal
  -> network.down
  -> client.render
```

至少展示以下分解：

- 采集等待时间。
- 编码队列和编码耗时。
- RTSP 首包、持续发送和重传。
- 车云网络 RTT、丢包和拥塞。
- ZLMediaKit 接收、转协议和排队耗时。
- WebRTC 信令建立和 ICE/DTLS 状态。
- 用户端首帧、卡顿和渲染延迟。

### 5.2 指令流链路

```text
controller.input
  -> api.receive
  -> command.validate
  -> mqtt.publish_or_tcp.send
  -> network.up
  -> vehicle.receive
  -> ros.execute
  -> can.send
  -> vehicle.ack
```

指令链路必须额外记录：

- `command.id`、序列号和产生时间。
- 是否通过权限、模式和安全门禁。
- 发布、接收、执行、确认的时间戳。
- 超时、丢弃、重复、乱序和重放原因。
- 车辆当前模式、网络链路和控制会话。

控制数据的可观测性不能突破安全边界。采集原始控制内容前必须确认脱敏、访问控制、保留周期和法规要求。

## 6. 采集与传输策略

### 6.1 车端

车端 Agent 与 Collector 应具备：

- 本地 WAL 或优先级队列，断网时优先保存错误、状态变化和关键 Trace。
- 资源上限：CPU、内存、磁盘和网络带宽必须有硬阈值。
- 优先级：安全事件 > 指令 Trace > 视频首帧/卡顿事件 > 普通网络流量。
- 批量压缩、限流和退避，不能与控制链路争抢关键资源。
- mTLS、设备身份和证书轮换。
- 远程配置必须可审计、可回滚，禁止无审批打开全量抓包。

### 6.2 云端

Collector Gateway 负责：

1. 校验设备身份和租户边界。
2. 丢弃未授权来源和超大属性。
3. 统一补充环境、区域和版本标签。
4. 对错误 Trace、关键指令和新版本提高采样率。
5. 对普通流量执行 tail sampling，避免高基数和存储失控。
6. 将生产主流量和 DataBuff PoC 副本隔离。

## 7. 看板与告警

### 7.1 黄金指标

视频、指令和服务统一使用：

- 延迟：P50/P95/P99、首帧、端到端和阶段分解。
- 流量：消息数、字节数、帧率、吞吐。
- 错误：连接失败、重传、丢包、协议错误、执行失败。
- 饱和度：CPU、内存、队列、socket buffer、磁盘、Collector backlog。

### 7.2 首批看板

1. 车队总览：在线率、版本、平台、网络、Agent 健康。
2. 视频链路：首帧、卡顿、RTSP/WebRTC 错误、ZLMediaKit 负载。
3. 指令链路：端到端延迟、确认率、超时、丢弃和安全门禁。
4. 单车诊断：进程、网络、Trace、日志、配置变更和最近发布。
5. 采集系统：Agent/Collector 丢弃、队列、WAL、传输失败和成本。

### 7.3 告警分级

```text
P0: 控制链路大面积不可用、车辆安全状态异常
P1: 关键车队或核心云服务不可用、视频/指令 SLO 持续违反
P2: 单车持续异常、版本回归、网络质量恶化
P3: 采集器容量、单点 Agent、低影响配置或数据质量问题
```

告警必须携带证据入口，而不是只发送一条错误字符串：

```text
incident_id
vehicle_scope
service_scope
time_window
trace_query
metric_query
log_query
deployment_version
recent_changes
recommended_runbook
```

## 8. DSH（DeepSeek Harness）优化控制面

可以利用 DSH 优化车-云-端整个链路，但“优化”是通过观测、诊断、建议、验证和受控执行完成，不是让大模型进入车辆硬实时控制回路。

DSH 是 DeepSeek 官方开源的 Agent Harness，基于 Cordis 插件系统组合模型、工具、Skills、会话、沙箱、存储、循环、调度和 UI。其仅追加会话日志可用于检查、恢复、分叉和回放分析过程。当前版本仍是 Developer Preview，官方明确提示核心插件和 API 会持续演进，因此生产 PoC 必须锁定 DSH、插件和模型版本，不能直接跟随浮动最新版。

DSH 在本方案中负责：

- 故障优化：关联 Trace、Metric、Log、拓扑、配置和发布，缩短 MTTD/MTTR。
- 性能优化：发现视频首帧、指令确认和服务调用的主要耗时阶段。
- 容量优化：分析 CPU、网络、队列、Broker、ZLMediaKit 和 Collector 饱和趋势。
- 配置优化：生成采样率、超时、连接池、队列和灰度范围建议。
- 发布优化：比较发布前后 SLO，给出继续、暂停或回滚建议。
- 运维优化：把历史事故固化为可回放的 Session、Skill 和 Runbook。
- 知识治理：将确认过的设计决策、实施状态、验证结果和阻塞项及时写入版本化文档。

DSH 不负责：

- 采集 eBPF 原始数据或保存生产 Trace。
- 取代 Tempo、Prometheus、Loki、DeepFlow、DataBuff 或 Grafana。
- 在 ROS 2 控制线程、CAN 下发、视频实时处理等硬实时路径内同步调用模型。
- 直接控制车辆、绕过安全门禁或根据模型结论自主执行高风险动作。

### 8.1 DSH 插件化落地

仓库已提供与本节对应的 [DSH Integration Pack](dsh/README.md)，包括
`vehicle-cloud-observability.profile.json`、Incident/Query/Query Response/Evidence/Action/Session
六类 JSON Schema 和依赖无关校验脚本。该 Pack 固化的是能力边界和适配器契约，
不是 DSH/Cordis runtime 或生产插件已经部署的证明；当前 profile 的
`design_status=implemented`、`runtime_status=unverified`。

建议建立独立的 `vehicle-cloud-observability` Profile，通过 Cordis 配置挂载能力：

| DSH 能力 | 本方案插件/实现 | 约束 |
|---|---|---|
| Model | 企业私有 DeepSeek 或兼容模型端点 | 请求脱敏、出口审计、模型版本固定 |
| Tools | Tempo、Prometheus、Loki、DeepFlow、DataBuff 查询插件 | 首期只读、限制时间窗和车辆范围 |
| Change Tools | 发布、配置中心、证书、CMDB、Broker Session 查询插件 | 查询与执行使用不同身份 |
| Vehicle Health | 通过车云诊断网关读取进程、网络、Agent、WAL 状态 | 禁止 DSH 直接 SSH 车辆 |
| Skills | 视频 QoE、MQTT、ROS 2、CAN、ZLMediaKit、发布和 Runbook | 代码评审、版本化、带适用范围 |
| Sessions/Storage | 仅追加事故证据、分析轨迹、审批和执行结果 | 加密、保留周期、支持历史回放 |
| Sandbox | 隔离的只读分析工作区 | 禁止挂载生产密钥和宿主机写目录 |
| Loop/Scheduling | 告警触发分析、发布后验证、周期巡检 | 有并发、预算、超时和熔断限制 |
| UI | War Room、证据审核和审批入口 | SSO、RBAC、操作留痕 |
| OTel Telemetry | DSH Session Telemetry OTLP Logs | 默认关闭正文上报，启用前先配置脱敏和授权 |

官方 DSH Session Telemetry 可以通过 OTLP 导出结构化会话日志，但它不等于完整的 Agent Trace。首期只要求记录 Session、工具调用、耗时、状态和证据引用；Prompt、模型回复、工具参数和结果正文默认不出域。若后续引入社区 GenAI Trace 插件，必须单独完成兼容性、安全和数据泄露评审。

### 8.2 专项 Multi-Agent

Multi-Agent 不是让多个模型自由讨论，而是按固定职责、输入和输出并行取证，由协调 Agent 合并结论：

| Agent | 责任 | 主要证据 |
|---|---|---|
| Incident Coordinator | 确认范围、拆分任务、合并时间线和最终报告 | 告警、拓扑、各 Agent 证据 |
| Vehicle Diagnostics | 检查车端进程、网络、配置加载、资源和 Agent 健康 | 车辆健康、车端日志、配置快照 |
| Network Correlation | 分析 DNS、TCP/TLS、RTT、重传、丢包和链路切换 | DeepFlow、eBPF、网络指标 |
| Video QoE | 定位采集、编码、RTSP、ZLM、WebRTC 和渲染瓶颈 | 视频 Trace、QoE、ZLM 指标 |
| Command Reliability | 定位 API、MQTT/TCP、ROS 2、CAN 和 ACK 异常 | `command.id` Trace、Broker、车端事件 |
| Cloud/Change Analysis | 对照云服务、发布、配置、证书和容量变化 | 发布记录、配置 Diff、云端指标 |
| Evidence Reviewer | 检查证据是否支持结论，识别冲突和缺失数据 | 查询引用、时间范围、数据新鲜度 |

DSH 官方 Agent Teams 当前属于实验性、显式启用能力。PoC 可先使用 Coordinator 调度受限 Subagent 或由外部工作流编排，不应让生产方案强依赖尚未稳定的私有 Agent Teams 接口。

所有专项 Agent 只能返回结构化证据和假设，不得直接调用生产写工具。Coordinator 在 Evidence Reviewer 完成复核前不能输出 `high` 置信度结论。

### 8.3 DSH 的输入

DSH 不直接消费未经处理的 eBPF 原始流量，而接收结构化 Incident Envelope：

```json
{
  "incident_id": "inc-20260825-001",
  "severity": "P1",
  "route_type": "command",
  "vehicle_scope": ["vehicle_hash_001"],
  "time_window": {
    "start": "2026-08-25T10:00:00Z",
    "end": "2026-08-25T10:10:00Z"
  },
  "symptoms": ["command_ack_timeout"],
  "trace_ids": ["trace-..."],
  "service_versions": ["gateway@..."],
  "recent_changes": ["release-..."]
}
```

除告警外，还可以由以下事件创建 Envelope：

- 新版本发布完成，需要观察 15～30 分钟 SLO。
- 车辆网络切换、进程重启、证书轮换或配置重载。
- 周期巡检发现容量、错误率或数据质量趋势异常。
- 人工输入车辆、会话、命令或视频 Session 范围。

### 8.4 DSH 的只读工具

建议先提供 Profile 中注册的十个只读适配器，统一返回带时间范围和来源的证据。
工具名以 Profile 的 registry 为唯一来源，不再同时维护未注册的查询别名：

| 工具 | 查询内容 |
|---|---|
| `query_command_path` | 指令 Trace、阶段耗时、错误和收发/执行关系 |
| `query_media_path` | 视频 Trace、阶段耗时、RTP/WebRTC/渲染错误和会话关系 |
| `query_broker_session` | MQTT Client 连接、订阅、发布/确认和会话状态 |
| `query_zlm_stream` | ZLMediaKit 流、读者、码率、输入包年龄和 API 错误 |
| `query_ebpf_network` | TCP/UDP、RTT、重传、RTO、队列和调度旁证 |
| `query_vehicle_health` | 车端进程、资源、Agent/WAL 和 eBPF 能力 |
| `query_topology` | 车端、云端、Broker、ZLMediaKit 依赖关系 |
| `query_deployments` | 版本、发布、配置、证书和变更时间线 |
| `query_gateway_state` | DC/FDC 等网关启用状态、实例、Client ID、订阅和加载时间 |
| `query_runbook` | 已审批的排障步骤和回滚条件 |

每个工具都必须：

- 限制查询时间窗、车辆范围和返回大小。
- 记录调用者、参数摘要和结果引用。
- 默认只读、脱敏和最小权限。
- 返回原始查询、数据时间和数据源，支持人工复核。
- 标注数据新鲜度、缺口和不确定性，禁止把“无日志”直接解释为“组件正常”。
- 使用结构化参数，不允许模型拼接任意 Shell、SQL、PromQL 或 LogQL 后直接执行。

### 8.5 优化闭环

```text
Observe
  -> Diagnose
  -> Propose
  -> Simulate/Check
  -> Approve
  -> Execute
  -> Verify
  -> Rollback/Learn
```

各阶段要求：

1. `Observe`：接收告警，确定车辆、服务、版本和时间范围。
2. `Diagnose`：并行拉取 Trace/Metric/Log/拓扑/变更，构建时间线并证伪假设。
3. `Propose`：输出一个或多个按风险排序的配置、容量、发布或 Runbook 建议。
4. `Simulate/Check`：执行配置语法校验、依赖检查、影响范围计算、台架回放或数字孪生验证。
5. `Approve`：根据风险等级进入人工审批，P0/P1 和车辆相关动作不得自动批准。
6. `Execute`：由独立受控执行器使用短期凭证执行，DSH 只提交已审批任务。
7. `Verify`：比较动作前后 SLO、错误率、影响车辆和新告警。
8. `Rollback/Learn`：不满足退出条件则回滚；将证据、结果和新规则写入事故库。

DSH 输出应采用固定格式：

```text
结论：最可能的根因
证据：查询结果、时间戳、Trace/Log/Metric 引用
排除项：已验证但不成立的假设
影响：车辆、服务、版本和时间范围
建议：下一步 Runbook 和预期结果
风险：可能影响的链路或安全边界
置信度：high / medium / low
```

### 8.5.1 设计文档与进度治理

DSH 会话日志用于恢复和回放分析过程，但不能作为设计和实施状态的唯一事实源。已经确认的方案、
接口、约束和验收结果必须及时写入仓库中的版本化文档；禁止仅保留在聊天记录、临时 Prompt、
本地控制台或某个 Agent 的短期上下文中。

文档和进度更新遵守以下规则：

1. 开始实施前，记录目标、范围、非目标、影响模块、风险和验收方法。
2. 设计决策确认后立即更新设计文档，不等到全部代码完成后再补写。
3. 每完成一个可独立验证的里程碑，更新状态和验证结果；长任务不能只在最终结束时一次性更新。
4. 代码实现、配置部署、现场验证和生产验收分别记录，不能将“设计完成”写成“已上线”。
5. 发现新风险、数据矛盾或实施阻塞时，及时记录阻塞原因、已有证据、负责人和下一步。
6. 验证失败时保留失败结果和条件，不覆盖为模糊的“待优化”；回退或废弃方案也必须记录原因。
7. DSH、专项 Agent 和人工工程师引用同一份文档状态，输出报告前先检查文档更新时间和代码版本。
8. 设计文档更新应进入正常代码评审和版本控制流程，避免多个 Agent 并行工作时产生事实分叉。

统一状态枚举：

```text
proposed       已提出，尚未评审
approved       设计已确认，尚未实施
in_progress    正在实施
implemented    代码或配置已完成，尚未完成全部验证
verified       已通过约定的静态、集成或现场验证
blocked        存在明确阻塞，需要外部输入或环境变化
deferred       已评审但延期，保留原因和恢复条件
rejected       已否决或废弃，保留证据和替代方案
```

每个进度项至少记录：

```text
work_item
status
owner
updated_at
scope
changed_artifacts
verification
known_gaps
next_step
```

DSH 可以自动生成进度更新草稿、检查文档与代码是否一致，并提示长时间未更新的项目；但生产状态、
验收结论和高风险变更完成状态必须由工具证据或人工审批确认，不能由模型自行宣告。

### 8.6 三个典型分析问题

视频首帧变慢：

1. DSH 先按 `video.session.id` 查询首帧 Trace。
2. 比较 `capture`、`encode`、RTSP 上行、ZLMediaKit 和 WebRTC 信令 Span。
3. 查询同时间窗口的丢包、RTT、编码队列和 ZLMediaKit CPU。
4. 对照最近版本和同平台正常车辆。
5. 输出“编码拥塞、车云网络、ZLM 处理或浏览器渲染”的证据排序。

指令确认超时：

1. 按 `command.id` 查询 API、MQTT publish、车端 receive、ROS execute 和 CAN send。
2. 判断延迟发生在发布前、Broker、网络、车端接收、ROS 执行还是 CAN。
3. 检查 MQTT reconnect、Client ID、订阅状态、网络切换和安全门禁。
4. 对照同一车辆前后时间段以及同批次车辆。
5. 只推荐经过审批的重连、配置回滚或流量切换动作。

DC 失败而 FDC 没有日志：

1. 现象是 `dc-mqtt-gw` 持续连接拒绝，而 `ziot-fdc-gw` 没有启动、连接或错误日志；禁用 DC 后，将 FDC 禁用再启用，FDC 才正常收取主题。
2. 该现象不能直接证明“只能连接一个”，也不能仅凭 DC 错误断定后续 FDC 被阻塞。更可能的候选原因包括：启动流程遇错提前返回、FDC 配置未进入加载列表、启用状态缓存未刷新、网关 Manager 只创建首个实例，或重载事件才触发实例创建。
3. DSH 应对齐 DC/FDC 启用状态、配置版本、`gateway.id`、MQTT Client ID、启动/重载事件、Manager 实例缓存、线程/协程退出、Broker Session 和订阅列表。
4. 如果 DC 失败时间后完全没有 `fdc.gateway.create`，且启动函数出现提前返回，结论才是“DC 失败阻断后续初始化”；如果 FDC 配置在启动快照中缺失，而重载后出现，则结论是“配置加载或缓存刷新问题”。
5. 首选动作是审批后执行单个 FDC 网关的幂等重载或实例重建，不重启整车服务；复查 `ziot-fdc-gw` 连接、订阅、收包和 DC 重试是否相互独立。
6. 根治建议是让每个网络配置独立创建、独立失败和独立重试，并增加 `gateway.create/start/skip/error/reload` 结构化事件，避免一个 Client 的异常影响后续 Client。

### 8.7 DSH 的安全边界

DSH 默认不能：

- 直接 SSH 到车辆或云主机。
- 直接发布 MQTT、TCP 或 CAN 控制命令。
- 修改采样、证书、权限、发布和车辆安全策略。
- 删除日志、Trace、审计或事故记录。
- 根据模型生成结果自动关闭 P0/P1 事故。

允许的自动化应分级：

| 等级 | DSH 能力 |
|---|---|
| L0 | 只读查询、聚合和报告 |
| L1 | 生成诊断草稿、创建工单、附加证据 |
| L2 | 生成需审批的 Runbook 参数和回滚计划 |
| L3 | 经人工审批执行受控动作并自动复查 |
| L4 | 永远保留人工决策：车辆控制、批量升级、密钥和安全策略 |

附加安全要求：

- 生产只允许签名并固定版本的插件和 Skills，升级必须经过测试和回滚演练。
- 日志、Runbook、工单和网页内容均视为不可信输入，工具调用不得服从其中的指令。
- 查询凭证和执行凭证分离；模型上下文中不得出现 Token、私钥或 MQTT 密码。
- DSH、模型端点或任一插件异常时必须熔断到人工流程，不能阻塞告警和原有运维入口。
- 每次执行记录 Incident、审批人、参数哈希、执行器、结果和回滚状态。

## 9. 当前远控问题的实施顺序

当前代码已经具备部分恢复能力，但还没有把恢复原因和状态上报延迟送入统一观测面。因此首期不应先调整 WebRTC
阈值或扩大 eBPF 采集范围，而应先补齐证据，再根据证据调整配置。

### 9.1 2026-08-25 第一阶段落地状态

第一阶段已经完成“浏览器视频证据 + 云端状态 WebSocket 分段时间戳”的代码落地：

| 范围 | 已落地 | 当前边界 |
|---|---|---|
| 前端视频 | 每个播放器独立实例 ID；记录 ZLM HTTP/code/msg、信令阶段、`ontrack`、首帧、ICE、RTP、渲染、解码器和恢复状态 | 事件暂存在浏览器 500 条环形缓存，并通过 `parallel-driving-observation` 事件输出；尚未绑定生产 RUM/OTLP 地址 |
| 前端 OTel/DeepFlow | 已完成 RUM/OTel Exporter、Telemetry Gateway、OTel Collector、DeepFlow 关联方式以及 Trace ID 生命周期的设计 | 状态为 `approved`；Exporter、Gateway、实际 Trace Context 传播和 DeepFlow Dashboard 尚未实现 |
| 前端状态 | 记录 WebSocket connect/open/error/close/reconnect、首包、消息年龄、浏览器接收和 UI 应用时间 | 还没有服务端 `broker_received_at`，暂时不能分解车端到 Broker 与 Broker 到 EventBus |
| 云端状态 | WebSocket 活跃会话、开关连接、EventBus 接收、入队、发送、订阅错误和 sink failure 指标；消息附带三个云端时间戳 | Micrometer 指标已注册，但当前仓库的 Actuator 依赖和 Prometheus exposure 配置仍为注释状态，Grafana 抓取尚未验收 |
| ZLMediaKit | 前端已记录 `/index/api/webrtc` 请求结果和业务错误 | 流列表、输入包年龄、输入/输出码率、线程负载和服务日志尚未采集 |
| DeepFlow/eBPF | 已明确首批网络观测范围 | Agent、Collector、存储和 Dashboard 尚未部署 |
| DSH | 已定义只读证据模型和安全边界 | 不在第一阶段接入生产分析或执行 |

代码位置：

```text
zeron-cloud-web/
  src/modules/parallel-driving-manager-ui/components/WebRtcPlayer.vue
  src/modules/parallel-driving-manager-ui/components/VideoCell.vue
  src/modules/parallel-driving-manager-ui/utils/observability.ts
  src/modules/parallel-driving-manager-ui/utils/websocket.ts
  src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue

jetlinks-community/
  jetlinks-manager/parallel-driving-manager/src/main/java/
    org/jetlinks/community/parallel/driving/metrics/ParallelDrivingLatencyMetrics.java
    org/jetlinks/community/parallel/driving/websocket/ParallelDrivingWebSocketHandler.java
```

### 9.1.1 前端状态 WebSocket 埋点时间语义

状态消息中的时间戳来自不同设备或服务进程，不能默认处于同一个时钟域。当前约定如下：

| 字段 | 语义 | 是否可作为耗时 |
|---|---|---|
| `occurredAt` | 浏览器记录事件时生成的 ISO 墙上时间 | 仅用于排序和对齐日志 |
| `durationMs` | 同一浏览器上下文内用 `performance.now()` 计算的耗时 | 可以；包括 `open -> first_message` 和 `browser_received -> browser_applied` |
| `localDurationMs` | 明确标识同一浏览器单调时钟域内的耗时 | 可以；避免与跨机器耗时混淆 |
| `crossDomainDurationMs` | 车、云、浏览器跨时钟域耗时 | 当前固定为 `null` |
| `browserToAppliedMs` | 浏览器收到状态到 RAF 应用状态的本地耗时 | 可以 |
| `eventbusToQueueMs` | EventBus 接收至 WebSocket 入队，服务端同一时钟域 | 可以，但需校验非负 |
| `queueToSendMs` | WebSocket 入队至发送，服务端同一时钟域 | 可以，但需校验非负 |
| `vehicleToEventbusMs` | 车端时间戳与 EventBus 时间戳的差值 | 仅在完成时钟同步且结果可信时可用 |
| `*ClockOffsetMs` / 旧 `*ClockDeltaMs` | 两个时钟域的墙上时间偏移 | 不能当作网络延迟 |
| `*ClockOffsetBaselineMs` | 当前 WebSocket 连接首个有效偏移样本 | 仅用于连接内相对比较 |
| `*ClockOffsetDeltaMs` | 当前偏移减去连接基线 | 可以用于发现偏移突变，不能当作端到端延迟 |
| `sendToBrowserMs` | 服务端发送至浏览器接收 | 当前为 `null`，因为尚未完成时钟同步 |

浏览器内部的间隔统一使用 `performance.now()`，不能使用 `Date.now()` 计算持续时间。
ISO `occurredAt` 可以继续使用 `new Date().toISOString()`，但它不参与浏览器耗时计算。
车端、服务端和浏览器不以时钟同步为前置条件；`crossDomainDurationMs` 必须为 `null`，
并附带 `crossDomainDurationUnavailableReason: "clock_domain_unsynchronized"`。
旧 `durationUnavailableReason` 暂时保留用于兼容现有监听器。为避免顶层 `durationMs`
被误解，状态事件同时提供 `localDurationMs`、`crossDomainDurationMs` 和
`crossDomainDurationUnavailableReason`；其中浏览器接收与 RAF 应用还记录
`browserReceivedPerfMs`、`browserAppliedPerfMs`。

固定时钟偏移和偏移异常是两个概念。当前实现按每次状态 WebSocket 连接记录首个有效偏移
作为基线，连接重建时清空基线；后续样本相对基线变化达到 `1000ms` 时设置
`clockOffsetAnomalySuspected=true` 和 `clockOffsetStable=false`。该阈值用于发现“稳定约
37 秒偏移之外又多出约 1 秒以上变化”，不表示时钟已同步，也不能直接定位变化来自网络、
排队还是某个节点校时。`clockOffsetObserved` 只表示存在可比较的墙上时间字段，
`clockDomainsSynchronized` 仍固定为 `false`。`clockSkewSuspected` 暂时作为
`clockOffsetAnomalySuspected` 的兼容别名保留，新监听器不得再用它判断节点是否同步。
当前日志中的
`serverToBrowserClockDeltaMs: -2420` 和 `vehicleToEventbusClockDeltaMs: -36969` 应解释为
时钟偏移，不是 2.42 秒或 36.969 秒的消息传输耗时。

当前偏移字段统一采用“后一个时间源减前一个时间源”的方向：

```text
serverToBrowserClockOffsetMs = browserReceivedAtMs - websocketSentAtMs
vehicleToEventbusClockOffsetMs = eventbusReceivedAtMs - vehicleTimestampMs
vehicleToBrowserAppliedClockOffsetMs = browserAppliedAtMs - vehicleTimestampMs
```

因此负值表示后一个时间源的墙上时间早于前一个时间源；例如
`serverToBrowserClockOffsetMs=-2457` 表示服务端时间相对浏览器快约 2.457 秒，
`vehicleToBrowserAppliedClockOffsetMs=-39286` 表示车端时间相对浏览器快约 39.286 秒。
这只能说明时钟未对齐，不能说明消息经历了负延迟。只有同一时钟域或完成时钟同步后，
才允许把跨阶段差值用于延迟分析；本系统默认不依赖这种同步。

#### 现场日志字段解释示例

以下表格采用 HTML `border` 表格，便于复制到飞书后保留边框和字段结构。
示例来源于 `status_ws_message_sample` 事件：

```text
serverToBrowserClockOffsetMs: -115
vehicleToEventbusClockOffsetMs: -36967
vehicleToEventbusClockOffsetBaselineMs: -36964
vehicleToEventbusClockOffsetDeltaMs: -3
queueToSendMs: 64
```

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>字段</th>
      <th>当前值</th>
      <th>含义</th>
      <th>用途 / 判断</th>
    </tr>
  </thead>
  <tbody>
    <tr><td><code>browserReceivedAtMs</code></td><td>1787706690168</td><td>浏览器收到消息时的墙上时间，Unix 毫秒</td><td>用于和服务端日志对齐，不用于浏览器耗时计算</td></tr>
    <tr><td><code>browserReceivedPerfMs</code></td><td>96076</td><td>浏览器收到消息时的单调时钟值</td><td>用于计算浏览器内部耗时</td></tr>
    <tr><td><code>clockDomainsSynchronized</code></td><td>false</td><td>车端、云端、浏览器不假设时钟同步</td><td>跨设备耗时不直接计算</td></tr>
    <tr><td><code>clockOffsetObserved</code></td><td>true</td><td>已观察到可比较的墙上时间字段</td><td>表示偏移数据存在</td></tr>
    <tr><td><code>clockOffsetStable</code></td><td>true</td><td>当前偏移相对本次连接基线稳定</td><td>当前没有明显时钟跳变</td></tr>
    <tr><td><code>clockOffsetAnomalySuspected</code></td><td>false</td><td>偏移变化未达到异常阈值</td><td>未发现超过 1000ms 的偏移突变</td></tr>
    <tr><td><code>clockOffsetAnomalyThresholdMs</code></td><td>1000</td><td>偏移异常判断阈值</td><td>相对基线变化达到 1 秒才报警</td></tr>
    <tr><td><code>clockSkewSuspected</code></td><td>false</td><td>兼容旧字段，等价于偏移异常判断</td><td>不表示时钟是否已同步</td></tr>
    <tr><td><code>crossDomainDurationMs</code></td><td>null</td><td>跨车端、云端、浏览器的耗时</td><td>时钟未同步，保持为空</td></tr>
    <tr><td><code>crossDomainDurationUnavailableReason</code></td><td><code>clock_domain_unsynchronized</code></td><td>跨域耗时不可用的原因</td><td>说明是主动不计算，不是数据丢失</td></tr>
    <tr><td><code>durationUnavailableReason</code></td><td><code>clock_domain_unsynchronized</code></td><td>旧版兼容字段</td><td>兼容已有日志消费者</td></tr>
    <tr><td><code>localDurationMs</code></td><td>null</td><td>浏览器内部单调时钟耗时</td><td>本条是消息采样事件，没有执行 RAF 应用，因此为空</td></tr>
    <tr><td><code>eventbusToQueueMs</code></td><td>0</td><td>EventBus 收到消息到进入 WebSocket 队列的耗时</td><td>服务端内部耗时，当前正常</td></tr>
    <tr><td><code>queueToSendMs</code></td><td>64</td><td>WebSocket 入队到发送的耗时</td><td>服务端排队 / 发送耗时</td></tr>
    <tr><td><code>eventbusToSendMs</code></td><td>64</td><td>EventBus 收到到 WebSocket 发送的总耗时</td><td>服务端链路总耗时</td></tr>
    <tr><td><code>sendToBrowserMs</code></td><td>null</td><td>服务端发送到浏览器接收的耗时</td><td>跨时钟域，当前不计算</td></tr>
    <tr><td><code>serverMonotonicTimingAvailable</code></td><td>true</td><td>服务端支持单调时钟耗时</td><td>服务端 duration 字段具备分析条件</td></tr>
    <tr><td><code>serverToBrowserClockDeltaMs</code></td><td>-115</td><td>浏览器接收时间减服务端发送时间</td><td>表示墙上时间差，不是确定的网络延迟</td></tr>
    <tr><td><code>serverToBrowserClockOffsetBaselineMs</code></td><td>-115</td><td>本次 WebSocket 连接的首次偏移基线</td><td>用于后续比较</td></tr>
    <tr><td><code>serverToBrowserClockOffsetDeltaMs</code></td><td>0</td><td>当前偏移相对基线的变化量</td><td>0 表示没有变化</td></tr>
    <tr><td><code>serverToBrowserClockOffsetMs</code></td><td>-115</td><td>当前云端到浏览器的墙上时间偏移</td><td>只能用于偏移观察，不能当网络耗时</td></tr>
    <tr><td><code>vehicleToEventbusClockDeltaMs</code></td><td>-36967</td><td>EventBus 时间减车端时间</td><td>表示车端约领先 EventBus 36.967 秒</td></tr>
    <tr><td><code>vehicleToEventbusClockOffsetBaselineMs</code></td><td>-36964</td><td>本次连接的车端偏移基线</td><td>用于判断偏移是否突变</td></tr>
    <tr><td><code>vehicleToEventbusClockOffsetDeltaMs</code></td><td>-3</td><td>当前车端偏移相对基线变化 -3ms</td><td>变化很小，属于稳定范围</td></tr>
    <tr><td><code>vehicleToEventbusClockOffsetMs</code></td><td>-36967</td><td>当前车端与 EventBus 的墙上时间差</td><td>约固定 -37 秒，不是消息延迟</td></tr>
    <tr><td><code>vehicleToEventbusMs</code></td><td>null</td><td>车端到 EventBus 的跨设备耗时</td><td>时钟未同步，因此不作为真实延迟使用</td></tr>
    <tr><td><code>vehicleToBrowserClockOffsetMs</code></td><td>-37017</td><td>浏览器时间减车端时间</td><td>表示车端约领先浏览器 37.017 秒</td></tr>
    <tr><td><code>vehicleToBrowserMs</code></td><td>null</td><td>车端到浏览器的跨设备耗时</td><td>时钟未同步，因此不计算</td></tr>
    <tr><td><code>propertyCount</code></td><td>1</td><td>本条状态消息包含的属性数量</td><td>用于确认消息内容是否为空或异常</td></tr>
  </tbody>
</table>

该示例的测试结论为：状态消息已正常收到，EventBus 入队没有阻塞，服务端发送耗时约
`64ms`，车端约固定领先 37 秒且当前偏移稳定；该事件本身没有视频黑屏证据。
测试应将 `status_ws_message_sample` 用于验证消息接收和服务端发送链路，将
`status_ws_browser_applied` 用于验证 `localDurationMs >= 0`、`browserToAppliedMs >= 0`
以及 `crossDomainDurationMs = null`。

`status_ws_message_sample` 是每条连接内的节流采样，`value` 是该连接的消息计数，不是全局
序号；WebSocket 重连后计数会重新开始。`status_ws_last_message_age` 也是浏览器单调时钟
计算的本地年龄，不能与服务端时间戳混用。

顶层 `cockpitId` 在本地结构化出口统一规范为字符串或 `null`。监控模式、未接管或上下文
尚未加载时不得输出 `undefined`、空字符串等多种缺失形式；这只改善事件聚合和后续
OTel/DeepFlow Schema 稳定性，不改变 WebSocket 连接参数、视频播放或重连逻辑。

#### 2026-08-25 现场 `JOYSTICK_IDLE_TIMEOUT` 分析

现场日志 `/Users/minyi/Downloads/ztd_cloud_driving_20260825134823.log` 共出现 7 条包含
`JOYSTICK_IDLE_TIMEOUT` 的记录，其中真正的 `MRC 0 -> 2` 触发有 3 次；另外 4 条是
MRC 来源变化或恢复记录，不能按 4 次新的超时计算。

| 现场时间（日志 epoch 秒） | 车端证据 | 同窗口其他证据 | 当前判断 |
|---|---|---|---|
| `1787647373.732` | `detecting loss gap=300ms`，约 `595ms` 后 `MRC1 triggered gap=895ms`，随后 `0 -> 2` | 后续 `remotejoystick` 统计降为 `0 msg/s`；`Failed to report chassis_status`；`cloudLinkPing` 回复超时并等待重连 | 更接近车云连接或链路失效，但仍缺云端接收/转发证据 |
| `1787649278.972` | `detecting loss gap=351ms`，约 `568ms` 后 `MRC1 triggered gap=919ms`，随后 `0 -> 2` | `1787649278.629` 发出 `cloudLinkPing`；稍后出现 `cloudLinkPing rtt_ms=2041`，并在 `1787649280.042` 才继续收到摇杆消息 | 故障窗口存在明显延迟，可能在云端排队、网络瞬时异常或车端处理排队，当前不能唯一归因 |
| `1787652176.884` | `detecting loss gap=338ms`，约 `557ms` 后 `MRC1 triggered gap=896ms`，随后 `0 -> 2` | `1787652177.299` 的 `cloudLinkPing rtt_ms=77`；但 `remotejoystick` 随后多个 5 秒窗口均为 `0 msg/s`，约 36 秒后才恢复 | 车云 TCP 探活正常但摇杆消息没有继续进入 handler，更像发送端停发、云端未转发或特定消息通道异常；不能用 ping 正常排除这些情况 |

车端实现的实际判定是：在 R 模式下，约每 `100ms` 检查一次
`last_joystick_steady_ms_`；消息间隔达到 `300ms` 进入检测，连续检测达到阈值后约
`895~919ms` 触发 MRC1。这个时间戳在 `handle_remotejoystick()` 入口更新，因此它表示
“车端 handler 已处理的最后一帧”到当前的间隔，不等于 TCP 数据包已经到达车端内核的时间。

本次证据不能直接得出“云端消息阻塞”的结论。必须区分以下三类故障：

```text
驾驶舱/手柄未发送或发送线程暂停
  -> 云端已收到，但未转发、排队或丢弃
    -> 车端 TCP 已收到，但收包线程尚未完成解密/解析/分发
      -> 已进入 handler，但 ROS publish 或后续执行阻塞
```

当前日志只能可靠证明 `remotejoystick` 进入车端 handler 的时间、MRC 检测结果和
`cloudLinkPing` 的独立探活结果，不能证明消息在上述哪一个边界丢失或排队。尤其是：

- `cloudLinkPing` 与 `remotejoystick` 即使共用车云连接，也不是同一业务消息；ping 正常只说明
  该时刻探活请求能够完成，不证明摇杆帧按期发送、转发和处理。
- 第二次事件中的 `2041ms` ping RTT 是延迟风险证据，但不能区分云端排队、网络抖动和车端
  处理阻塞。
- 第三次事件中 ping RTT 为 `77~126ms`，但摇杆仍长时间为 `0 msg/s`，说明“整体 TCP
  探活正常”与“remotejoystick 业务流正常”不是等价条件。
- payload 内的 `timestamp` 与车端日志时间存在约 37 秒固定偏移，当前不能把两者相减当作
  网络延迟；必须使用各节点 monotonic 时间和统一关联字段。

要完成明确归因，驾驶舱、云端和车端必须对同一帧记录：

```text
message_id
seq
trace_id / correlation_id
remoteSessionId
cockpit_send_monotonic
cloud_receive_monotonic
cloud_forward_monotonic
vehicle_tcp_receive_monotonic
vehicle_decrypt_completed_monotonic
vehicle_parse_completed_monotonic
vehicle_handler_start/end_monotonic
vehicle_ros_publish_start/end_monotonic
drop_or_expire_reason
```

推荐排查顺序：

1. 先查驾驶舱发送计数、发送线程调度、发送失败和发送队列，确认故障窗口是否仍在产生
   `seq`。
2. 再用同一 `message_id/seq` 查云端接收、排队、转发和过期/丢弃记录。
3. 再查车端 `_receive_message()` 的收包、解密、JSON parse 和 `_process_message()` 进入时间。
4. 最后查 `handle_remotejoystick()`、ROS `publish()`、ROS executor、CPU 调度和 socket 队列。
5. 用 `cloudLinkPing`、TCP RTT、重传、RTO、发送/接收队列做旁证，不把它们当作
   `remotejoystick` 的替代探针。

当前最小补点应放在车端 `CloudDrivingClient::_receive_message()`、
`_process_message()`、`_handle_invoke_function()` 和
`cloud_driving_vehicle.cpp::handle_remotejoystick()`。现阶段不建议直接把监听线程改成
异步业务队列：这涉及控制时序和安全行为，应先取得阶段耗时和丢弃证据，再单独评审解耦方案。

#### 2026-08-27 `remotejoystick` 端到端分段埋点落地

本阶段补齐最可能导致 `JOYSTICK_IDLE_TIMEOUT` 的云端 latest-only 写出，以及车端
TCP body receive、解密、JSON parse、同步分发、handler 和 ROS publish，不改变 MRC 判定、
控制消息内容或 ROS QoS。

云端已落地：

- 自定义消息转发显式保留原始 `messageId`，保留 `seq`，并传播 `correlationId`；
  上游未提供时 `correlationId` 回退为 `messageId`。
- latest-only 记录在途发送开始时间、在途 `messageId`、pending 入队时间、pending age、
  发送完成耗时、完成结果和累计 coalesced 数。
- 在途超过 `300ms` 时输出限频的 `[remotejoystick-observation] inflight_slow`；
  最终完成仍超过阈值时输出 `send_completed_slow`。
- 新增 Micrometer 指标：

```text
parallel_driving.remotejoystick.dedup_dropped
parallel_driving.remotejoystick.mailbox_coalesced
parallel_driving.remotejoystick.inflight
parallel_driving.remotejoystick.mailbox_pending_age
parallel_driving.remotejoystick.send_completion_latency
parallel_driving.remotejoystick.inflight_slow
parallel_driving.remotejoystick.inflight_slow.duration
```

`parallel-driving.control.latest-only=true` 时，同一房间只有一帧可以在途。若设备发送器
完成信号长时间不返回，后续帧只会覆盖 pending，不会并发写出；因此
`inflight_slow + mailbox_coalesced` 同时增长是“云端 latest-only 被在途发送压住”的直接
证据。`sendAndForget` 完成最终对应当前 TCP 实现的 `socket.write(buffer, callback)`
成功，只能证明云端写调用完成，不能证明车端 TCP 收到完整消息或 handler 已执行。

当前 TCP 层已补充连接级观测，日志事件包括：

```text
[tcp-connection] device_bound / replace_socket / exception / close / closed
[tcp-write] write_start / write_queue_full / write_complete / write_complete_slow
            / write_error / write_throwable / write_cancel
```

日志包含 `writeId`、`clientId`、认证后的 `deviceId`、远端地址、连接代际、连接存活时间、payload 字节数、
写队列是否已满和 `writeDurationMs`。其中 `write_complete` 是 Vert.x
`socket.write` 回调完成点，表示该写请求已被底层 TCP 实现接受或失败；仍不等于车端长度头、
完整 body 或业务 handler 已到达。默认 `write_complete_slow` 阈值为 `300ms`，可通过
JVM 参数 `gateway.tcp.network.write-slow-ms` 调整，设为 `0` 关闭慢写告警。

设备身份在首条消息认证后绑定到连接对象。现场应按
`deviceId + clientId + remoteAddress` 区分连接代际：同一车辆出现多个 `clientId`，或旧连接
长期没有 `closed/exception` 但 `write_complete` 持续变慢时，应重点检查双 5G 切换后的旧
TCP 连接黑洞、云端 session 路由和连接替换。

车端 `cloud_driving_client.cpp` 和 `cloud_driving_vehicle.cpp` 已落地：

- 接收层按采样或异常输出 `transport_dispatch`，记录 `frame_bytes`、`body_receive_us`、
  `decrypt_us`、`parse_us`、`parse_to_dispatch_us` 和 `transport_us`。
- 记录相邻 remotejoystick 在监听线程开始分发的 `listener_dispatch_gap_us`；达到
  `joystick_msg_timeout_ms` 时强制告警，并携带前后 `message_id/source_seq`。该字段包含
  前一同步 handler、其他消息处理和当前收包过程，不是纯网络耗时。
- 正常帧按 `remotejoystick_log_sample_every` 采样，默认每 `50` 帧记录
  `observation_seq/message_id/source_seq/correlation_id/payload_bytes`。
- body receive、解密、JSON parse 和 parse-to-dispatch 累计达到
  `remotejoystick_slow_transport_ms` 时强制告警，默认 `10ms`。
- handler 总耗时达到 `remotejoystick_slow_handler_ms` 时强制告警，默认 `10ms`；
  记录 `handler_us/publish_us/result`。
- MRC1 触发时补充
  `last_publish_age_ms/last_message_id/last_source_seq/last_correlation_id`。
- 移除每帧完整 `inputs.dump()`、`INVOKE_FUNCTION` 和 skip-reply DEBUG 日志；
  `0` 可关闭正常帧采样，异常和 MRC 日志仍保留。

当前诊断口径：

| 证据 | 可确认结论 |
|---|---|
| 云端 `inflight_slow`、coalesced 增长，随后 `send_completed_slow` | 云端设备发送器/TCP write 完成过慢，latest-only 确实压住后续帧 |
| 车端 `body_receive_us` 高 | 长度头已到达，但完整 body 接收慢；优先查网络分片/重传、接收调度和云端写出 |
| 车端 `decrypt_us/parse_us/parse_to_dispatch_us` 高 | 车端 AES、JSON 或解析后同步分发阶段慢 |
| 车端 `listener_dispatch_gap_us` 超过 MRC 窗口，本帧 transport 正常 | 一段时间未开始分发 remotejoystick；结合前一 handler 和云端序列判断停发、未送达或监听线程占用 |
| 车端有 `handler_start`，`handler_us` 或 `publish_us` 超阈值 | 车端 handler 或 ROS publish 调用存在慢处理 |
| 车端 handler/publish 正常但 MRC 仍触发 | 查 MRC 时间戳更新、检测 timer、并发可见性和模式状态 |

仍未闭环的边界是驾驶舱 send start/result、TCP 长度头到达和内核收包时刻、ROS 下游消费
以及底盘最终执行确认。下一阶段必须让驾驶舱、云端、车端统一输出
`messageId + seq + correlationId`，再按同一帧比对阶段是否存在，不能依赖跨机器墙上时间
直接相减。

后端 WebSocket 状态链路同时提供 JVM 进程内的单调时钟耗时字段：

| 字段 | 语义 | 是否可作为耗时 |
|---|---|---|
| `eventbusToQueueDurationMs` | 同一后端 JVM 内，EventBus 回调开始到进入 WebSocket 最新值队列 | 可以 |
| `queueToSendDurationMs` | 同一后端 JVM 内，进入最新值队列到构造发送消息 | 可以，包含 `latest/sample` 等待 |
| `eventbusToSendDurationMs` | 同一后端 JVM 内，EventBus 回调开始到构造发送消息 | 可以 |
| `serverMonotonicTimingAvailable` | 本条消息是否成功采集到后端单调时钟起止点 | 可以用于判断字段是否有效 |

这些字段由 `System.nanoTime()` 计算，只在同一后端进程的阶段之间成立，不代表车端到云端或云端到浏览器的网络耗时。
原有 `eventbusReceivedAt`、`websocketQueuedAt`、`websocketSentAt` 继续保留，用于跨日志墙上时间对齐；
前端埋点应优先使用上述 `*DurationMs` 字段，缺失时才兼容使用同一服务端墙上时间字段的差值。
单调时钟读取和整数差值计算不引入定时器、锁、网络请求或额外线程；性能开销相对状态对象复制、采样和 JSON 序列化可忽略。

已完成静态验证：

```text
npm exec -- vite build --mode development
Build successful

./mvnw -pl jetlinks-manager/parallel-driving-manager -am -DskipTests compile
BUILD SUCCESS
```

前端仓库现有的 `vue-tsc 1.8.27 + TypeScript 5.9.2` 组合无法启动，普通 `tsc` 也被已有
`Certificate/type.d.ts` 语法问题阻断，因此当前以前端 Vite 完整构建作为编译验收。

### 9.1.2 前端 OTel/RUM 与 DeepFlow 接入设计

当前 `observability.ts` 已提供稳定的结构化出口：

```text
WebRtcPlayer / VideoCell / VehicleRemoteDeck
  -> recordParallelDrivingObservation
  -> 浏览器固定容量 500 条环形缓存
  -> parallel-driving-observation CustomEvent
```

后续不让浏览器直接连接 DeepFlow Agent 或暴露 Collector 的生产凭证。推荐链路为：

```text
parallel-driving-observation
  -> 前端 RUM/OTel Adapter
  -> 同源 Telemetry Gateway
  -> OTel Collector
  -> Tempo / Loki / Prometheus
  -> DeepFlow 的应用 Span 与 eBPF 网络 Span 关联
```

原因和能力边界：

1. DeepFlow/eBPF 只能自动观察部署 Agent 的车端、云端节点、进程和网络，不能进入用户浏览器，
   也不能自动获得 `requestVideoFrameCallback`、`framesDecoded`、video 可见性和 Vue 生命周期。
2. 浏览器必须主动上报 RUM/领域事件，才能区分“RTP 未到”“已到但未解码”“已解码但未渲染”
   和“视频被页面布局遮挡”。
3. 浏览器到云端之间没有部署 Agent 的网络区段不能仅靠 DeepFlow 还原；需要浏览器提供
   WebRTC stats、信令耗时和页面生命周期证据，云端 DeepFlow 提供服务端及媒体节点侧证据。
4. Telemetry Gateway 负责认证、CORS、脱敏、限流、批处理和失败降级。采集系统失败不得影响
   WebRTC 建链、状态 WebSocket、页面渲染或自动恢复。

#### 标识符职责

`traceId` 不能替代现有 `sessionId`。两者生命周期和职责不同：

- `sessionId` / `remoteSessionId` 贯穿整个远控会话，可能持续数小时，用于关联车辆、驾驶舱、
  状态 WebSocket 和全部视频。
- `traceId` 只描述一次有限操作，例如首次拉流、信令协商、一次重连或一次黑屏恢复。
- `spanId` 描述该操作中的一个阶段，例如获取 SDP、设置 `RemoteDescription`、`ontrack`、
  冻结确认或首帧呈现。

推荐的逻辑关系如下：

```text
remoteSessionId
  └── traceId: 首次拉流
        ├── span: 获取 SDP
        ├── span: 设置 RemoteDescription
        ├── span: ontrack
        └── span: 首帧呈现

  └── traceId: render_stall 恢复
        ├── span: 冻结确认
        ├── span: 重建 PeerConnection
        └── span: 恢复首帧
```

| 标识符 | 生命周期 | 用途 |
|---|---|---|
| `sessionId` / `remoteSessionId` / `session.id` | 整个远控会话，可能持续数小时 | 关联车辆、驾驶舱、状态 WebSocket 和全部视频；不能被 `traceId` 替代 |
| `videoSessionId` / `video.session.id` | 单路逻辑视频会话 | 关联同一路摄像头的正常、异常和恢复事件 |
| `playerInstanceId` | Vue 播放器实例 | 定位组件 mount/unmount、布局和实例级状态 |
| `sharedSessionId` | 共享 WebRTC 会话 | 关联 leader/follower、refCount、共享建链和共享重连 |
| `traceId` | 一次有限操作 | 首次拉流、一次信令协商、一次重连或一次黑屏恢复；不覆盖整个远控会话 |
| `spanId` | Trace 内单个阶段 | SDP、answer、`ontrack`、首帧、冻结确认和恢复首帧 |
| `correlationId` | 无法传播 Trace Context 的边界 | WebSocket、媒体流和跨系统日志的补偿关联 |

前端观测对象后续增加可选字段：

```ts
interface ParallelDrivingObservation {
  traceId?: string
  spanId?: string
  parentSpanId?: string
  correlationId?: string

  sessionId: string
  videoSessionId?: string
  playerInstanceId?: string
  sharedSessionId?: string
}
```

Trace ID 和 Span ID 应由 OpenTelemetry SDK 生成和校验，不能手工拼接。当前已有
`createObservationSessionId()` 继续用于业务会话和 correlation ID，不作为 OTel Trace ID 生成器。

#### Trace 生命周期

首次拉流可以形成以下 Trace：

```text
trace: webrtc.initial_connect
  span: offer.prepare
  span: zlm.webrtc.request
  span: remote_description.apply
  span: webrtc.ontrack
  span: video.first_frame
```

一次黑屏恢复使用新的 Trace，并通过原 `sessionId`、`videoSessionId` 和 `sharedSessionId`
关联到原视频会话：

```text
trace: webrtc.render_stall_recovery
  span: stall.confirm
  span: peer_connection.rebuild
  span: zlm.webrtc.request
  span: video.recovered_first_frame
```

以下事件创建或加入 Trace/Span：

```text
signal_failed
stream_not_found
no_first_frame
ice_failed
stall_inbound
stall_render
decoder_freeze
reconnect_start
recovered
session_failed
```

普通 `video_health_change`、状态消息和 250ms `getStats()` tick 不逐条创建 Span。它们保留在
本地状态机中，只按周期摘要、状态转换或异常边界上报。

#### 当前前端埋点完成边界

黑屏诊断所需的前端基础埋点基本完成，但生产级 OTel/DeepFlow 链路尚未完成。

已完成并已进入前端结构化事件出口的能力：

```text
WebRTC 信令、ZLMediaKit HTTP/code/msg、stream not found
ontrack、首帧、ICE、PeerConnection 状态
RTP 入流、framesDecoded、FPS、码率、丢包、RTT、jitter、PLI、NACK、freeze
render_stall、inbound_stall、解码冻结、重连和恢复原因
页面可见性、渲染资格、video readyState/paused 等黑屏归因字段
状态 WebSocket 的接收、发送、浏览器应用耗时
后端 JVM 单调耗时字段的前端消费
parallel-driving-observation 结构化事件出口和 500 条环形缓存
诊断采集默认关闭，支持远控工作台和车辆详情页按需开启；离开页面自动关闭是设计目标，
当前组件卸载时尚未统一调用关闭开关，仍需补充生命周期处理
前端 Vite 构建和后端 Maven 编译验证
```

这里的“黑屏诊断已完成”只表示链路、RTP、解码和渲染层的基础证据已经采集，不表示
前端能够对视频画面做像素级黑屏识别，也不表示能够捕获所有短时卡顿。当前实现对
WebRTC 有以下判定边界：

| 判定目标 | 主要证据 | 结论 |
|---|---|---|
| 无首帧 | `ontrack` 后首帧事件、`readyState`、播放事件、首帧超时 | 可较高置信度确认播放器没有首帧 |
| 收流停滞 | Peer/ICE 正常且 `inbound_bytes_delta` 连续为零 | 可较高置信度确认 RTP 没有继续进入 |
| 解码冻结 | RTP 增长且 `frames_decoded` 不增长 | 可较高置信度怀疑浏览器解码器冻结 |
| 渲染冻结 | 页面可见可渲染，RTP 增长但 `requestVideoFrameCallback` 无新帧 | 可较高置信度确认页面没有继续呈现 |
| 视觉黑帧 | 连续帧存在但像素接近全黑 | 当前未实现，不能与真实黑场区分 |
| 短时卡顿 | 帧间隔、FPS 或 PLI/NACK 短时恶化 | 当前未形成独立确认规则 |

黑屏和卡顿必须按证据链归因：先排除隐藏页面、系统休眠、采样间隔异常和 UI 不可渲染，
再判断信令/ICE、RTP、解码和呈现。`NACK`、`PLI`、RTT、丢包或 `freezeCount` 单独都
不能作为黑屏结论。当前 WebRTC 远控模式主要能确认持续数秒的断流或冻结；200ms 至数秒
的短卡顿、低 FPS 但仍出帧、摄像头真实黑画面以及非 WebRTC `Player` 路径仍需要专项方案。

现场建议按以下矩阵分析：

```text
Peer/ICE failed
  -> 媒体连接失败，查信令、ZLMediaKit、ICE/TURN 和网络

Peer/ICE 正常 + inbound_bytes_delta 持续为 0
  -> 收流停滞，查车端推流、ZLMediaKit 输入和媒体网络

RTP 增长 + frames_decoded 不增长
  -> 优先查浏览器解码器、编码格式和解码冻结

frames_decoded 增长 + requestVideoFrameCallback 无新帧
  -> 优先查页面渲染、布局遮挡、video 尺寸和主线程

document_hidden=true 或 stats_sample_gap_ms 异常
  -> 暂不下黑屏/卡顿结论，恢复可见后重新建立观测窗口
```

要提升判定能力，需要分别增加两个辅助指标：

1. 视觉黑帧：页面可见且已出帧后，低频采样 canvas 的低亮度占比和画面方差；连续多个窗口
   接近全黑时只能标记 `suspected_black_frame`，不能直接触发重连，因为夜景、遮挡和镜头
   盖住都可能是真实黑画面。
2. 短时卡顿：基于 `requestVideoFrameCallback` 记录帧间隔，计算有效 FPS、p95/max frame
   gap、连续超时次数，并与 `frames_decoded`、`frames_dropped`、RTP 增量和主线程长任务
   联合判断。建议输出 `degraded_frame_pacing`、`suspected_stall` 和 `confirmed_stall`
   三档状态，而不是单一布尔值。

详细的前端判定边界、现场字段顺序和阈值标定要求见
[04 前端黑屏与本地可观测性](observability/04-frontend-black-screen.md)。

尚未实现或尚未完成验证的能力：

```text
生产 RUM/OTel Exporter
Telemetry Gateway、OTel Collector 路由和 DeepFlow Dashboard
实际 traceId、spanId、parentSpanId、correlationId 字段生成与注入前端事件
信令 HTTP 的 W3C traceparent 传播
WebSocket 的 correlationId 传播
Playwright 和真实黑屏场景专项回归
视觉黑帧辅助采样、RVFC 帧间隔统计和短时卡顿阈值标定
采集开启与关闭时的 CPU、内存、长任务和首帧性能对比
```

因此当前状态应表述为：前端埋点基础已完成，生产 OTel/DeepFlow 埋点未完成；本地阶段主要
通过 `parallel-driving-observation` 浏览器事件和控制台分析，不应称为生产级上报链路。

#### 上下文传播

1. `/index/api/webrtc` 等信令 HTTP 请求使用 W3C `traceparent` 传播到云端；跨域部署时必须在
   CORS 中显式允许该请求头。
2. 服务端继续向业务服务、ZLMediaKit 适配层和 OTel/DeepFlow 传播 Trace Context。
3. 浏览器 WebSocket API 不能设置任意握手请求头，状态 WebSocket 使用连接 query、cookie、
   subprotocol 或连接建立后的首条应用消息传递 `sessionId/correlationId`。不要为每条状态消息
   创建独立 Trace。
4. WebRTC RTP/RTCP 媒体数据不能直接承载业务 Trace Context，使用
   `sessionId + videoSessionId + app + stream + 时间窗` 与 DeepFlow/ZLMediaKit 证据关联。
5. 墙上时间未同步时，时间窗只用于宽松检索；阶段耗时仍必须使用各节点自己的单调时钟。

#### 上报与性能预算

前端 Exporter 必须遵守以下约束：

1. `signal_failed`、`no_first_frame`、`stall_render`、`decoder_freeze`、重连和恢复事件全量上报；
   健康事件按比例采样。
2. 250ms WebRTC stats 不直接上报，按每路 10 至 30 秒聚合为一条摘要。现有 30 秒摘要可作为
   初始生产配置。
3. 使用批量发送，例如每批 20 至 50 条或每 5 至 10 秒一次；页面退出时使用 `sendBeacon()`，
   但不得等待采集完成后才允许页面卸载。
4. Exporter 设置固定内存上限、请求超时、重试上限和熔断；环形缓存满时优先保留异常、恢复和
   会话边界事件，允许丢弃重复健康摘要。
5. `sessionId`、`videoSessionId`、`playerInstanceId`、`sharedSessionId`、车辆 ID 等高基数字段
   放入 Trace/Log 属性，不能作为 Prometheus 标签。
6. 上报 payload 不包含 SDP 正文、ICE credential、Token、完整 IP 详情或车辆敏感原始属性。
7. Exporter 失败只能产生低频自监控事件，不触发视频 reload，不参与 WebRTC 重连判断。

验收时需要同时验证：

```text
采集开启和关闭时的页面 CPU、内存、长任务和首帧耗时差异
批量队列长度、丢弃数、发送失败数和重试数
异常 Trace 是否能通过 session/video/player/shared session 定位
浏览器 Span 是否能与云端服务 Span、DeepFlow 网络证据和 ZLM 日志对齐
Collector 或 Gateway 不可用时视频是否继续正常播放和恢复
```

#### OTel/DeepFlow 部署前的本地埋点阶段

在 OTel、Telemetry Gateway、OTel Collector 和 DeepFlow 尚未部署前，前端先保留结构化本地埋点。
埋点通过 `parallel-driving-observation` 浏览器事件提供给现场调试、自动化测试和后续
OTel/RUM Adapter，不依赖网络服务即可使用。

本地控制台监听示例：

```javascript
window.__pdObsHandler = (event) => {
  const detail = event.detail
  if (
    detail.event === 'video_health_change' ||
    detail.event === 'status_ws_error' ||
    detail.event === 'status_ws_close'
  ) {
    console.info('[parallel-driving-observation]', detail)
  }
}

window.addEventListener(
  'parallel-driving-observation',
  window.__pdObsHandler,
)
```

现场长期观察建议只过滤与故障定位直接相关的顶层事件，避免多路视频下无过滤的
`console.info` 增加 DevTools 和主线程压力。当前实现中，黑屏状态通常由
`video_health_change.reason` 表达，而不是独立派发名为 `stall_render` 或
`decoder_freeze` 的事件：

```javascript
const watchedReasons = new Set([
  'S4_RTP_STALLED',
  'S5_RENDER_STALLED',
  'S6_DECODER_FREEZE',
  'RECOVERING',
])

window.addEventListener('parallel-driving-observation', (event) => {
  const detail = event.detail
  if (
    detail.event === 'video_health_change' &&
    watchedReasons.has(detail.reason)
  ) {
    console.info('[parallel-driving-observation]', detail)
  }
})
```

采集默认关闭。开始复现前，在远控工作台或车辆详情页控制条打开“诊断采集”，再注册上述
监听器并复现问题；结束后移除监听器并关闭开关。开启时会清空旧缓存并开始新的观测会话，
关闭时停止缓存和事件派发并清空本地缓存。该开关不影响 WebRTC 健康检测、自动恢复、状态
WebSocket 或远控指令。

```javascript
window.removeEventListener(
  'parallel-driving-observation',
  window.__pdObsHandler,
)
delete window.__pdObsHandler
```

如果调试代码可以导入前端工具模块，也可以使用带过滤和异常隔离的辅助订阅：

```ts
const unsubscribe = subscribeParallelDrivingObservation(
  (observation) => {
    console.info('[parallel-driving-observation]', observation)
  },
  {
    events: ['video_health_change'],
    predicate: (observation) =>
      ['S4_RTP_STALLED', 'S5_RENDER_STALLED', 'S6_DECODER_FREEZE', 'RECOVERING']
        .includes(observation.reason ?? ''),
  },
)

// 页面卸载或测试结束时调用 unsubscribe() 释放监听器
```

当前代码中实际可观察的顶层事件包括：

```text
video_health_change
video_source_identity
status_ws_connect_start
status_ws_open
status_ws_first_message
status_ws_message_sample
status_ws_browser_applied
status_ws_last_message_age
status_ws_error
status_ws_close
status_ws_reconnect
```

`video_health_change.details` 还包含信令阶段、ZLMediaKit HTTP/code/msg、ICE/Peer 状态、
RTP 入流、解码帧、渲染资格、冻结和重连相关字段；现场过滤应优先使用顶层
`event` 加 `reason`/`result`，不要依赖控制台堆栈文本推断状态。
远控工作台会将部分原因归一化为 `S4_RTP_STALLED`、`S5_RENDER_STALLED`、
`S6_DECODER_FREEZE` 等分类；车辆详情页仍可能保留 `stall_inbound`、`stall_render`、
`decoder_freeze` 等原始媒体状态名，现场应以实际页面出口为准。

#### 前端黑屏与卡顿字段使用口径

当前前端已经在 `WebRtcPlayer -> VideoCell -> VehicleRemoteDeck/车辆详情页` 这条路径上，将媒体健康
事件统一为 `video_health_change`。事件顶层保留会话、车辆、摄像头和归因上下文，
媒体诊断指标放入 `details`。这些字段足以完成浏览器侧
黑屏分类和卡顿初步归因，但不能替代车端采集、编码、RTP、ZLMediaKit 的全链路证据。

```text
事件上下文：
  event, occurredAt, observedAtPerfMs, sequence
  sessionId, vehicleId, cockpitId, camera, app, stream, protocol
  reason, result, durationMs

播放身份（details）：
  playerInstanceId, effectiveStream, sharedSessionId
  sharedSessionRefCount, sharedLeader

信令/首帧：
  kind, loading, error
  peerState, iceState, signalAttempt, signalPhase, reconnectAttempt
  zlmHttpStatus, zlmCode, zlmMessage
  negotiationDurationMs, trackToFirstFrameMs

RTP/网络：
  inboundBytesDelta, inboundBytesReceived, inboundZeroStreak
  statsSampleGapMs, fps, bitrateKbps, lossPercent, rttMs, jitterMs
  pliCount, nackCount

解码/渲染：
  decodedFramesDelta, lastFrameAgeMs
  renderStallCandidateMs, renderStallThresholdMs
  freezeCount, decoder
  videoReadyState, videoPaused, videoRenderEligible
  rvfcMonitoring, documentHidden

恢复：
  lastRecoveryHint, reconnectAttempt
```

前端黑屏/卡顿归因按以下证据组合进行：

```text
S1_SIGNAL_FAILED
  signalPhase 未完成或存在 error/zlmHttpStatus/zlmCode/zlmMessage 错误

S2_STREAM_NOT_FOUND
  ZLM 明确返回流不存在，结合 app/stream 和 video_source_identity

S3_ICE_FAILED
  peerState/iceState failed，或 SDP 成功后 ICE/DTLS 无法建立

S4_RTP_STALLED
  Peer/ICE 可用，但 inboundBytesDelta 长时间接近 0，inboundZeroStreak 持续增长

S5_RENDER_STALLED
  RTP 字节仍增长，decodedFramesDelta 为 0，lastFrameAgeMs 增长，
  且 videoRenderEligible=true、documentHidden=false

S6_DECODER_FREEZE
  freezeCount 增长，通常结合 decoder、lossPercent、pliCount、nackCount 判断

S8_UI_OBSCURED
  有入流/解码/呈现证据，但 videoRenderEligible=false 或页面布局状态遮挡
```

`status_ws_last_message_age.value` 只表示浏览器本地状态 WebSocket 最近消息年龄，不是视频
帧延迟；`status_ws_browser_applied.details.browserToAppliedMs` 只表示状态对象从浏览器接收
到业务应用的本地处理时间，也不是指令端到端延迟或 WebRTC 播放延迟。

#### 2026-08-26 本地观测样例分析

本次现场样例：

```text
event: status_ws_browser_applied
occurredAt: 2026-08-26T12:43:24.176Z
sequence: 149
eventbusToQueueMs: 0
eventbusToSendMs: 3
browserToAppliedMs: 115.3
serverToBrowserClockOffsetMs: -276
serverToBrowserClockOffsetDeltaMs: 0
vehicleToEventbusClockOffsetMs: -36968
vehicleToEventbusClockOffsetDeltaMs: -5
crossDomainDurationMs: null
result: applied
```

结论：

1. EventBus 入队无排队，云端接收至 WebSocket 发送约 `3ms`。
2. 浏览器收到状态消息后到业务应用完成约 `115.3ms`；该值属于浏览器本地处理时间，
   高于此前约 `16ms` 的样例，现场可结合长任务、Vue 更新和 `getStats()` 调度继续观察。
3. Server/Browser 存在稳定的 `276ms` 墙上时钟偏移，`delta=0`，不能把未经校正的
   `-276ms` 当作负网络延迟。
4. 车辆与云端约 `37s` 偏移已确认是车端 RTK 基线偏差；当前变化仅 `5ms`，因此应作为
   已知校准偏移和数据质量标记，不作为车辆时钟故障或 WebSocket 延迟告警。
5. 因车辆、服务器、浏览器时钟域未统一，`crossDomainDurationMs`、
   `vehicleToEventbusMs`、`vehicleToBrowserAppliedMs` 保持 `null` 是正确的保护行为。
6. 这条事件是状态 WebSocket 的浏览器应用观测，不能推出指令端到端延迟、视频延迟或
   WebRTC 播放延迟。要计算这些指标，必须有同一 `commandId`/`videoFrameId` 贯穿各阶段
   的本地 monotonic 时间账本。

与之配套的 `status_ws_last_message_age` 中，`value: 200.9` 表示检查时距浏览器最近收到
状态 WebSocket 消息约 `201ms`，`result: fresh` 表示低于当前新鲜度阈值。它只能证明状态
链最近仍有消息，不证明视频 RTP、解码或屏幕呈现正常。

#### 2026-08-26 WebRTC shared 与后台页面样例分析

本次现场日志涉及 `cam_rb_10`、`cam_f_7`、`cam_lb_4`、`cam_f_12`、`cam_b_18` 和 `ipm`
六路流。`WebRTC shared` 中：

```text
sharedLeader=true  -> 首个播放器，负责共享会话
sharedLeader=false -> 后续播放器，复用共享会话
sharedRefCount=2   -> 同一路流当前有两个播放器引用
sharedRefCount=1   -> 该路只有一个播放器引用
```

`cam_f_12` 和 `cam_b_18` 的 `sharedRefCount=2`、相同
`sharedSessionId` 表明共享 PeerConnection 生效，不应解释为重复建链。`acquire` 与
`bind` 是播放器获取共享租约和绑定流的生命周期事件，本身不是错误。

页面可见时，各路都保持：

```text
peer_state=connected
ice_state=connected
video_ready_state=4
video_paused=false
last_frame_age_ms=约 24~90ms
```

可见时丢包率大多为 `0.3%~1.9%`，RTT 约 `31~56ms`，jitter 约 `4~9ms`，没有持续性
WebRTC 断链或视频卡死证据。`ipm` 和 `cam_b_18` 曾出现约 `5.6%~9.4%` 的短时丢包、
NACK 增长和累计 freeze，但后续恢复到约 `1.6%~1.9%` 丢包，应先记为短时网络波动。

在 `2026-08-26 14:13:12` 至 `14:14:42` 的样本中，所有播放器的
`document_hidden=true`、`video_render_eligible=false`，`stats_sample_gap_ms` 最高达到
数秒，`last_frame_age_ms` 从约 `2.6s` 增长到约 `92s`。但同一期间
`inbound_bytes_delta` 和 `decoded_frames_delta` 仍持续增长，Peer/ICE 仍为 connected；
页面恢复可见后，`last_frame_age_ms` 立即回到约 `6~90ms`。结论是这些几十秒数值来自浏览器
后台对渲染回调和 stats 调度的限制，不是车端 RTK 偏差，也不能当作视频真实延迟或黑屏。

为保证实时远控优先保持画面连续，前端已增加以下保护：

1. 页面隐藏或视频不可渲染时，诊断事件的 `lastFrameAgeMs` 置为 `null`，避免用旧的呈现
   时间制造几十秒延迟。
2. `statsSampleGapMs` 明显超出正常周期时，不推进 `inboundZeroStreak`，避免浏览器休眠、
   隐藏 Tab 或主线程长任务误触发 `inbound_stall` 重连。
3. `render_stall` 仅在页面可见、视频可渲染、采样连续且解码帧没有增长时成立。
4. VideoToolbox 的 VP8 规避重连增加页面可见、视频可渲染和采样连续条件，避免后台期间
   累计 `freezeCount` 触发解码器重建。
5. 页面恢复可见仍会调用 `video.play()`，并重新建立可见渲染观测窗口；这些保护只减少
   误判和误重连，不停止 WebRTC、RTP、解码或已有的真实故障恢复路径。

#### 2026-08-26 14:38~14:46 新样本：健康、后台采样与真实断连

`remote-deck-fb25c999-7b77-4b4b-bc96-eb2c1e9bdeb9`（车辆
`L584C4VC5SD001331`、驾驶舱 `GQ004`）在 `14:38:53` 的首帧健康事件中，7 路播放器
均已经进入 `peerState=connected`、`iceState=connected`、`videoReadyState=4`、
`videoPaused=false`。首帧耗时约 `119~259ms`，可见路的 FPS 约 `18~20`，RTT 约
`34~39ms`，jitter 约 `6~10ms`，没有首帧失败或当时黑屏证据。

`cam_lb_4` 的丢包率约 `1.20%`，`cam_b_18` 约 `0.72%`，其余样本接近 `0%`；
结合 `decodedFramesDelta` 和 `inboundBytesDelta` 均大于零，属于轻微网络波动，不应仅凭
NACK/丢包触发重连。`cam_b_18` 和 `cam_f_12` 的 follower 使用相同
`sharedSessionId` 且 `sharedRefCount=2`，是共享连接的正常绑定。

在 `14:45:38~14:46:09`，多路日志出现 `documentHidden=true`、
`videoRenderEligible=false`、`statsSampleGapMs≈990~1011ms`，但 `inboundBytesDelta`
和 `decodedFramesDelta` 仍持续增长。这说明浏览器后台仍在收包和解码，只有页面呈现被挂起；
此时 `lastFrameAgeMs` 增长到约 `9~40s` 不能作为黑屏或卡顿结论。

随后 `cam_f_7` 和 `ipm` 同时出现 `peer=disconnected`、`ice=disconnected`、
`inboundBytesDelta=0`、`decodedFramesDelta=0`，且 `lastFrameAgeMs` 约
`13~14s`。这与前面的隐藏页观测不同，属于有网络/连接状态证据支持的真实断连；
`disconnect_grace` 重连是合理恢复动作。恢复期间应保留现有 `video.srcObject` 和最后画面，
不要先清空视频元素；只有 source 变化、用户停止或组件销毁才执行完整 teardown。

本批日志没有显示重连后的 `bind/first_frame/healthy` 事件，因此不能仅凭
`scheduleReconnect` 断定恢复成功。现场应继续按同一 `playerInstanceId` 追踪：

```text
scheduleReconnect(disconnect_grace)
  -> shared reconnect（同一 sharedSessionId，且只接受一次）
  -> bind
  -> signalPhase=first_frame
  -> video_health_change(result=healthy)
```

#### 首次加载重复重载的判定与修复

首次进入页面时，车辆查询、在线状态、视频区挂载和 `internalCode` 可能不在同一 Vue 更新周期
完成。若 source watcher 的首次 `immediate` 回调先 `stop()` 再 `play()`，或者旧的异步 SDP
协商在 source 变化后仍继续完成，就会出现“刚加载出来又重新加载”。这属于前端初始化竞态，
不能把它误判为 ZLMediaKit、车端 RTSP 或 WebRTC 网络故障。

当前 `WebRtcPlayer` 的初始化/换流规则如下：

1. 首次有效 `baseUrl/app/stream` 只启动一次错峰播放，不先 teardown 尚未建立的连接。
2. 只有已有播放或协商中的真实 source 变化才执行 teardown 和重新协商。
3. `playGeneration` 隔离每次播放；source 变化、重试和销毁会使旧协商失效，关闭待协商
   PeerConnection，并取消旧的 `ontrack` 等待。
4. 旧 generation 的 SDP 响应、连接状态和共享连接回调不能绑定当前视频元素或覆盖当前状态。
5. 同一 `RTCPeerConnection` 的重复 bind 保持幂等，不重复启动 stats/RVFC/首帧流程。

分析首次加载问题时，应按 `playerInstanceId` 对齐以下事件和字段：

```text
video_source_identity
acquire / bind
sharedSessionId / sharedRefCount / sharedLeader
signalAttempt / signalPhase
reconnectAttempt / lastRecoveryHint
```

正常首次加载通常是：

```text
video_source_identity -> acquire -> bind -> first_frame
```

如果 source 未变化，却在首帧前出现同一播放器的多次 teardown/acquire，或旧协商响应在新
generation 之后才绑定，则是初始化竞态。`sharedRefCount=2` 且 `sharedSessionId` 相同只说明
同一路流有两个播放器引用，不等于重复建链。

判定后台样例时，必须优先检查以下组合，而不是单独看 `last_frame_age_ms` 或
`freeze_count`：

```text
document_hidden
video_render_eligible
stats_sample_gap_ms
inbound_bytes_delta
decoded_frames_delta
peer_state
ice_state
```

本次本地实现补充了以下能力：

1. 固定容量环形缓存：写入使用索引覆盖，快照按时间顺序返回，容量始终不超过 500 条，
   避免高频埋点触发数组搬移。
2. 页面内递增 `sequence`：为本地事件提供稳定的排序依据；清空缓存不会重置序号，
   避免同一页面内出现重复序号。
3. 浏览器单调时间 `observedAtPerfMs`：记录 `performance.now()` 采样值，用于同一浏览器
   进程内排序和耗时关联；它不是跨机器墙上时间，也不能替代后端单调耗时字段。
4. `clearParallelDrivingObservationBuffer()`：为现场测试、页面切换和自动化用例提供显式
   清理入口，不会影响下一条事件的序号连续性。
5. `subscribeParallelDrivingObservation()`：支持按顶层 `event` 和 predicate 过滤，返回
   取消订阅函数；过滤器或监听器异常都会被隔离，不进入视频状态机。
6. 事件派发失败保护：`CustomEvent`、监听器和本地调试逻辑失败不会触发视频 reload、
   WebRTC reconnect，也不参与黑屏判定。

本地阶段的性能边界：

1. 浏览器只维护固定上限为 500 条的环形缓存，不会因埋点持续增长而无界占用内存。
2. 诊断采集关闭时，生产者直接返回，不写缓存、不读取 `performance.now()`、不派发
   `CustomEvent`，并停止状态 WebSocket 最近消息年龄的观测定时器；刷新页面后默认仍为关闭。
   离开页面自动关闭仍是生命周期待补能力，当前不能作为已实现行为对外承诺。
3. 诊断采集开启时，`CustomEvent` 只在当前页面进程内派发，不产生网络请求、额外线程或
   额外定时器。
4. 开启采集后，每条事件增加一次递增计数和一次 `performance.now()` 读取；正常事件量下
   开销很小。
5. 事件对象和详情对象会产生少量 JavaScript 分配；正常事件量下相对视频解码、渲染和
   `getStats()` 开销可忽略。
6. `console.info` 不是生产采集方案，持续打印全部状态事件可能拖慢 DevTools 和主线程；
   现场调试应按事件过滤、按时间窗口观察，必要时关闭控制台监听。
7. `CustomEvent` 是同步派发；监听器自身的重计算、序列化或同步打印仍可能占用主线程，
   因此现场监听器必须保持轻量。
8. 监听器抛错、后续本地分析逻辑失败或未来 Exporter/Gateway 不可用，都不得触发视频
   reload、WebRTC 重连或改变黑屏判定。
9. 后续接入 OTel/DeepFlow 时复用同一结构化出口，新增批量、采样和失败隔离逻辑，不改变
   当前视频播放路径。

### 9.1.3 当前工作项进度

更新时间：`2026-08-27`

| work_item | status | owner | updated_at | scope | changed_artifacts / verification | known_gaps / next_step |
|---|---|---|---|---|---|---|
| 状态 WebSocket JVM 单调耗时 | `verified` | 云端 | `2026-08-25` | 后端同 JVM 阶段耗时 | `ParallelDrivingWebSocketHandler`、`ParallelDrivingLatencyMetrics`；后端 Maven compile 成功 | 部署后确认新增 duration 字段非负，并接入 Micrometer/Grafana |
| 前端消费服务端单调耗时 | `verified` | 前端 | `2026-08-25` | 消费 `*DurationMs` 并兼容旧字段 | `VehicleRemoteDeck.vue`；前端 Vite build 成功 | 现场确认新旧后端兼容回退和真实消息字段 |
| 状态 WebSocket 时钟与标识语义 | `verified` | 前端 | `2026-08-26` | `cockpitId` 统一为字符串或 `null`；本地/跨域耗时拆分；连接级偏移基线、变化量和异常判断 | `observability.ts`、`VehicleRemoteDeck.vue` 已修改；偏移异常阈值为连接内 `1000ms`；`npm exec -- vite build --mode development` 成功 | 现场确认固定约 37 秒偏移时 `clockOffsetStable=true`，人为增加偏移后异常字段翻转 |
| WebRTC stats in-flight 门禁 | `implemented` | 前端 | `2026-08-25` | 每实例 250ms stats 轮询互斥 | `WebRtcPlayer.vue`；前端 Vite build 成功 | 补慢 `getStats()`、重连代际和多路播放器专项测试 |
| 黑屏恢复与误重载防护 | `implemented` | 前端 | `2026-08-25` | 播放身份、共享租约、渲染资格和恢复状态机 | internalCode 锁定、旧响应隔离、shared session、render eligibility 等代码已落地 | 尚需 Playwright、隐藏 Tab、HMR、换车和真实黑屏现场回归 |
| 本地结构化埋点出口 | `verified` | 前端 | `2026-08-26` | 固定 500 条环形缓存、页面序号、浏览器单调时间、过滤订阅、异常隔离和现场观察 | `zeron-cloud-web/src/modules/parallel-driving-manager-ui/utils/observability.ts`；`npm exec -- vite build --mode development` 成功，文档/冲突标记静态检查通过 | 尚无专门单元测试；后续由 OTel/RUM Adapter 复用，不直接视为生产上报 |
| 云端进入到车端的 `remotejoystick` 分段埋点 | `implemented/unverified` | 车端/云端/可观测性 | `2026-08-29` | 暂不依赖驾驶仓；覆盖 ziot latest-only 在途/完成、TCP write/连接生命周期，以及车端 body receive/decrypt/parse/dispatch、handler/publish/MRC 日志 | `ParallelDrivingRoom`、`ParallelDrivingLatencyMetrics`、`ParallelDrivingCustomMessageHandler`、`VertxTcpClient`、`TcpClient`、`TcpDeviceSession`、`cloud_driving_client.hpp/.cpp`、`cloud_driving_vehicle.cpp`；ziot `/actuator/prometheus` 和自定义指标注册已有现场输出证据；专题文档 02/03/10 | 待执行一条真实云端下发指令，确认云端指标/日志增长、同一 `messageId/seq/correlationId` 在车端出现，并验证 DeepFlow/Collector/DataBuff；ROS 下游消费和底盘执行暂不纳入 |
| OTel/RUM Exporter | `approved` | 可观测性/前端 | `2026-08-25` | 批量、采样、熔断、`sendBeacon()` 和失败隔离 | 本文档 9.1.2 已完成设计 | 尚未实现 Exporter；需先定义 OTLP/RUM payload 和性能预算验收 |
| Trace/Span 前端上下文 | `approved` | 可观测性/前端 | `2026-08-25` | traceId、spanId、parentSpanId、correlationId 生命周期 | 已完成 session/trace/span 职责和 Trace 拓扑设计 | 尚未加入 `ParallelDrivingObservation` 实际字段和 SDK 生成逻辑 |
| 信令 HTTP Trace Context | `approved` | 前端/云端 | `2026-08-25` | `/index/api/webrtc` 的 W3C `traceparent` 传播 | 已记录传播边界和 CORS 要求 | 尚未实现浏览器注入、服务端接收和上下文验证 |
| 状态 WebSocket correlationId | `approved` | 前端/云端 | `2026-08-25` | WebSocket 连接级上下文传播 | 已记录 query/cookie/subprotocol/首消息候选方案 | 尚未选定协议并实现连接建立与服务端关联 |
| Telemetry Gateway / Collector / DeepFlow | `approved` | 可观测性/平台 | `2026-08-25` | 网关、Collector 路由、DeepFlow 关联和 Dashboard | 架构和故障隔离边界已记录 | 尚未部署；下一阶段单独评审凭证、脱敏、限流和网络拓扑 |
| 车端控制业务事件出口 | `approved` | 车端/可观测性 | `2026-08-26` | `ztd_cloud_driving` 收包、解析、handler、ROS publish 和异常事件 | 已完成现有调用链、字段、采样和故障隔离设计 | 尚未新增统一事件模块、`InvocationContext` 和本地环形队列 |
| ROS 2 控制下游 Trace 延伸 | `approved` | 车端控制/可观测性 | `2026-08-26` | 从 `control_info` publish 延伸到订阅回调、安全门禁和最终控制输出 | 已明确 publish 返回只证明消息交给 ROS 2，不能证明下游执行 | 尚未在 `e2e_control` 增加消费/执行事件，也未验证 ros2_tracing/LTTng 方案 |
| 车端视频/GStreamer 事件出口 | `approved` | 车端/可观测性 | `2026-08-26` | `ztd_rtsp` 客户端、ROS 帧、appsrc、编码输出、RTP、pipeline 错误和恢复 | 已完成现有 GStreamer hook、事件和黑屏分段设计 | 尚未新增稳定 `videoSessionId`、pipeline bus 事件和首帧状态机 |
| 车端 monotonic timing | `approved` | 车端 | `2026-08-26` | 控制和视频进程内阶段耗时统一使用 `steady_clock` | 已确认现有 `cloudLinkPing` 局部使用 `steady_clock`，RTSP 聚合仍混用墙上时间 | 尚未统一 `startMonotonicNs/endMonotonicNs/durationNs` 字段和测试 |
| 控制协议 Trace Context 兼容扩展 | `approved` | 车端/云端 | `2026-08-26` | 自定义 TCP JSON 的 `traceparent`、`tracestate`、session 和 correlation metadata | 已确认现有消息支持 `headers` 且已有 `messageId/functionId` | 尚未实现版本协商、解析校验、回复传播和旧版本回退 |
| 视频 stream-level session 关联 | `approved` | 车端/云端/ZLM | `2026-08-26` | `remoteSessionId/videoSessionId/stream` 注册表和拉流建立关联 | 已完成控制面预绑定、TTL 和时间窗降级设计 | 尚未实现云端预绑定消息、车端 registry 和 ZLM 日志字段 |
| 控制进程到 RTSP 进程 Trace 绑定 | `approved` | 车端 | `2026-08-26` | 通过专用 ROS 2 消息跨进程传递视频预绑定，并在 RTSP 进程维护有界 TTL registry | 已确认 `ztd_cloud_driving` 与 `ztd_rtsp` 为独立进程；已定义 `VideoTraceBinding.msg`、QoS、消费和降级规则 | 尚未新增消息、publisher/subscriber、registry、过期清理和跨进程测试 |
| 车端 eBPF Agent 能力验收 | `approved` | 车端平台/可观测性 | `2026-08-26` | BTF、BPF syscall、JIT、capability、host PID/network、cgroup 和安全策略 | 启动脚本已有 `--pid=host`、`--privileged=true`、`--net=host` 和 cgroup mount 基础条件 | 尚未在目标车载镜像执行内核、权限、CO-RE 和 Agent 兼容性检查 |
| 车端 USDT/custom eBPF 消费验证 | `approved` | 车端平台/可观测性 | `2026-08-26` | 验证自定义 USDT probe 的编译、挂载、字段稳定性、消费端和 DeepFlow 关联方式 | 已明确 DeepFlow 自动网络观测不等于自动消费自定义 USDT | 尚未选定 custom libbpf/BCC consumer，也未确认 DeepFlow 版本的自定义协议或事件接入能力 |
| 车端 Agent 性能基线 | `approved` | 车端平台/测试 | `2026-08-26` | Agent、事件队列、Exporter 对控制时延、视频 FPS、CPU、内存和网络的影响 | 已定义分阶段开关、失败隔离和初始验收预算 | 尚未完成关闭/仅事件/事件加 Agent/全链路四组对照测试 |
| 车端节点性能监控 | `approved` | 车端平台/可观测性 | `2026-08-26` | 进程、线程、CPU、内存、调度、网络、磁盘、容器和 Agent 自身健康 | 已明确 eBPF 基础采集、业务进程指标和资源预算；不进入控制同步路径 | 尚未在目标车载镜像部署 Agent 和节点指标采集，需完成四组性能对照 |
| 车-云-端三链路闭环 | `approved` | 车端/云端/前端/测试 | `2026-08-27` | 视频、指令、状态上报三条链路统一会话关联、分段耗时和故障证据 | 已整理代码挂点、关联键和时钟口径；控制链已补云端 latest-only 与车端 transport/handler/publish 分段日志 | 尚未实现统一事件出口、Trace Context、驾驶舱 send、视频预绑定、ROS 下游执行和云端/前端闭环验收 |
| 车端单车单路 Trace 验收 | `approved` | 车端/云端/前端/测试 | `2026-08-26` | 单条控制消息和单路视频从车端到浏览器的证据闭环 | 已定义正常、无图像、编码停滞、网络丢包、ZLM 拉流失败和浏览器黑屏矩阵 | 尚未部署 OTel/DeepFlow，也未执行真实车辆验证 |
| 公开行业方案对标 | `approved` | 可观测性/架构 | `2026-08-26` | 对照公开专利、公开技术资料和本项目现状，确定车端分层实现边界 | 已记录远程驾驶分段耗时账本、物理测量、业务事件、OTel、eBPF/DeepFlow 和 DataBuff/WAL 的职责边界 | 没有厂商内部白皮书或量产架构证据，不能确认小米、小鹏、理想的具体 SDK、Agent 或后端组合；实施前以目标车辆性能和协议兼容性验收为准 |
| Playwright 与真实黑屏回归 | `approved` | 前端/测试 | `2026-08-25` | 多路、换车、隐藏 Tab、HMR、慢 stats 和恢复场景 | 验收场景已记录，尚未执行 | 补自动化和现场回归证据，记录失败条件和版本 |
| DSH Integration Pack 与文档治理 | `implemented` | 可观测性 | `2026-08-27` | Profile、Schema、能力边界、里程碑状态、证据和阻塞原因 | 本文档 8.1/8.5.1 已定义 DSH 能力；`.github/dsh/` 已落盘并通过依赖无关契约校验 | DSH/Cordis runtime、插件、适配器和数据源部署后逐项留存运行证据；当前 runtime 仍为 `unverified` |
| GreptimeDB Edge/Arrow 车端数据平面 | `approved` | 车端平台/数据平台/可观测性 | `2026-08-26` | Edge 本地时序、Edge Manager 控制面、Arrow 内存/批量交换、Parquet 归档、WAL/DataBuff 断点续传和三链路映射 | [专题文档 06](observability/06-greptime-edge-and-arrow.md) 已记录职责边界、数据模型、资源门禁、Flow batching/向量版本校验和 V0-V6 落地顺序 | 尚未部署 Edge、Arrow/IPC、Parquet 归档或 OTAP；需先完成目标车版本矩阵、单车 POC、断网恢复和四组性能对照 |

### 9.1.4 车端控制、视频与 eBPF 实施设计

设计状态：`approved`。本节最初基于以下代码完成静态分析；截至 `2026-08-27`，
`remotejoystick` 控制链的 receive/decrypt/parse/dispatch、handler 和 ROS publish
分段日志已落地，统一事件出口、视频链路和 eBPF 部分仍处于设计或待验证状态：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/
aura/src/ztd/ztd_network/ztd_rtsp/
aura/tools/systemd_service/start_service.sh
aura/docker/docker_run.sh
```

#### 核心结论

eBPF 不能单独串起车端业务 Trace。它能证明某进程在何时进行了 TCP/UDP 收发、连接是否重传、
socket 队列是否堆积、线程是否被调度阻塞，但默认不知道以下业务事实：

```text
这条 TCP payload 是否为 remotejoystick
messageId/functionId 是什么
消息是否通过模式和安全门禁
ROS 2 control_info 是否已经 publish
某个 H.264 输出是否为 IDR
某路 RTSP 是否属于当前 remoteSessionId
浏览器是否已经解码和渲染
```

因此车端必须采用四层证据：

```text
业务显式事件/Span
  + ROS 2/GStreamer 稳定 hook
  + eBPF/DeepFlow 网络与调度事实
  + 云端 ZLMediaKit 和浏览器事件
```

首期不直接对大量 C++ 成员函数部署 uprobe。优化、内联、符号裁剪和版本变化会使探针失效。
如果后续需要内核外的稳定探针，优先由业务代码提供少量 USDT/static tracepoint wrapper，
eBPF 只读取稳定的数值标识和时间，不读取原始手柄 payload、VIN、密钥或图像内容。

#### 现有代码挂点与缺口

<table border="1">
  <thead>
    <tr>
      <th>链路</th>
      <th>现有挂点</th>
      <th>当前可证明的事实</th>
      <th>缺口</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>控制 TCP 接收</td>
      <td><code>CloudDrivingClient::_receive_message()</code></td>
      <td>4 字节长度读取完成后的 body receive、payload 字节数、AES 解密和 JSON parse 单调耗时</td>
      <td>未记录长度头到达时刻、内核收包时刻和稳定 connection id；无法单独拆分长度头到达前的云端、网络与车端调度等待</td>
    </tr>
    <tr>
      <td>控制分发</td>
      <td><code>_process_message()</code>、<code>_handle_invoke_function()</code></td>
      <td><code>messageId</code>、<code>functionId</code>、handler 命中、reply/skip reply</td>
      <td>未解析 Trace Context，handler API 无法接收结构化上下文</td>
    </tr>
    <tr>
      <td>手柄处理</td>
      <td><code>handle_remotejoystick()</code></td>
      <td>输入解析、MRC 状态、handler/publish 单调耗时、最后消息关联键和 ROS 2 <code>/zeron/parallel_driving/control_info</code> 发布调用</td>
      <td>正常帧按采样记录且不再逐帧打印完整 payload；publish 返回不能证明 ROS 下游消费和底盘执行</td>
    </tr>
    <tr>
      <td>链路探活</td>
      <td><code>send_cloud_link_ping()</code>、<code>handle_cloud_link_ping_reply()</code></td>
      <td>已有 <code>steady_clock</code> RTT、pending messageId 和 reply timeout</td>
      <td>尚未转换为统一 Span/Event，无法直接与 eBPF TCP RTT 和云端处理耗时对齐</td>
    </tr>
    <tr>
      <td>视频 ROS 输入</td>
      <td><code>RtspStream::ros2_image_callback()</code></td>
      <td>ROS header stamp、接收时间、最新帧覆盖、是否立即 push</td>
      <td>跨节点 header stamp 只能表示墙钟偏移参考；缺少本进程单调接收时刻和 frame sequence</td>
    </tr>
    <tr>
      <td>RTSP pipeline</td>
      <td><code>gst_media_configure()</code>、<code>gst_need_data()</code>、<code>push_data()</code></td>
      <td>客户端触发 pipeline、appsrc push、GstFlowReturn、pipeline flushing</td>
      <td>缺少稳定 client/session id、首帧状态机、pipeline bus error/recovery 事件</td>
    </tr>
    <tr>
      <td>编码与 RTP</td>
      <td><code>idH264</code> pad probe、<code>pay0</code> src pad probe</td>
      <td>编码器输出可观察，调试模式可写 RTP timestamp extension</td>
      <td>未记录 IDR、编码停滞、首个 RTP 发出；帧在丢弃或共享 pipeline 下可能无法严格一一对应</td>
    </tr>
    <tr>
      <td>系统与网络</td>
      <td>车端 host PID/network、privileged 容器基础条件</td>
      <td>具备部署独立 eBPF Agent 的初步容器条件</td>
      <td>尚未验证内核 BTF、BPF syscall、JIT、capability、cgroup 和安全策略</td>
    </tr>
  </tbody>
</table>

#### 车端统一事件层

建议新增独立 ROS 2/C++ 包：

```text
aura/src/ztd/ztd_common/ztd_observability/
  include/ztd_observability/observation.hpp
  include/ztd_observability/trace_context.hpp
  src/observation.cpp
  src/trace_context.cpp
```

第一阶段只提供本地事件和上下文，不直接引入网络 Exporter：

```cpp
struct ObservationEvent {
    const char* event_name;
    uint64_t observed_monotonic_ns;
    int64_t observed_unix_ms;
    TraceContext trace;
    ObservationAttributes attributes;
    ObservationPriority priority;
};

bool try_emit(const ObservationEvent&) noexcept;
```

实现要求：

1. `try_emit()` 不阻塞、不抛异常，不等待磁盘、网络、Collector 或锁竞争。
2. 使用有界队列；队列满时丢弃低优先级事件并增加 drop counter，不能反压控制或视频线程。
3. 正常路径使用固定字段或预分配小对象，禁止在每个 RTP 包上构造大 JSON。
4. 消费线程负责批量转为 JSON Lines、ROS 诊断或后续 OTel Span/Event。
5. Exporter、Collector 或本地文件失败只影响观测数据，不调用 reconnect、reload、停车或视频恢复逻辑。
6. 编译开关和运行时开关分离，至少支持 `off/local/otel` 三种模式。
7. `service.name` 分别使用 `ztd_cloud_driving` 和 `ztd_rtsp`，并补充版本、host、vehicle 和进程属性。

#### 控制链路 Trace

正常控制消息频率高，不为每条消息无条件创建和导出完整 Trace。推荐模型：

```text
session.id = remoteSessionId，贯穿整个远控会话
cloud.connection.id = 单次车云 TCP 注册连接
message.id = 协议现有 messageId
correlation.id = messageId；缺失时车端生成兼容值

trace_id = 一次被采样的 remotejoystick 操作
        或一次 cloudLinkPing
        或一次 timeout/MRC/模式切换异常诊断
```

被采样的 `remotejoystick` Trace：

```text
vehicle.control.receive
  -> vehicle.control.decrypt
  -> vehicle.control.parse
  -> vehicle.control.dispatch
  -> vehicle.control.remotejoystick
  -> vehicle.control.ros_publish
```

具体改造顺序：

1. 将 `_receive_message()` 的内部观测结果封装为 `ReceivedEnvelope`，至少携带
   `payloadBytes`、`receiveStartMonotonicNs`、`receiveEndMonotonicNs`、
   `decryptDurationNs`、`parseDurationNs` 和 connection id；业务返回仍兼容现有 JSON。
2. 增加 `InvocationContext`，包含 `messageId/functionId/sessionId/correlationId/TraceContext`
   和各阶段单调时间。
3. 保留现有 `FunctionHandler(const json&, const string&)`，新增带 context 的 V2 handler 或适配层，
   避免一次性破坏现有调用方。
4. `_handle_invoke_function()` 校验 W3C Trace Context；非法或缺失时生成本地 context，并记录
   `trace_context_invalid` 或 `trace_context_generated`，不能拒绝控制消息。
5. `handle_remotejoystick()` 在 ROS publish 前后读取 `steady_clock`，事件结束点是 publish 返回；
   fire-and-forget 消息不等待不存在的 reply。
6. 删除生产环境的完整 `inputs.dump()`，改为白名单字段、payload 大小、序列、模式和处理结果；
   原始杆量只允许在受控调试开关、短时间窗和脱敏后采集。

当前阶段的控制 Trace 结束点是 `pd_control_pub_->publish()` 返回。该返回值只能证明消息已交给
ROS 2 publisher，不能证明 `e2e_control` 订阅回调已执行、安全门禁已通过或底盘命令已输出。
如果目标是完整控制执行 Trace，还需要在下游增加：

```text
vehicle.control.ros_subscriber_received
  -> vehicle.control.safety_gate_evaluated
  -> vehicle.control.command_computed
  -> vehicle.control.command_published
```

ROS 2 业务消息不建议为了观测直接破坏性增加 Trace 字段。首选顺序是：

1. 若消息定义允许兼容扩展，增加独立 `correlation_id/message_sequence`，但不能替代现有业务序列。
2. 若安全消息不允许修改，发布旁路轻量 correlation 事件，并用 publisher GID、topic、sequence
   和单调时间窗关联。
3. 使用 `ros2_tracing/LTTng` 获取 callback、publish、take 和 executor 调度事实，作为业务事件的
   系统侧证据。
4. eBPF 只补 DDS socket、线程调度、run queue 和 off-CPU 证据；同进程、共享内存或 intra-process
   通信不能依赖 eBPF 网络包还原业务消息。

控制事件最小字段：

<table border="1">
  <thead>
    <tr>
      <th>字段</th>
      <th>含义</th>
      <th>用途</th>
    </tr>
  </thead>
  <tbody>
    <tr><td><code>session.id</code></td><td>整个远控会话</td><td>关联云端、车端和浏览器长期会话</td></tr>
    <tr><td><code>cloud.connection.id</code></td><td>单次 TCP 注册连接</td><td>区分断线重连前后的 socket 和 eBPF flow</td></tr>
    <tr><td><code>message.id</code></td><td>协议现有 messageId</td><td>单条消息去重、回复和跨系统关联，不能被 traceId 替代</td></tr>
    <tr><td><code>function.id</code></td><td>例如 remotejoystick、cloudLinkPing</td><td>区分控制类型</td></tr>
    <tr><td><code>correlation.id</code></td><td>默认等于 messageId</td><td>Trace Context 未贯穿时的补偿键</td></tr>
    <tr><td><code>trace_id/span_id/parent_span_id</code></td><td>一次被采样操作及阶段</td><td>连接云端业务 Span 和车端 Span</td></tr>
    <tr><td><code>receive/parse/handler/publish.duration_ns</code></td><td>同进程 steady clock 阶段耗时</td><td>判断卡在收包、解析、业务还是 ROS publish</td></tr>
    <tr><td><code>payload.bytes</code></td><td>密文或明文 payload 长度，需明确口径</td><td>定位超大消息和吞吐异常</td></tr>
    <tr><td><code>drive.mode/mrc.level</code></td><td>处理时的模式与安全状态</td><td>解释消息为何执行、降级或被门禁</td></tr>
    <tr><td><code>result/drop.reason</code></td><td>成功、解析失败、无 handler、超时、重复等</td><td>故障分类和错误采样</td></tr>
  </tbody>
</table>

控制协议已有 `headers` 对象用于 `noReply/sendAndForget/async`，可兼容增加：

```json
{
  "messageId": "existing-message-id",
  "functionId": "remotejoystick",
  "headers": {
    "traceparent": "00-<trace-id>-<parent-span-id>-01",
    "tracestate": "...",
    "remoteSessionId": "...",
    "correlationId": "existing-message-id",
    "schemaVersion": "2"
  }
}
```

兼容规则：

1. 未携带 `headers` 的旧云端消息保持原行为。
2. 不认识新增字段的旧车端应继续忽略它们。
3. `traceparent` 校验失败只记录观测错误，不改变控制消息执行结果。
4. reply 继续保留 `requestMessageId`，并在支持时回传当前 `traceparent/correlationId`。
5. AES 只保护现有 payload 传输；Trace 属性进入日志或 Exporter 后仍必须独立脱敏。

#### 视频链路 Trace

视频不能把整个数小时 RTSP 会话做成一个超长 Trace，也不能给每个 RTP 包创建 Span。推荐拆成：

```text
video.session.id = 当前 remoteSessionId 下的一路逻辑视频会话
vehicle.rtsp.session.id = 车端一次实际 RTSP client/pipeline 生命周期

Trace A：一次 RTSP 拉流建立
  vehicle.rtsp.client_connected
    -> vehicle.rtsp.pipeline_configure
    -> vehicle.rtsp.wait_first_ros_frame
    -> vehicle.rtsp.first_appsrc_push
    -> vehicle.video.first_encoder_output
    -> vehicle.rtp.first_packet

Trace B：一次视频异常与恢复
  vehicle.video.stall_confirmed
    -> vehicle.video.failure_stage
    -> vehicle.rtsp.pipeline_recovered
    -> vehicle.rtp.first_packet_after_recovery
    -> browser.render_recovered
```

现有车端 RTSP 服务无法从主动拉流连接中直接得到浏览器 `remoteSessionId`。首选方案是由云端在
ZLMediaKit 发起拉流前，通过已有车云控制通道发送短生命周期预绑定：

```json
{
  "functionId": "bindVideoTrace",
  "messageId": "...",
  "inputs": {
    "remoteSessionId": "...",
    "videoSessionId": "...",
    "streamApp": "ZSD-DP010",
    "streamName": "cam_f_12",
    "traceparent": "00-...",
    "expiresAtMs": 1787700000000
  }
}
```

车端维护只读查询、容量受限、带 TTL 的 registry：

```text
streamApp + streamName
  -> remoteSessionId
  -> videoSessionId
  -> pending trace context
  -> expiresAt
```

`ztd_cloud_driving` 与 `ztd_rtsp` 是两个独立进程，因此该 registry 不能只保存在
`ztd_cloud_driving` 的进程内存中。控制进程收到 `bindVideoTrace` 后，应通过专用 ROS 2
观测消息传给 RTSP 进程：

```text
cloud_driving
  -> /zeron/observability/video_trace_binding
  -> rtsp_server
  -> bounded TTL registry
  -> gst_media_configure()/client-connected 查询并消费
```

建议在现有消息包中新增：

```text
aura/src/ztd/ztd_msgs/ztd_network_monitoring_msgs/msg/VideoTraceBinding.msg
```

建议字段：

```text
string remote_session_id
string video_session_id
string stream_app
string stream_name
string traceparent
string tracestate
string correlation_id
uint64 expires_at_unix_ms
uint64 published_monotonic_ns
```

`published_monotonic_ns` 只用于控制进程自身的发布阶段计时。ROS 2 消息到达另一个进程后，
不能直接把两个进程的 monotonic 值相减；RTSP 进程应记录自己的
`binding_received_monotonic_ns` 和 registry 查询耗时。

跨进程绑定规则：

<table border="1">
  <thead>
    <tr>
      <th>项目</th>
      <th>建议</th>
      <th>原因</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Topic</td><td><code>/zeron/observability/video_trace_binding</code></td><td>与控制和视频业务 Topic 隔离，便于独立关闭和限流</td></tr>
    <tr><td>QoS</td><td>reliable、keep_last(32)、transient_local</td><td>RTSP 进程晚启动或短暂重启后仍可获得未过期绑定；容量必须有上限</td></tr>
    <tr><td>TTL</td><td>初始 30 秒，可配置为 5 至 120 秒</td><td>覆盖云端下发绑定到 ZLM 发起拉流的正常间隔，避免长期持有旧上下文</td></tr>
    <tr><td>Registry 容量</td><td>每车初始最多 64 条</td><td>限制异常或重复请求造成的内存增长</td></tr>
    <tr><td>Key</td><td><code>stream_app + stream_name</code></td><td>与当前 RTSP mount/云端拉流键一致；同一路重复绑定以较新版本替换</td></tr>
    <tr><td>消费</td><td>成功匹配 RTSP 建连后标记 consumed；保留短暂审计记录后删除</td><td>避免旧 Trace Context 被后续连接重复使用</td></tr>
    <tr><td>重复</td><td>同 key、同 videoSessionId 幂等；同 key、新 videoSessionId 替换并记录 superseded</td><td>支持云端重试，同时保留会话切换证据</td></tr>
    <tr><td>不匹配</td><td>记录 stream_mismatch，不绑定 Trace</td><td>不能把其他摄像头或旧会话错误串入当前 Trace</td></tr>
    <tr><td>过期</td><td>按 RTSP 进程本地定时清理，记录 expired counter</td><td>墙钟有固定偏移时仍以本地接收时间加 TTL 为主要过期依据</td></tr>
    <tr><td>失败降级</td><td><code>session.correlation.mode=time_window</code></td><td>ROS 消息丢失、RTSP 进程未订阅或绑定过期时仍可用 stream、五元组和时间窗关联</td></tr>
  </tbody>
</table>

`transient_local` 只用于短生命周期观测绑定，不允许把它变成控制依赖。publisher、subscriber、
QoS 匹配或 registry 失败时，只增加 `video_trace_binding_dropped/missed/expired` 事件，不能阻止
ZLMediaKit 拉流、创建 RTSP pipeline 或发送视频。

`gst_media_configure()` 或 RTSP client-connected hook 建立 pipeline 时查询并消费该绑定。预绑定缺失时：

1. 生成本地 `vehicle.rtsp.session.id`。
2. 使用 `vehicle.id + stream.name + client.ip + 五元组 + 时间窗` 与 ZLM/eBPF 证据关联。
3. 明确标记 `session.correlation.mode=time_window`，不能伪装成已贯穿 Trace Context。

不建议把完整 Trace ID 写入每个 RTP 包。RTP 头扩展会增加带宽、兼容性和敏感信息暴露风险；
现有代码也只在 `debug_clock_overlay` 时启用自定义扩展，以避免标准 RTSP 客户端解码失败。
帧级首期只记录本地递增 `frame.sequence`、ROS capture stamp 和单调阶段时间，并做聚合或抽样。

视频事件最小字段：

<table border="1">
  <thead>
    <tr>
      <th>事件</th>
      <th>建议挂点</th>
      <th>关键字段</th>
      <th>黑屏判断价值</th>
    </tr>
  </thead>
  <tbody>
    <tr><td><code>rtsp_mount_created</code></td><td><code>factory_gst_video_pipeline()</code></td><td>stream、encoder、GOP、bitrate、mount</td><td>证明 URL 和 factory 已创建</td></tr>
    <tr><td><code>rtsp_client_connected</code></td><td>server client-connected / <code>gst_media_configure()</code></td><td>client、五元组、RTSP session、video session</td><td>区分“无人拉流”和“已建立 pipeline”</td></tr>
    <tr><td><code>ros_frame_received</code></td><td><code>ros2_image_callback()</code></td><td>frame sequence、尺寸、encoding、receive monotonic</td><td>证明摄像头/ROS 有输入</td></tr>
    <tr><td><code>frame_dropped_as_stale</code></td><td><code>push_data()</code> stale 分支</td><td>frame age、阈值、stream</td><td>解释有输入但无输出</td></tr>
    <tr><td><code>appsrc_push_completed</code></td><td><code>push-buffer</code> 返回后</td><td>GstFlowReturn、buffer bytes、duration</td><td>区分 appsrc 失败或 flushing</td></tr>
    <tr><td><code>encoder_output</code></td><td><code>idH264</code> probe</td><td>output sequence、bytes、IDR、since last output</td><td>判断编码器是否停滞、是否有可恢复 IDR</td></tr>
    <tr><td><code>rtp_packetized</code></td><td><code>pay0</code> src probe</td><td>SSRC、sequence、marker、payload bytes</td><td>证明 RTP 已生成；正常流只聚合，不逐包导出</td></tr>
    <tr><td><code>rtsp_first_frame_sent</code></td><td>首个有效 RTP marker/packet</td><td>setup duration、first frame duration</td><td>定位车端首帧之前的等待阶段</td></tr>
    <tr><td><code>rtsp_pipeline_error</code></td><td>GStreamer bus error/warning/state</td><td>domain、code、element、state</td><td>识别编码器、caps、pipeline 和资源错误</td></tr>
    <tr><td><code>rtsp_client_disconnected</code></td><td>client closed / pipeline weak ref</td><td>reason、lifetime、last frame age</td><td>区分主动断开、网络断开和 pipeline 销毁</td></tr>
  </tbody>
</table>

视频阶段时间必须拆为两类：

```text
同进程单调耗时，可直接用于 SLO：
ros_receive_to_push_ns
push_call_duration_ns
push_to_encoder_output_ns
encoder_output_to_rtp_ns
pipeline_configure_to_first_rtp_ns

跨节点墙钟观测，只用于偏移和粗粒度关联：
capture_timestamp_ms
vehicle_wall_timestamp_ms
clock_offset_baseline_ms
clock_offset_delta_ms
cross_domain_duration_ms = null（时钟域未同步时）
```

现有 `system_clock - ROS header.stamp` 统计不能命名为可靠的端到端 latency。它应保留为
`clock_offset_observed` 或 capture age 参考，并与新加的 `steady_clock` 阶段耗时分开。
`capture_stamp_ns_queue_` 在 leaky queue、编码丢帧或共享 pipeline 下可能失配；在未验证
`GstMeta` 能跨 `x264enc/nvh264enc` 稳定传播前，不以该队列计算严格逐帧 Trace。

#### eBPF/DeepFlow 采集范围

<table border="1">
  <thead>
    <tr>
      <th>采集层</th>
      <th>首期采集内容</th>
      <th>关联键</th>
      <th>不得承担的职责</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>内核网络</td><td>connect/accept/close、send/recv、TCP RTT/RTO、重传/reset、socket queue、UDP 收发、网卡丢包</td><td>PID/TID、cgroup、五元组、时间窗</td><td>解析 remotejoystick、判断 IDR 或浏览器渲染</td></tr>
    <tr><td>调度与资源</td><td>CPU、run queue、off-CPU、上下文切换、内存和进程生命周期</td><td>host、PID/TID、service.name、时间窗</td><td>替代业务阶段单调计时</td></tr>
    <tr><td>业务事件</td><td>控制 message、ROS publish、RTSP session、首帧、编码/RTP 停滞、pipeline error</td><td>session、trace、message、video session、stream</td><td>抓取原始 payload 或全量视频帧</td></tr>
    <tr><td>可选 USDT</td><td>少量稳定 probe：control_received、control_published、rtsp_connected、encoder_stalled、first_rtp</td><td>哈希后的 session/message id、数值状态</td><td>直接探测易变 C++ ABI 或传输敏感字符串</td></tr>
  </tbody>
</table>

这里必须区分两种部署能力：

```text
DeepFlow/eBPF Agent
  -> 自动采集网络、进程、系统调用、调度和资源事实

业务事件/OTel
  -> 显式输出 messageId、remoteSessionId、videoSessionId、stream、首帧和故障阶段

可选 USDT
  -> 需要单独的 custom libbpf/BCC consumer，或经验证可用的 Agent 自定义事件接入
```

不能默认认为 DeepFlow Agent 会自动发现并消费 Aura 新增的 USDT probe。V0/V5 阶段必须以目标
DeepFlow 版本做能力验证；如果没有稳定的原生入口，就由独立低开销 consumer 读取 USDT，
再转换为 OTLP Event/Metric 或结构化日志。即使不启用 USDT，业务事件加 DeepFlow 网络证据
也应能够完成首期 Trace 关联。

推荐首期 eBPF 程序和关联 Map：

<table border="1">
  <thead>
    <tr>
      <th>程序/Tracepoint</th>
      <th>采集字段</th>
      <th>适用链路</th>
      <th>关联方式</th>
    </tr>
  </thead>
  <tbody>
    <tr><td><code>sock:inet_sock_set_state</code></td><td>旧/新 TCP 状态、地址、端口、PID/cgroup、socket cookie</td><td>控制 TCP、RTSP TCP</td><td>连接 id、五元组、时间窗</td></tr>
    <tr><td><code>tcp:tcp_retransmit_skb</code></td><td>重传次数、字节、socket cookie</td><td>控制和视频卡顿</td><td>同一 socket 的业务异常窗口</td></tr>
    <tr><td>socket send/recv 计数</td><td>方向、bytes、errno、duration、socket cookie</td><td>控制收包、RTSP/RTP 发送</td><td>业务事件前后时间窗，不解析加密 payload</td></tr>
    <tr><td><code>net:net_dev_queue</code> / receive</td><td>网卡、包长、drop/queue</td><td>车云网络出口</td><td>接口、五元组、时间桶</td></tr>
    <tr><td><code>sched:sched_switch</code> / wakeup</td><td>TID、off-CPU、run queue wait</td><td>handler 或编码停滞</td><td>service PID/TID 与业务 Span 时间窗</td></tr>
    <tr><td>进程/cgroup 资源</td><td>CPU、RSS、page fault、OOM、进程退出</td><td>控制、RTSP、Agent</td><td>service.name、PID、container/cgroup</td></tr>
    <tr><td>可选稳定 USDT</td><td>probe id、哈希 correlation、状态、单调时间</td><td>业务边界补强</td><td>custom consumer 转换为 OTel Event</td></tr>
  </tbody>
</table>

eBPF Map 建议以 `cgroup_id + process_id + socket_cookie` 为主键保存连接级状态，以
`five_tuple + start_monotonic_ns` 为兼容键。用户态 Agent 周期聚合后输出，不从内核事件直接
同步调用 Collector。`trace_id` 不应写入每个网络包或内核 Map；Agent 通过业务事件中的
`service.instance.id/connection.id` 与 socket cookie、五元组和时间窗做关联。只有目标 Agent
已验证支持可靠的 Trace Context 注入/提取时，才将自动网络 Span 挂为业务 Span 的子级；
否则应标记为 correlated evidence，而不是伪造 parent-child。

车端 Agent 最好独立于 Aura 业务进程部署。现有量产脚本使用 host PID、host network、
privileged 和 cgroup mount，为 POC 提供了基础条件，但上线前必须在目标镜像逐项验证：

```text
uname -r
/sys/kernel/btf/vmlinux
CONFIG_BPF_SYSCALL
CONFIG_BPF_JIT
bpf() syscall
CO-RE/libbpf
cgroup v1/v2
CAP_BPF
CAP_PERFMON
perf_event_paranoid
SELinux/AppArmor
Agent 对 host PID/network namespace 的可见性
```

不能因为容器使用 `--privileged` 就判定 eBPF 已可用。生产方案应逐步收紧 capability 和挂载，
并验证 Agent 重启、Collector 不可达、WAL 满和配置错误时不会影响 Aura 主容器。

#### 采样、限流与性能预算

<table border="1">
  <thead>
    <tr>
      <th>信号</th>
      <th>初始策略</th>
      <th>保留条件</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>remotejoystick 正常消息</td><td>全量低成本 counter/histogram；完整 Trace 初始采样 1%，可配置</td><td>异常、超时、乱序、重复、MRC/模式变化时 100%</td></tr>
    <tr><td>cloudLinkPing</td><td>低频请求 100% Trace</td><td>所有 timeout 和 reply mismatch</td></tr>
    <tr><td>RTSP session 建立/断开</td><td>100% 事件/Trace</td><td>全部连接生命周期</td></tr>
    <tr><td>正常视频帧</td><td>每路每秒聚合；最多每秒抽样一个帧级事件</td><td>首帧、首个 IDR、恢复首帧 100%</td></tr>
    <tr><td>RTP 包</td><td>仅 eBPF/进程指标聚合，不逐包创建业务 Span</td><td>异常窗口可短时提高采样</td></tr>
    <tr><td>错误和恢复</td><td>100% 保留，受总速率和本地容量硬限制</td><td>队列满时优先保留 P0/P1 控制和状态变化事件</td></tr>
  </tbody>
</table>

初始性能门禁是验收目标，不代表当前已经达标：

1. `try_emit()` 在控制和视频生产线程中必须非阻塞；队列满时立即丢弃低优先级事件。
2. 开启本地事件后，`remotejoystick receive -> ROS publish` P99 相对关闭埋点的回归不超过
   `0.2ms` 且不超过 `5%`；超过任一值即停止放量并分析。
3. 开启视频事件后，单车全摄像头 FPS 不出现持续下降，pipeline queue/drop 不因埋点增加；
   车端视频进程 CPU 增量目标不超过一个核的 `2%`。
4. eBPF Agent 的 CPU、内存、磁盘 WAL 和网络上报分别设置硬上限；初始 CPU 目标不超过整机
   `2%`，超限自动降采样或关闭高开销 probe。
5. Exporter 使用独立低优先级线程、批量和退避；禁止在控制 handler、ROS callback、
   GStreamer pad probe 中进行 OTLP、DNS、TLS、磁盘 fsync 或同步日志格式化。
6. 四组对照测试必须分开执行：全部关闭、仅本地业务事件、仅 eBPF Agent、业务事件加 Agent。

#### 分阶段实现顺序

1. **Phase V0：环境验收。** 在一台测试车检查 BTF/BPF/capability/cgroup，记录内核、镜像、
   Aura 版本和基线资源，不安装业务探针。
2. **Phase V1：本地事件层。** 新增 `ztd_observability`、有界队列、drop counter 和 JSONL
   调试 sink；先接 `cloudLinkPing`、控制异常、RTSP session、pipeline error 和首帧事件。
3. **Phase V2：单调阶段耗时。** 控制侧引入 `ReceivedEnvelope/InvocationContext`；视频侧增加
   ROS receive、push、encoder output、first RTP 的 steady-clock 字段。
4. **Phase V3：上下文传播。** 云端控制消息兼容加入 Trace Context；增加 `bindVideoTrace`，
   由 `ztd_cloud_driving` 发布 `VideoTraceBinding`，`ztd_rtsp` 订阅并维护 TTL registry。
   该阶段不改变 AES、控制门禁、编码参数和 RTSP URL。
5. **Phase V4：OTel 适配。** 在消费线程接 OpenTelemetry C++，批量导出到本机或同网段
   Collector；断网、超时和 Collector 故障必须快速失败并进入本地降级。
6. **Phase V5：eBPF/DeepFlow。** 独立部署 Agent，只开启进程、TCP/UDP、RTT、重传、队列和
   调度基础能力；通过 service/PID/五元组/时间窗与业务 Trace 关联。
7. **Phase V6：单车单路闭环。** 先验证一条 `remotejoystick` 和一路 `cam_f_12`，再扩展到
   多摄像头和车队；每扩大范围前更新本表状态和性能证据。

#### 车端验收矩阵

<table border="1">
  <thead>
    <tr>
      <th>场景</th>
      <th>车端业务证据</th>
      <th>eBPF/云端证据</th>
      <th>预期结论</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>正常手柄消息</td><td>receive、parse、handler、ROS publish 非负单调耗时，messageId 一致</td><td>同一连接 TCP send/recv 正常</td><td>控制消息已到车并发布 ROS</td></tr>
    <tr><td>消息解析失败</td><td>parse error、payload bytes、connection id，无原始 payload</td><td>TCP 接收正常</td><td>故障在协议/数据，不在网络断链</td></tr>
    <tr><td>ROS publish 变慢</td><td>handler/publish duration 增长</td><td>TCP RTT 正常，线程可能 off-CPU/run queue 增长</td><td>故障在车端进程或 ROS 调度</td></tr>
    <tr><td>控制链路丢包/重传</td><td>消息间隔、ping RTT 或 timeout 增长</td><td>TCP retrans/RTO/queue 增长</td><td>车云网络异常</td></tr>
    <tr><td>无 ROS 图像</td><td>RTSP client 存在但 <code>ros_frame_received</code> age 增长</td><td>ZLM 已连接，网络连接仍在</td><td>采集或 ROS 上游问题</td></tr>
    <tr><td>appsrc push 失败</td><td>GstFlowReturn 非 OK、flushing 或 pipeline error</td><td>RTSP 连接状态辅助</td><td>车端 GStreamer/pipeline 问题</td></tr>
    <tr><td>编码器停滞</td><td>ROS/appsrc 持续，encoder output age 增长</td><td>RTP/网络发送同步停止</td><td>编码器或 caps/资源问题</td></tr>
    <tr><td>车端 RTP 正常、ZLM 无流</td><td>first/last RTP 持续更新</td><td>车端 socket send 与 ZLM receive/RTSP 日志不一致</td><td>车云网络、NAT、防火墙或 ZLM ingest 问题</td></tr>
    <tr><td>ZLM 有流、浏览器黑屏</td><td>车端 ROS、编码、RTP 正常</td><td>ZLM/WebRTC 正常或浏览器 decoder/render 异常</td><td>问题不在车端采集和编码</td></tr>
    <tr><td>Collector/Agent 故障</td><td>drop counter 或 exporter error 增长，业务事件生产不阻塞</td><td>观测后端不可用</td><td>控制和视频必须继续正常</td></tr>
</tbody>
</table>

#### 9.1.5 公开行业参考与本项目最佳取舍

目前没有足够的公开证据证明小米、小鹏或理想在量产车端采用本项目所列的固定组合
`eBPF + OpenTelemetry + DeepFlow + DataBuff`，也不能据此推断其内部的 Trace SDK、采样策略、
车端 Agent 权限和数据后端。公开资料最多能说明行业会采用类似的观测思路，不能替代厂商内部
架构、版本和性能数据。

公开可参考的方向有两类：

1. 小鹏公开的远程驾驶相关专利描述了将传感器采集、云端反馈、控制传输、驾驶舱和执行器等
   环节拆开测量延迟；另有公开专利描述从图像注入、车辆、云端、驾驶舱、显示屏到外部相机的
   时间戳测量。这类资料证明“分段时间账本和物理测量”是合理的工程方向，但不构成小鹏量产
   软件实现的证明。
2. DeepFlow 官方站点将小米、理想汽车等列为客户/品牌展示，但没有公开其具体业务范围、
   车端部署边界、Agent 配置或 Trace 字段。因此这只能说明存在产品或技术合作/使用的公开
   信号，不能证明小米汽车或理想汽车车端使用了同一套 Agent、OTel SDK、DataBuff 或相同的
   业务字段。小鹏汽车的公开专利可以证明其重视远程驾驶分段时延和物理链路测量，但仍不能
   证明其量产系统采用本项目列出的具体软件组件组合。

本项目不应以“是否使用某个厂商同名技术”为验收标准，而应以能否得到以下证据为准：

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>层次</th>
      <th>车端最佳实现</th>
      <th>能回答的问题</th>
      <th>不能替代的内容</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>业务账本</td>
      <td><code>ztd_cloud_driving</code> 和 <code>ztd_rtsp</code> 输出结构化事件、messageId、session、stream、阶段状态和结果</td>
      <td>这条控制消息或这路视频当前处于哪个业务阶段，是否解析、发布、编码、首帧和恢复成功</td>
      <td>不能证明内核网络实际收发，也不能证明 ROS 下游或浏览器已经消费</td>
    </tr>
    <tr>
      <td>单调耗时</td>
      <td>每个进程使用 <code>steady_clock</code> 或等价单调时钟记录阶段起止和 <code>duration_ns</code></td>
      <td>同一进程内收包、解析、handler、publish、appsrc、编码和 RTP 阶段耗时</td>
      <td>不能把不同机器的墙钟相减当成端到端 latency</td>
    </tr>
    <tr>
      <td>上下文关联</td>
      <td>控制协议兼容 <code>traceparent</code>；视频使用 <code>videoSessionId</code> 和短 TTL 预绑定；缺失时明确标记时间窗降级</td>
      <td>将一次远控会话、一次操作、一路视频和一次恢复关联起来</td>
      <td>不能要求旧车端、旧云端或 ZLM 一次性升级，否则会扩大上线风险</td>
    </tr>
    <tr>
      <td>系统事实</td>
      <td>独立 eBPF/DeepFlow Agent 采集 TCP/UDP、RTT、重传、socket queue、调度、CPU、RSS 和进程生命周期</td>
      <td>网络是否重传、队列是否堆积、线程是否 off-CPU、资源是否异常</td>
      <td>不能识别 remotejoystick、H.264 IDR、ROS 业务语义或浏览器渲染结果</td>
    </tr>
    <tr>
      <td>数据缓冲</td>
      <td>本地有界队列和可选 WAL/DataBuff 只承担批量、断网缓存、重试和丢弃计数</td>
      <td>观测后端短时不可达时保留关键事件，并控制磁盘和内存上限</td>
      <td>不是 Trace 生成器，也不能进入控制、编码和重连同步路径</td>
    </tr>
    <tr>
      <td>验证闭环</td>
      <td>线上事件与实验室外部相机、显示屏、注入帧或 GPIO/LED 物理信号进行抽样校准</td>
      <td>确认“车端 RTP 正常但画面黑屏”是否发生在 ZLM、WebRTC、解码或显示渲染</td>
      <td>物理测量成本高，不适合每条消息或每个视频帧长期在线采集</td>
    </tr>
  </tbody>
</table>

结合当前两个车端服务，推荐的最小可行顺序是：

1. **先做车端本地事件层和单调账本。** 控制侧先覆盖 TCP receive、decrypt、parse、handler、
   ROS publish；视频侧先覆盖 RTSP client、ROS frame、appsrc、encoder output、first RTP、
   pipeline error。此阶段不引入网络 Exporter，不改变控制和视频行为。
2. **再做跨进程和跨节点关联。** 云端通过控制通道发送短 TTL 的 `bindVideoTrace`，由
   `ztd_cloud_driving` 转发给 `ztd_rtsp`；控制 Trace 通过 `traceparent` 兼容传播。旧版本
   缺少上下文时使用 `messageId`、stream、五元组和时间窗，并显式标记关联质量。
3. **然后启用 eBPF/DeepFlow 系统证据。** 先只采集连接、收发、重传、队列、调度和资源，
   用 PID/cgroup/socket cookie/五元组与业务事件关联。不要把完整 Trace ID 写入 RTP，也
   不要逐 RTP 包生成 Span。
4. **最后接 OTel Gateway、Collector 和 DataBuff/WAL。** Exporter 必须异步、批量、采样、
   快速失败；观测链路不可达时只增加 drop/error 事件，不得触发视频重载、重连、控制降级或
   安全动作。
5. **完成单车单路闭环后再扩容。** 先验证一条 `remotejoystick` 和一路
   `cam_f_12`，再扩展多路视频、更多车型和车队；每次放量都要更新 DSH 进度表并附性能
   对照证据。

因此，本项目的最佳方案不是“车端全量接入所有观测组件”，而是：

```text
车端业务事件 + 进程内 monotonic ledger
  -> ROS/GStreamer 稳定 hook
  -> eBPF/DeepFlow 系统事实
  -> OTel/Collector/DataBuff 异步传输与留存
  -> 云端 ZLMediaKit + 浏览器事件
  -> DSH 只读证据关联和根因分析
```

其中业务事件和单调账本是车端的必选基础，eBPF/DeepFlow 是系统侧补证，OTel 是统一传输
语义，DataBuff/WAL 是可靠性缓冲，DSH 是分析和治理控制面。任何一层失效都必须降级为较低
关联质量，而不能阻断控制或视频主链路。

#### 9.1.6 三家公开方案整理与当前车端映射

以下内容只采用公开专利、公开技术交流和公开厂商联合案例。它们可以证明某种工程方法
存在或被公开讨论，不能证明厂商内部所有车型、所有量产版本都使用相同实现。

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>厂商/公开资料</th>
      <th>公开可确认的做法</th>
      <th>对当前项目的可借鉴点</th>
      <th>不能直接下的结论</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>小米：DeepFlow 在小米落地的公开 Meetup 材料</td>
      <td>在既有 Hera、Falcon 等监控体系上补充 DeepFlow；通过 eBPF/cBPF 获取应用和网络观测，使用 socket、五元组、进程和发布系统信息做应用关联；针对老内核、LVS、混部进程和高基数连接做适配与过滤。</td>
      <td>车端可保留现有日志/指标体系，再用 eBPF 补充 TCP/UDP、重传、队列、调度和进程资源；低版本内核采用能力探测和降级，而不是假设 eBPF 一定可用；对长连接、无效进程和高频事件限流。</td>
      <td>不能据此证明小米汽车使用 DeepFlow、OTel、DataBuff 或同一套车端 Agent 配置。</td>
    </tr>
    <tr>
      <td>小鹏：CN113904959A/B、CN119232920A/B 等远程驾驶时延资料</td>
      <td>公开资料将远程驾驶拆为传感器采集/输出、云端反馈、控制传输、执行器响应等阶段；图像全链路测试还采用时间戳注入、链路中间点记录以及显示屏前智能相机等物理测量手段。</td>
      <td>车端必须建立控制和视频的阶段账本；线上用本进程 monotonic duration，实验室用注入帧、显示屏相机或 GPIO/LED 做端到端校准；把命令、视频、数据/状态通道分开监控。</td>
      <td>专利不是量产代码证明，也不能说明其内部使用 OTel、eBPF、DeepFlow 或某种 Trace SDK。</td>
    </tr>
    <tr>
      <td>理想：车端数据架构公开联合案例</td>
      <td>公开案例描述将采集、解码和时序数据库部署到车端，在车端先将原始报文结构化、压缩并按文件上传对象存储，以降低流量和云端处理压力，避免大数据上传阻塞实时通信。</td>
      <td>车端观测采用本地有界队列/WAL/DataBuff 作为异步缓冲；控制和视频事件先落本地轻量结构，批量上传；上传失败、磁盘满或后端不可达时只丢弃低优先级观测，不能阻塞实时线程。</td>
      <td>该案例不等于理想汽车采用 DeepFlow 或 OTel，也不等于本项目可以直接复制其数据库、压缩算法和上传协议。</td>
    </tr>
  </tbody>
</table>

三家公开资料汇总后的共同模式是：

```text
车端本地采集和结构化
  -> 分段时间账本
  -> 本地有界缓存/批量上传
  -> 业务语义与网络/进程事实关联
  -> 云端服务、媒体节点和驾驶舱继续补证
  -> 线上诊断 + 实验室物理校准
```

本项目当前车端不能简单照搬“全量 Trace”或“全量 eBPF”。`ztd_cloud_driving` 的控制消息、
`ztd_rtsp` 的视频帧和 RTP 包速率不同、线程模型不同、敏感性不同，必须采用分层采集。

#### 9.1.7 当前车端节点性能监控设计

车端节点监控分为四个层次。第一层是业务进程自身指标，第二层是进程/线程资源，第三层是
网络和内核事实，第四层是观测系统自身健康。四层都必须具备开关、采样和资源上限。

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>层次</th>
      <th>采集对象</th>
      <th>首期字段</th>
      <th>当前实现位置</th>
      <th>用途</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>业务进程</td>
      <td><code>ztd_cloud_driving</code></td>
      <td>连接数、收包数、解析失败、handler 耗时、ROS publish 耗时、reply/timeout、MRC/模式变化</td>
      <td><code>_receive_message()</code>、<code>_process_message()</code>、<code>handle_remotejoystick()</code></td>
      <td>定位控制消息卡在协议、业务、ROS 还是下游执行</td>
    </tr>
    <tr>
      <td>业务进程</td>
      <td><code>ztd_rtsp</code></td>
      <td>pipeline 数、client 数、ROS 帧 age、丢帧、appsrc push、编码输出 age、IDR、RTP 首帧、Gst error</td>
      <td><code>ros2_image_callback()</code>、<code>push_data()</code>、<code>idH264</code>/<code>pay0</code> probe</td>
      <td>定位黑屏发生在采集、队列、appsrc、编码、RTP 或 RTSP 会话</td>
    </tr>
    <tr>
      <td>进程/线程</td>
      <td>控制、RTSP、ROS executor、GStreamer 线程</td>
      <td>CPU、RSS、线程数、上下文切换、run queue、off-CPU、page fault、OOM、进程退出</td>
      <td>eBPF/DeepFlow + 进程自监控</td>
      <td>解释业务耗时增长是否由调度、CPU 抢占、内存压力或进程重启造成</td>
    </tr>
    <tr>
      <td>网络/内核</td>
      <td>车云 TCP、RTSP/RTP UDP、DDS/ROS 2 socket</td>
      <td>连接状态、socket cookie、五元组、RTT、重传、RTO、零窗、发送/接收队列、网卡 drop</td>
      <td>eBPF/DeepFlow Agent</td>
      <td>区分应用处理慢、车云网络抖动、NAT/防火墙和网卡/内核丢包</td>
    </tr>
    <tr>
      <td>观测系统</td>
      <td>本地队列、WAL/DataBuff、Exporter、Agent</td>
      <td>队列深度、drop counter、WAL 使用量、重试、上报延迟、Agent CPU/RSS、Collector 可达性</td>
      <td><code>ztd_observability</code> 和 Agent 自监控</td>
      <td>证明观测故障没有反向影响控制和视频</td>
    </tr>
  </tbody>
</table>

节点监控实现顺序：

1. 在目标车载镜像执行 V0 环境验收，记录内核、BTF、BPF syscall、JIT、cgroup、权限模型、
   PID/network namespace 可见性和基线 CPU/RSS/FPS。
2. 先增加进程自身的低开销 counters/histograms 和关键错误事件，不安装 eBPF，不改变实时
   控制线程和 GStreamer pipeline。
3. 再接入独立 eBPF Agent，首期只启用连接、收发、重传、socket queue、调度、CPU/RSS 和
   进程生命周期；不抓原始控制 payload，不抓视频内容，不逐 RTP 包导出。
4. 为控制进程、RTSP 进程和观测 Agent 分配独立 service/resource 属性；使用
   `cgroup_id + pid + socket_cookie` 和五元组/时间窗关联，不能把自动网络 Span 伪装成业务
   Span 的子 Span。
5. 将本地事件、Agent 指标和后续 OTel Exporter 分成四组对照：全关闭、仅业务事件、仅
   eBPF、业务事件加 eBPF；分别测控制 P99、视频 FPS/冻结、CPU、RSS、磁盘和网络增量。

#### 9.1.8 三条车-云-端链路的全链路追踪

三条链路共用车辆、驾驶舱和远控会话关联，但不共用同一个长生命周期 Trace：

**当前阶段收敛（2026-08-29）：** 暂不依赖驾驶仓埋点，先验收
`ziot cloud_receive -> latest-only/send_complete -> vehicle TCP body receive ->
decrypt/parse/dispatch -> handler -> ROS publish`。本阶段只判断云端进入后的下行
链路是否有发送阻塞、网络异常、车端接收/解析/处理变慢；ROS publish 返回不代表
下游控制器或底盘已经执行。DeepFlow/eBPF 作为 TCP、进程、容器和调度事实来源，
不替代云端/车端业务事件，也不单独提供单条消息的业务关联。

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>链路</th>
      <th>端到端拓扑</th>
      <th>主关联键</th>
      <th>车端必采事件</th>
      <th>耗时口径</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>指令链路</td>
      <td>驾驶舱手柄 -> 云端接入/业务 -> 车云 TCP -> <code>ztd_cloud_driving</code> -> ROS 2 -> 安全门禁/控制器 -> 执行器 -> 状态确认</td>
      <td><code>remoteSessionId</code>、<code>messageId</code>、<code>functionId</code>、<code>traceId</code>、<code>correlationId</code></td>
      <td><code>control_received</code>、<code>decrypt_completed</code>、<code>parse_completed</code>、<code>handler_started/completed</code>、<code>ros_publish_completed</code>、下游 <code>subscriber_received</code>、<code>safety_gate_evaluated</code>、<code>actuator_command_sent</code></td>
      <td>各进程内用 monotonic duration；跨节点只记录发送/接收事件、offset 和关联质量</td>
    </tr>
    <tr>
      <td>视频链路</td>
      <td>摄像头/ROS 帧 -> <code>ztd_rtsp</code> -> appsrc -> 编码器 -> RTP/RTSP -> 云端 ZLMediaKit -> WebRTC -> 浏览器 ontrack/decode/render</td>
      <td><code>remoteSessionId</code>、<code>videoSessionId</code>、<code>streamApp</code>、<code>streamName</code>、RTSP session、SSRC、五元组</td>
      <td><code>ros_frame_received</code>、<code>appsrc_push_completed</code>、<code>encoder_output</code>、<code>idr_output</code>、<code>rtp_first_packet</code>、<code>rtp_last_packet</code>、<code>pipeline_error</code>、<code>client_disconnected</code></td>
      <td>车端记录 ROS->push->encode->RTP 的本地阶段耗时；云端和浏览器分别记录拉流、WebRTC、解码和渲染阶段</td>
    </tr>
    <tr>
      <td>状态上报链路</td>
      <td>车端状态采集 -> 车云上报 -> EventBus -> queue -> WebSocket send -> 浏览器 receive -> RAF/apply</td>
      <td><code>remoteSessionId</code>、状态消息序号、<code>correlationId</code>、车端/云端/浏览器事件序列</td>
      <td><code>status_publish</code>、<code>eventbus_received</code>、<code>queue_enqueued</code>、<code>websocket_sent</code>；浏览器已有 <code>status_ws_message_sample</code>、<code>status_ws_browser_applied</code></td>
      <td>车端、云端、浏览器各自使用本地 monotonic duration；固定约 37 秒的车端偏移只做 offset 记录，不计算跨域真实 latency</td>
    </tr>
  </tbody>
</table>

三条链路的 Trace 关系建议如下：

```text
remoteSessionId
  ├── command trace: cockpit -> cloud -> ztd_cloud_driving -> ROS/control
  ├── video trace: bindVideoTrace -> ztd_rtsp -> ZLM -> WebRTC -> browser
  └── status trace: vehicle status -> EventBus -> WebSocket -> browser apply
```

其中：

```text
remoteSessionId = 数小时远控会话
traceId         = 一次指令、一次视频建连/恢复或一次状态异常
spanId          = 某一阶段，如 parse、ROS publish、encoder、ZLM、browser render
messageId       = 协议级单条消息，不得被 traceId 替代
videoSessionId  = 一路逻辑视频会话，不得用 stream 名称单独替代
```

车端实现必须支持旧版本降级：

1. 旧云端没有 <code>traceparent</code> 时，车端生成本地 Trace，并以
   <code>messageId + connectionId</code> 作为关联证据。
2. 没有 <code>bindVideoTrace</code> 时，RTSP 生成本地 <code>videoSessionId</code>，以
   stream、五元组和时间窗与 ZLM 关联，并标记 <code>time_window</code>。
3. Agent 或 Collector 不可用时，本地业务事件继续运行；队列满时按优先级丢弃，不得阻塞
   控制收包、ROS 回调、编码和 RTP 发送。
4. 任意观测字段解析失败、Trace Context 非法或时钟域未同步，只降低数据质量字段，不拒绝
   控制消息、不触发视频重载、不改变安全门禁。

#### 9.1.9 车端分阶段实施计划

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>阶段</th>
      <th>实施内容</th>
      <th>涉及模块</th>
      <th>完成判据</th>
      <th>失败隔离</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>V0 环境基线</td>
      <td>采集内核、BTF、权限、cgroup、CPU/RSS/FPS、网络和进程基线</td>
      <td>车载镜像、启动脚本、Agent 安装环境</td>
      <td>目标车型形成可复现基线报告</td>
      <td>只读检查，不改变业务配置</td>
    </tr>
    <tr>
      <td>V1 业务事件</td>
      <td>新增本地有界队列、结构化事件、drop counter；覆盖控制异常、RTSP 生命周期、首帧和 pipeline error</td>
      <td><code>ztd_observability</code>、<code>ztd_cloud_driving</code>、<code>ztd_rtsp</code></td>
      <td>事件可在本地 JSONL/诊断接口查询，生产线程无阻塞</td>
      <td>事件失败只丢观测，不影响实时业务</td>
    </tr>
    <tr>
      <td>V2 单调耗时</td>
      <td>补齐 receive/decrypt/parse/handler/publish 和 ROS/push/encode/RTP 阶段计时</td>
      <td>控制和视频业务代码</td>
      <td>同进程 duration 非负、单位统一、P95/P99 可聚合</td>
      <td>不使用跨机器时间相减</td>
    </tr>
    <tr>
      <td>V3 跨进程关联</td>
      <td>新增 <code>VideoTraceBinding</code>、TTL registry 和旧版本回退；控制协议兼容 Trace Context</td>
      <td><code>ztd_network_monitoring_msgs</code>、两个车端进程、云端控制协议</td>
      <td>单次远控会话可以关联一路视频建连和恢复事件</td>
      <td>绑定缺失时继续提供 stream/五元组/时间窗证据</td>
    </tr>
    <tr>
      <td>V4 节点 eBPF</td>
      <td>启用网络、调度、进程和资源采集，完成 socket cookie/PID/cgroup 关联</td>
      <td>DeepFlow/eBPF Agent、车端 host</td>
      <td>能区分应用慢、网络重传、调度阻塞和资源不足</td>
      <td>Agent 可单独停止；业务进程继续运行</td>
    </tr>
    <tr>
      <td>V5 OTel/WAL</td>
      <td>消费线程批量转换 OTLP，接本地 Collector/Gateway；WAL/DataBuff 异步缓存和限额</td>
      <td>OTel C++、Collector、DataBuff/WAL</td>
      <td>断网可缓存、恢复可补传，观测链路错误可量化</td>
      <td>快速失败、退避、磁盘满自动降级</td>
    </tr>
    <tr>
      <td>V6 云端和浏览器闭环</td>
      <td>接入 ZLMediaKit、WebRTC stats、浏览器本地事件、状态 WebSocket 事件</td>
      <td>ZLM、云端网关、前端 WebRTC/状态模块</td>
      <td>视频黑屏可定位到采集/编码/RTP/ZLM/WebRTC/解码/渲染，指令和状态可分段定位</td>
      <td>前端上报或监听异常不触发重载和重连</td>
    </tr>
    <tr>
      <td>V7 物理校准与放量</td>
      <td>使用注入帧、显示屏相机或 GPIO/LED 抽样校准线上事件；完成单车单路到车队放量</td>
      <td>实验室测试设备、测试平台、DSH 证据包</td>
      <td>线上账本与物理测量误差在批准阈值内，性能预算通过</td>
      <td>不把实验室探针带入生产全量路径</td>
    </tr>
  </tbody>
</table>

#### 9.1.10 GreptimeDB Edge 与 Apache Arrow 车云数据平面

设计状态：`approved`。本节的详细数据模型、格式边界、车端分层、断网补传、资源预算
和实施阶段见[专题文档 06](observability/06-greptime-edge-and-arrow.md)。

结合当前车端 `ztd_cloud_driving`、`ztd_rtsp` 和既有前端本地埋点，最终采用以下边界：

```text
业务事件/monotonic ledger
  -> 有界队列
  -> GreptimeDB Edge 或 OTel 异步批次
  -> Arrow 内存/IPC/批量传输
  -> DataBuff/WAL 断网缓存
  -> 云端 GreptimeDB/Collector/DeepFlow
  -> Parquet 长期归档
  -> DSH 只读证据关联
```

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>决策</th>
      <th>当前结论</th>
      <th>对黑屏和全链路追踪的意义</th>
      <th>状态</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>GreptimeDB Edge</td>
      <td>候选车端时序和诊断数据平面；不进入控制、编码、RTP 和 WebRTC 重连同步路径</td>
      <td>可在车端保留 CPU/RSS、编码 age、RTP gap、首帧和恢复窗口，断网后再上传</td>
      <td><code>approved</code></td>
    </tr>
    <tr>
      <td>Arrow</td>
      <td>实时内存列式布局、跨语言交换和批量上传格式</td>
      <td>降低事件批量转换和上传开销，但不生成 Trace，也不替代业务事件</td>
      <td><code>approved</code></td>
    </tr>
    <tr>
      <td>Parquet</td>
      <td>车端诊断文件和云端对象存储归档格式</td>
      <td>便于按车辆、会话、时间窗做历史黑屏和控制异常回放</td>
      <td><code>approved</code></td>
    </tr>
    <tr>
      <td>WAL/DataBuff</td>
      <td>异步缓存、重试、checksum、断点续传和淘汰策略</td>
      <td>观测后端短时不可用不丢失关键诊断窗口，同时不反压实时视频和指令</td>
      <td><code>approved</code></td>
    </tr>
  </tbody>
</table>

GreptimeDB Edge Manager 只作为数据平面的控制面使用，负责 Edge 设备、
数据模型、质量检查、上传任务、版本和设备健康管理。它不能直接下发车辆控制、
同步触发视频 reload，也不能成为控制、视频或状态实时链路的单点依赖。

三者边界固定如下：

```text
Arrow     = 内存列式布局、跨语言交换和微批传输
Parquet   = 压缩落盘、对象存储和历史归档
Trace     = traceId/spanId/parentSpanId/correlationId 的链路语义
```

Arrow 和 Parquet 都可以携带 Trace 字段，但不能替代 Trace Context；WAL/DataBuff
只负责异步缓存、重试、校验和断点续传，也不负责生成 Trace。GreptimeDB Flow、
SQL 和 UDF 首期只用于诊断派生、窗口聚合和异常告警，不能直接触发控制、视频 reload
或其他安全动作。Flow 实施优先采用目标版本支持的 batching mode；旧式非聚合
streaming mode 是否可用必须纳入版本矩阵。向量类型只作为后续感知特征诊断 POC，
目标版本、查询性能和资源成本必须单独验证。

首期不承诺公开案例中的固定写入吞吐、CPU、内存或压缩比例；这些数字必须在目标车辆
上用“全关闭、本地事件、Edge 写入、全链路上传”四组对照实测。只有在能力、性能、断网
恢复、数据安全和版本兼容性验证通过后，才能更新 DSH 状态并进入车队放量。

### 9.2 第一阶段现场验证步骤

先选择一台测试车、一个驾驶舱和前视一路视频，固定车辆版本、前端版本、ZLMediaKit 节点和网络环境。
不要同时调整码率、重连阈值、ZLM 配置和车端推流参数。

1. 部署本次前端和 `parallel-driving-manager`，打开远控页面。
2. 在页面控制条打开“诊断采集”，再在浏览器控制台注册事件观察器：

```javascript
window.__pdObsHandler = (event) => {
  console.info('[parallel-driving-observation]', event.detail)
}

window.addEventListener(
  'parallel-driving-observation',
  window.__pdObsHandler,
)
```

3. 在浏览器 Network 的 WebSocket Frames 中确认状态消息包含：

```text
timestamp
eventbusReceivedAt
websocketQueuedAt
websocketSentAt
```

4. 连续观察至少 10 分钟，确认能收到：

```text
status_ws_open
status_ws_first_message
status_ws_message_sample
status_ws_browser_applied
status_ws_last_message_age
video_health_change
```

5. 保存一次正常基线，至少包含首帧耗时、FPS、码率、丢包、RTT、jitter、freeze、PLI、NACK 和
   状态链各阶段耗时。
6. 逐个执行可回滚故障注入，每次只改变一个条件：

| 验证场景 | 操作 | 预期分类或证据 |
|---|---|---|
| ZLM 信令不可达 | 测试环境阻断 `/index/api/webrtc` | `S1_SIGNAL_FAILED`，有 HTTP/网络错误和 attempt |
| 流不存在 | 停止单路车端推流或使用隔离测试流名 | `S2_STREAM_NOT_FOUND`，记录 app/stream 和 ZLM msg |
| SDP 成功但无首帧 | 保持信令成功并阻断媒体路径 | 10 秒后 `no_first_frame`，且旧连接计时器不得影响新连接 |
| ICE 失败 | 测试环境阻断对应 UDP 媒体端口 | `S3_ICE_FAILED` |
| RTP 停止 | 建链后停止车端单路推流 | `S4_RTP_STALLED` 或 ZLM 流注销证据 |
| RTP 在进但画面不动 | 使用浏览器/解码器专项测试条件 | `S5_RENDER_STALLED` 或 `S6_DECODER_FREEZE` |
| 状态延迟 | 延迟测试车状态发送，不影响视频 | `vehicleToEventbusMs` 明显增长，云端和浏览器阶段保持正常 |
| 云端排队 | 在隔离环境制造服务背压 | `eventbusToQueueMs` 或 `queueToSendMs` 增长 |
| 浏览器阻塞 | 在隔离页面制造主线程长任务 | `browserToAppliedMs` 增长 |

7. 每个场景至少重复 3 次，记录误分类、漏报、恢复耗时和是否出现重连风暴。
8. 只有证据稳定后，才进入 ZLMediaKit 指标采集、DeepFlow 部署和阈值优化。

### P0：建立可定位的事实链

先保留现有业务逻辑，只补结构化日志和低基数指标。所有事件至少带：

```text
vehicle_id
cockpit_id
session_id
route_type
camera
stream_app
stream_name
trace_id（无法贯穿时使用 correlation_id）
event_time
```

`vehicle_id`、`cockpit_id` 不作为 Prometheus 标签，放在结构化日志、Trace 属性和低频 Incident
事件中，避免高基数。

状态上报必须记录以下时间点：

```text
vehicle_message_timestamp
broker_received_at
eventbus_received_at
websocket_queued_at
websocket_sent_at
browser_received_at
browser_applied_at
```

由此计算：

```text
vehicle_to_broker
broker_to_eventbus
eventbus_to_websocket_queue
websocket_queue_to_send
send_to_browser
browser_to_ui
```

如果 `vehicle_message_timestamp` 本身已经落后当前时间约 60 秒，根因在车端缓存、车端调度、
网络重传或 Broker；如果 EventBus 到达及时但 WebSocket 发送落后，才检查云端背压、线程池和连接清理。

### P1：先打通状态链和浏览器生命周期

云端 `ParallelDrivingWebSocketHandler` 需要新增：

- WebSocket active/connect/close/reconnect 计数。
- 订阅成功、订阅异常、类型转换异常计数。
- 状态消息 received、stale、sink emit failure 计数。
- EventBus、入队、实际发送的 Timer。
- 当前连接的 `vehicle_id`、`cockpit_id`、订阅主题和绑定车辆，写入结构化日志。
- 使用类型过滤替代无保护的 `cast(ReportPropertyMessage.class)`，订阅流异常时必须保留错误指标。
- 核对并补充 `/org/*/device/.../message/property/report` 和 `function/reply` 主题；不能仅凭
  `/device/*/...` 主题判断所有上报都能被消费。

前端 WebSocket 工具需要把现有空回调接入页面诊断：

```text
ws_connect_start
ws_open
ws_error
ws_close
ws_reconnect
ws_first_message
ws_last_message_age
```

页面至少显示或上报 `last_message_age`。不能把车辆在线轮询当作实时状态链路；当前轮询周期为 5 秒，
只适合在线状态和会话状态，不适合解释 1 分钟级延迟。

### P1：补齐视频会话证据

`WebRtcPlayer` 已经能够识别 `healthy`、`stall_inbound`、`stall_render`、`disconnect_ice`、
`peer_disconnected` 和 `recovering`，也已经采集 FPS、RTT、jitter、码率、丢包、分辨率、解码器、
PLI、NACK 和 freeze。

下一步必须完成事件上收：

1. `VideoCell` 转发 `media-health-change`。
2. `VehicleRemoteDeck` 为每一路绑定 `vehicle_id/session_id/camera/app/stream`。
3. 首次调用 `/index/api/webrtc`、收到 SDP、ICE connected、`ontrack`、首帧、卡顿、重拉、
   恢复和最终失败分别记录事件。
4. 记录 ZLMediaKit 返回的 HTTP 状态、业务 `code/msg`、app/stream、attempt 和耗时。
5. 将 `stream not found`、`Failed to fetch`、ICE failed、RTP 收流停滞、RTP 在进但无渲染帧
   分成不同故障原因，禁止统一记成“黑屏”。

当前配置中 ZLMediaKit 地址、app 生成规则和摄像头流名直接影响首帧：

```text
baseUrl = http://10.7.30.44
app = vehicle.internalCode
stream = cam_f_12 / ipm / cam_f_7 / cam_b_18 ...
```

这些值必须在诊断事件中记录为可检索字段；若车辆 `internalCode` 变化或短暂为空，必须能够证明
播放器是否发生了全路重挂载。

### P1：ZLMediaKit 和网络侧并行采集

云端先采集 ZLMediaKit 的流在线状态和服务日志，再部署 DeepFlow/eBPF。至少建立以下检查：

```text
车端编码进程是否持续输出帧
车端 RTSP 是否持续发送
ZLMediaKit 是否收到 RTSP、最近收到包时间、输入码率
ZLMediaKit 是否存在对应 app/stream
WebRTC offer/answer 是否成功
ICE/DTLS 是否成功
浏览器 inbound-rtp 是否持续增长
浏览器 requestVideoFrameCallback 是否持续出帧
```

DeepFlow 首期只关注节点、进程、TCP/UDP、RTSP 和 WebRTC 信令/媒体路径，观察：

- 车端到 ZLMediaKit 的 RTT、重传、丢包、连接重建和 socket 队列。
- ZLMediaKit CPU、内存、线程、连接数、UDP 接收队列和出口带宽。
- 云端入口和 ZLMediaKit 节点看到的 HTTP 信令耗时、UDP 媒体可达性和连接失败。
- 浏览器侧的完整 HTTP、ICE、RTP、解码和渲染阶段由 RUM/OTel 主动上报，再通过
  `sessionId/videoSessionId/app/stream` 与 DeepFlow 时间窗关联。

不要一开始在车端打开全量系统调用、全量抓包或高开销 profile；先用单车、单路、单版本做基线。

### P2：形成两个可复用的 Incident Envelope

黑屏事件：

```json
{
  "incident_type": "remote_video_black_screen",
  "vehicle_id": "...",
  "session_id": "...",
  "camera": "front",
  "app": "...",
  "stream": "cam_f_12",
  "window": "前后各 2 分钟",
  "evidence": [
    "webrtc_offer_result",
    "zlm_stream_state",
    "ice_state",
    "inbound_rtp_delta",
    "render_frame_delta",
    "deepflow_network_path",
    "recent_deployments"
  ]
}
```

状态延迟事件：

```json
{
  "incident_type": "vehicle_status_delivery_delay",
  "vehicle_id": "...",
  "session_id": "...",
  "message_id": "...",
  "source_timestamp": "...",
  "observed_delay_ms": 60000,
  "stage_durations": {
    "vehicle_to_broker_ms": null,
    "broker_to_eventbus_ms": null,
    "eventbus_to_websocket_ms": null,
    "websocket_to_browser_ms": null
  },
  "evidence": [
    "vehicle_agent_log",
    "mqtt_broker_log",
    "eventbus_metric",
    "websocket_metric",
    "browser_ws_lifecycle"
  ]
}
```

字段缺失时必须标记为 `unknown`，不能由 DSH 用模型推测。

### P2：Grafana 首批面板和告警

先建立四个页面：

1. **单车状态链**：最后上报时间、状态消息速率、各阶段 P95/P99、WebSocket 活跃连接和
   `last_message_age`。
2. **视频单路诊断**：首帧耗时、成功率、卡顿率、ICE 失败、重拉次数、码率、FPS、丢包、
   freeze、ZLMediaKit 流状态。
3. **ZLMediaKit 资源**：CPU、内存、连接数、输入/输出码率、RTSP 输入断流、WebRTC 信令错误。
4. **采集系统**：DeepFlow Agent/Collector up、队列、WAL、丢弃、上报失败和资源占用。

首批规则建议：

```text
vehicle_status_last_message_age > 10s：单车 P2，> 60s：单车 P1
vehicle_status_delivery_p95 > 2s：P2，> 10s：P1
video_first_frame_failure_ratio > 5%：P1
video_stall_ratio > 3% 或单路 5 分钟内自动重拉 > 3 次：P2
zlm_stream_not_found 持续 1 分钟：P1
DeepFlow/Collector 丢弃率 > 1%：P2
```

上述阈值在 POC 中按车型、网络制式和视频码率校准，不直接作为最终安全 SLO。

### P3：DSH 接入方式

DSH 首期只做四件事：

1. 接收 Incident Envelope。
2. 并行查询 Grafana/Prometheus、Loki、Tempo、DeepFlow、ZLMediaKit、Broker 和发布记录。
3. 按时间顺序生成证据图，输出根因候选、证据、反证和缺失数据。
4. 给出下一步 Runbook 建议，但默认不执行。

推荐的专项 Agent：

```text
VideoAgent       负责 ZLMediaKit/WebRTC/浏览器证据
TelemetryAgent   负责车端上报、Broker、EventBus、WebSocket
NetworkAgent     负责 DeepFlow/eBPF、RTT、重传、丢包和队列
ReleaseAgent     负责版本、配置、证书和最近变更
EvidenceReviewer 负责时间窗、来源、冲突证据和高基数泄露检查
```

只有以下低风险动作可以在后期经人工审批后开放：

```text
重新建立单路 WebRTC 会话
重新查询/刷新单路 ZLMediaKit 流状态
重启单个观测 Agent
对单车单路提高短时采样率
```

禁止 DSH 直接修改车辆控制参数、MQTT/CAN 数据、实时控制调度、ZLMediaKit 全局配置或批量重启车端进程。

## 10. 视频黑屏专项优先级

视频黑屏应作为第一阶段的主线问题，但“黑屏”必须先拆成不同状态，不能只用一个
`video_error` 计数器覆盖所有情况。

### 优先级判断

视频优先的原因：

- 直接影响远控人员是否能判断车辆周边环境。
- `WebRtcPlayer` 已有 ICE、RTP、渲染帧、解码器和自动恢复信号，短期内可获得较高诊断收益。
- 当前前端已经锁定车辆 `internalCode`，并对多路 SDP 请求做了错峰，适合先增加观测而不改变恢复策略。
- 视频故障与状态上报故障可能同时发生，必须保留状态 WebSocket 的 `last_message_age` 作为旁证。

第一阶段只追求“能准确分类和复现”，不立即修改重连阈值、码率策略或 ZLMediaKit 全局配置。

### 黑屏分类模型

```text
S0_NOT_MOUNTED
  页面没有挂载 VideoCell/WebRtcPlayer，或 selectedVideoDirections/app/stream 为空

S1_SIGNAL_FAILED
  /index/api/webrtc 请求失败、CORS/混合内容、HTTP 错误、ZLM code/msg 错误

S2_STREAM_NOT_FOUND
  ZLMediaKit 上 app/stream 不存在，或车端 RTSP 尚未推入

S3_ICE_FAILED
  SDP 已返回，但 ICE/DTLS/PeerConnection 未进入可用状态

S4_RTP_STALLED
  Peer 已连接，但 inbound-rtp bytes/packets 长时间不增长

S5_RENDER_STALLED
  RTP 仍在增长，但 requestVideoFrameCallback 长时间没有新帧

S6_DECODER_FREEZE
  浏览器解码器冻结，尤其是 VideoToolbox + 丢包后的 freeze

S7_SOURCE_REPLACED
  app/stream/baseUrl 发生变化，组件被 teardown 后重新建链

S8_UI_OBSCURED
  视频已经有帧，但被布局、黑色遮罩、全屏切换或组件卸载遮挡
```

每次黑屏 Incident 必须保存一个 `black_screen_state` 和一个 `black_screen_reason`，
例如 `S4_RTP_STALLED`，而不是只保存“自动重连失败”。

### 已修复的前端黑屏风险

本轮及前一轮前端修复已经覆盖以下会直接造成黑屏或放大黑屏的缺陷：

1. `internalCode` 轮询短暂为空时清空播放 app，导致多路播放器全部 teardown/reconnect。
   现在首次拿到非空 app 后按车辆和路由锁定，后续缺失值保留上次有效值。
2. 旧车辆、旧请求或旧路由响应覆盖当前车辆，导致 app/stream 错配。现在使用请求代际、
   车辆 ID 和路由 ID 校验，旧响应不能污染当前播放源。
3. 普通轮询中的 `internalCode` 变化直接驱动播放器 source。现在动态变化只记录
   `video_source_identity` / `raw_internal_code_changed`，不会直接 reload；只有换车或
   明确的播放身份变化才允许重建。
4. 同一路流的多个播放器各自建立连接或同时发起重连，造成信令、解码和主线程竞争。现在
   使用 shared WebRTC session、leader/refCount 和共享重连。
5. 250ms 统计轮询在 `getStats()` 变慢时重叠执行，放大主线程压力。现在每个播放器有
   单实例 in-flight 门禁；统计请求不会因为定时器重复而并发堆积。
6. `render_stall` 将 `display:none`、不可见 tab、HMR、系统休眠或主线程长任务误认为解码
   冻结。现在先检查 render eligibility，并在采样断档后重置可见渲染观察窗口。
7. VideoToolbox 只要被检测到就反复触发重连。现在仅在已经出现 freeze 时尝试一次 VP8
   优先协商，并保留冷却和会话内一次性保护。
8. 动态路由未注册时使用错误 href，产生 `No match found` 告警。现在使用 router history
   的 href 生成方式；这不是黑屏根因，但避免了路由跳转噪声。

上述修复不等于已经证明车端编码器或 ZLMediaKit 输入流没有问题。若出现黑屏，仍必须用
`inboundBytesDelta`、`framesDecoded`、`requestVideoFrameCallback`、video 可见性和
`video_source_identity` 联合归因。NACK 单独不能触发重连。

### WebRTC 周期摘要字段

每 30 秒由 shared session leader 输出一条低频摘要，除 FPS、码率、丢包、RTT、jitter、
freeze、PLI、NACK 和 decoder 外，还应包含：

```text
frames_decoded
decoded_frames_delta
inbound_bytes_delta
inbound_bytes_received
last_frame_age_ms
video_ready_state
video_paused
video_render_eligible
rvfc_monitoring
stats_sample_gap_ms
render_stall_candidate_ms
inbound_zero_streak
peer_state
ice_state
document_hidden
```

判定矩阵：

| 证据 | 主要结论 |
|---|---|
| `inbound_bytes_delta=0` 且 Peer/ICE 正常 | 优先查车端推流、ZLMediaKit 输入流和媒体路径 |
| RTP 字节持续增长、`frames_decoded` 不增长 | 优先查浏览器解码器或编码参数 |
| 解码帧增长、`last_frame_age_ms` 增大且不可渲染 | 优先查布局、遮罩、`display:none`、video 尺寸 |
| 采样间隔明显大于周期 | 先排除 HMR、休眠、隐藏 tab 或主线程长任务，不要立即重连 |
| NACK 增长但 freeze=0、FPS 正常 | 记录弱网趋势，不以 NACK 单指标重载视频 |

### 首批埋点

浏览器端每一路视频建立独立 `video_session_id`，并记录：

```text
session_start
webrtc_offer_start
webrtc_offer_http_result
zlm_stream_not_found
remote_sdp_received
ice_connected
peer_connected
ontrack
first_frame
inbound_stall_start
render_stall_start
decoder_freeze
reconnect_scheduled
reconnect_start
recovered
session_failed
session_stop
```

事件字段使用低基数维度和受控业务字段：

```text
vehicle_id
camera
app
stream
layout
browser
browser_version
network_type
reason
attempt
duration_ms
peer_state
ice_state
fps
bitrate_kbps
packets_lost
packets_received
decoder
```

车辆和会话字段进入 Trace/日志，不直接作为 Prometheus 标签。Prometheus 只保留
`camera`、`reason`、`protocol`、`result`、`environment` 等低基数标签。

### 前端改造顺序

1. `VideoCell` 转发 `WebRtcPlayer` 的 `media-health-change`。
2. `VehicleRemoteDeck` 为每一路传入车辆、会话和摄像头上下文。
3. 将 `fetch(/index/api/webrtc)` 的请求开始、HTTP 状态、ZLM `code/msg` 和耗时统一记录。
4. 将 `ontrack` 与真正的首帧分开记录；`ontrack` 不等于用户已经看到画面。
5. 将 `inbound-rtp` 和 `requestVideoFrameCallback` 分开记录，区分网络无流和解码/渲染冻结。
6. 记录 `baseUrl/app/stream` 变化，识别状态轮询或布局切换是否触发了全路重建。
7. 记录 `document.visibilityState`、全屏切换和 video `paused/readyState`，排除页面生命周期因素。

### 前端后续工作

当前还需要完成以下工作，才能把“浏览器看起来正常”升级为可闭环的生产证据：

1. 将 `parallel-driving-observation` 事件和 30 秒 WebRTC 摘要接入统一 OTel/RUM 出口，
   保留 `session_id`、`video_session_id`、`player_instance_id`、`shared_session_id`、车辆、
   摄像头和 app/stream 关联；首次拉流、重连和黑屏恢复分别创建短生命周期 Trace。
2. 在 ZLMediaKit 侧补充 app/stream 存在性、输入包年龄、输入/输出码率、关键帧和编码器
   信息，并与浏览器的 `inbound-rtp` 同一时间窗对齐。
3. 继续补浏览器布局证据：`document.visibilityState`、全屏切换、组件 mount/unmount、
   video 尺寸和遮罩层变化；HMR 事件应单独记录，现场复现时避免把 HMR 当故障因素。
4. 为 `internalCode` 锁定、旧响应丢弃、共享租约、stats in-flight 门禁和 render-stall
   误判分别增加单元测试；用 Playwright 覆盖换车、切换布局、隐藏 tab、HMR 后恢复和多路
   同流绑定场景。
5. 对 `cam_rb_10` 等 NACK 增长流建立 `NACK + packetsLost + framesDecoded + freeze`
   联合告警，禁止仅凭 NACK 自动重连。
6. 处理 Vue `default slot` 非函数告警，避免长期噪声掩盖 WebRTC 真正异常；它目前不是
   黑屏根因。

### 云端和 ZLMediaKit 对照证据

在同一 `video_session_id` 时间窗内，必须同时查询：

```text
车端编码进程帧率与 RTSP 发送状态
DeepFlow 车端 -> ZLMediaKit 的 TCP/UDP、重传、丢包和 socket 队列
ZLMediaKit app/stream 存在性、输入包时间、输入码率和输出连接
ZLMediaKit /index/api/webrtc 请求结果
浏览器 ICE、inbound-rtp 和渲染帧
最近的前端发布、车端配置、ZLMediaKit 配置和证书变更
```

这样可以快速归因：

| 现象 | 首要怀疑 |
|---|---|
| 没有 `offer_http_result` | 页面未挂载、参数为空或前端生命周期问题 |
| `code != 0` 且 stream not found | 车端未推流、app/stream 不一致或流注册晚于拉流 |
| SDP 成功但 ICE failed | UDP 可达性、externalIP、防火墙或 TURN |
| ICE connected 但 inbound-rtp 不增长 | ZLM 无输入、上游断流或媒体路径异常 |
| inbound-rtp 增长但无新渲染帧 | 浏览器解码器、VideoToolbox 或页面渲染问题 |
| 多路同时失败且 offer 请求集中 | ZLM 负载、浏览器并发、网络出口或同时重连风暴 |
| 单次状态变更后全部视频重建 | app/stream 变化、组件 v-if 卸载或布局重挂载 |

### 视频优先的 Grafana 面板

首个 Dashboard 只做五个区域：

1. 首帧成功率、首帧 P50/P95/P99。
2. 各 `black_screen_reason` 的数量和占比。
3. ICE 失败、RTP 停滞、渲染停滞、解码冻结、自动重连次数。
4. ZLMediaKit 各 app/stream 的输入包年龄、输入/输出码率和在线连接。
5. 单车单路时间线，联动浏览器日志、ZLM 日志、DeepFlow Trace 和最近变更。

建议起始告警：

```text
单路 5 分钟内首帧失败 >= 3 次：P2
关键前视流首帧失败率 > 5% 持续 5 分钟：P1
单路 render_stall 持续超过 5 秒：P2
单路 10 分钟内自动重连 > 3 次：P2
同一 ZLMediaKit 节点 5 分钟内多路 ICE 失败：P1
ZLMediaKit 输入流包年龄 > 3 秒：P1
```

### DSH 接入时机

DSH 不应在埋点完成前接入生产自动修复。正确顺序是：

```text
第一周：浏览器 + ZLM 事件完整
第二周：DeepFlow 网络证据和 Grafana 面板
第三周：回放真实黑屏事件，校验 DSH 根因排序
第四周：DSH 只读生成 RCA 和 Runbook
后续：人工审批后开放单路重连等低风险动作
```

DSH 对每次黑屏必须输出：

```text
最可能根因
支持证据
反证
尚未采集的证据
建议的下一步查询
是否允许执行恢复动作
```

## 11. POC 与落地顺序

### Phase 0：能力验收

- 在 x86、AD1、Jetson 各取一台设备。
- 检查内核版本、BPF syscall、BTF、JIT、CO-RE、capability 和容器权限。
- 建立 Agent CPU、内存、磁盘、网络和控制链路延迟基线。
- 验证断网、重启、证书过期和 Agent 升级行为。

### Phase 1：单链路打通

- 先打通一台车、一路前视视频的首帧和卡顿链路。
- 保留同车状态 WebSocket 分段时间戳作为视频故障旁证。
- 视频证据稳定后，再扩展到指令链路和其他摄像头。
- 验证车端 -> Collector -> Tempo/Prometheus/Loki/Grafana。
- 只将错误和关键 Trace 的受控副本发送到 DataBuff。

### Phase 2：DSH 只读分析

- 固化 Incident Envelope 和证据引用格式。
- 固定 DSH、模型、Cordis Profile、插件和 Skills 版本，建立升级兼容测试。
- 实现 Trace、Metric、Log、DeepFlow、Broker、部署、网关状态和车辆健康查询插件。
- 建立 Incident Coordinator、专项 Agent 和 Evidence Reviewer。
- 用 DC/FDC、视频首帧、指令超时等历史故障回放，验证根因排序、证据完整性和误判率。
- 验证 Session 仅追加记录、事故重放和分析结果可复现。
- 执行 Prompt Injection、越权查询、敏感数据外泄和恶意插件测试。
- 禁止接入生产写操作。

### Phase 3：车队扩展

- 按平台、版本和网络区域逐步放量。
- 建立采样、保留、成本和数据脱敏策略。
- 将视频和指令 SLO 纳入发布门禁。
- 先开放发布后验证、工单和建议，再通过人工审批开放有限的幂等 Runbook。
- 验证审批、短期凭证、执行审计、失败回滚和人工接管。
- 注入 DSH、模型、插件、Collector 和观测后端故障，确认业务链路不受影响。

## 12. 验收标准

POC 通过至少应满足：

- 关键 Trace 具备车端、云端和会话关联。
- 指令链路可以定位到具体阶段的 P95/P99 延迟。
- 视频首帧和卡顿可以区分采集、编码、网络、ZLM、WebRTC 和渲染原因。
- 断网后关键事件可本地留存并在恢复后补传。
- Agent 资源占用不突破车端预算，且不影响控制链路。
- DataBuff 故障不会阻断生产主链路。
- DSH、模型端点或任一插件故障不会阻断视频、指令、OTA、告警和人工运维链路。
- DSH 每个结论都带可复核的查询证据。
- DSH 能回放历史 Incident，并在固定数据、版本和配置下得到可解释且基本一致的结论。
- Evidence Reviewer 能识别无来源结论、时间窗错误、陈旧数据和相互冲突的证据。
- DC/FDC 案例能够区分“前序失败阻断初始化”和“配置未加载/缓存未刷新”，不能把没有日志当作连接成功。
- Prompt Injection、越权查询和敏感信息外泄测试全部通过。
- DSH 插件和 Skills 均固定版本、来源可追溯，并具备升级和回滚记录。
- DSH 没有生产写权限，所有受控动作均可审计、审批和回滚。
- 经审批执行的 Runbook 必须具备前置检查、影响范围、成功条件、退出条件和回滚结果。

## 12.1 2026-08-26 下一执行批次

已为下一批 POC 准备独立工具，目录为
`aura/tools/observability_poc/`。关机前仅完成代码和文档落盘，尚未运行测试、安装
`pyarrow`、部署 GreptimeDB Edge 或执行目标车辆验证。

下一批必须按顺序完成：

1. 建立 AD1、Jetson、x86 目标车型版本矩阵。
2. 在单车上完成 GreptimeDB Edge POC，先覆盖一路 `cam_f_12` 和一条
   `remotejoystick`。
3. 验证 Arrow/IPC 从内存批次、原子文件发布、读回、checksum、Schema 演进到回收的
   完整生命周期。
4. 验证断网 5 分钟、积压、磁盘水位、重启、重复 batch 和恢复幂等补传。
5. 执行 A/B/C/D 四组性能对照：全关闭、本地事件、Edge 写入、全链路上传。

每组必须同时记录系统资源和业务 SLO，至少包括 CPU、RSS、磁盘读写、网络流量、控制
P95/P99、视频 FPS、首帧耗时和黑屏次数。开发机结果只能验证工具，不得替代实车结论。
观测组件失败不得触发视频重载、WebRTC 重连、控制降级或安全动作。

## 13. 相关仓库基线

- [运维自动化工具链](skills/zota/references/ops-automation-toolchain.md)
- [SCM 到 War Room 开源蓝图](skills/zota/references/scm-to-war-room-open-source-blueprint.md)
- [数据闭环可观测性指标](skills/zota/references/shuangbai-project-data-ota-functional-performance-indicators.md)
- [DeepSeek Harness 官方主页](https://www.deepseek.com/harness/)
- [DeepSeek Harness 官方仓库](https://github.com/deepseek-ai/deepseek-harness)
- [DeepSeek Harness 架构文档](https://deepseek-harness.github.io/deepseek-harness/reference/)
- [DeepSeek Harness Session Telemetry](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session-telemetry.md)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry C++](https://opentelemetry.io/docs/languages/cpp/)
- [OpenTelemetry C++ 官方仓库](https://github.com/open-telemetry/opentelemetry-cpp)
- [Linux BTF](https://docs.kernel.org/bpf/btf.html)
- [Linux libbpf](https://docs.kernel.org/bpf/libbpf.html)
- [GStreamer Tracing Design](https://gstreamer.freedesktop.org/documentation/additional/design/tracing.html)
- [GStreamer Pad](https://gstreamer.freedesktop.org/documentation/gstreamer/gstpad.html)
- [GStreamer RTSP Server](https://gstreamer.freedesktop.org/documentation/gst-rtsp-server/)
- [DeepFlow 官方文档](https://deepflow.io/docs/)
- [小鹏公开专利 CN113904959B：一种时延分析方法、装置、车辆、存储介质](https://patents.google.com/patent/CN113904959B/zh)
- [公开专利 CN119232920B：一种远控驾驶系统的全链路图像传输延时测试方法和系统](https://patents.google.com/patent/CN119232920B/zh)
- [DeepFlow 用户文章：DeepFlow 在小米落地现状以及挑战](https://deepflow.io/docs/zh/about/users/)
- [理想汽车车端数据架构联合案例：从黑匣子到全量可观测](https://greptime.cn/blogs/2026-03-04-lixiang-vehicle-data-architecture)
