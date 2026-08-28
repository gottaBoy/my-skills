# 04 前端黑屏与本地可观测性

更新时间：`2026-08-27`

## 已完成的黑屏风险修复

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>风险</th><th>修复</th><th>是否会造成不合理重载</th></tr></thead>
  <tbody>
    <tr><td><code>internalCode</code> 短暂为空</td><td>首次有效 app 锁定，后续缺失值保留有效值</td><td>不会因瞬时空值清空多路播放器</td></tr>
    <tr><td>旧车辆/旧请求响应覆盖当前源</td><td>请求代际、车辆 ID、路由 ID 校验</td><td>旧响应不能污染当前播放源</td></tr>
    <tr><td>轮询发现编码变化</td><td>只记录 source identity 变化；明确播放身份变化才重建</td><td>普通动态值变化不会触发 reload</td></tr>
    <tr><td>多播放器共享流重连竞争</td><td>shared session、leader/refCount、共享重连</td><td>避免同流重复建链和重连风暴</td></tr>
    <tr><td>慢 <code>getStats()</code> 重叠</td><td>每实例 in-flight 门禁</td><td>不会因 stats 定时器堆积触发视频重载</td></tr>
    <tr><td>不可见页面误判 render stall</td><td>render eligibility、采样断档重置</td><td>隐藏 Tab、HMR、休眠不直接触发重连</td></tr>
    <tr><td>VideoToolbox 反复切换</td><td>freeze 后最多一次 VP8 尝试，带冷却和会话保护</td><td>避免 decoder 检测造成循环重建</td></tr>
  </tbody>
</table>

## 黑屏分类

```text
S0_NOT_MOUNTED       未挂载或 app/stream 为空
S1_SIGNAL_FAILED     WebRTC HTTP/业务 code/msg/网络失败
S2_STREAM_NOT_FOUND  ZLMediaKit 没有 app/stream
S3_ICE_FAILED        SDP 成功但 ICE/DTLS 不可用
S4_RTP_STALLED       Peer 正常但 inbound RTP 不增长
S5_RENDER_STALLED    RTP 增长但没有新渲染帧
S6_DECODER_FREEZE    解码器冻结
S7_SOURCE_REPLACED   播放身份发生变化并重建
S8_UI_OBSCURED       有帧但被布局、遮罩或组件状态遮挡
```

## 黑屏与卡顿的判定边界

前端不能只根据一个字段准确判断“用户看到的画面是否为黑色”。当前实现判断的是
WebRTC 媒体链路和浏览器视频管线是否仍然产生、解码和呈现视频帧。因此“黑屏”应拆成
以下几类：

| 用户现象或故障 | 前端可观测证据 | 当前结论能力 |
|---|---|---|
| 信令失败、流不存在、ICE 失败 | ZLMediaKit HTTP/code/msg、PeerConnection、ICE 状态 | 高；可以定位到信令、流注册或媒体连接阶段 |
| 已收到 track 但长时间没有首帧 | `ontrack`、`readyState`、`playing/timeupdate`、首帧超时 | 较高；当前首帧等待超过 10 秒标记 `no_first_frame` |
| 连接正常但 RTP 停止进入 | `peer_state/ice_state` 正常，`inbound_bytes_delta` 连续为零 | 较高；优先指向车端推流、ZLMediaKit 输入或媒体网络 |
| RTP 仍在进入但解码停止 | RTP 字节增长，`frames_decoded` 不增长 | 较高；优先指向浏览器解码器或编码参数 |
| 已解码但页面没有新帧 | `requestVideoFrameCallback` 无新帧，且页面可见、元素可渲染 | 较高；优先指向解码/渲染管线或主线程 |
| 摄像头真实拍到黑色场景 | 视频仍持续出帧 | 当前不能区分；会被视为健康视频 |
| 已显示黑帧但后续仍有新帧 | 帧时序正常，像素内容异常 | 当前不能判断；没有视频像素分析 |

因此当前的“黑屏”不是视觉像素结论，而是“没有首帧、媒体断流、解码冻结、渲染冻结、
连接失败或 UI 遮挡”等可观测故障的统称。黑屏分类必须带上 `document_hidden`、
`video_render_eligible`、`stats_sample_gap_ms` 等上下文，不能只看最后一条
`healthy`、`freezeCount` 或单个 NACK 值。

### 当前卡顿判定

卡顿需要区分“收流卡”和“画面卡”：

1. **收流卡**：Peer/ICE 仍正常，且该播放器曾经收到过 RTP，但 `inbound_bytes_delta`
   连续不增长。远控快恢复模式约 3 秒显示收流停滞，普通模式约 5 秒显示；它说明媒体
   数据没有继续进入，不等同于已经证明用户画面冻结。
2. **画面卡**：页面可见、视频元素可渲染、采样连续、RTP 仍在增长，但
   `frames_decoded` 不增长且 `requestVideoFrameCallback` 超过阈值没有新帧。远控快恢复
   模式阈值为 5 秒，普通模式为 10 秒。
3. **解码冻结**：在画面卡的基础上，浏览器报告 `freezeCount` 或检测到
   VideoToolbox 冻结，归类为 `decoder_freeze`。

当前判定对“持续数秒的断流或冻结”有效，但以下情况不能保证捕获：

- 200ms 至数秒的短时卡顿、帧间隔抖动和 GOP 等待；
- FPS 降低但仍持续出帧；
- RTP 和解码帧都增长，但画面内容重复或摄像头输出异常；
- 页面不可见、系统休眠、HMR 或主线程长任务期间的渲染停顿；
- 非 WebRTC 的 `Player` 播放路径。

### 现场分析顺序

遇到黑屏或卡顿时，按同一路 `camera + stream + playerInstanceId` 保存事件序列，并按
以下顺序排查：

```text
1. 页面上下文：
   document_hidden、video_render_eligible、video_ready_state、video_paused、
   stats_sample_gap_ms
2. 信令和连接：
   signal_phase、signal_attempt、zlm_http_status、zlm_code、zlm_message、
   peer_state、ice_state
3. 媒体输入：
   inbound_bytes_delta、inbound_bytes_received、inbound_zero_streak、
   loss_percent、rtt_ms、jitter_ms、nack_count、pli_count
4. 解码：
   frames_decoded、decoded_frames_delta、freeze_count、decoder
5. 页面呈现：
   last_frame_age_ms、render_stall_candidate_ms、requestVideoFrameCallback、
   video_render_eligible
6. 车辆和业务上下文：
   vehicle_id、app、stream、effective_stream、video_source_identity
```

推荐使用组合证据，而不是二值判断：

| 组合证据 | 建议结论 |
|---|---|
| 页面可见 + Peer/ICE failed | 已确认媒体连接失败 |
| Peer/ICE 正常 + RTP 长时间不增长 | 已确认收流停滞，查上游推流或媒体网络 |
| RTP 增长 + `frames_decoded` 不增长 + 长时间无新呈现帧 | 高置信度解码/渲染冻结 |
| `frames_decoded` 增长 + `last_frame_age_ms` 增大且元素不可渲染 | 高置信度 UI/布局遮挡或页面呈现问题 |
| 仅 NACK、PLI、丢包升高 | 只能记录网络风险，不能单独判定黑屏或卡顿 |
| `document_hidden=true` 或采样间隔异常 | 暂不下结论，等待页面恢复可见并重新采样 |

### 后续提高准确性的方向

如果产品必须识别“视觉黑屏”，可以在页面可见且已经确认出帧后低频采样视频画面：

1. 使用 `canvas` 每 500ms 至 1s 采样少量像素，计算低亮度像素占比和画面方差；
2. 只有在连续多个采样窗口都接近全黑，且视频帧时间仍在推进时，才标记
   `suspected_black_frame`；
3. 与 `frames_decoded`、`requestVideoFrameCallback`、页面可见性联合，避免把“没有新帧”
   和“新帧内容是黑色”混为一类；
4. 该信号只能是辅助判断。夜景、遮挡、镜头盖住和车辆进入黑暗环境都可能是真实黑画面，
   不能仅凭像素黑度触发重连或控制动作。

如果产品必须识别短时卡顿，应从 `requestVideoFrameCallback` 记录帧间隔，计算窗口内
的 `avg/p95/max frame gap`、有效 FPS 和连续超时次数，并结合 `frames_decoded`、
`frames_dropped`、RTP 字节增量和页面长任务数据，分别输出：

```text
healthy
degraded_frame_pacing   帧仍在出，但间隔或 FPS 恶化
suspected_stall         多个证据指向卡顿，尚未达到确认阈值
confirmed_stall         连续窗口无新帧或解码冻结
```

阈值应按摄像头目标帧率、编码 GOP、网络环境和远控安全要求通过现场数据标定，不能把
单一的 RTT、NACK、丢包率或 freezeCount 当作通用黑屏阈值。

## 当前本地埋点

```text
WebRtcPlayer / VideoCell / VehicleRemoteDeck
  -> recordParallelDrivingObservation
  -> 诊断采集开启时：最多 500 条环形缓存 + parallel-driving-observation CustomEvent
```

已经记录 WebRTC 信令、ZLM code/msg、ontrack、首帧、ICE、RTP、
`framesDecoded`、FPS、码率、丢包、RTT、jitter、PLI、NACK、freeze、
render/inbound stall、恢复、页面可见性、readyState、paused 和渲染资格。
这些字段足以支持链路、收流、解码和渲染层的故障归因，但不等于已经具备视频像素级黑屏
识别或所有短时卡顿的检测能力。

## 诊断采集开关

诊断采集默认关闭，且不写入 `localStorage`；刷新页面会恢复为关闭状态。
“离开远控页面后自动关闭”是设计目标，当前组件卸载时尚未统一调用关闭开关，仍需补充
生命周期处理；在此之前现场排查结束应手动关闭采集。
远控工作台和车辆详情页控制条都有“诊断采集”开关。

现场操作顺序：

1. 平时保持“诊断采集”为“关”。
2. 准备复现黑屏或卡顿前，打开浏览器控制台监听器。
3. 点击页面控制条中的“诊断采集”开关，切换为“开”。开启时会清空旧的 500 条缓存，并
   生成新的本地观测会话。
4. 复现问题，保存同一路 `camera + stream + playerInstanceId` 的事件序列。
5. 复现结束后先移除控制台监听器，再关闭“诊断采集”。关闭时会停止后续诊断事件的缓存和
   `CustomEvent` 派发，并清空本地缓存。

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

排查结束后执行：

```javascript
window.removeEventListener(
  'parallel-driving-observation',
  window.__pdObsHandler,
)
delete window.__pdObsHandler
```

如果需要查看全部事件，可以暂时使用：

```javascript
window.__pdObsHandler = (event) => {
  console.info('[parallel-driving-observation]', event.detail)
}
window.addEventListener(
  'parallel-driving-observation',
  window.__pdObsHandler,
)
```

`window.addEventListener` 只接收监听器注册之后的新事件，不会读取之前的缓存。前端代码或自动化
测试可通过 `getParallelDrivingObservationSnapshot()` 获取当前缓存，并在测试结束后调用
`clearParallelDrivingObservationBuffer()`。

该开关只控制诊断观测出口，不影响视频播放、WebRTC `getStats()`、RTP/解码/渲染健康检测、
卡顿判定、自动恢复、状态 WebSocket 或远控指令。

## 前端现场应重点观察的字段

当前 `video_health_change` 事件已经包含黑屏和卡顿归因所需的主要字段，包括共享 WebRTC
会话字段。`sessionId`、车辆和摄像头等是事件顶层上下文，媒体诊断指标位于
`details`。现场排查时，
优先保存同一路 `camera + stream + playerInstanceId` 的事件序列，不要只看最后一条
`healthy` 或单个 `freezeCount`。

### 1. 事件上下文

```text
event
occurredAt
observedAtPerfMs
sequence
sessionId
vehicleId
cockpitId
camera
app
stream
protocol
reason
result
durationMs
```

### 2. 播放身份

```text
playerInstanceId
effectiveStream
sharedSessionId
sharedSessionRefCount
sharedLeader
```

这些字段用于确认“看的是否还是同一辆车、同一路摄像头和同一个播放器”。身份变化时，
优先结合 `video_source_identity` 判断是否发生了合法换流或旧响应污染。

### 3. 信令、建链和首帧

```text
loading
error
peerState
iceState
signalAttempt
signalPhase
reconnectAttempt
zlmHttpStatus
zlmCode
zlmMessage
negotiationDurationMs
trackToFirstFrameMs
```

判定重点：

| 观察结果 | 主要归因 |
|---|---|
| `signalPhase` 未到 `response_received`，且有 HTTP/网络错误 | 信令失败、CORS、混合内容或 ZLM 接口不可达 |
| ZLM 返回流不存在 | `S2_STREAM_NOT_FOUND`，检查车端推流和 app/stream |
| SDP/`track_received` 成功但 `trackToFirstFrameMs` 持续为空 | 首帧未出，继续区分 RTP、解码和渲染 |
| `peerState`/`iceState` 为 `failed` | `S3_ICE_FAILED` 或媒体网络不可达 |

### 4. RTP 入流和网络质量

```text
inboundBytesDelta
inboundBytesReceived
inboundZeroStreak
statsSampleGapMs
fps
bitrateKbps
lossPercent
rttMs
jitterMs
pliCount
nackCount
```

判定重点：

| 观察结果 | 主要归因 |
|---|---|
| Peer/ICE 正常，但 `inboundBytesDelta` 持续接近 0，`inboundZeroStreak` 增长 | `S4_RTP_STALLED`，优先查车端编码、RTP、ZLM 或媒体网络 |
| `lossPercent`、`jitterMs`、`rttMs`、`nackCount` 同时升高 | 弱网、丢包、拥塞或路径抖动 |
| `pliCount` 持续升高但仍有入流 | 关键帧请求/丢参考帧恢复压力，不能单独判定黑屏 |
| `statsSampleGapMs` 异常变大 | 浏览器休眠、隐藏 Tab、主线程阻塞或 `getStats()` 变慢，不能直接当作视频卡顿 |

### 5. 解码和实际渲染

```text
decodedFramesDelta
lastFrameAgeMs
renderStallCandidateMs
renderStallThresholdMs
freezeCount
decoder
videoReadyState
videoPaused
videoRenderEligible
rvfcMonitoring
documentHidden
```

判定重点：

| 观察结果 | 主要归因 |
|---|---|
| RTP 字节仍在增长，`decodedFramesDelta == 0`，`lastFrameAgeMs` 增长，且 `videoRenderEligible == true` | `S5_RENDER_STALLED` 候选 |
| `freezeCount` 增长，`decoder` 显示 VideoToolbox，且伴随丢包/PLI | `S6_DECODER_FREEZE`，重点排查硬解和参考帧恢复 |
| `videoPaused == true` 或 `videoReadyState` 不足 | 播放元素状态问题，先确认是否调用 `play()` 和是否有首帧 |
| `videoRenderEligible == false` 或 `documentHidden == true` | 不应判定为解码冻结，可能是隐藏 Tab、布局或页面状态 |
| `rvfcMonitoring == true` 但 `lastFrameAgeMs` 持续增长 | 有视频帧回调监控，但实际没有新呈现帧 |

### 页面隐藏期间的指标口径与恢复保护

`documentHidden == true` 时，浏览器可能暂停或降频调度
`requestVideoFrameCallback`、`getStats()` 和页面定时器。此时即使 RTP 仍在接收、解码帧仍在
增长，`lastFrameAgeMs` 也可能被旧的呈现时间撑大到几十秒，`statsSampleGapMs` 也可能明显
超过正常采样周期。

因此当前实现采用以下规则：

1. 页面隐藏或视频元素不可渲染时，`lastFrameAgeMs` 输出为 `null`，不把旧呈现时间解释成
   实时视频延迟。
2. 采样间隔超过正常周期时，清零本次 `inboundZeroStreak`，不让浏览器休眠、隐藏 Tab 或
   主线程长任务触发 `S4_RTP_STALLED` 重连。
3. `render_stall` 继续要求 `videoRenderEligible == true`、页面可见、采样连续且
   `decodedFramesDelta == 0`；隐藏页面不会触发渲染重连。
4. VideoToolbox 的 VP8 规避重连也要求页面可见、视频可渲染且采样连续，避免把后台期间
   浏览器累计的 `freezeCount` 当成真实解码冻结。
5. 页面恢复可见时仍调用 `video.play()`，并重新建立可见渲染观测窗口；这些改动只收紧误判
   和恢复触发条件，不停止 WebRTC、RTP、解码或视频播放。

实时远控页面的优先级是“先保证画面连续，再做诊断”。任何诊断缓存、事件监听器、控制台
输出或后续 Exporter 异常都不得调用 `stop()`、`softStop()`、`scheduleReconnect()`，也不得
改变黑屏判定。真正可见页面中的 RTP 停止、ICE 失败或持续渲染冻结仍保留原有自动恢复路径。

#### 2026-08-26 WebRTC 日志分析

本次采集涉及 `cam_rb_10`、`cam_f_7`、`cam_lb_4`、`cam_f_12`、`cam_b_18` 和 `ipm` 六路流。
`WebRTC shared` 日志中的 `sharedLeader`、`sharedRefCount` 和 `sharedSessionId` 表明同一
流的播放器正在复用共享 PeerConnection；例如 `cam_f_12` 和 `cam_b_18` 的引用数为 `2`，
属于预期行为，不是重复建链错误。

页面可见时，各路均满足 `peer_state=connected`、`ice_state=connected`、
`video_ready_state=4`、`video_paused=false`，并且 `last_frame_age_ms` 约为
`24~90ms`。可见时丢包率大多约 `0.3%~1.9%`，RTT 约 `31~56ms`，jitter 约
`4~9ms`，说明当前没有持续性的 WebRTC 断链或视频卡死。

`14:13:12` 至 `14:14:42` 的样本中 `document_hidden=true`，期间
`last_frame_age_ms` 从约 `2.6s` 增长到约 `92s`，但 `inbound_bytes_delta` 和
`decoded_frames_delta` 仍持续大于零，且 Peer/ICE 仍为 connected。该几十秒数值是后台页面
导致的渲染/采样观测失真，不能作为车端视频延迟或真实黑屏证据。页面恢复后各路年龄回到
`6~90ms`，进一步支持该结论。

隐藏期间 `freezeCount` 和 `freeze_total_s` 也持续增长，不能单独据此判定真实冻结；应结合
`documentHidden`、`videoRenderEligible`、`statsSampleGapMs`、`decodedFramesDelta` 和
`inboundBytesDelta`。`ipm` 和 `cam_b_18` 在可见阶段曾出现约 `5.6%~9.4%` 的短时丢包和
NACK 增长，但随后恢复到约 `1.6%~1.9%`，目前更符合短时网络波动，而非持续故障。

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

#### 首次打开页面后立即再次加载

首次打开时，车辆数据、在线状态和 `internalCode` 可能在不同的 Vue 更新周期内到达。
旧逻辑的 `source` watcher 在首次 `immediate` 回调中也会先执行 `stop()`，再执行 `play()`；
当 `app` 从空值变成有效值，或视频区刚完成挂载时，这会把“首次启动”表现成“刚出画又重载”。
这属于前端初始化竞态，不是 `sharedRefCount=2` 或同流双播放器本身异常。

当前播放器按以下规则处理：

1. 首次 source watcher 只安排一次错峰 `play()`，不对尚未建立的播放器执行无意义 `stop()`。
2. 已有有效播放或正在协商时，只有真实的 `baseUrl/app/stream` 变化才执行
   `stop() -> play()`。
3. 每次播放有独立的 generation；source 变化、手动重试或销毁时，旧 generation 立即失效，
   关闭待协商的 PeerConnection，并取消等待 `ontrack` 的旧流程。
4. 过期的 SDP 响应、旧连接或旧状态事件不能绑定当前 `<video>`，也不能覆盖当前错误和健康状态。
5. 同一个连接的重复 `bind` 只重新确保 `srcObject` 和 `video.play()`，不重复启动统计和首帧计时。

现场判断是否真的发生了首次重复重载，应按同一个 `playerInstanceId` 对齐
`video_source_identity`、`acquire`、`bind`、`signalAttempt` 和 `reconnectAttempt`：

```text
首次正常：source_identity -> acquire -> bind -> first_frame
真实换流：source_identity(变化) -> release/stop -> acquire(新 sharedSessionId)
初始化竞态：同一 source_identity 在首帧前出现 stop/acquire，或旧 generation 的响应晚于新 generation
```

只看到同一 `sharedSessionId` 下 `sharedRefCount=2` 的 `acquire/bind`，不能判定重载；
这通常表示同一路流的两个 `<WebRtcPlayer>` 正在共享同一个 PeerConnection。

### 6. 恢复和组件竞争

```text
lastRecoveryHint
reconnectAttempt
sharedSessionId
sharedSessionRefCount
sharedLeader
```

用来判断是否发生自动重拉、同流共享连接竞争或重连循环。`RECOVERING` 只表示恢复动作
已经开始，不表示视频已经恢复；必须等待新的 `signalPhase: first_frame` 或 `healthy` 事件。

### 黑屏/卡顿最小取证组合

现场至少同时保存以下字段：

```text
occurredAt, observedAtPerfMs, sequence
sessionId, vehicleId, cockpitId, camera, app, stream, protocol
reason, result, durationMs
playerInstanceId, effectiveStream, sharedSessionId, sharedSessionRefCount, sharedLeader
error
peerState, iceState, signalPhase
trackToFirstFrameMs
inboundBytesDelta, inboundZeroStreak, statsSampleGapMs
decodedFramesDelta, lastFrameAgeMs, renderStallCandidateMs
videoReadyState, videoPaused, videoRenderEligible, rvfcMonitoring, documentHidden
fps, bitrateKbps, lossPercent, rttMs, jitterMs
freezeCount, pliCount, nackCount, decoder
reconnectAttempt, lastRecoveryHint
```

不要把 `status_ws_last_message_age` 当作视频延迟。它只表示状态 WebSocket 最近一条消息
距浏览器本地检查时刻的年龄；可作为“页面和状态链仍活跃”的旁证，不能证明视频 RTP、
解码或渲染正常。

本地监听方式：

```javascript
window.addEventListener('parallel-driving-observation', event => {
  const detail = event.detail
  if (
    detail.event === 'video_health_change' &&
    ['S4_RTP_STALLED', 'S5_RENDER_STALLED', 'S6_DECODER_FREEZE', 'RECOVERING']
      .includes(detail.reason ?? '')
  ) {
    console.info('[parallel-driving-observation]', detail)
  }
})
```

采集开启时只写固定容量缓存并同步派发 CustomEvent，不产生网络请求或额外线程；状态 WebSocket
的“最近消息年龄”10 秒检查定时器也只在采集开启时运行。关闭时观测出口直接返回，不写缓存、
不读取 `performance.now()`、不派发事件，并停止该观测定时器。监听器、控制台打印、未来
Exporter 或 Gateway 失败都不得触发视频 reload、WebRTC reconnect 或参与黑屏判定。多路视频
现场不要长期无过滤打印全部事件。

## 尚未完成

1. 实际生成和传播 `traceId/spanId/parentSpanId/correlationId`。
2. 信令 HTTP `traceparent`、WebSocket `correlationId`。
3. OTel/RUM Exporter、Telemetry Gateway、Collector、DeepFlow Dashboard。
4. `getStats()` 慢调用、换车、隐藏 Tab、HMR、多路共享、真实黑屏和短时卡顿 Playwright 回归。
5. 采集开启/关闭时的 CPU、内存、长任务、首帧和重连次数对照。
6. Vue `default slot` 非函数告警治理；该告警目前不是黑屏根因。
7. 视觉黑帧辅助采样和 RVFC 帧间隔指标的阈值标定；在完成现场验证前不得作为自动重连依据。

详细字段和测试场景见[完整设计基线第 9.1.2 节和第 10 节](../full-link-observability.md#912-前端-otelrum-与-deepflow-接入设计)。
