# 02 车端节点性能监控

更新时间：`2026-08-27`

## 目标

在不影响车端控制、视频采集、编码和 RTP 发送的前提下，回答：

- `ztd_cloud_driving` 是卡在收包、解密、解析、handler、ROS publish 还是下游执行？
- `ztd_rtsp` 是没有 ROS 帧、队列丢帧、appsrc 失败、编码停滞、RTP 不发还是 RTSP 会话断开？
- 资源、调度或网络问题是否解释了业务耗时和黑屏？
- 观测系统自身是否丢数据、占用过高或反向影响业务？

## 四层采集

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>层次</th>
      <th>首期采集</th>
      <th>实现方式</th>
      <th>验收问题</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>业务进程</td><td>控制连接、parse、handler、ROS publish、RTSP client、ROS frame、appsrc、encoder、RTP、Gst error</td><td>C++ 结构化事件和 counters/histograms</td><td>业务阶段是否成功、耗时是否增长</td></tr>
    <tr><td>进程/线程</td><td>CPU、RSS、线程数、上下文切换、run queue、off-CPU、page fault、OOM、退出</td><td>eBPF/DeepFlow + 进程自监控</td><td>是否由调度、内存或重启导致</td></tr>
    <tr><td>网络/内核</td><td>connect、send/recv、RTT、RTO、重传、socket queue、UDP、网卡 drop</td><td>独立 eBPF Agent</td><td>应用慢还是网络慢</td></tr>
    <tr><td>观测自身</td><td>队列深度、drop、WAL、重试、Agent CPU/RSS、Collector 可达性</td><td>本地观测模块和 Agent 自监控</td><td>观测故障是否与业务隔离</td></tr>
  </tbody>
</table>

## 现有车端挂点

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr><th>服务</th><th>代码挂点</th><th>应补字段</th></tr>
  </thead>
  <tbody>
    <tr><td><code>ztd_cloud_driving</code></td><td><code>_receive_message()</code>、<code>_process_message()</code>、<code>_handle_invoke_function()</code>、<code>handle_remotejoystick()</code></td><td>connectionId、messageId、functionId、trace context、receive/decrypt/parse/handler/publish monotonic duration、result</td></tr>
    <tr><td><code>ztd_rtsp</code></td><td><code>ros2_image_callback()</code>、<code>push_data()</code>、<code>idH264</code> probe、<code>pay0</code> probe、GStreamer bus</td><td>videoSessionId、client/pipeline、frame sequence、ROS frame age、push result、IDR、encoder/RTP age、first RTP、pipeline error</td></tr>
    <tr><td>系统</td><td>车载 host PID/network、cgroup、内核 BPF 能力</td><td>BTF、BPF syscall、JIT、capability、CO-RE、namespace 可见性、Agent 版本</td></tr>
  </tbody>
</table>

## 分阶段实施

1. `V0`：目标车只读检查 `uname -r`、BTF、`CONFIG_BPF_SYSCALL`、JIT、cgroup、权限和基线 CPU/RSS/FPS。
2. `V1`：新增 `ztd_observability`，提供 `try_emit() noexcept`、有界队列、drop counter 和 JSONL 调试 sink。
3. `V2`：控制和视频进程统一使用 `steady_clock`/monotonic，所有阶段输出 `duration_ns`。
4. `V3`：控制协议兼容 `traceparent`；通过 ROS 2 `VideoTraceBinding` 把视频预绑定从控制进程传到 RTSP 进程。
5. `V4`：独立部署 eBPF/DeepFlow Agent，首期只开进程、TCP/UDP、RTT、重传、队列、调度和资源。
6. `V5`：消费线程批量转换 OTLP，接本地 Collector/Gateway；断网用有界 WAL/DataBuff 缓存。
7. `V6`：单车单路验证后扩展多路和车队；每次放量更新 DSH 状态和性能证据。

## 性能和故障隔离

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr><th>对象</th><th>初始门禁</th><th>超限处理</th></tr>
  </thead>
  <tbody>
    <tr><td>业务事件</td><td>生产线程非阻塞；控制 P99 相对关闭埋点增量不超过 0.2ms 且不超过 5%</td><td>停止放量，降低采样或关闭事件层</td></tr>
    <tr><td>视频埋点</td><td>不造成持续 FPS 下降；视频进程 CPU 增量目标不超过整机一个核的 2%</td><td>关闭帧级事件，只保留 session/错误/首帧摘要</td></tr>
    <tr><td>eBPF Agent</td><td>整机 CPU 初始目标不超过 2%，有独立内存、磁盘和网络上限</td><td>降采样或停止 Agent，业务继续运行</td></tr>
    <tr><td>Exporter/WAL</td><td>独立低优先级消费线程，批量、退避、快速失败</td><td>本地丢弃低优先级观测，不阻塞控制、ROS、编码和 RTP</td></tr>
  </tbody>
</table>

必须做四组对照：全部关闭、仅本地业务事件、仅 eBPF、业务事件加 eBPF。观测失败不得触发
视频 reload、WebRTC reconnect、控制降级、停车或安全动作。

## `JOYSTICK_IDLE_TIMEOUT` 当前可观测性

`JOYSTICK_IDLE_TIMEOUT` 是车端远控消息超时保护，不是视频黑屏结论。当前实现的检测窗口为：

```text
ping_joystick timer       约 100ms
joystick_msg_timeout_ms   300ms
joystick_mrc1_consecutive 6
连续检测后 MRC1           理论 300ms + 100ms × (6 - 1) = 800ms
                           实际约 800~900ms，取决于最后一帧与定时器的相位
```

`last_joystick_steady_ms_` 在 `handle_remotejoystick()` 函数入口更新，当前因此只能证明
“最后一次进入车端业务 handler 的时间”。如果消息已经到达 TCP 接收缓冲区、但仍在
`_receive_message()`、AES 解密、JSON parse、`_process_message()` 或前序 handler 中排队，
超时检测仍可能继续累加。

当前已经有的证据：

| 证据 | 能回答的问题 | 不能回答的问题 |
|---|---|---|
| `remotejoystick` 窗口计数、累计数、`msg/s` | 车端 handler 是否持续收到消息 | 驾驶舱是否发送、云端是否转发 |
| `transport_dispatch` 的 `body_receive_us/decrypt_us/parse_us/parse_to_dispatch_us` | 已读取长度头后，消息体接收、解密、JSON 解析和同步分发前处理是否慢 | 长度头到达前的等待究竟发生在云端、网络还是车端线程 |
| `listener_dispatch_gap_us`、前后 `message_id/source_seq` | 车端监听线程连续两次开始分发 remotejoystick 的间隔，超 MRC 窗口时强制留证 | 单独不能区分云端未发送、网络未送达、前一 handler 阻塞或其他消息占用监听线程 |
| `handler_start/end` 的 `observation_seq`、`message_id`、`source_seq` | handler 是否开始、是否返回以及相邻采样的业务序列是否连续 | TCP 完整消息何时到达、未采样正常帧的逐帧耗时 |
| `handler_us`、`publish_us`、`result` | handler 或 ROS publish 调用是否出现慢处理 | ROS 下游订阅者是否已执行、车辆执行器是否生效 |
| MRC 的 `last_publish_age_ms`、`last_message_id`、`last_source_seq` | 超时时最后一次 handler/publish 关联线索 | 最后一帧之前具体在哪个跨机器阶段丢失 |
| payload `timestamp` | 发送端墙上时间的关联线索 | 未同步时钟下的真实网络耗时 |
| `detecting loss`、`MRC1 triggered`、MRC source/status | 车端何时做出安全裁决 | 消息具体在哪个车云边界丢失 |
| `cloudLinkPing` RTT/reply timeout | 车云探活是否存在延迟或断连风险 | `remotejoystick` 业务流是否正常 |

车端 `cloud_driving_vehicle.cpp` 已增加以下低开销参数：

| 参数 | 默认值 | 语义 |
|---|---:|---|
| `remotejoystick_log_sample_every` | `50` | 每 N 帧输出一组正常 `handler_start/end` 摘要；`1` 表示全量，`0` 表示关闭正常帧采样 |
| `remotejoystick_slow_handler_ms` | `10` | handler 总耗时达到阈值时强制输出 `WARN`；`0` 表示关闭慢处理告警 |
| `remotejoystick_slow_transport_ms` | `10` | body receive、解密、JSON parse 和 parse-to-dispatch 累计达到阈值时强制输出 `WARN`；`0` 表示关闭慢传输告警 |

`listener_dispatch_gap_us` 的告警阈值复用 `joystick_msg_timeout_ms`，当前默认 `300ms`。
它刻意不命名为网络耗时，因为该间隔还包含前一同步 handler 和监听线程处理其他消息的时间。

结构化日志示例：

```text
[remotejoystick-observation] transport_dispatch result=sampled|slow_transport|dispatch_gap|slow_transport_and_dispatch_gap transport_seq=... message_id=... source_seq=... correlation_id=... previous_message_id=... previous_source_seq=... frame_bytes=... body_receive_us=... decrypt_us=... parse_us=... parse_to_dispatch_us=... transport_us=... listener_dispatch_gap_us=...
[remotejoystick-observation] handler_start observation_seq=... message_id=... source_seq=... correlation_id=... payload_bytes=...
[remotejoystick-observation] handler_end result=published|published_slow|drop_not_remote observation_seq=... message_id=... source_seq=... correlation_id=... handler_us=... publish_us=...
[joystick] MRC1 triggered gap=... last_publish_age_ms=... last_message_id=... last_source_seq=... last_correlation_id=...
```

解释规则：

- `body_receive_us` 高，说明已经读到 4 字节长度头，但读取完整 body 的过程慢，优先查 TCP 分片、
  重传、接收调度和对端写出。
- `decrypt_us`、`parse_us` 或 `parse_to_dispatch_us` 单项高，分别收敛到 AES、JSON 或车端监听
  线程的解析后处理。
- `listener_dispatch_gap_us >= joystick_msg_timeout_ms`，但本帧 `transport_us` 正常，表示车端
  一段时间没有开始分发新的 remotejoystick；结合前一帧 `handler_us` 和云端同一
  `messageId/seq/correlationId` 判断是前序 handler 占用、云端停发还是消息未送到车端。
- 有 `handler_start` 且 `handler_us` 长时间不结束，优先查 handler 内锁竞争、解析映射和线程调度。
- `handler_us` 正常但 `publish_us` 异常，优先查 ROS publisher、executor 和进程资源。
- 云端存在对应 `messageId/seq` 的发送完成记录，但车端没有对应 `transport_dispatch` 或
  `handler_start`，只能把范围收敛到云端发送器完成回调之后、车端解析/handler 之前。
- ROS `publish()` 返回只表示消息已交给 ROS 2 发布路径，不表示下游控制节点已经消费或执行。

现场按以下顺序取证：

1. 从 `MRC1 triggered` 取得 `last_message_id/last_source_seq/last_correlation_id` 和
   `last_publish_age_ms`，确定超时前最后一帧。
2. 在车端日志中按关联键回查最后一帧及恢复后的第一帧，比较 `listener_dispatch_gap_us`、
   `body_receive_us/decrypt_us/parse_us/parse_to_dispatch_us`、`handler_us/publish_us`。
3. 在云端按同一 `messageId/seq/correlationId` 回查 `inflight_slow`、
   `send_completed_slow`、pending age 和 coalesced total。
4. 云端没有该序列时回查驾驶舱发送；云端已完成而车端没有该消息时，再结合 TCP
   RTT、重传、socket 队列和车端线程调度缩小范围。
5. 不使用跨机器墙上时间直接相减；跨机器只比较同一关联键的阶段事件是否存在，
   进程内耗时使用 monotonic duration。

现场补充分析表明，三次 `0 -> 2 (JOYSTICK_IDLE_TIMEOUT)` 中，第一次同时出现连接异常
和探活超时；第二次附近出现 `2041ms` ping RTT；第三次 ping 保持约 `77~126ms`，但
`remotejoystick` 仍长时间为 `0 msg/s`。因此不能把“现场网络较好”或“ping 正常”直接
等价为“摇杆消息链路正常”，也不能仅凭现有日志判定是云端消息阻塞。

当前车端已经按以下边界补充低开销、限流事件：

```text
tcp_body_receive
decrypt
json_parse
parse_to_dispatch
listener_dispatch_gap
handler_start/end
ros_publish_start/end
```

尚未落地的是驾驶舱 send start/result、TCP 长度头到达时刻、内核收包时间、ROS 下游消费
确认和底盘最终执行确认。当前 `body_receive_us` 从长度头读取完成后开始计时；
`listener_dispatch_gap_us` 能发现长空窗，但必须与云端日志和前一 handler 耗时联合归因。

生产环境应移除或限流 `inputs.dump()` 这类高频完整 payload 日志，改为字段白名单、消息大小、
序列、模式、处理结果和阶段耗时。埋点必须使用有界本地队列或非阻塞 sink，不得在控制收包
线程中同步写远端观测系统。

当前实现已经移除每帧完整 payload 输出和每帧 `INVOKE_FUNCTION/skip reply` DEBUG 输出，
只在采样帧计算序列化后的 `payload_bytes`。`CloudDrivingClient` 已记录长度头读取完成后的
TCP body receive、解密、JSON parse 和 dispatch 阶段耗时，因此能够发现消息在完整 body
接收、解密、解析或同步分发阶段变慢；但长度头到达前的等待仍无法仅靠应用日志拆成云端、
网络和车端调度耗时。

详细 eBPF tracepoint、Map、QoS、`VideoTraceBinding` 和验收矩阵见[完整设计基线第 9.1.4 节](../full-link-observability.md#914-车端控制视频与-ebpf-实施设计)。
