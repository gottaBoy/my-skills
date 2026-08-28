# 06 GreptimeDB Edge 与 Apache Arrow 车云数据平面

更新时间：`2026-08-26`

## 结论

GreptimeDB Edge、Apache Arrow、Parquet、OpenTelemetry、eBPF/DeepFlow 和
DataBuff/WAL 可以组合成车云一体的数据平面，但它们的职责必须分开：

```text
车端业务事件 + monotonic ledger
  -> 本地有界队列
  -> GreptimeDB Edge / OTel 异步写入
  -> Arrow 批量内存与传输
  -> DataBuff/WAL 断网缓存和补传
  -> 云端 Collector/GreptimeDB
  -> Parquet 数据湖归档
  -> DeepFlow/DSH 只读关联和分析
```

本方案采用“两种格式、三类语义、四层数据”的原则：

1. **Arrow 是内存和批量交换格式**，适合实时处理、跨语言零拷贝和批量上传。
2. **Parquet 是持久化文件格式**，适合车端落盘或云端对象存储、历史归档和批量查询。
3. **Trace Context 是链路关联语义**，Arrow 和 Parquet 都不能替代
   `traceId/spanId/parentSpanId`。
4. **业务事件、系统事实、时序指标和原始诊断数据分层保存**，不能把所有视频帧、
   控制 payload 或高频内核事件直接写入车端数据库。

GreptimeDB Edge 在本项目中是**候选车端数据平面组件**，不是当前已部署事实。
首期必须在目标 AD1、Jetson 和 x86 设备上验证架构、版本、写入能力、内存、断网
补传和对实时业务的影响后，才能把状态从 `approved` 更新为 `implemented` 或
`verified`。

## 公开资料校核

Greptime 官方公开的车云一体方案包含 Edge、云端 GreptimeDB 和 Edge Manager
三个部分；Edge Manager 的定位是管理边缘设备、数据模型、质量监控和上传任务的
控制面。它可以作为本项目的配置和任务管理参考，但不能进入控制消息、视频重连
或安全动作路径。

官方公开案例还给出了高通 8295、Android 12、Edge v2.0 等特定环境下的写入、
CPU、内存和压缩测试结果。由于测试数据类型、表结构、WAL 开关、批量大小、压缩
配置和设备资源都会影响结果，本项目只把这些数字作为 POC 的压测输入，不把它们
写成当前 AD1、Jetson 或 x86 的承诺指标。

官方 GreptimeDB 文档说明其查询引擎使用 Apache Arrow 作为内存数据表示，并以
Parquet 作为主要持久化文件格式；这支持本专题的“Arrow 处理、Parquet 归档”
分工。向量类型应按实际目标版本验证，不能仅依据宣传材料固定 `v0.10.2`；
官方历史发布说明中已能确认 `v0.10.1` 出现向量类型能力。

## 组件定位

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>组件</th>
      <th>车云一体定位</th>
      <th>适合承载</th>
      <th>明确不承担</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>业务事件与 OTel</td>
      <td>生成业务语义和 Trace/Span 关联</td>
      <td>控制阶段、视频生命周期、状态上报、首帧、恢复和错误事件</td>
      <td>不能替代内核网络事实，也不能证明浏览器最终显示</td>
    </tr>
    <tr>
      <td>monotonic ledger</td>
      <td>记录同一进程或时钟域的可信阶段耗时</td>
      <td><code>receive</code>、<code>parse</code>、<code>handler</code>、<code>encode</code>、
        <code>RTP</code>、<code>first_frame</code> 等阶段</td>
      <td>不能用不同设备墙钟相减计算端到端延迟</td>
    </tr>
    <tr>
      <td>eBPF/DeepFlow</td>
      <td>补充节点和网络系统事实</td>
      <td>TCP/UDP、RTT、重传、socket queue、调度、CPU、RSS、进程和连接</td>
      <td>不能理解 <code>remotejoystick</code>、H.264 IDR、ROS 业务语义或渲染结果</td>
    </tr>
    <tr>
      <td>GreptimeDB Edge</td>
      <td>车端结构化时序、事件和诊断窗口的本地数据平面</td>
      <td>指标、事件索引、聚合窗口、异常前后数据和有限期本地查询</td>
      <td>不能成为控制同步依赖、编码热路径依赖或唯一可靠传输通道</td>
    </tr>
    <tr>
      <td>Apache Arrow</td>
      <td>内存列式布局和批量交换格式</td>
      <td>同进程 C Data Interface、跨进程 IPC/共享内存、批量上传前的列式批次</td>
      <td>不是 Trace 系统、消息协议、时钟同步机制或长期归档格式</td>
    </tr>
    <tr>
      <td>Parquet</td>
      <td>持久化列式文件和云端归档格式</td>
      <td>车端诊断文件、对象存储、按车辆/时间/事件类型分区的批量查询</td>
      <td>不适合逐消息同步控制，也不应成为视频实时发送路径</td>
    </tr>
    <tr>
      <td>DataBuff/WAL</td>
      <td>观测数据的异步缓存、批量、重试和断点续传</td>
      <td>断网期间的关键事件、指标批次、drop 计数和补传状态</td>
      <td>不是 Trace 生成器，不保证所有低优先级事件永久保存</td>
    </tr>
    <tr>
      <td>DSH</td>
      <td>只读查询、证据关联、根因分析和进度治理</td>
      <td>关联车端时序、Trace、DeepFlow、ZLMediaKit、浏览器事件和发布记录</td>
      <td>不进入控制、视频重连、数据库写入或安全动作路径</td>
    </tr>
    <tr>
      <td>GreptimeDB Edge Manager</td>
      <td>统一控制面，管理 Edge 配置、数据模型、质量和上传任务</td>
      <td>版本/配置下发、任务编排、设备健康和上传策略</td>
      <td>不直接下发车辆控制，不同步触发视频 reload，不作为实时链路依赖</td>
    </tr>
  </tbody>
</table>

## Arrow 与 Parquet 的边界

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>维度</th>
      <th>Apache Arrow</th>
      <th>Parquet</th>
      <th>本项目选择</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>格式属性</td>
      <td>列式内存格式</td>
      <td>列式持久化文件格式</td>
      <td>内存处理用 Arrow，落盘归档用 Parquet</td>
    </tr>
    <tr>
      <td>主要阶段</td>
      <td>采集后的批量聚合、分析和跨语言交换</td>
      <td>车端诊断文件、云端对象存储和历史查询</td>
      <td>不要为了统一格式而让实时链路直接读写 Parquet</td>
    </tr>
    <tr>
      <td>复制开销</td>
      <td>在满足布局和生命周期条件时可以低复制或零拷贝</td>
      <td>读取通常需要解压、解码和页级访问</td>
      <td>先验证 C Data Interface/IPC 的实际生命周期，不承诺所有跨进程场景零拷贝</td>
    </tr>
    <tr>
      <td>空间效率</td>
      <td>内存占用通常更高，适合短生命周期批次</td>
      <td>压缩和编码后更适合长期保存</td>
      <td>车端只保留有限 Arrow batch；归档优先转换为 Parquet</td>
    </tr>
    <tr>
      <td>Trace 关联</td>
      <td>通过列字段携带 Trace Context</td>
      <td>通过列字段和分区携带 Trace/车辆/时间范围</td>
      <td>统一字段语义，不能把格式本身当作 Trace 系统</td>
    </tr>
    <tr>
      <td>实时性</td>
      <td>适合微批和窗口分析</td>
      <td>适合批处理和历史分析</td>
      <td>控制和视频热路径只产生异步事件，不同步等待格式转换</td>
    </tr>
  </tbody>
</table>

公开案例中出现的 Arrow/Parquet 容量和性能数字只能作为压测假设，不能直接套用
到当前车型。车端最终选择必须以目标 CPU、内存、磁盘介质、压缩算法、写入频率和
网络条件的实测结果为准。

## 四层数据模型

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>数据层</th>
      <th>示例</th>
      <th>首选格式/存储</th>
      <th>保留策略</th>
      <th>优先级</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>业务事件</td>
      <td>控制接收、解析结果、handler、ROS publish、视频首帧、pipeline error</td>
      <td>结构化事件 + Arrow micro-batch；必要时 WAL</td>
      <td>关键成功/失败事件优先，按会话和时间窗保留</td>
      <td>高</td>
    </tr>
    <tr>
      <td>时序指标</td>
      <td>CPU、RSS、FPS、码率、RTT、jitter、重传、队列深度、首帧耗时</td>
      <td>GreptimeDB Edge；云端 GreptimeDB</td>
      <td>车端短期高分辨率，云端降采样长期保存</td>
      <td>中高</td>
    </tr>
    <tr>
      <td>系统事实</td>
      <td>eBPF socket、调度、进程、网络和 Agent 健康事件</td>
      <td>DeepFlow/OTel 批次；必要时本地 WAL</td>
      <td>按采样率、异常窗口和资源预算保存</td>
      <td>中</td>
    </tr>
    <tr>
      <td>诊断原始数据</td>
      <td>异常前后 CAN 窗口、编码器摘要、有限网络统计和校准片段</td>
      <td>压缩文件/Parquet；大对象进入对象存储</td>
      <td>只保留获准窗口，不保存原始视频帧或敏感控制 payload</td>
      <td>按需</td>
    </tr>
  </tbody>
</table>

以下数据默认禁止进入 GreptimeDB Edge 实时写入路径：

- 视频帧、完整 RTP payload、完整 SDP、ICE credential。
- 手柄原始控制 payload、密钥、令牌和个人身份信息。
- 逐 RTP 包生成的 Span。
- 未经采样的高频 eBPF 原始事件。

## 与三条链路的接入

### 指令链路

```text
ztd_cloud_driving
  -> InvocationContext + monotonic ledger
  -> 本地事件队列
  -> Arrow micro-batch
  -> GreptimeDB Edge / OTel
  -> DataBuff/WAL
  -> 云端 Trace/Metric/DSH
```

必选字段：

```text
remoteSessionId, messageId, functionId, traceId, spanId,
connectionId, processId, receiveMonotonicNs, durationNs,
result, errorCode, schemaVersion, samplingPriority
```

`GreptimeDB Edge` 只保存控制阶段的摘要和统计，不参与消息确认、ROS publish
返回判定或安全门禁。写入失败、Arrow 批次满和磁盘不可用都只能增加
`observability_drop_count`，不能阻塞 `_receive_message()` 或
`handle_remotejoystick()`。

### 视频链路

```text
ztd_rtsp/GStreamer hooks
  -> videoSessionId + VideoTraceBinding
  -> 编码/RTP 聚合指标
  -> Arrow micro-batch
  -> GreptimeDB Edge / OTel
  -> 云端 ZLMediaKit + DeepFlow + 浏览器事件
```

必选字段：

```text
remoteSessionId, videoSessionId, streamApp, streamName,
traceId, spanId, frameSequence, encoderOutputAgeMs,
firstRtpObserved, pipelineState, errorCode, samplingPriority
```

视频热路径只更新轻量计数器或无锁/低锁快照；批量转换和写入由低优先级消费者
完成。不能以 GreptimeDB 写入成功作为编码器、RTP 或 WebRTC 重连条件。

### 状态上报链路

状态 WebSocket 的车端/云端/浏览器事件可以进入同一数据平面，但时间字段必须保留
时钟域语义：

```text
eventbusReceivedAt
websocketQueuedAt
websocketSentAt
browserReceivedAt
browserAppliedAt
vehicleTimestamp
```

同一节点使用 monotonic duration；车端、云端和浏览器墙钟固定偏移只保存为
`clockOffsetBaseline/delta`。当时钟域未同步时，`crossDomainDurationMs` 和
`vehicleToBrowserMs` 必须为 `null`，不能写入伪造的负延迟。

## Edge 数据平面

### 推荐分层

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>层</th>
      <th>职责</th>
      <th>故障行为</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Producer</td>
      <td>业务进程、eBPF Agent、GStreamer 和状态模块产生事件/指标</td>
      <td>只做轻量封装，禁止同步网络和数据库 I/O</td>
    </tr>
    <tr>
      <td>Local buffer</td>
      <td>内存环形队列、优先级、drop counter 和微批聚合</td>
      <td>满时先丢低优先级数据，关键错误保留摘要</td>
    </tr>
    <tr>
      <td>Edge store</td>
      <td>GreptimeDB Edge 保存短期时序和事件索引</td>
      <td>服务停止不影响业务；恢复后按策略补写或丢弃</td>
    </tr>
    <tr>
      <td>Durable spool</td>
      <td>DataBuff/WAL 保存需跨断网保留的批次和上传状态</td>
      <td>达到磁盘上限后按优先级和 TTL 淘汰，记录原因</td>
    </tr>
    <tr>
      <td>Uploader</td>
      <td>批量压缩、HTTPS/OTLP/Arrow 传输、断点续传和退避</td>
      <td>网络不可达时本地积压；不得反压控制和视频生产者</td>
    </tr>
    <tr>
      <td>Cloud store</td>
      <td>云端 GreptimeDB、Trace 后端、DeepFlow 和 Parquet 数据湖</td>
      <td>云端不可用时保留车端 spool 和上传失败指标</td>
    </tr>
  </tbody>
</table>

### 批量与断点续传

批次建议至少携带：

```text
batchId, vehicleId, bootId, schemaVersion, min/maxObservedPerfMs,
min/maxWallTime, rowCount, compression, checksum, priority,
createdMonotonicNs, uploadAttempt, sourceComponent
```

上传规则：

1. 先写临时文件或 WAL，再原子提交为可上传批次。
2. 上传成功后记录服务端确认的 `batchId` 和 checksum。
3. 失败采用指数退避和最大重试次数，避免占满车端网络。
4. 断点续传按批次或文件范围进行，不能重复发送控制消息。
5. 云端重复收到批次时通过 `batchId`、行键和 checksum 幂等去重。
6. 本地磁盘接近上限时先淘汰低优先级正常样本，保留错误、恢复和资源异常摘要。

## Edge SQL、流式计算与 UDF 边界

车端 SQL、窗口聚合和可用的 UDF/函数扩展适合做诊断派生，不适合作为实时控制或
视频恢复的隐藏依赖。正式接入前必须按目标 Edge 版本确认函数、UDF、Flow 和权限
能力；首期优先采用普通 SQL 和连续聚合，避免依赖未验证的扩展接口。

当前官方 Flow 文档推荐聚合类任务使用 batching mode，旧式非聚合 streaming mode
已标记为 deprecated。因此本项目的车端规则优先设计为短窗口批处理和派生告警，
不把旧式 streaming 作为生产前提。

允许的例子：

- 计算过去 30 秒编码输出 age、RTP gap 和 CPU 的关联窗口。
- 检测控制链路 P99 超阈值并上传异常前后事件摘要。
- 对视频首帧、freeze、NACK 和重连次数生成每路会话统计。

禁止的例子：

- SQL/UDF 直接决定方向盘、制动、挡位或安全门禁。
- 查询失败时阻止控制消息或改变 ROS QoS。
- Edge 流式规则直接触发全量视频 reload。
- 在 UDF 中读取密钥、原始控制 payload 或完整视频内容。

建议采用“告警建议 -> 云端/DSH 证据复核 -> 人工审批 -> 受控动作”的路径。

## 资源预算与验证

公开 GreptimeDB Edge 案例中的写入吞吐、CPU、内存和压缩数字只能作为测试假设。
例如，特定 8295/Android/Edge 版本和测试配置下公开过 35 万点/秒、单核 CPU、
内存和峰值等数据，但这些结果不能替代本项目实车基线。本项目需要对每一种目标
车硬件建立基线，并比较以下四组：

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>组别</th>
      <th>开启项</th>
      <th>观测指标</th>
      <th>通过门禁</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A</td>
      <td>全部观测关闭</td>
      <td>控制 P99、视频 FPS/首帧、CPU、RSS、网络和磁盘</td>
      <td>形成硬件基准</td>
    </tr>
    <tr>
      <td>B</td>
      <td>本地事件和 monotonic ledger</td>
      <td>事件生产耗时、队列深度、drop、控制和视频指标</td>
      <td>生产线程无阻塞，控制 P99 增量目标不超过 0.2ms 且不超过 5%</td>
    </tr>
    <tr>
      <td>C</td>
      <td>B + Edge 指标写入</td>
      <td>写入 CPU/RSS、批次延迟、磁盘写入、实时业务指标</td>
      <td>Edge 不进入热路径，视频 FPS 和控制时延不超过批准预算</td>
    </tr>
    <tr>
      <td>D</td>
      <td>C + eBPF/OTel/Arrow/WAL/上传</td>
      <td>Agent、转换、压缩、上传、断网积压和恢复补传</td>
      <td>观测故障可降级，业务链路与 A 组相比无不可接受回退</td>
    </tr>
  </tbody>
</table>

至少验证：

- 单车单路 `cam_f_12`：ROS 帧、编码、RTP、ZLMediaKit、WebRTC、解码和渲染证据。
- 单条 `remotejoystick`：收包、解析、handler、ROS publish 和执行确认。
- 断网 5 分钟、网络恢复、进程重启、磁盘接近上限和 Edge 服务停止。
- Arrow batch 满、Parquet 转换失败、WAL 损坏、checksum 不一致和重复上传。
- 多路视频同时运行时，Edge/Agent 不引起 render stall、误重连或黑屏。
- 观测全关闭、仅本地事件、Edge 开启和全链路开启四组性能差异。

## 分阶段落地

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>阶段</th>
      <th>内容</th>
      <th>状态</th>
      <th>产物</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>V0 资料与能力</td>
      <td>确认 GreptimeDB Edge、Arrow、Parquet、OTel/OTAP 版本和目标车架构兼容性</td>
      <td><code>approved</code></td>
      <td>版本矩阵、许可证、安全和能力检查表</td>
    </tr>
    <tr>
      <td>V1 本地事件</td>
      <td>先使用现有本地事件出口和有界队列，定义 schema、优先级和 drop 计数</td>
      <td><code>implemented</code></td>
      <td>本地事件样本、字段字典、性能基线</td>
    </tr>
    <tr>
      <td>V2 Edge POC</td>
      <td>旁路写入节点和链路摘要，不接控制确认、视频重连和安全动作</td>
      <td><code>approved</code></td>
      <td>单车 Edge 镜像、写入/查询/资源报告</td>
    </tr>
    <tr>
      <td>V3 Arrow/IPC</td>
      <td>验证 C Data Interface、跨进程 IPC/共享内存和批量序列化生命周期</td>
      <td><code>approved</code></td>
      <td>跨语言复制次数、延迟、内存和故障测试</td>
    </tr>
    <tr>
      <td>V4 WAL/Parquet</td>
      <td>实现批次落盘、压缩、checksum、断点续传和云端归档转换</td>
      <td><code>approved</code></td>
      <td>断网恢复报告、对象存储文件和幂等记录</td>
    </tr>
    <tr>
      <td>V5 云端闭环</td>
      <td>接 Collector/Gateway/DeepFlow/GreptimeDB，按 Trace/车辆/时间窗关联</td>
      <td><code>approved</code></td>
      <td>单车单路三链路查询和 DSH 证据包</td>
    </tr>
    <tr>
      <td>V6 车队放量</td>
      <td>按车型、版本、区域和采样策略逐步启用，持续检查资源和数据成本</td>
      <td><code>approved</code></td>
      <td>放量门禁、回滚方案和月度成本报告</td>
    </tr>
  </tbody>
</table>

## 风险与决策

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>风险</th>
      <th>表现</th>
      <th>决策</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>版本能力不一致</td>
      <td>Edge、OTAP、Arrow Flight 或 Collector 版本不支持预期接口</td>
      <td>建立版本矩阵；不把未验证接口写成生产依赖，必要时先用 OTLP/压缩文件</td>
    </tr>
    <tr>
      <td>内存峰值</td>
      <td>Arrow batch、压缩和查询同时运行造成 RSS 增长</td>
      <td>限制 batch 行数、字节数和并发；独立低优先级进程或线程并设置硬上限</td>
    </tr>
    <tr>
      <td>写盘磨损</td>
      <td>高频指标和重复重试消耗车端存储</td>
      <td>微批、压缩、TTL、异常优先和磁盘水位淘汰</td>
    </tr>
    <tr>
      <td>观测反向影响业务</td>
      <td>数据库写入、Exporter 或 console 阻塞实时线程</td>
      <td>业务线程只入队/更新计数器；所有下游失败快速返回并计数</td>
    </tr>
    <tr>
      <td>数据安全</td>
      <td>Trace、控制字段和车辆数据泄露</td>
      <td>字段白名单、脱敏、加密传输、短期凭证、车端最小权限和审计</td>
    </tr>
  </tbody>
</table>

## DSH 进度要求

本专题首次建立时状态为 `approved`，表示设计已记录，可以进入 POC；不表示
GreptimeDB Edge、Arrow、Parquet、OTel/OTAP 或 DeepFlow 已在车端部署。

每个阶段必须更新：

```text
work_item
status
owner
updated_at
target_vehicle
version_matrix
changed_artifacts
verification_evidence
resource_delta
known_gaps
next_step
```

## 向量数据的后续边界

GreptimeDB 的向量类型可以为感知结果、特征摘要或异常片段检索提供后续能力，但
首期不把摄像头原始帧、激光雷达原始点云或高维 embedding 写入远控实时链路。
建议按以下顺序评估：

1. 先保存时间戳、来源、模型版本、维度和质量分数等元数据。
2. 再选取已脱敏、低频、固定维度的特征摘要做离线 POC。
3. 对查询 CPU、内存、磁盘和上传成本单独设预算。
4. 向量相似度结果只能作为诊断证据，不能直接触发控制或视频重连。

参考资料：

- [Greptime 端边云一体解决方案](https://greptime.cn/carcloud)
- [Greptime Edge 性能与压缩案例](https://greptime.cn/blogs/2024-11-22-edge)
- [GreptimeDB 查询引擎与 Arrow/Parquet](https://docs.greptime.com/contributor-guide/datanode/query-engine/)
- [GreptimeDB Flow 计算](https://docs.greptime.com/user-guide/flow-computation/overview/)
- [GreptimeDB 向量类型](https://docs.greptime.com/user-guide/vectors/vector-type/)
- [Apache Arrow Documentation](https://arrow.apache.org/docs/)
- [Apache Parquet Documentation](https://parquet.apache.org/docs/)
- [GreptimeDB Documentation](https://docs.greptime.com/)
- [理想汽车车端数据架构联合案例](https://greptime.cn/blogs/2026-03-04-lixiang-vehicle-data-architecture)
- [OpenTelemetry Protocol](https://opentelemetry.io/docs/specs/otlp/)

## 2026-08-26 POC 执行冻结点

### 已落盘

- `aura/tools/observability_poc/pocctl.py`
  - 目标车型和运行环境能力矩阵。
  - Arrow/IPC 原子发布、读回、Schema metadata、单调时钟和 checksum 验证。
  - WAL 离线积压、恢复上传、重复 batch 幂等和损坏隔离验证。
- `aura/tools/observability_poc/four_group_runner.py`
  - A：全关闭。
  - B：仅本地结构化事件。
  - C：本地事件与 Edge 写入。
  - D：本地事件、Edge 写入和全链路上传。
  - 采集 CPU、RSS、磁盘、网络和进程数，并接收控制 P95/P99、视频 FPS、
    首帧和黑屏次数等业务指标。
- `aura/tools/observability_poc/poc-config.example.json`
- `aura/tools/observability_poc/tests/test_pocctl.py`
- `aura/tools/observability_poc/README.md`

### 尚未执行

- 开发机单元测试和 smoke test。
- AD1、Jetson、x86 目标车型版本矩阵。
- 单车 GreptimeDB Edge 安装、连接和资源测试。
- 安装 `pyarrow` 后的 Arrow/IPC 生命周期测试。
- 真实 Gateway、对象存储或 Collector 上传适配器。
- 断网 5 分钟、进程重启、磁盘水位和 Edge 停止测试。
- A/B/C/D 实车性能对照。

### POC 强制边界

1. Edge、Arrow、WAL、Exporter 和 eBPF 均为旁路观测，不进入控制、编码、RTP、
   WebRTC 重连或安全动作的同步调用链。
2. 观测失败只能增加 error/drop 指标，不能触发视频 reload、PeerConnection 重建、
   控制降级或车辆动作。
3. `traceId/spanId/parentSpanId/correlationId` 继续承担链路关联；Arrow、Parquet、
   WAL 和数据库主键不能替代 Trace Context。
4. 开发机结果只证明工具可运行，不能证明目标车型兼容，也不能作为资源预算结论。
5. 公开案例的吞吐、CPU、RSS 和压缩率只作为压测输入，最终门槛由 AD1、Jetson、
   x86 的实测基线决定。

### 下次开机入口

先运行工具自检和开发机 matrix/WAL/Arrow，然后补真实 Edge 与上传适配器，最后进入目标车：

```bash
cd /Users/minyi/workspace/autodrive/aura
python3 -m unittest discover -s tools/observability_poc/tests -v
python3 tools/observability_poc/pocctl.py matrix \
  --vehicle-model development-host \
  --environment local-poc \
  --output poc-results/version-matrix-local.json
python3 tools/observability_poc/pocctl.py wal-recovery \
  --batches 8 \
  --output poc-results/wal-recovery-local.json
python3 tools/observability_poc/pocctl.py arrow-ipc \
  --rows 1000 \
  --output poc-results/arrow-ipc-local.json
```

当前专题状态保持 `approved`。
