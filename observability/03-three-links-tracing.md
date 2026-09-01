# 03 车-云-端三条链路全链路追踪

更新时间：`2026-08-29`

## 当前阶段范围（2026-08-29）

当前先收敛验证范围，不依赖驾驶仓埋点，边界为：

```text
指令进入 ziot 云端
  -> 云端接收/排队/latest-only/设备发送
  -> 车端 TCP body 接收
  -> 解密/解析/同步分发
  -> remotejoystick handler
  -> ROS publish
```

本阶段目标是回答：

- 指令进入 ziot 后，云端转发和设备发送是否变慢、合并、丢弃或失败；
- 云端发送完成后，车端是否收到并完成 body 接收、解密、解析、handler 和 ROS publish；
- DeepFlow/eBPF 的网络事实是否能解释云端发送到车端接收之间的异常。

本阶段暂不纳入驾驶仓 `send_start/send_result`，也不把 ROS publish 返回当作
安全门禁、控制器或底盘已经执行。跨节点单条消息关联优先使用
`messageId + source_seq + correlationId`；未完成时钟同步时，不直接用两台机器的
墙上时间相减计算毫秒级云端到车端耗时。

## 标识符规则

`remoteSessionId/sessionId` 贯穿数小时远控会话；`traceId` 只描述一次有限操作；`spanId`
描述操作中的阶段；`messageId` 是协议级单条消息；`videoSessionId` 是单路逻辑视频会话；
`correlationId` 是无法传播 Trace Context 时的补偿键。

```text
remoteSessionId
  ├── command trace: 一次控制操作
  ├── video trace: 一次视频建连或恢复
  └── status trace: 一次状态异常或发送窗口
```

## 三条链路

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>链路</th>
      <th>拓扑</th>
      <th>车端关键事件</th>
      <th>耗时口径</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>指令</td>
      <td>驾驶舱手柄 -> 云端接入 -> 车云 TCP -> <code>ztd_cloud_driving</code> -> ROS 2 -> 安全门禁/控制器 -> 执行器 -> 状态确认</td>
      <td>control received、decrypt、parse、handler、ROS publish、subscriber、safety gate、actuator command</td>
      <td>每个进程用 monotonic；跨节点只保留接收/发送事件、offset 和关联质量</td>
    </tr>
    <tr>
      <td>视频</td>
      <td>摄像头/ROS -> <code>ztd_rtsp</code> -> appsrc -> 编码器 -> RTP/RTSP -> ZLMediaKit -> WebRTC -> 浏览器解码/渲染</td>
      <td>ROS frame、appsrc push、encoder output、IDR、first RTP、last RTP、pipeline error、disconnect</td>
      <td>车端记录 ROS/push/encode/RTP；云端记录 ZLM；浏览器记录 ICE/RTP/decode/render</td>
    </tr>
    <tr>
      <td>状态上报</td>
      <td>车端状态 -> 车云上报 -> EventBus -> queue -> WebSocket send -> 浏览器 receive -> RAF/apply</td>
      <td>status publish、eventbus received、queue enqueued、websocket sent；浏览器已有 sample/applied/age</td>
      <td>各节点使用本地 monotonic；固定约 37 秒偏移只做 offset，不计算跨域 latency</td>
    </tr>
  </tbody>
</table>

## Trace/Span 拆分

```text
command trace
  -> control.receive
  -> decrypt
  -> parse
  -> handler
  -> ros.publish
  -> downstream safety/actuator

video initial-connect trace
  -> offer.prepare
  -> zlm.webrtc.request
  -> remote-description.apply
  -> ontrack
  -> first-frame

video recovery trace
  -> stall.confirm
  -> peer-connection.rebuild
  -> zlm.webrtc.request
  -> recovered-first-frame
```

普通状态消息和 250ms `getStats()` tick 不逐条创建 Span；仅对首次拉流、重连、黑屏恢复、
超时、协议异常和状态异常建立短生命周期 Trace。

## `remotejoystick` 云端到车端分段追踪

`JOYSTICK_IDLE_TIMEOUT` 只说明车端在规定窗口内没有观察到新的
`remotejoystick` handler 处理结果。当前阶段要回答“云端是否转发、车端是否收到并处理”，
必须对同一帧使用 `messageId + seq + correlationId` 关联以下时间点：

```text
云端：
  cloud_receive
  cloud_latest_mailbox_enter/leave
  cloud_send_start/completion
  cloud_drop/expire

车端：
  tcp_receive_start/end
  decrypt_completed
  parse_completed
  dispatch_enter
  handler_start/end
  ros_publish_start/end
```

当前阶段先使用云端和车端两侧证据。驾驶仓发送事件保留在完整设计中，暂不作为
本阶段验收前提。两侧事件需要携带同一关联键，才能判断云端发送完成后车端是否出现
对应消息。

三类故障的判定口径：

| 证据组合 | 结论 |
|---|---|
| 云端有接收但没有 send start，或 dedup/coalesced 明显增长 | 云端去重、latest-only 信箱或房间转发问题 |
| 云端 `inflight_slow`，且 `send_completion_latency` 超过 300ms | 云端设备发送器或底层 TCP write 回调长时间未完成；latest-only 期间后续帧只覆盖 pending |
| 云端有 `send_complete`，车端没有对应 `transport_dispatch` | 范围收敛到云端发送完成回调之后、车端应用分发之前；结合 DeepFlow 重传、RTO、socket queue 和车端调度继续判断 |
| 云端和车端都有同一 `messageId/seq`，但车端阶段耗时增长 | 指令已到车端，继续按 body 接收、解密、解析、handler 和 ROS publish 分段定位 |
| 车端 `body_receive_us` 高 | 长度头已到达，但完整 body 接收慢；查网络分片/重传、接收调度和对端写出 |
| 车端 `decrypt_us/parse_us/parse_to_dispatch_us` 高 | 车端 AES、JSON 解析或解析后同步分发阶段慢 |
| 车端 `listener_dispatch_gap_us` 超过 MRC 窗口，但本帧 transport 正常 | 车端长时间未开始分发 remotejoystick；结合前一 handler 和云端序列判断停发、未送达或监听线程占用 |
| 车端 handler 已开始但 `ros_publish` 耗时异常 | 车端业务处理或 ROS 调度阻塞 |
| 车端 handler 持续正常，但仍有 MRC 超时 | 检查时间戳更新位置、并发可见性、检测定时器和模式状态 |

当前云端已在 latest-only 转发路径增加：

| Micrometer 指标 | 类型 | 语义 |
|---|---|---|
| `parallel_driving.remotejoystick.dedup_dropped` | Counter | 同 `messageId` 重复帧被 dedup 丢弃 |
| `parallel_driving.remotejoystick.mailbox_coalesced` | Counter | 在途发送期间，旧 pending 帧被更新帧覆盖 |
| `parallel_driving.remotejoystick.inflight` | Gauge | 当前等待设备发送器完成的 remotejoystick 数 |
| `parallel_driving.remotejoystick.mailbox_pending_age` | Timer | 最新帧从进入 latest-only 信箱到开始发送的等待时间 |
| `parallel_driving.remotejoystick.send_completion_latency` | Timer | 从开始转发到设备发送器完成的耗时，带 `result` 标签 |
| `parallel_driving.remotejoystick.inflight_slow` | Counter | 在途发送被观察到超过 300ms 的次数 |
| `parallel_driving.remotejoystick.inflight_slow.duration` | Timer | 观察到慢在途时的持续时间 |

云端慢发送日志使用 `[remotejoystick-observation] inflight_slow` 和
`send_completed_slow`，包含 room、cockpit、vehicle、messageId、seq、correlationId、
pending age、send duration 和 coalesced total。当前云端重建下行消息时保留原始
`messageId`，同时传播 `seq` 和 `correlationId`；缺少 `correlationId` 时回退为
`messageId`。

`parallel-driving.control.latest-only=true` 时，同一房间只允许一帧在途。如果
`sendAndForget` 的完成信号长时间不返回，后续帧不会并发写出，只会持续覆盖 pending，
这可能使车端超过 MRC 窗口没有新消息。必须同时观察 `inflight_slow`、
`mailbox_coalesced` 和 `send_completion_latency`，不能只看云端入口消息数。

这里的“发送完成”只表示 JetLinks 设备发送器完成；当前 TCP 实现最终等待
`VertxTcpClient` 的 `socket.write(buffer, callback)` 回调。它不代表车端应用已收到完整
消息，更不代表 `handle_remotejoystick()` 或 ROS publish 已执行。

当前 TCP 层已补充以下连接级观测：

```text
[tcp-connection] device_bound / replace_socket / exception / close / closed
[tcp-write] write_start / write_queue_full / write_complete / write_complete_slow
            / write_error / write_throwable / write_cancel
```

这些日志包含 `writeId`、`clientId`、认证后的 `deviceId`、远端地址、连接代际、连接存活时间、payload 字节数、
写队列是否已满和 `writeDurationMs`。`write_complete` 是 Vert.x
`socket.write` 回调完成点，表示该写请求已被底层 TCP 实现接受或失败；仍不等于车端
长度头到达、完整 body 到达或车端业务 handler 已执行。默认 `write_complete_slow` 阈值为
`300ms`，可通过 JVM 参数 `gateway.tcp.network.write-slow-ms` 调整，设为 `0` 关闭慢写告警。

设备 ID 在 TCP 首条消息认证后绑定到连接对象，因此现场应优先按
`deviceId + clientId + remoteAddress` 区分连接代际。若同一车辆出现多个 `clientId`，或
旧连接长期没有 `closed/exception` 但 `write_complete` 延迟持续升高，应重点检查双 5G
切换后的旧 TCP 连接黑洞、云端 session 路由和连接替换。

当前车端已记录采样或异常帧的 `transport_dispatch`，包括 `body_receive_us`、
`decrypt_us`、`parse_us`、`parse_to_dispatch_us`、`transport_us`、
`listener_dispatch_gap_us`、前后 `message_id/source_seq`，并记录
`handle_remotejoystick()` 的 `handler_start/end`、`handler_us`、`publish_us` 和
`correlation_id`。其中 `listener_dispatch_gap_us` 是同一监听线程两次开始分发
remotejoystick 的间隔，包含前一同步 handler、其他消息处理和当前收包过程，不是纯网络耗时。

当前不要求驾驶仓记录统一的 send start/result；车端也没有 TCP 长度头到达、内核收包、
ROS 下游消费和底盘最终执行确认。因此当前可以确认云端 latest-only 写出是否慢、车端
body/decrypt/parse、handler 和 ROS publish 调用是否慢，但不能证明 ROS publish 之后已经
被控制器或底盘执行。
`cloudLinkPing` 只作为网络旁证，不替代 `remotejoystick` 的业务序列探针。

`remotejoystick` 频率高，不建议为每帧创建完整远端 Trace。推荐按采样比例保留正常帧，
对以下事件强制保留短 Trace/Event：

```text
timeout_detecting
mrc_joystick_idle_timeout
first_frame_after_timeout
message_drop_or_expire
handler_slow
cloud_link_ping_timeout
```

每个阶段使用本地 monotonic duration；跨机器只比较带关联键的发送/接收事件，不使用
payload `timestamp` 直接计算网络延迟，除非已完成时钟同步并明确时钟域。

## 跨进程/跨协议关联

1. 控制协议在已有 `headers` 中兼容 `traceparent`、`tracestate`、`remoteSessionId`、
   `correlationId` 和 `schemaVersion`；非法 context 只记录观测事件，不拒绝控制消息。
2. 云端在 ZLMediaKit 主动拉流前发送短 TTL `bindVideoTrace`，由
   `ztd_cloud_driving` 发布 `/zeron/observability/video_trace_binding`，`ztd_rtsp` 维护
   有界 registry。
3. RTP 不写完整 Trace ID，不逐 RTP 包创建业务 Span；使用 `stream/app`、RTSP session、
   SSRC、五元组和时间窗关联。
4. 浏览器 WebSocket 通过连接 query、cookie、subprotocol 或首条应用消息传播
   `correlationId`；不能假设浏览器可设置任意握手 header。
5. 车端、云端、浏览器时钟不要求同步。每个节点记录自己的 monotonic duration；跨域字段使用
   `clockOffset*` 和 `crossDomainDurationMs=null` 表达数据质量。

## 旧版本降级

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>缺失能力</th><th>降级关联</th><th>禁止行为</th></tr></thead>
  <tbody>
    <tr><td>旧云端无 <code>traceparent</code></td><td>车端生成本地 Trace，以 messageId + connectionId 关联</td><td>不能拒绝控制消息</td></tr>
    <tr><td>无 <code>bindVideoTrace</code></td><td>本地 videoSessionId + stream/五元组/时间窗</td><td>不能伪装为完整 Trace Context</td></tr>
    <tr><td>Agent/Collector 不可用</td><td>本地事件继续，按优先级丢弃或缓存</td><td>不能阻塞收包、ROS、编码和 RTP</td></tr>
    <tr><td>时钟域未同步</td><td>保留 offset、baseline、delta 和关联质量</td><td>不能把负数称为负延迟</td></tr>
  </tbody>
</table>

具体字段和代码改造顺序见[完整设计基线第 9.1.8 节](../full-link-observability.md#918-三条车-云-端链路的全链路追踪)。
