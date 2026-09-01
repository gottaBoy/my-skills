# 车端 RTSP 首次拉流失败与频繁重拉分析记录

更新时间：`2026-09-01`

状态：`analysis/unverified`

说明：本记录用于定位车端 RTSP 首次被拉流后没有及时开始供帧的问题。当前尚未完成目标车辆上的构建产物核对和长时间实车回归，不能写成 `verified`。

## 0. 已确认前提

用户已确认 ZLMediaKit 没有修改，且此前同一套 ZLMediaKit 页面和 ZIOT 前端可以直接播放。
因此本次不把 ZLMediaKit 代码、配置或播放页面作为回归原因。当前重点是车端
`ztd_rtsp` 的首次拉流触发、RTSP media 配置、`appsrc need-data`、`push_data` 和
pipeline 生命周期。

本仓库相关 OTel/RTSP 提交的差异中也没有 ZLMediaKit 源码变更。另一个分支中将
`/raw_image` 改为 `/rtsp_raw_image` 的提交不属于本次分析范围。

## 1. 问题范围

本记录只覆盖车端：

```text
/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle
```

用户现场曾出现前端持续显示“重拉”，车端日志中同一路反复出现：

```text
Client connected for /cam_rb_10
Client connected for /cam_f_12
Client connected for /cam_lb_4
```

这说明 RTSP client 侧正在反复建立媒体连接。前端无画面或重拉是表象，车端侧必须区分以下几类原因：

1. 请求没有到达车端 RTSP server，或请求到达但没有完成 media 配置。
2. media 已配置但没有触发 `need-data`。
3. 已触发 `need-data`，但车端没有执行或没有成功执行 `push_data`。
4. GStreamer 返回 `GST_FLOW_FLUSHING` 或其他 flow error，导致媒体被关闭。
5. RTSP media pipeline 生命周期管理错误，旧 pipeline 回调影响新 pipeline。
6. 编码后 H.264 队列丢失参考帧，导致下游无法持续解码。

前端、云端和 ZLMediaKit 只作为“车端输出是否已经恢复”的观察端，不作为本次
车端回归的首要修改对象。Operator 端逻辑不在本次范围内。

## 2. 实车证据

现场日志中的普通摄像头通常为：

```text
recv P50/P90 约 55-85 ms
rtsp_proc P50/P90 约 0-3 ms
push P50/P90 约 60-90 ms
cloud P50/P90 约 65-100 ms
```

`/ipm` 的延迟明显更高，常见范围为：

```text
push 约 115-150 ms
cloud 约 125-170 ms
```

这批日志没有显示持续性的 `rtsp_proc` 阻塞。少量 `Max` 达到 100-290 ms，只能说明存在偶发抖动，不能单独证明是 RTSP 处理线程长期卡住。

更有价值的信号是连接日志。例如在早期约 20 秒的现场日志内，先后出现多个路的：

```text
encoder ... props applied
Client connected for ...
pci id for fd ... driver (null)
```

同一路多次出现 `Client connected`，与前端反复重拉的时间关系高度一致。该段日志代表修复前或旧部署版本的现场行为，
不能直接代表后续稳定性。

### 2.1 最新一批现场日志状态

后续实车日志时间戳范围约为 `1787969253` 至 `1787969266`，并且用户确认当前前端没有继续出现“重拉”。
这批日志中的普通摄像头表现为：

```text
/cam_f_7    recv P50 55-68ms，P90 61-77ms，cloud P50 65-75ms
/cam_f_12   recv P50 56-66ms，P90 57-78ms，cloud P50 66-73ms
/cam_b_18   recv P50 60-72ms，P90 67-77ms，cloud P50 69-80ms
/cam_rb_10  recv P50 55-66ms，P90 65-77ms，cloud P50 64-73ms
/cam_lb_4   recv P50 55-62ms，P90 57-68ms，cloud P50 63-72ms
```

`rtsp_proc` 大多为 `0-3ms`，`push_attempt` 与 `push_ok` 基本一致，且诊断窗口中：

```text
flow_flushing=0
flow_error=0
pipeline_destroy=0
```

各路 `need_data` 与 `push_ok` 也基本同步。这说明在该采样窗口内，车端 appsrc 供给没有表现出持续失败，
也没有证据表明 pipeline 在高频销毁。

`/ipm` 仍明显偏高，约为：

```text
recv P50 326-366ms，P90 331-383ms，cloud P50 333-373ms
```

目前只能确认 `/ipm` 的高延迟主要已经存在于车端 `recv` 阶段，不能据此归因于 RTSP push；
其输入源时间戳、上游生产、调度或时间基准仍需单独核对。

作为对照，之前一批旧版本现场日志时间戳范围约为 `1787926116` 至 `1787926137`，曾出现多路媒体重新建立连接：

```text
1787926116.397  Client connected for /cam_rb_10
1787926119.179  Client connected for /cam_f_12
1787926120.851  Client connected for /cam_lb_4
1787926125.760  Client connected for /cam_b_18
1787926129.164  Client connected for /cam_rb_10
1787926129.650  Client connected for /cam_f_12
1787926136.203  Client connected for /cam_lb_4
1787926136.734  Client connected for /ipm
```

因此当前现场结论是：

1. 用户已确认前端当前没有继续显示重拉；这批日志的车端数据面表现暂时稳定。
2. 普通摄像头的 `recv`、`push`、`cloud` P50/P90 大多在约 `55-80ms`，`rtsp_proc` 大多为 `0-3ms`；不支持“持续 CPU 处理阻塞”是当前唯一根因。
3. 新日志中的 `rtsp_diag` 已能证明 push 成功率、flow 和 pipeline 销毁状态，但用户提供的实际运行日志仍为旧版简化字段，
尚未看到本地新代码中的完整 `window=10s`、`push_busy`、`encoder_output`、`rtp_packet` 等字段。
4. 因此稳定现象可以作为现场结果记录，但不能据此确认“本地最新源码已部署”。必须核对构建产物、部署版本和完整诊断字段。

在完成编译、二进制核对、至少 30 分钟实车回归和 `/ipm` 归因之前，本记录状态保持为：

```text
analysis/unverified
```

### 2.2 `ffprobe` 的作用：触发请求，不是修复 ZLMediaKit

现场现象是：ZLMediaKit 页面原本没有画面；执行：

```bash
ffprobe -rtsp_transport tcp rtsp://127.0.0.1:8554/cam_f_12
ffprobe -rtsp_transport tcp rtsp://127.0.0.1:8554/cam_b_18
```

后，ZLMediaKit 页面恢复播放。

这不能解释为“`ffprobe` 修复了 ZLMediaKit”。`ffprobe` 本身创建了一个新的
RTSP 客户端请求，可能触发或保持 ZLMediaKit 的按需拉流；这个请求又使车端
RTSP server 进入了正常的 `media-configure -> need-data -> push_data -> RTP`
路径。更准确的因果链是：

```text
ZLMediaKit 页面请求
  -> ZLMediaKit 按需请求车端 RTSP
  -> 车端首次请求没有完成媒体配置或供帧
  -> 页面无画面

ffprobe 创建新的 RTSP 请求
  -> 车端重新进入或完成媒体 pipeline
  -> 车端开始输出 RTP
  -> ZLMediaKit 后续播放恢复
```

因此下一步应记录车端是否收到第二次请求，以及第二次请求是否产生
`pipeline_configure`、`need_data` 和 `push_ok`；不应把“执行 `ffprobe` 后恢复”
当作 ZLMediaKit 的修复步骤。

## 3. OTel 提交不是纯埋点

对比当前分支中的 OTel 提交 `dc4ba11f2 (feat: otel)` 与其父提交
`3a49e024b`，`ztd_rtsp` 车端代码有大量运行路径变化。当前分支随后还包含
`3b22a6819 (fix: rtsp)` 和 `dd2b92982 (fix: cast)`。主要变化如下：

| 变化 | 是否影响运行行为 | 风险 |
|---|---:|---|
| 增加 header stamp、`GstReferenceTimestampMeta` 和延迟统计 | 是，改变 buffer metadata 和统计线程 | 中 |
| `ros2_image_callback()` 在检测到消费请求时立即调用 `push_data()` | 是，改变 push 调度模型 | 高 |
| 引入 `push_in_progress_`，并发调用时直接返回 | 是，可能丢失一次供给机会 | 高 |
| `push_data()` 先快照、释放锁，再复制和 `push-buffer` | 是，改变状态转移的原子性 | 高 |
| 对 appsrc、pipeline、media-configure 做引用和 weak callback 管理 | 是，改变 pipeline 生命周期 | 高 |
| 新增/调整 raw queue 和 encoded queue | 是，直接影响帧丢弃和 H.264 解码连续性 | 高 |
| 修改 crop/scale、编码器属性和参数持久化 | 是，影响 pipeline 配置 | 中 |
| 调整时间叠加和 RTP 扩展注入 | 是，但通常不是重拉首因 | 中 |

因此，正确的原则不是把 OTel 提交整体回退，而是以已稳定的旧版推流协议为基线，只保留经过确认的埋点和低风险 metadata。

### 3.1 当前现场日志对应的状态

在用户提供的 `ztd_rtsp_20260901101904.log` 中，启动后约 10 秒，
`/cam_f_12` 和 `/cam_b_18` 均出现类似状态：

```text
active=0
need_data=0
push_attempt=0
push_ok=0
pipeline_configure=0
pipeline_generation=0
callback=约 200
callback_skip=约 200
frame_generation=1
```

这组数据说明：

1. ROS 图像订阅仍然在收到数据。
2. 车端没有把这次首次拉流转换成有效的 RTSP media pipeline。
3. 没有发生 `media-configure`、`need-data` 或 `push_data`。
4. 因此当前证据指向车端 RTSP 请求/媒体初始化阶段，而不是编码后的 RTP
   解码质量，也不是 ZLMediaKit 页面本身。

日志中随后出现：

```text
grpc server changed to proxy 127.0.0.1 30035 ...
Failed to dial controller: Dial server(127.0.0.1 30035) failed
The Process exits due to signal Some(15).
```

这些是控制连接切换和进程重启事件，可能解释为什么之后状态重新初始化，但不能
替代对 RTSP 首次请求是否到达车端的确认。

### 3.2 最高概率的车端问题

现阶段最高优先级不是“ZLMediaKit 播放异常”，而是车端首次请求没有进入完整链路：

```text
RTSP request
  -> media-configure
  -> appsrc need-data
  -> push_data
  -> encoder
  -> RTP packet
```

需要优先验证两类代码风险：

1. **首次 media/configure 触发丢失**：新旧 media、appsrc 或 pipeline 交错时，
   stale appsrc 判断或生命周期回调可能丢弃了首次 `need-data`。
2. **push 状态转移竞态**：`need-data`、ROS callback 和周期 refresh 并发更新
   demand/frame 状态时，快照和清理动作可能互相覆盖，导致 pipeline 存在但没有
   后续 push。

编码后队列和 H.264 参考帧连续性是第二优先级，只有在车端已经有
`push_ok`、encoder output 和 RTP packet 后才进入该分支。

### 3.3 判断矩阵

```text
车端没有收到 RTSP 请求
  -> 检查请求是否到达车端、目标地址、路由和 8554 端口

收到请求但没有 media-configure
  -> 检查车端 RTSP path、factory 和 RTSP 协商流程

有 media-configure 但没有 need-data
  -> 检查 appsrc 连接、pipeline 状态和 stale appsrc 判断

有 need-data 但 push_attempt=0
  -> 检查 active/frame/demand 状态机和首次帧调度

有 push_attempt 但 push_ok=0
  -> 检查 GStreamer flow、appsrc 状态和 pipeline 状态

push_ok、encoder_output、rtp_packet 都正常
  -> 车端输出已恢复，再观察 ZLMediaKit 接收和前端播放
```

### 3.4 现场验证

以下命令用于确认车端是否真的收到拉流请求，不是修改或怀疑 ZLMediaKit：

```bash
sudo ss -lntp | grep 8554
sudo tcpdump -ni any 'tcp port 8554 or udp port 8554'
```

在 ZLMediaKit 所在环境分别测试 TCP/UDP：

```bash
ffprobe -rtsp_transport tcp rtsp://10.7.20.145:8554/cam_f_12
ffprobe -rtsp_transport udp rtsp://10.7.20.145:8554/cam_f_12
```

同时观察车端 `[rtsp_diag]`：

```text
首次页面请求：是否增加 pipeline_configure / need_data
ffprobe 请求：是否新增一次 configure / need_data / push_ok
push_ok 增长但页面无画面：车端已恢复，转观察 ZLMediaKit 接收和前端链路
```

## 4. 最高概率根因：push 状态竞态

旧版推流流程大体是一个连续状态转移：

```text
need-data
  -> 标记 gst_data_request_
  -> 选择最新 ROS 帧
  -> 构造 GstBuffer
  -> push-buffer
  -> 根据结果清理状态
```

OTel 版本将这条流程拆开：

```text
线程 A: 快照 gst_data_request_ / latest_image_ / appsrc
线程 A: 释放 mutex
线程 B: need-data 或 ROS callback 更新状态
线程 A: push-buffer
线程 A: 清理 gst_data_request_ / ros2_new_data_
```

其中有两个问题：

1. `push_in_progress_` 让另一次合法的 `push_data()` 直接返回。周期 `refresh()` 和 ROS callback 都可能触发 push，返回后没有独立的 pending 状态保证一定会再次调度。
2. 旧 push 的清理动作与新的 `need-data` 请求不是同一个原子事务。旧 push 完成时可能清掉新请求，造成 pipeline 仍然存在但不再持续供给；前端随后表现为卡住并重拉。

这与日志中的现象相符：处理耗时通常很低，但 client 连接会重新出现。问题更像是供给状态丢失或媒体被动恢复，而不是单纯 CPU 编码慢。

## 5. 第二个高风险点：encoded H.264 队列丢帧

OTel 版本曾将同一个 `leaky` queue 放在 `idH264` 之后。对 raw frame 丢旧帧通常是可接受的，但对已经编码的 H.264 帧丢弃 P-frame 可能破坏参考帧链：

```text
I-frame -> P-frame -> P-frame
              ^
        丢掉这里可能导致后续帧无法解码
```

解码端等到下一个可恢复的 IDR 前可能持续异常，云端或前端就可能重新拉流。

后续提交 `3b22a6819 (fix: rtsp)` 已将队列拆分为：

```text
raw queue:     leaky=downstream，允许丢旧 raw frame
encoded queue: 非 leaky，不主动丢 H.264 frame
```

这是必要修复，但必须确认实车部署的二进制确实包含该提交，而不是只部署了某个 OTel 镜像或旧构建产物。

## 6. 20 Hz 是否是根因

不是根因，更可能是放大因素。

20 Hz 会提高以下事件的交错频率：

```text
ROS image callback
GStreamer need-data
main loop refresh
media configure/destroy
```

如果状态转移本身没有串行化，20 Hz 更容易触发快照、push 和清理之间的竞态。把 `main_loop_hz` 改低只能降低触发概率，不能修复状态机；也可能增加供给间隔和端到端延迟。

当前建议先修正并发协议，再根据实车 CPU/网络情况选择合适的刷新频率。不要把“改成不是 20 Hz”当作根治方案。

## 7. 当前分支已包含的修改

当前分支相关代码涉及：

```text
aura/src/ztd/ztd_network/ztd_rtsp/include/ztd_rtsp/rtsp_stream.hpp
aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/rtsp_stream.cpp
```

`dc4ba11f2` 及后续 RTSP 修复提交中已包含的内容：

1. 删除 `push_in_progress_`，避免并发调用静默丢失。
2. `push_data()` 从检查 demand、选择 frame、构造 buffer、执行 `push-buffer` 到成功/失败清理，使用同一把 `mutex_` 串行化。
3. stale frame 或无效帧只清理当前帧状态，不在可能存在新 demand 时错误清除 `gst_data_request_`。
4. 保留延迟统计和 header stamp metadata，不改变正常播放时间戳。
5. 保留 raw queue 可丢旧帧、encoded queue 不丢 H.264 帧的队列拓扑。
6. 保留 pipeline 的 weak callback、旧 appsrc 过滤和销毁清理逻辑。
7. 增加低频诊断计数和有界时序摘要，避免现场只能从 latency 日志猜测：

```text
need_data
push_attempt
push_ok
flow_flushing
flow_error
stale_drop
pipeline_configure
pipeline_destroy
```

每路每 10 秒输出一次累计值：

```text
[rtsp_diag] /cam_xxx window=10s active=... need_data=...
push_attempt=... push_ok=... push_busy=... push_bytes=...
flow_ok=... flow_flushing=... flow_error=...
pipeline_configure=... pipeline_configure_error=...
pipeline_destroy=... pipeline_replace=... factory_error=...
encoder_output=... keyframe=... rtp_packet=... rtp_bytes=...
```

这些计数用于区分：

```text
need_data 增加但 push_ok 不增加      -> push 路径或 frame 状态问题
flow_flushing 增加                    -> client/pipeline 正在断开或 flush
flow_error 增加                       -> GStreamer flow 错误
pipeline_configure/destroy 成对增加   -> media 反复创建和销毁
pipeline configure 增加而 destroy 少  -> 生命周期或回调清理异常
```

当前本地代码还覆盖以下车端 RTSP 观测点：

| 阶段 | 已记录内容 |
|---|---|
| ROS 图像 callback | callback 次数、跳过、空帧、非法时间戳、帧年龄、callback 间隔 |
| appsrc demand | `need-data` 次数、旧 appsrc 回调、最近 demand 年龄、demand 到 push 间隔 |
| push 准备 | appsrc 不可用、旧帧丢弃、非法 payload、不支持编码、GstBuffer alloc/map 失败 |
| push 执行 | attempt/success/busy/bytes、buffer alloc/map/copy/push-buffer/push_data 耗时 |
| GStreamer flow | `OK`、`FLUSHING`、`EOS`、`NOT_LINKED`、`NOT_NEGOTIATED`、其他 error、异常 |
| pipeline 生命周期 | configure、configure error、replace、destroy、当前 pipeline generation |
| 编码与 RTP | encoder output、关键帧、缺失 capture timestamp、RTP packet/bytes、缺失 timestamp、encoder/RTP/clock-overlay probe 安装失败 |
| GStreamer bus | ERROR、WARNING、EOS、bus 不可用 |

输出类型为 `[latency_1s]`、`[rtsp_diag]`、`[rtsp_timing]` 和 `[gst_bus]`。
其中帧级路径只累计有界窗口和原子计数，不在每帧打印日志；RTP 自定义 timestamp extension
仅在显式 debug 模式启用，普通模式不改变标准 RTP 行为。

另外，server 级别每 10 秒输出一次 `[rtsp_server_diag]`，覆盖：

```text
raw/compressed callback
compressed convert error
stream init attempt/success/error
subscription error
RTSP attach/refresh success/error
video reconfig success/error/not-found
bitrate update success/error
```

初始化失败边界也已纳入诊断：`main_loop_hz` 非 finite 或小于等于 0 时记录错误并回退到
`10.0 Hz`；GStreamer RTSP server attach 失败时立即清理并退出，不再进入无效主循环；
mount points 或 media factory 创建失败时记录 `factory_error`。

当前已通过：

```bash
cd /Users/minyi/workspace/autodrive/aura
git diff --check
```

尚未完成：

```bash
colcon build --packages-select ztd_rtsp
```

也尚未完成目标车辆的长时间实车验证。

本次开发机检查未发现 `colcon`、`cmake`、`pkg-config`，因此本轮不能声称 `ztd_rtsp`
已经在当前环境构建通过。最新现场日志证明的是“前端现象暂时稳定”和“旧版诊断字段的
push/pipeline 状态正常”，不是本地最新源码已完成部署验证。

当前源码埋点覆盖状态：`implemented`。
目标车重新构建、部署版本核对和长时间实车回归状态：`unverified`。

## 8. 车端 WebRTC 链路埋点

由于车端 `src/vehicle` 同时包含 `VehicleRtspServer` 和
`VehicleWebRtcServer`，仅有 RTSP server 的计数不能覆盖车端到 WebRTC
消费者的完整路径。本次又在：

```text
aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/webrtc_server_node.cpp
```

增加了低频诊断，不改变现有 lazy start、解码选择、队列丢帧策略或 reset
行为。每 10 秒输出：

```text
[webrtc_server_diag]
[webrtc_diag] <camera>
```

覆盖内容：

| 阶段 | 已记录内容 |
|---|---|
| pipeline 初始化 | parse attempt/success/error、元素查找失败、PLAYING 设置 attempt/success/error |
| RTSP 输入 | `rtspsrc` pad-added、输入 buffer/bytes、缺失 PTS、输入 probe 安装失败 |
| 解码后媒体输出 | 进入 WebRTC 前 queue 的 buffer/bytes、缺失 PTS、媒体 probe 安装失败 |
| WebRTC consumer | consumer added/removed、当前 active consumer、异常 remove |
| GStreamer bus | ERROR、WARNING、EOS、pipeline state changed |
| reset | reset 次数、reset error、reset 总耗时 |

诊断字段的解释：

```text
source_buffer=0 且 active_consumers>0
  -> RTSP source 没有持续收到媒体，优先查车端 RTSP 输入或上游服务

source_buffer 持续增长但 media_buffer=0
  -> 解码、协商、queue 或硬件解码链路异常

media_buffer 持续增长但 consumer_added=0
  -> WebRTC 没有消费者，属于访问/信令侧状态，不应误判为车端断流

bus_error/bus_eos/reset 持续增长
  -> 车端 WebRTC pipeline 正在被动重启，需要结合具体 GST ERROR/WARNING 日志
```

因此现在“车端埋点”覆盖两条车端媒体链路：

```text
ROS image -> VehicleRtspServer -> appsrc -> encoder -> RTSP
RTSP -> VehicleWebRtcServer -> decode/raw queue -> webrtcsink -> consumer
```

该部分同样只完成源码和静态检查，尚未在目标车辆完成构建产物核对及长时间
实车回归，状态仍为 `analysis/unverified`。

## 9. 第二阶段可选优化

如果第一阶段修复后仍有重拉，再把布尔 flag 状态升级为带代次的状态机。推荐至少增加：

```text
frame_seq       每次收到 ROS 帧递增
demand_seq      每次 need-data 递增
push_pending    是否还有未满足的 demand
active_appsrc   当前 appsrc 的身份或 generation
```

目标是不依赖“一个布尔值同时表示 demand、frame 和 pipeline 状态”：

```text
need-data(demand_seq++)
ROS frame(frame_seq++)
push(frame_seq, demand_seq)
只完成对应代次的状态
旧 appsrc 不能清理新 appsrc 的状态
```

这个改动需要配合单元测试或可重复的 GStreamer 集成测试，不能直接在实车上盲改。

## 10. 参数核验

车上部署后先确认实际参数和实际节点名称：

```bash
ros2 param get /vehicle/network/video/VehicleRtspServer inactivity_timeout
ros2 param get /vehicle/network/video/VehicleRtspServer main_loop_hz
ros2 param get /vehicle/network/video/VehicleRtspServer max_frame_age_ms
```

当前配置中需要特别关注：

```text
inactivity_timeout: 默认代码值 3 秒；配置文件可能覆盖为 60 秒
main_loop_hz:       默认代码值 10 Hz；配置文件可能覆盖为 12 Hz
max_frame_age_ms:   默认代码值 0；配置文件可能覆盖为 500 ms
```

若实车使用 `max_frame_age_ms=500`，应同时观察 `stale_drop`。如果该值持续增长，说明输入帧年龄已经超过阈值，但它本身不应导致 client 重拉；代码应继续等待新帧。

## 11. 验收标准

### 必须通过

1. 编译 `ztd_rtsp` 成功，且部署的二进制来自当前修复后的源码。
2. 至少连续 30 分钟实车测试。
3. 前端不再持续显示重拉。
4. 同一路不反复出现 `Client connected`。
5. `push_ok` 持续增长，且与 `push_attempt` 基本一致。
6. `flow_error` 不持续增长。
7. `pipeline_configure` 和 `pipeline_destroy` 不出现异常高频增长。

### 需要记录

```text
车辆 ID、软件构建版本、git commit
每一路图像实际频率
实际 main_loop_hz/inactivity_timeout/max_frame_age_ms
重拉发生时间
重拉前后对应路的 rtsp_diag 计数
是否同时有网络切换、ZLMediaKit 重启或浏览器切页
```

### 判定方式

若 `pipeline_configure/destroy` 与前端重拉同步增长，优先继续查媒体生命周期。

若 pipeline 没有重建但 `need_data` 增长、`push_ok` 停止，优先查 push 状态机。

若 `flow_error` 增长，记录具体 flow code，并检查编码后队列、H.264 IDR/SPS/PPS 和下游读取速度。

若车端计数稳定而前端仍重拉，才进入 ZLMediaKit 接收、WebRTC 或网络链路的
联调；这不改变当前“ZLMediaKit 未修改、首要问题在车端首次 RTSP 拉流路径”的结论。

## 12. 与其他错误的边界

之前出现的：

```text
POST /api/parallel-driving/takeover
400 Bad Request
io.lettuce.core.output.ValueOutput does not support set(long)
```

属于控制面/Redis 客户端问题，不是本专题的 RTSP 车端数据面证据。本次不修改 Operator 或 takeover 逻辑；该错误应由对应后端服务单独记录和修复。
