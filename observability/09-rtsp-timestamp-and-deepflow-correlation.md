# 车端 RTSP 时间戳与 DeepFlow 链路耗时关联

更新时间：`2026-08-29`

状态：`approved/unverified`

## 1. 结论

车端 aura 运行在 Linux Docker 容器内时，不需要在 RTSP 源码中编写 eBPF
probe。DeepFlow Agent 应部署在车机 Linux 宿主机，使用宿主机网络、进程和
容器观测能力采集 aura 的网络流量。

车端 RTSP 可以携带媒体时间信息，但不能据此直接认为：

```text
ZLMediaKit 侧 DeepFlow/eBPF
  = 自动得到 header.stamp 到 ZLMediaKit 收包的帧级耗时
```

当前能可靠得到的是：

```text
车端 RTSP 应用埋点：
  ROS header.stamp
  -> appsrc push
  -> 编码器输出
  -> RTP 包产生

ZLMediaKit 宿主机 DeepFlow：
  连接、端口、五元组、吞吐、RTT、重传、reset、网卡丢包和容器归属

ZLMediaKit 应用埋点：
  RTP/RTSP 收包时间、stream、SSRC、RTP sequence、session_id
```

只有把车端发送侧时间和 ZLMediaKit 接收侧时间按帧或 RTP 包关联，才能计算
“车端到云端”的网络传输耗时。

## 2. 当前车端时间信息现状

### 2.1 ROS 时间与播放时间是两套时间

当前车端代码对 `appsrc` 使用：

```text
format=GST_FORMAT_TIME
is-live=true
do-timestamp=true
```

这是为了维持稳定的 GStreamer running-time/RTSP 播放时钟。

ROS 图像的 `header.stamp` 通过 `GstReferenceTimestampMeta` 保存在 buffer
metadata 中，用于车端诊断。它与 GStreamer 的 PTS、RTP timestamp 不是同一个
字段，也不应直接混用。

当前 `[latency_1s]` 中的：

```text
recv
rtsp_proc
push
cloud
```

都以车端系统当前时间减去 ROS `header.stamp` 计算。特别是当前 `cloud` 的实际
采样点位于车端 `idH264` encoder probe，含义是：

```text
cloud = 车端编码器输出时间 - header.stamp
```

它不是：

```text
ZLMediaKit 收到 RTP 包的时间 - 车端 header.stamp
```

因此当前日志可以定位车端接收、处理、push 和编码延迟，但不能单独证明车端到
ZLMediaKit 的网络传输耗时。

### 2.2 RTP timestamp 的含义

RTP header 中的 timestamp 是媒体时钟值，通常用于接收端播放排序、同步和抖动
缓冲。它一般不是 Unix wall-clock，也不自动等于 ROS `header.stamp`。

RTCP Sender Report 可以建立 RTP 媒体时钟和 NTP 时间之间的映射，但这仍然不等于
DeepFlow 会自动获得 ROS 采集时间，也不等于每个媒体帧都有可直接查询的业务时间。

### 2.3 当前 RTP 调试扩展

车端 RTP probe 当前会：

```text
默认：
  统计 RTP 包数、字节数、缺少时间戳的包数
  不改变标准 RTP payload/header

debug_clock_overlay=true：
  尝试把 ROS header.stamp 写入自定义 RTP header extension
```

该自定义扩展只适合受控诊断。标准 RTSP/WebRTC 客户端不一定识别它，不能把它
作为默认协议契约，也不能假设 DeepFlow Agent 会解析该扩展。

### 2.4 不能用 eBPF 无损改写 RTP timestamp

eBPF 可以在 socket、网络设备或内核网络路径上记录事件时间，但“给 RTP 包增加
一个 timestamp”属于修改正在传输的数据包，不是观测。

理论上，XDP/TC 程序可以尝试改写 RTP header 或增加 RTP header extension，但这
需要同时处理：

```text
RTP header 长度和扩展长度
UDP length
UDP checksum
IP checksum
MTU、分片和 GRO/GSO
RTP 包边界、SSRC 和 sequence
DTLS/SRTP 加密后的不可修改 payload
接收端对自定义扩展的兼容性
```

任一步骤失败都可能导致丢包、校验失败、解码异常或连接重建。因此这种方式
不能称为“无损无侵入”，也不适合作为 DeepFlow Agent 的默认职责。DeepFlow 的
采集配置面向抓包位置、过滤和 payload 截断，是采集路径，不是 RTP 协议改写路径。

正确区分如下：

```text
eBPF 观测：
  记录内核看到的发送/接收事件时间
  不改变 RTP 包
  适合补充网络传输证据

GStreamer/RTSP 应用：
  生成标准 RTP timestamp
  或在受控 debug 模式增加自定义 RTP extension
  适合携带业务帧时间
```

如果目标只是得到车端网络出口时间，可以让 eBPF 通过旁路事件记录发送时间，
再与 ZLMediaKit 收包事件按五元组、UDP sequence 或 SSRC 关联；这仍然不等于
把时间戳写入 RTP 包，也不能由 DeepFlow 默认自动完成。

## 3. ZLMediaKit 侧 eBPF 能否计算耗时

### 3.1 DeepFlow/eBPF 可以直接提供的证据

在 ZLMediaKit Docker 宿主机部署 Agent 后，可以按容器、进程、网卡、端口和五元组
观察：

```text
车端到 ZLMediaKit 的 TCP connect/accept/close
RTSP 控制连接的 RTT、重传、reset、RTO
RTP/RTCP UDP 的包数、字节数和 socket 网络事实
ZLMediaKit 容器、PID、cgroup 和 network namespace
宿主机网卡 RX/TX、drop、error、队列和带宽
```

这些数据可以回答：

```text
是否断连
是否重传
是否存在网络拥塞或网卡丢包
ZLMediaKit 是否收到持续流量
流量是否归属于预期的 ZLMediaKit 容器
```

### 3.2 DeepFlow/eBPF 不能单独提供的结果

仅在 ZLMediaKit 宿主机采集时，不能直接得到：

```text
某个 RTP 包对应车端哪一个 ROS header.stamp
某个视频帧从车端 appsrc 到 ZLMediaKit 的准确耗时
ZLMediaKit 是否已经完成该帧的媒体解析或转发
浏览器是否解码、渲染或触发重拉
```

原因是 eBPF/DeepFlow 主要观测内核网络和进程事实；它不会默认解析
ROS metadata、GStreamer buffer metadata 或自定义 RTP 扩展并建立帧级关联。

此外，只有 ZLMediaKit 侧时间而没有车端发送时间时，单端观测无法计算单向耗时。
RTT 也不能直接除以二作为视频单向传输延迟，因为上下行路径和排队情况可能不同。

## 4. 推荐的耗时测量方案

### 4.1 第一阶段：应用埋点与 DeepFlow 对照

保留车端现有埋点，并补充明确的网络边界事件：

```text
车端：
  rtsp_frame_id 或 frame_seq
  vehicle_id
  stream/camera
  video_session_id
  ros_header_stamp_ns
  appsrc_push_time_ns
  encoder_output_time_ns
  rtp_packet_time_ns
  rtp_ssrc
  rtp_sequence
  payload_bytes
```

ZLMediaKit 侧补充：

```text
zlm_node
  container_id
  stream/app/vhost
  session_id
  rtp_receive_time_ns
  rtp_ssrc
  rtp_sequence
  payload_bytes
```

两端使用同步的 wall clock，并把单调时钟仅用于本机阶段耗时：

```text
本机阶段耗时：
  monotonic_end - monotonic_start

跨主机单向耗时：
  zlm_receive_time_ns - vehicle_rtp_send_time_ns
```

跨主机计算前必须验证 NTP/PTP 偏差。记录：

```text
clock_offset_estimate_ns
clock_sync_status
clock_sync_observed_time
```

如果时钟偏差大于目标网络耗时量级，结果只能作为趋势，不能当作绝对值。

### 4.2 第二阶段：DeepFlow 关联网络事实

将应用事件与 DeepFlow 流记录按以下顺序关联：

```text
1. vehicle_id + stream + video_session_id
2. 时间窗口
3. container_id/process
4. src_addr/src_port + dst_addr/dst_port + protocol
5. RTP SSRC/sequence（仅应用层收发日志可提供）
```

DeepFlow 的作用是验证该时间窗口内的网络事实：

```text
发送前后是否有重传
ZLMediaKit 接收前是否有 RTO 或 reset
网络吞吐是否下降
容器或网卡是否丢包
是否发生连接重建
```

DeepFlow 的流时间不能直接替代 RTP 帧接收时间。最终诊断应同时保留：

```text
frame_transport_latency_ms
network_rtt_ms
tcp_retransmit_count
tcp_reset_count
udp_packet_count
zlm_input_bitrate
zlm_session_generation
```

## 5. 三种落地选择

| 方案 | 能得到什么 | 代价和限制 | 建议 |
|---|---|---|---|
| 仅 ZLMediaKit 宿主机 DeepFlow | 网络连接、吞吐、RTT、重传、容器归属 | 不能做 ROS 帧到达耗时 | 必做 |
| 车端应用事件 + ZLM 应用收包事件 | 帧级车端到 ZLM 收包耗时 | 需要两端埋点、时钟同步和关联字段 | 首选 |
| 自定义 RTP 扩展 + ZLM 解析器 | 可在收包侧读取车端时间 | 需要协议兼容评审，DeepFlow 不会自动解析 | 仅短时诊断 |

不建议为此编写 DeepFlow 专用 eBPF 程序去解析 H.264/RTP payload。视频协议
解析放在 ZLMediaKit 接收层或旁路诊断程序更合适，DeepFlow 保持网络事实采集
职责。

## 5.1 如果业务时间戳传不过去，如何降级

这里需要区分两种情况：

```text
业务时间戳传不过去：
  ROS header.stamp 没有到达 ZLMediaKit

标准 RTP 字段仍然存在：
  SSRC、RTP timestamp、sequence 可以在 RTP 包中读取
```

推荐不要让 `header.stamp` 成为 RTSP 正常运行或前端播放的前置条件。当前车端
已经通过 `GstReferenceTimestampMeta` 在本地保存它，因此它仍然可以用于计算：

```text
header.stamp -> recv
header.stamp -> appsrc push
header.stamp -> encoder output
```

如果自定义 RTP header extension 没有被 ZLMediaKit 或其他中间层保留，则不再
尝试通过 eBPF 修改 RTP 包，也不把 RTP timestamp 当作 Unix wall-clock。此时
优先使用标准 RTP 字段做短时关联：

```text
车端 RTP 输出侧记录：
  stream/session
  SSRC
  RTP timestamp
  sequence
  vehicle_rtp_send_time_ns
  payload_bytes

ZLMediaKit RTP 接收侧记录：
  stream/session
  SSRC
  RTP timestamp
  sequence
  zlm_rtp_receive_time_ns
  payload_bytes
```

关联键按以下优先级使用：

```text
session_id + SSRC + sequence
session_id + SSRC + RTP timestamp + sequence
五元组 + 时间窗口 + SSRC + sequence
```

`sequence` 用于确认是否是同一个 RTP 包，`RTP timestamp` 用于确认媒体时钟
位置，`SSRC` 用于区分同一连接内的 RTP 源。必须同时保留 `session_id` 或
stream generation，避免重拉后新旧会话的 sequence 恰好重复。

在车端和 ZLMediaKit 的 wall clock 已通过 NTP/PTP 校准时，可以计算：

```text
rtp_transport_ms =
  zlm_rtp_receive_time_ns - vehicle_rtp_send_time_ns
```

这个值表示“车端 RTP 输出观测点到 ZLMediaKit RTP 接收观测点”的时间，不表示
ROS 采集到云端的完整帧延迟。完整链路仍需要额外保留：

```text
capture_to_rtp_ms =
  vehicle_rtp_send_time_ns - ros_header_stamp_ns

rtp_to_zlm_ms =
  zlm_rtp_receive_time_ns - vehicle_rtp_send_time_ns
```

### 5.2 连标准 RTP 关联字段也不可用时

如果由于加密、封装、抓取位置或现有日志能力，连 `SSRC/RTP timestamp/sequence`
都无法在两端稳定取得，则采用明确的窗口级降级方案：

```text
车端每 1-5 秒：
  stream
  video_session_id
  frame_generation
  rtp_packet_count
  rtp_bytes
  last_rtp_send_age_ms
  push_ok/push_error
  pipeline_generation

ZLMediaKit 每 1-5 秒：
  stream/session
  session_generation
  input_packet_count
  input_bytes
  last_packet_age_ms
  input_bitrate
  disconnect/reconnect/reset
```

再将这些窗口和 DeepFlow 的网络事实按 `stream/session`、五元组和时间窗口
对齐。该方案可以可靠回答：

```text
车端是否还在持续发包
ZLMediaKit 是否还在持续收包
中间是否出现断流、重连、reset、重传、丢包或吞吐下降
重拉发生前后是否存在输入流中断或 session generation 变化
```

但不能声称：

```text
某一帧从车端到 ZLMediaKit 的精确单向耗时
某一帧是否在云端被丢弃
前端重拉一定由某个 RTP 包直接触发
```

因此建议按运行模式分层：

```text
常态运行：
  DeepFlow 网络指标
  车端 rtsp_diag/rtsp_timing/latency_1s
  ZLMediaKit 流状态和输入速率

故障诊断窗口：
  临时开启车端 RTP 关联日志
  开启 ZLMediaKit RTP 收包日志
  采集 SSRC、RTP timestamp、sequence 和两端 wall-clock

前端重拉定位：
  ZLMediaKit session/disconnect/input-stall
  浏览器 WebRTC stats 和重拉事件
  与车端 session generation 对齐
```

这比持续在 RTP 包上增加自定义字段更适合生产环境：正常链路不增加协议风险，
故障时仍能逐步提升观测粒度。当前车端已增加以下默认关闭的诊断开关：

```text
rtp_correlation_debug=false
rtp_sample_every=0
```

开启后只读取 payloader 输出的标准 RTP 头，并按配置间隔输出
`SSRC/RTP timestamp/sequence/output_observed_time_ns` 抽样日志；不修改 RTP
包、不创建无界队列、不阻塞推流。车端到 ZLMediaKit 的双端关联及 ZLMediaKit
收包时间埋点尚未完成，不能把当前 `[latency_1s] cloud` 解释为网络传输耗时。

## 6. aura Docker 部署要求

车端拓扑：

```text
Linux 车机宿主机
├── aura RTSP Docker 容器
└── deepflow-agent
```

Agent 可作为独立容器运行，但需要具备宿主机观测能力：

```text
network_mode: host
pid: host
/sys/kernel/debug
/var/run/docker.sock
必要的 eBPF、网络和进程 capabilities
```

必须按实际网络模式检查：

```text
aura container -> veth/docker bridge -> eth0 -> 云端 ZLMediaKit
aura container -> lo -> 本机服务
```

如果车端 RTSP 连接直接出物理网卡，宿主机 Agent 可以观察出站流量；如果存在
本机回环路径，则要确认 Agent 采集 `lo`。容器识别需要保留 Docker/cgroup 元数据，
避免只能看到匿名端口流量。

## 7. 验收标准

### 必须验证

```text
1. DeepFlow 中可以按 aura container/process 找到车端出站流量。
2. DeepFlow 中可以按 ZLMediaKit container/process 找到对应入站流量。
3. 两侧五元组、端口和时间窗口可以关联。
4. 车端日志能给出 rtp_packet_time_ns 和 stream/session。
5. ZLMediaKit 日志或接收层能给出 rtp_receive_time_ns。
6. 时钟偏差在验收窗口内有记录。
7. 人为制造网络重传或断连时，DeepFlow 与应用事件同时出现。
8. 观测系统不可达时，RTSP 推流不被阻塞。
```

### 不能作为验收结论

以下结论不能仅凭 DeepFlow 得出：

```text
“某一帧一定在 80ms 内从车端到达 ZLMediaKit”
“前端一定因为该网络包触发了重拉”
“没有 TCP 重传就代表视频没有丢帧”
```

这些结论需要车端、ZLMediaKit 和浏览器三端事件共同证明。

## 8. 当前项目结论

当前车端已经有：

```text
header.stamp 年龄
recv / rtsp_proc / push / cloud 统计
encoder output 统计
RTP 包数、字节数和缺少时间戳统计
可选 RTP 调试时间扩展
```

当前还不能宣称已经完成：

```text
车端 RTP 发包时间与 ZLMediaKit 收包时间的帧级关联
DeepFlow Agent 在目标车机上的部署和采集验证
DeepFlow 数据上传 DataBuff 后的字段查询验证
```

本文件只记录 RTSP 时间戳和 DeepFlow 关联方案，不修改 `operator` 端逻辑。
