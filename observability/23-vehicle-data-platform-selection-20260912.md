# 量产车辆数据平台选型与实施方案

核查日期：`2026-09-12`。
状态：`design/recorded`。本文是方案与决策记录，不代表完成部署、实车测试或安全认证。

本文汇总此前的 TXT、SQLite、乘用车行业、5W、eBPF/collectd/OTel 讨论，
补充 DuckDB、GreptimeDB、MCAP/Parquet 以及端云职责划分。
公开事实引用文末 `[Sxx]`；没有厂商证据的内容明确标为工程建议。
代码级事实另存本地保密附录，不复制到可提交文档中。

## 1. 推荐结论

**不是不用 GreptimeDB 或 DuckDB，而是不让所有组件都成为每辆车的常驻必选项。**

建议采用以下职责分工：

| 层次 | 首期选择 | 后续选择条件 |
|---|---|---|
| 安全与控制 | 保留既有健康检查、看门狗和安全策略 | 独立安全变更评审；不依赖观测平台 |
| 原始证据 | 既有 ROS/MCAP 事件录制、媒体文件 | 改善封口、类型描述、限额、耐久性和回放 |
| 本地事务状态 | 既有可靠队列；复杂状态再迁 SQLite | 要求原子更新、租约、重试、查询和恢复时引入 |
| 结构化信号 | 有界批次、封口文件；优先在云端派生 Parquet | 有车内在线查询需求时评估车端列式库 |
| 离线 SQL | DuckDB 读取已封口、已解码的 Parquet | 工作站/云端任务优先；车端只按需限资源运行 |
| 在线时序 | 先复用已有指标后端 | GreptimeDB 云端作为 SQL 时序/日志查询候选 |
| 车端在线时序 | 首期不强制部署新数据库 | GreptimeDB Edge 通过需求、授权、资源和恢复 POC 后启用 |
| 观测契约和传输 | OTel/OTLP、字段白名单、有界异步导出 | Collector 构建和 receiver 依实际需要裁剪 |
| 内核诊断 | 能力探测后按问题部署 eBPF | 常态聚合，异常窗口短时增量采集 |
| 基础主机采集 | 每类指标只选一个采集源 | collectd 仅在已有部署/插件需求时采用 |

**首期默认：MCAP + 可靠事件状态 + OTel + 对象存储；DuckDB 做离线分析。**
GreptimeDB 云端可以并行做小规模数据查询 POC；Edge 上车是单独决策。
本方案不要求自研高频存储引擎，也不要求把所有消息转换成 Arrow 后才能上线。

## 2. 对前面讨论的修正

| 原先容易产生的理解 | 本次校正 |
|---|---|
| 四家乘用车都用 SQLite 或相同数据库 | 未找到公开证据；不能从架构相似推导产品相同 |
| SQLite 不能记录高频 ROS 数据 | 过于绝对；ROS2 有 SQLite 存储插件，应按批量、索引、负载和耐久参数测试 [S08] |
| TXT 一定比二进制大很多，必须全部替换 | 文本也可压缩；关键是类型、关联、写入开销和查询，不按扩展名判断 |
| TXT -> JSONL -> Protobuf -> Arrow 是升级路径 | 不是；它们分别涉及表示、Schema、消息编码和列式交换，按职责选择 |
| 有 WAL 就等于绝不丢数据 | 错误；提交确认、同步策略、介质、队列边界和断电时点共同决定 RPO [S07][S11] |
| 复制 SQLite 的三个文件就能在线备份 | 不应这样操作；使用一致性备份接口，或停止写入后按官方流程备份 [S07] |
| 所有 SQLite 数据库都应按行程滚动 | 持久任务账本不随行程清空；仅可独立滚动遥测分片 |
| eBPF 自动生成完整 ROS/DDS/CAN Trace | 不成立；共享内存、消息语义和 GPU 内部执行仍需要业务/框架证据 |
| 将工具放进容器一定不可用 | 不成立；受内核能力、挂载、权限、命名空间影响；宿主机部署是本方案的运维选择 |
| 加了时序库就可以替代黑匣子或 L4 安全证据 | 不成立；数据库不是安全等级、完整回放或法规记录器的证明 |

SQLite 官方 WAL 文档还记录了 WAL-reset 缺陷及修复版本；
选型需检查 `3.51.3` 或厂商等效回补是否覆盖目标版本，而非照抄系统自带版本。
`busy_timeout` 只是连接级等待策略，不是实时线程可以等待数据库的理由。[S07]

## 3. 小米、理想、小鹏、华为公开资料

### 3.1 证据口径

- `A`：官方产品说明、隐私政策或厂商/供应商联合实践案例。
- `B`：专利，说明公开技术方案，不证明量产实现。
- `C`：本文提出的工程建议，不属于厂商事实。

隐私政策说明数据处理目的/条件，不能当作内部数据库拓扑。
专利说明一种可行设计，不能证明采用比例、车型范围或落地版本。
乘用车辅助驾驶、研发测试和限定 ODD 的 L4 服务也不能混为一谈。

### 3.2 四家对照

| 厂商 | 可确认的公开方向 | 不能确认 | 可借鉴内容 |
|---|---|---|---|
| 理想 | Greptime 与理想数据团队联合案例描述车端解码、结构化时序、列式压缩及文件上传，`A` [S01] | 所有车型统一部署、SQLite 是否同时存在、完整智驾传感器存储栈 | 结构化前移、批量顺序写、端云兼容、实车资源优化 |
| 小鹏 | 官方材料描述量产车与 Robotaxi 共同训练、辅助驾驶与自动驾驶数据闭环，`A` [S14][S15] | SQLite/TSDB 名称、所有数据的文件格式、全车型统一策略 | 定向触发、场景筛选、采集到训练/仿真闭环 |
| 小米 | 公开专利描述事件前后车辆运行数据保存，`B` [S16] | 该专利是否量产部署、车端数据库、与集团云端观测产品的对应关系 | 有限缓存、事件前后窗口、按事件组织证据 |
| 华为 | 官方 Octopus 材料描述数据到训练/仿真闭环；专利描述黑匣子数据分级存储，`A+B` [S17][S18] | 不同合作车企/车型的具体数据库、车云实现是否一致 | 元数据治理、分级存储、训练仿真闭环 |

不能用“小米集团在数据中心部署某观测产品”证明“小米汽车车端也部署该产品”。
同样，华为云提供数据闭环产品，不代表所有 ADS 合作车型采用同样的存储部署。
上述资料不足以证明任一品牌全系乘用车已经实现 L4，更不能据此推导本项目安全等级。

### 3.3 理想案例的正确使用方法

用户提供的原文是《从黑匣子到全量可观测：理想汽车车载数据架构演进之路》
（2026-03-04）。它描述车辆信号采集与运营分析方向，不能直接等同于完整 L4 安全架构。
可借鉴的是结构化、批处理、压缩、端云协同；文章中的资源和收益数字不是跨硬件保证。
“全量车辆信号”也不能自动解释为所有视频、点云长期全量回传。[S01]

## 4. 先分清工具类别

| 类别 | 工具/格式 | 它解决什么 | 不解决什么 |
|---|---|---|---|
| 主机统计 | collectd、hostmetrics、已有监控器 | CPU、内存、网络、磁盘等统计 | 业务因果、原始传感器回放 |
| 内核观测 | eBPF/libbpf、适配的 DeepFlow Agent | 指定探针可见的调度/网络/进程事实 | 自动理解所有协议或恢复完整业务语义 |
| 语义和传输 | OTel API/SDK、OTLP、Collector | Metrics/Logs/Traces 采集与传递 | 在线数据库、原始记录器 |
| 本地事务库 | SQLite | 事件索引、状态、租约、幂等任务 | 默认无成本的全量分析服务 |
| 嵌入式分析 | DuckDB | SQL 扫描、Join、聚合、Parquet 查询 | 直接接管每个实时 ROS callback |
| 在线时序库 | GreptimeDB | 时序写入、SQL/PromQL、观测数据查询 | 原始媒体容器或完整安全证据链 |
| 车端时序产品 | GreptimeDB Edge | 端侧结构化时序、端云协同候选 | 等同于任意社区版安装包或免验收部署 |
| 消息记录格式 | MCAP | 多 Topic、类型/通道、时间和消息记录 | 自动转成可按业务字段 SQL 查询的表 |
| 列式格式 | Arrow、Parquet | 列式交换和分析归档 | Trace Context、上传确认和安全策略 |
| 云端大对象 | 对象存储 | 不可变文件、生命周期、数据集归档 | 毫秒控制或跨文件事务队列 |
| 云端业务账本 | 既有服务数据库/PostgreSQL 等 | 车辆、任务、Schema、权限、事件目录 | 自动替代数值时序分析 |
| 云端 OLAP | ClickHouse 等 | 持续多用户分析候选 | 每车必须安装的组件 |

工具能力依据见 [S02]-[S13]；表中的放置位置和取舍属于本文的设计建议。

## 5. SQLite、DuckDB、GreptimeDB 如何选

### 5.1 SQLite：管理事情进行到哪一步

建议在任务状态复杂时引入一个稳定的本地 `state.db`：

```text
event_index
segments
upload_jobs
upload_attempts
schema_registry_cache
configuration_revisions
```

典型查询是“哪些文件已封口但未上传”“这个事件最后一次失败原因是什么”。
这些属于短事务和状态更新，不应交给 DuckDB 分析任务抢写。

建议单一写入服务、批量短事务、有限索引和明确同步策略；读连接只做有界查询。
SQLite WAL 允许读者和写者并行，但单个数据库同一时刻只有一个写事务。[S07]

数据库与外部 MCAP 文件之间不存在自动跨文件原子事务，必须建立恢复协议。
迁移前先验证现有文件队列：若已足够可靠，不应只为“用数据库”立即重写。
比较 SQLite 录制性能时，应同时测试 ROS2 插件的性能配置和 resilient 配置，
不能把关闭耐久性的吞吐与生产耐久配置横向比较。[S08]

### 5.2 DuckDB：回答某个时间窗口内发生了什么

**建议使用，优先在工作站/云端离线任务，不默认常驻车端。**

适合：

- 从 MCAP 解码后的结构化 Parquet 查 Topic 延迟、事件前后指标和版本差异。
- 对一个行程、多段封口文件或脱敏样本进行 Join 和聚合。
- POC 阶段直接分析对象文件，验证是否真的需要常驻时序服务。

DuckDB 可直接查询 Parquet，并利用列裁剪/过滤下推减少读取。
本文采用其默认本地嵌入式工作方式：持久数据库由单进程管理；
不让多个车端模块同时写同一个 `.duckdb` 文件。[S04][S05]

如需车内离线 SQL，放在独立、限资源的 worker：

1. 只读取已封口且获准访问的数据。
2. 驻车、维护窗口或资源门禁允许时运行。
3. 限制线程、内存、临时盘、查询范围和执行时间。
4. 禁止写录制目录、控制配置、实时 SQLite 账本。
5. 不开放任意 SQL 给远程用户；SQL 也能触达文件/网络和扩展能力。

`memory_limit` 不是整个进程 RSS 的硬上限；应同时使用进程/cgroup 级限制，
并限定 spill 临时目录。扩展预装锁版本，不允许车辆运行中任意下载加载。[S06]

**DuckDB 不会自动把任意 ROS CDR/MCAP 解码成业务列。**
需要可信的消息类型定义、Schema 版本和 MCAP -> 结构化字段 -> Parquet 的派生步骤。
Arrow 批次可以作为该派生步骤的中间表示，但不是强制前置条件。[S05][S09]

### 5.3 GreptimeDB 云端：回答持续在线的车队时序问题

**值得评估，尤其当需求是长期接收、按时间查询、多用户在线查看。**

适合的需求包括：

- 按车型/软件版本比较指标趋势及异常比例。
- 关联设备指标、结构化事件、日志和发布记录。
- 在已有 PromQL 使用习惯之外增加 SQL 查询。

当前官方文档已说明 OTLP/HTTP Metrics、Logs、Traces 接入。
仍须按锁定版本验证 Trace 展示、查询、采样和异常响应，不能只凭接收成功判定完成。[S03]

迁移门禁还包括指标属性是否保留、delta/cumulative 语义、直方图支持和 Trace
部分成功响应。核查时的文档说明默认会筛除部分属性、delta 值不会自动累计、
ExponentialHistogram 尚不支持；必须与现有仪表盘和告警逐项对照。[S03]

两种合理选择：

- 已有可用指标/日志/Trace 后端：先接通 OTel，GreptimeDB 只接受控样本做对照。
- 没有合适的在线时序后端：可将 GreptimeDB 作为云端 POC 的首个候选。

升级到生产前必须完成鉴权、租户隔离、容量、TTL、备份、灾难恢复、升级回滚、
告警查询和数据导出验证。不要为了“端云同构”一次替换所有现有后端。
如果已有 DeepFlow 自管存储，业务数据应走受支持的接口或独立库，
不能直接写入其内部管理表。

### 5.4 GreptimeDB Edge：回答车内持续写入时还能不能在线查询

**它是有价值的量产候选，不是首期必装，也不是与 DuckDB 二选一。**

官方车云方案将 Edge、云端数据库、Edge Manager 分开介绍，并给出了商业授权信息。
因此需要单独确认端侧产品的获取、授权、支持、部署方式和导出能力，
不能把社区 GreptimeDB 的资源、许可或组件清单直接套到 Edge。[S02]

只有下列需求成立，才建议推进 Edge：

1. 行驶中确实需要不断写入并查询大量结构化信号。
2. 本地跨信号时间窗口查询是实际业务，不只是研发偶尔导出。
3. 文件 + SQLite 索引 + 按需 DuckDB 已无法满足查询时效或维护成本。
4. 目标硬件具备可证明的 CPU、RSS、闪存、功耗和启动时间余量。
5. 端侧授权、离线使用、云端依赖、升级和退出迁移成本可接受。

部署后建议由 Edge 接管一类结构化遥测的写入和保留策略，
避免同一信号永久同时写 SQLite 遥测表、Parquet、Edge、DuckDB 四份。
SQLite 可继续管理上传/任务事务；MCAP 继续保存原始事件证据；
DuckDB 继续分析导出的标准文件。

车云同构是接口和运维上的收益，不等于“所有车端内部文件都能直接当云端表读”。
必须实测 Schema、时间精度、压缩、兼容性和受支持的导入/导出路径。

### 5.5 其他组件是否需要

- **collectd**：已有稳定部署/专用插件时复用，否则不增加第二套主机采集 [S12]。
- **ClickHouse**：云端多用户 OLAP 的候选，不为单车临时 SQL 搬上车。
- **Prometheus/VM、Loki、Tempo**：若已具备这些后端，优先验证复用，不要求全部重建。
- **RocksDB/LMDB**：有明确 SDK 嵌入或 KV 需求才评估，不替代完整任务队列协议。
- **Kafka、Iceberg、分布式查询**：出现独立多消费者、重放隔离或大规模表治理需求再引入。

后三项是范围控制建议，并非宣称这些产品不能承载车辆数据。

## 6. 推荐端云架构

### 6.1 首期方案

```text
安全面
  既有健康检查 / 看门狗 / MRC / 控制 -> 执行器
  [不等待以下任何观测、数据库、网络请求]

观测面
  业务阶段事件、低基数指标、已有健康摘要
     -> 有界异步队列
     -> OTel Adapter / 精简 Collector
     -> 有界持久发送队列
     -> 云端鉴权网关
     -> 已有观测后端，或 GreptimeDB 云端 POC

证据面
  既有 ROS/传感器记录
     -> RingBuffer / 分段 MCAP
     -> 封口、校验、持久化
     -> 事件目录 + 任务状态 [按需要迁 SQLite]
     -> 既有分片上传服务 -> 对象存储

分析面
  已封口 MCAP + 类型定义 -> 受控解码 -> Parquet
     -> DuckDB [工作站/云端，车端按需]
     -> 报表、回放索引、场景挖掘
```

eBPF 在能力通过后，以独立受限 Agent 提供系统事实。
它可经适配输出到 OTel，也可沿 DeepFlow 官方采集通道进入后端；
不能假定所有 DeepFlow 数据本身就是原生 OTLP。

### 6.2 Edge 升级方案

```text
结构化遥测 -> 有界批次 -> GreptimeDB Edge
                            -> 本地只读诊断
                            -> 支持的批量导出/同步 -> 云端

SQLite: 事务状态                 [不重复保存全部遥测]
MCAP: 原始窗口                   [不被 Edge 替换]
DuckDB: 封口文件分析              [不读活跃数据库目录]
OTel: 语义、上下文、异步传递       [不被数据库替换]
```

在已有功能之上按职责替换，不长期堆叠多个等价常驻采集器和存储器。

## 7. 时间、关联键与 Schema

建议通用资源属性：

```text
vehicle_key, hardware_class, software_build, schema_version
boot_id, process_start_id, service_name
```

事件/证据关联字段：

```text
event_id, trip_id, trace_id, span_id, parent_span_id
source_seq, sensor_frame_id, correlation_method
source_time_ns, receive_time_ns, monotonic_ns, clock_domain
clock_sync_state, clock_uncertainty_ns
event_type, result, reason_code, artifact_id
```

约束：

- 同一主机/时钟域用单调时钟计算耗时；跨设备墙钟差必须带同步误差解释。
- ROS 仿真时间、PTP/UTC 和内核时间不能直接混算；记录时间源和有效性。
- `trace_id/event_id/trip_id` 放事件、Trace、索引，不作为常规指标 label。
- PID 需要主机/容器命名空间和进程启动标识，否则重启后可能关联错进程。
- 不给一个跨小时、跨断网的录制/上传流程创建无限长 Span；用短 Span 加事件关联。
- 没有传播 Trace Context 的 eBPF 事实只能做时间/PID/socket 关联，不能伪造 parent。
- 原始记录、解码结果和派生统计保留血缘：输入哈希、类型定义、解码器和转换版本。

### 7.1 不强制一种表结构

SQLite 事务表按事件、文件、上传任务建模；高频信号可以按同步组建宽表，
或按类型分开的窄表。选择取决于信号更新频率、稀疏度和查询条件。
避免把所有值无类型地存进一个字符串 `key/value` 表。
不要为了省空间抹掉单位、量纲、有效位和 Schema 版本。

## 8. 可靠性比数据库品牌更重要

### 8.1 文件与任务状态协议

建议状态机：

```text
CAPTURING -> SEALED -> VERIFIED -> LOCAL_DURABLE
                                -> UPLOAD_PENDING -> UPLOADING
                                -> REMOTE_VERIFIED -> RETAINED -> EXPIRED
失败分支: RETRY_WAIT / QUARANTINED / INCOMPLETE
```

建议顺序：

1. 写临时文件，关闭格式 writer，完成必要 footer/index 和校验。
2. 按数据等级同步文件与目录，并在同一文件系统原子发布。
3. 在状态账本登记可上传对象；明确 SQLite 提交与文件落盘的先后关系。
4. 启动对账发现“有文件无任务”“有任务无文件”“封口未完成”。
5. 用稳定 artifact/event ID 和内容校验实现幂等。
6. 云端确认对象及业务清单完整后才允许本地淘汰。

`rename()` 的命名原子性不等于掉电持久性。
对象存储 ETag 不应统一假定为文件内容哈希；分片对象使用明确的校验字段。
不得把“Collector 收到数据”当作“原始事件文件已经云端归档”。

### 8.2 分开三种缓冲

| 缓冲 | 用途 | 耐久边界 |
|---|---|---|
| 进程/共享内存 RingBuffer | 留存触发前窗口 | 掉电或重启可失，不是持久证据库 |
| Collector 持久发送队列 | 观测批次重试 | 容量、重试窗口和实际写入成功决定可恢复范围 |
| 文件上传账本 + 已封口文件 | 大对象与事件上传 | 文件和账本都必须处于持久介质并可启动对账 |

OTel 官方文档支持用 `file_storage` 等构建持久发送队列，但它不是通用 exactly-once
消息系统。只保证选定实现和故障模型下已经成功入队的数据；生产者队列溢出、
持久盘故障和超出重试窗口仍需单独处理。[S11]

### 8.3 优先级与保留

建议分为：安全事件证据、关键业务事件、健康趋势、临时调试四级。
每级设独立字节配额、保留时间、上传优先级和淘汰规则。
关键事件预留空间，空间不足必须记录显式失败，不能宣称有限磁盘“永不丢失”。
观测故障不自动触发 MRC；若记录能力属于安全需求，应由既有安全机制按批准规则处理。

## 9. OTel、eBPF、collectd 的落地顺序

### P0：盘点和修正基线

确认真实车型入口、镜像、BSP/内核、时钟、介质、断网时长和上传带宽。
标注已有代码、实际部署、实车验证三个状态。
修复已有采集的阻塞、无界缓存、无效数值、过度日志和保密字段问题。
不为了云端上报调整现有安全心跳频率。

### P1：一条业务事件闭环

选择一个事件，例如录制触发到云端校验完成：

- 统一 event/artifact ID 和版本。
- 打通本地事件索引、封口、上传状态和云端查询。
- 保留 MCAP 原始证据，工作站离线解码生成 Parquet。
- 用 DuckDB 检查缺失、重复、时间分布和阶段失败原因。

此阶段无需 GreptimeDB Edge；SQLite 也以解决实际状态一致性问题为前提。

### P2：OTel 与基础指标

部署一个与业务生命周期隔离的观测 Agent；优先镜像已有健康摘要。
基础主机指标只选已有直接采集器、OTel hostmetrics 或 collectd 中一个主源。
试验默认可用 1 Hz 业务摘要、5-10 秒导出批次；这些是 POC 起点，不是安全指标。
检查 Collector 组件发行包、架构支持、权限、丢弃计数和持久队列。[S10][S11][S12]

### P3：eBPF 定点增强

先核验内核 BPF syscall、BTF/CO-RE、可用 tracepoint、权限、命名空间和版本。
已有可用 Agent 优先，不先自研一整套探针平台。[S13]

先选连接/重传/进程退出；在特定延迟问题上再加入调度和 IO 观测。
高频 tracepoint 即使在内核聚合也可能有成本，必须 A/B 测量。
UDP 没有通用的 TCP 式重传和 RTT；ROS 共享内存不经过常规网络包路径，
GPU 执行需对应平台指标/工具。这些都不能由 eBPF 一项包办。

### P4：端云数据库对照 POC

使用同一份合成或获准脱敏数据，同一故障模型，对比：

| 组 | 内容 | 回答的问题 |
|---|---|---|
| A | 现有 MCAP + 文件任务队列 | 基线成本与缺口 |
| B | MCAP + SQLite 事务状态 + Parquet | 状态/归档分层是否足够 |
| C | B + 独立 DuckDB 查询 worker | 按需 SQL 的资源与时效 |
| D | MCAP + Edge 遥测 + 同等事务状态 | 持续写查时 Edge 的实际收益 |
| E | 受控遥测进入 GreptimeDB 云端 | 云端 SQL 查询/维护成本是否优于现有后端 |

所有组使用等价的耐久、保留、压缩、采样和查询条件，不拿“关闭 WAL”结果比较。
短期镜像写入必须有退出日期，避免把对照环境永久变成双份生产存储。

### P5：逐车发布

回放/台架 -> 单台试验设备 -> 有授权的测试车 -> 小车队 -> 更大范围。
每阶段独立验收、独立关闭开关；不要把 Agent 启动成功当成量产完成。
只有需求和 POC 都通过后，才把 Edge 从候选变成车型选装/默认组件。

## 10. 容量与验收

### 10.1 先算采集量

```text
R_capture = sum(topic_rate_i * measured_serialized_bytes_i)
M_window ~= R_capture * retained_seconds + metadata + codec_working_set
D_offline >= measured_persisted_rate * approved_offline_duration
```

还需要同时计入原始 RingBuffer、封口副本、压缩、加密、重试文件和数据库临时盘。
不要用 MCAP 文件压缩率代替运行时内存占用，也不要混淆行/秒、消息/秒和值/秒。
HTTP、MQTT 或其他传输不是成败标准；大对象协议必须具备所需的续传、限速和校验。

### 10.2 验收矩阵

| 维度 | 必须验证 |
|---|---|
| 实时影响 | 开关 Agent/查询/压缩时控制与感知 deadline、P99/P99.9、掉帧的差异 |
| 资源 | 每组件 CPU 核秒、RSS/峰值、共享内存、IO、flash 写入量、温度、功耗 |
| 数据质量 | 时间有效性、序号断口、重复、Schema、记录和源消息计数差 |
| 故障恢复 | SIGKILL、重启、获准台架掉电、文件损坏、空间满、只读盘、后端不可用 |
| 网络 | 断连、恢复、重试风暴、弱网、分片损坏、限速与控制通道隔离 |
| 查询 | 事件窗口、历史行程、写查并发、长查询取消、DuckDB spill |
| 安全边界 | 关闭所有观测组件后现有安全与业务行为不变 |
| 运维 | Schema 升降级、旧文件读回、备份恢复、授权变化与退出迁移 |
| 业务效果 | 能否用同一个 event_id 定位到故障阶段和原始证据 |

资源门禁必须由目标硬件和实时预算定值。旧文档中的 CPU 百分比或控制 P99
目标只能作为初始参考，不作为已测保证；CPU 必须明确是整机百分比还是单核口径。
尚未确定的数据：每类设备空闲资源、标量写入量、需要离线保留多久、车内在线查询 QPS、
云端并发和每车成本上限。缺少它们时不能宣布某数据库已经最优。

## 11. 5W 与安全保密

用户提供的 DeepFlow 5W 方法强调从 Who/When/Which/Where/What 逐步定位问题。[S19]
车辆版建议：

| 5W | 查询入口 | 证据落点 |
|---|---|---|
| Who | 匿名车辆键、模块、软件版本 | 资源属性和配置目录 |
| When | 行程、事件窗口、时间质量 | 事件索引、时序查询 |
| Which | 场景、控制请求、帧或录制任务 | 业务事件与 Trace |
| Where | 应用阶段、调度、网络、存储 | OTel + eBPF/平台指标 |
| What | 故障原因、错误码、前后状态 | MCAP/媒体、解码数据和版本血缘 |

数据可关联不等于因果已经证明；时间近邻不能自动当成同一 Trace 或根因。

保密要求：

- 公开检索不包含内部地址、车辆标识、代码段或配置。
- 车端字段白名单默认不包含原始控制 payload、凭证、完整命令行、地理轨迹和图像。
- 元数据、原始证据和派生数据执行各自的授权、加密、审计和保留规则。
- 网络出口白名单和有效证书校验；采用适合环境的双向认证或设备身份机制。
- 远程诊断只执行获准查询模板，不开放任意 SQL、Shell、BPF 程序上传或扩展安装。
- 本地保密附录被 `.gitignore` 排除；这只降低误提交风险，不代替文件权限和数据治理。
- 本次不执行提交、推送、云端导入或 AURA 运行变更。

## 12. 本次决策记录

| 决策 | 状态 |
|---|---|
| 数据分层，不再以 TXT/数据库扩展名划分架构 | 建议采纳 |
| 保留已有 ROS/MCAP 原始证据链 | 建议采纳 |
| SQLite 用于需要事务保证的状态账本 | 条件采用 |
| DuckDB 用于离线/按需分析，首期不常驻实时进程 | 建议采纳 |
| GreptimeDB 云端以受控样本做在线查询 POC | 候选，非部署结论 |
| GreptimeDB Edge 按车型需求与资源验收 | 候选，非默认依赖 |
| OTel 统一语义与异步出口，eBPF 按问题增强 | 建议分阶段采用 |
| 不额外堆叠 collectd/hostmetrics/已有相同指标采集 | 建议采纳 |
| 数据库、Collector、AI 诊断不进入安全控制闭环 | 硬边界 |

与已有文档的关系：
[总体策略](01-strategy-and-industry.md)、
[车端监控](02-vehicle-node-monitoring.md)、
[Edge/Arrow 候选设计](06-greptime-edge-and-arrow.md)
继续保留历史背景；本专题补充数据库选型门槛和首期默认路径，
不将历史 `approved` 候选改写成 `implemented/verified`。

本地保密附录：`observability/private/aura-data-platform-assessment-20260912.md`。
该文件不纳入版本控制；对外共享本专题时，不附带内部代码证据。

## 13. 公开来源索引

访问核查日期均为 `2026-09-12`；`stable/current` 文档会变化，实施时锁定版本复核。
只引用官方文档、专利或厂商/供应商原始材料，不以二手文章证明量产部署。

- `[S01]` Greptime，理想汽车数据团队联合案例，2026-03-04。
  `https://greptime.cn/blogs/2026-03-04-lixiang-vehicle-data-architecture`
- `[S02]` Greptime 车云一体方案，Edge/云端/管理与授权说明。
  `https://greptime.cn/carcloud`
- `[S03]` GreptimeDB 官方 OTLP Metrics/Logs/Traces 文档。
  `https://docs.greptime.com/user-guide/ingest-data/for-observability/opentelemetry/`
- `[S04]` DuckDB，Concurrency；本文使用默认本地嵌入式模式。
  `https://duckdb.org/docs/stable/connect/concurrency`
- `[S05]` DuckDB，Reading and Writing Parquet Files。
  `https://duckdb.org/docs/stable/data/parquet/overview`
- `[S06]` DuckDB，Limits / Securing DuckDB。
  `https://duckdb.org/docs/stable/operations_manual/limits`
  `https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview`
- `[S07]` SQLite，Write-Ahead Logging / Online Backup API。
  `https://www.sqlite.org/wal.html`
  `https://www.sqlite.org/backup.html`
- `[S08]` ROS2 Jazzy，rosbag2_storage_sqlite3 README 与 resilient 设置。
  `https://github.com/ros2/rosbag2/blob/jazzy/rosbag2_storage_sqlite3/README.md`
- `[S09]` MCAP，文件格式与 ROS2 指南。
  `https://mcap.dev/spec`
  `https://mcap.dev/guides/getting-started/ros-2`
- `[S10]` OpenTelemetry Collector Host Metrics Receiver，官方源码。
  `https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver`
- `[S11]` OpenTelemetry Collector，Resiliency。
  `https://opentelemetry.io/docs/collector/resiliency/`
- `[S12]` collectd，Features。
  `https://collectd.org/features.html`
- `[S13]` Linux Kernel，libbpf Overview / BPF Ring Buffer。
  `https://docs.kernel.org/bpf/libbpf/libbpf_overview.html`
  `https://docs.kernel.org/bpf/ringbuf.html`
- `[S14]` 小鹏汽车，G9 Robotaxi 公开数据闭环材料。
  `https://www.xiaopeng.com/news/company_news/4969.html`
- `[S15]` 小鹏汽车，G9 自动驾驶路测与零改装量产 Robotaxi 模式，2022-11-02。
  `https://www.xiaopeng.com/news/company_news/4553.html`
- `[S16]` 小米汽车相关专利 CN115454355B，Vehicle operation data storage。
  `https://patents.google.com/patent/CN115454355B/en`
- `[S17]` 华为云，HUAWEI Octopus 自动驾驶开发平台。
  `https://www.huaweicloud.com/news/2019/0418104530862.html`
- `[S18]` 华为相关专利 CN110570538B，智能驾驶汽车黑匣子数据管理。
  `https://patents.google.com/patent/CN110570538B/zh`
- `[S19]` DeepFlow，5W Method。
  `https://deepflow.io/docs/zh/guide/quick-start/5w-method/`
