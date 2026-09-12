# 0818 PD Test 分支 IPM FPS 波动分析记录

分析日期：`2026-09-11`

日志时间：`2026-09-11 21:52` 左右

分支：`feature/llm-on-vehicle-0818-pd-test`

HEAD：`826c75d62 关闭日志和debug的图片的保存`

状态：`analysis/unverified`

本记录只基于本批日志和当前分支代码完成分析，没有修改业务代码，也没有完成目标车辆上的编译、部署和实车回归。

## 1. 日志范围

- `/Users/minyi/Downloads/cam18_20260911215230.log`
- `/Users/minyi/Downloads/cam10_20260911215230.log`
- `/Users/minyi/Downloads/cam7_20260911215229.log`
- `/Users/minyi/Downloads/cam4_20260911215229.log`
- `/Users/minyi/Downloads/cam13_20260911215230.log`
- `/Users/minyi/Downloads/cam12_20260911215230.log`
- `/Users/minyi/Downloads/cam11_20260911215230.log`
- `/Users/minyi/Downloads/camera_merge_20260911215229.log`
- `/Users/minyi/Downloads/ztd_rtsp_20260911215230.log`

## 2. 结论

本批次的 IPM 问题首先表现为**上游生成频率低且有明显抖动**，不是
`ztd_rtsp` 编码、网络或 RTSP pipeline 推送失败。

从 `/ipm` 的 RTSP 诊断窗口统计：

```text
诊断窗口              43
有客户端的窗口          38
callback               2210
callback_skip           226
need_data              1983
push_attempt           1982
push_ok                1982
push_busy                 7
stale_drop                0
flow_error                0
pipeline_configure        1
pipeline_destroy          0
```

按有客户端的约 `38 * 10s` 统计，`/ipm` 实际推送约为：

```text
1982 / 380s = 5.22 FPS
```

同时，普通相机在相同 `ztd_rtsp` 进程中的累计帧数接近 20 FPS：

```text
cam_f_12   7776 frames
cam_b_18   7764 frames
cam_rb_10  7805 frames
cam_f_7    7559 frames
cam_lb_4   7783 frames
```

因此本批次的故障边界可以确定为：

```text
三路相机仍能采集
    -> IPM 使用 compressed 输入并做三路同步、解码、投影和融合
    -> /ipm 只产生约 5.22 FPS
    -> ztd_rtsp 对已经到达的 IPM 帧正常 push
```

`ztd_rtsp` 日志没有出现本批次上一轮分析中的 `stale_drop`、pipeline 重建或
推流状态被清除现象，不能把上一批日志的 RTSP stale-demand 结论带入本批次。

## 3. IPM 直接证据

### 3.1 RTSP 已经收到低频 IPM，而不是主动丢帧

典型 10 秒窗口：

- [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260911215230.log:694)
  记录 `callback=55`、`push_attempt=53`、`push_ok=53`、`stale_drop=0`。
- [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260911215230.log:3528)
  记录 `callback=54`、`push_attempt=54`、`push_ok=54`、`stale_drop=0`。
- [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260911215230.log:4711)
  记录 `callback=43`、`push_attempt=43`、`push_ok=43`，只有一次
  `push_busy`，没有 `flow_error`。
- [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260911215230.log:5064)
  记录 `callback=50`、`push_attempt=50`、`push_ok=50`，`push_data` 最大值
  只有 `1ms`。

这些窗口的共同特征是：

```text
callback_age        约 140~220ms
callback_gap P50    约 106~203ms
callback_gap P90    约 286~547ms
最大 callback_gap   约 1.3s
push_data           通常 0~1ms
stale_drop          0
flow_error          0
```

`callback_gap` 已经反映出 IPM 帧到达 RTSP 的间隔不稳定；而 `push_data` 基本
不耗时，说明 RTSP 没有把稳定输入处理成低 FPS，RTSP 看到的就是低频、抖动的
上游输入。

### 3.2 普通相机对照

普通相机的累计帧数约为 `7.5k~7.8k`，对应约 20 FPS。普通相机与 IPM 共用
`ztd_rtsp` 进程，但只有 IPM 表现为约 5.22 FPS，说明：

1. 进程级 RTSP 主循环没有整体停顿。
2. 编码器和 appsrc 没有普遍性阻塞。
3. 问题集中在 IPM 专用的三路输入、同步和融合路径。

## 4. 相机启动阶段的影响

三路参与 IPM 的相机在启动阶段都出现过一次明显慢采集：

| 相机 | 启动阶段证据 |
| --- | --- |
| `cam_l_11` | `total=415.2ms`，预期 50ms，见 [日志](/Users/minyi/Downloads/cam11_20260911215230.log:24) |
| `cam_f_12` | `total=559.0ms`，预期 50ms，见 [日志](/Users/minyi/Downloads/cam12_20260911215230.log:24) |
| `cam_r_13` | `total=433.7ms`，预期 50ms，见 [日志](/Users/minyi/Downloads/cam13_20260911215230.log:24) |

普通相机启动阶段也出现过类似现象，例如：

```text
cam_b_18  total=469.4ms
cam_rb_10 total=672.0ms
cam_f_7   total=708.5ms
cam_lb_4  total=428.4ms
```

这说明启动时存在多路相机、CUDA、内存或调度资源竞争。但这些慢采集主要
集中在启动阶段，不能单独解释整个有客户端窗口内持续的 IPM 低频；持续问题
仍应优先从 `camera_merge` 的输入频率、同步策略和处理耗时查起。

## 5. 当前代码链路

### 5.1 相机输出不是同一频率

当前相机处理代码明确分成两条路径：

- 每帧的 RTSP 原图路径约 20 Hz，见
  [camera.cpp](/Users/minyi/workspace/autodrive/aura/src/drivers/sensing_camera/src/camera.cpp:735)。
- `ori`、`corr`、`compressed` 和曝光信息走 10 Hz 路径，见
  [camera.cpp](/Users/minyi/workspace/autodrive/aura/src/drivers/sensing_camera/src/camera.cpp:683)。
- 压缩图只在 `skip_frames == 0 || frames_to_skip == 0` 时生成，见
  [camera.cpp](/Users/minyi/workspace/autodrive/aura/src/drivers/sensing_camera/src/camera.cpp:722)。

本分支的 `skip_frames=1` 意味着 `camera_merge` 使用的三路
`raw_image/compressed` 输入约为 10 Hz，而不是 20 Hz。

### 5.2 `camera_merge` 使用三路压缩图同步

`camera_merge` 订阅三路：

```text
/zeron/driver/camera/cam_l_11/raw_image/compressed
/zeron/driver/camera/cam_f_12/raw_image/compressed
/zeron/driver/camera/cam_r_13/raw_image/compressed
```

订阅和同步配置见
[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:523)：

```text
Sensor Data QoS
MutuallyExclusive callback group
ApproximateEpsilonTime queue=10
同步容差=50ms
```

同步回调内串行执行：

```text
三路 JPEG 解码
    -> 三路 remap
    -> 三路 CV_32FC3 转换
    -> 481x481 浮点累加和逐像素融合
    -> 自车 overlay
    -> 裁剪为 480x480
    -> ROS publish
```

代码证据：

- 三路 JPEG 解码：[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:563)
- remap、浮点转换和逐像素融合：[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:462)
- IPM 发布：[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:597)
- 当前分支已经关闭逐帧 INFO 和 debug 图片保存：[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:616)

队列深度 `10` 在约 10 Hz 输入下可以容纳约 1 秒的历史组合；在多路输入
到达时间不一致或回调处理不及时的情况下，容易产生：

```text
历史帧驻留
    -> 三路时间同步等待或丢弃
    -> 同步回调间隔扩大
    -> IPM 发布频率下降并抖动
```

当前没有 `decode`、`remap`、`blend` 分阶段耗时，因此不能仅凭本批日志断言
具体是 JPEG 解码、OpenCV remap 还是浮点融合占用最多 CPU。可以确定的是，
低频发生在这条 IPM 专用处理链路，而不是 RTSP push 阶段。

## 6. 是否只改 `camera_merge`

### 6.1 如果目标是约 10 FPS

**可以优先只修改 `camera_merge`，这是本批次最小且合理的修改范围。**

理由：

1. 当前 IPM 的设计输入是三路约 10 Hz compressed。
2. RTSP 统计显示收到多少 IPM 就基本成功推送多少，`push_ok=1982/1982`。
3. 本批次没有 `stale_drop`、`flow_error` 或 pipeline 销毁证据。
4. 普通相机仍接近 20 FPS，说明不是 `ztd_rtsp` 进程整体吞吐不足。

建议只在 `camera_merge` 做以下优化：

1. 将同步队列从 `10` 先降到 `2~3`，避免处理历史组合。
2. 明确采用最新帧优先，不能让旧的三路组合长期占用同步队列。
3. 在同步回调前后记录三路输入频率、时间戳偏差、匹配成功数和丢组数。
4. 增加 `decode`、`remap`、`blend`、overlay、publish 分阶段耗时。
5. 复用固定尺寸的 `cv::Mat` 和中间 buffer，减少每帧分配。
6. 保持当前已经关闭的逐帧 INFO 和 `cv::imwrite` 设置，不要恢复生产路径的
   同步图片写盘。

### 6.2 如果目标是 20 FPS

**只改 `camera_merge` 不足以达到 20 FPS。**

原因是当前 `camera_merge` 的输入是 `skip_frames=1` 的 compressed 10 Hz；
上游最多提供约 10 Hz 的三路同步组合。即使 `camera_merge` 的处理速度足够，
也不能从 10 Hz 输入稳定生成真实的 20 FPS 新画面。

要验收 20 FPS，需要额外评估以下方向：

```text
方案 A：camera_merge 改用 20 Hz rtsp_raw_image
方案 B：调整相机 compressed 输出策略，提供 20 Hz 输入
方案 C：camera_merge 保持 10 FPS，产品侧明确 IPM 目标就是 10 FPS
```

方案 A/B 会增加带宽、内存和 CPU/GPU 压力，不能直接把目标频率改成 20
就视为修复，必须基于目标车实测。

### 6.3 本批次不建议先改 `ztd_rtsp`

本批次没有以下证据：

```text
stale_drop > 0
flow_error > 0
pipeline_destroy > 0
push_ok 明显低于 push_attempt
push_data 持续高耗时
```

因此，本批次不建议为了 IPM 低 FPS 直接修改 `ztd_rtsp` 的旧帧门限、appsrc
需求状态或 pipeline 生命周期。那些属于另一类“RTSP 收到帧后丢弃或停止推送”
问题，应由对应日志证据触发，不能与本批次的上游低频混在一起。

## 7. 推荐实施边界

### P0：先改 `camera_merge`

```text
输入：三路 compressed 10 Hz
处理：最新帧优先 + 小同步队列 + 阶段耗时埋点
输出：稳定约 10 FPS，且不消费明显过旧的组合
```

本阶段不改变 e2e、watchdog、RTSP 状态机和 `health_manager`。

### P1：根据目标频率决定是否改上游

只有在产品或测试明确要求 IPM 20 FPS 时，才继续评估：

- `camera_merge` 改订阅 20 Hz `rtsp_raw_image`；
- 相机压缩输出频率调整；
- 三路原图传输和内存占用；
- CUDA/OpenCV 阶段是否可以满足 20 FPS；
- 启动时多路相机和 GPU 资源错峰初始化。

### P2：保留 RTSP 侧独立观测

本批次不改 `ztd_rtsp`，但后续验收仍需保留：

- `/ipm` 的 `callback_age`、`callback_gap`；
- `push_attempt`、`push_ok`、`push_busy`；
- `stale_drop`、`flow_error`；
- pipeline configure/destroy 次数。

这样可以避免 camera_merge 优化后出现新的下游问题而无法区分。

## 8. 验收标准

### 目标为约 10 FPS 时

- IPM 输出保持 `10 +/- 1 FPS`；
- 10 秒窗口内 `push_ok / push_attempt >= 99.5%`；
- `stale_drop=0`、`flow_error=0`；
- `callback_gap` P90 不长期超过 `150ms`；
- 不出现连续数秒无新 IPM 帧；
- IPM 输入帧时间戳与发布墙钟之间的延迟不持续增长。

### 目标为 20 FPS 时

必须先切换或补足 20 Hz 输入，再验收：

- IPM 输出保持 `19~20 FPS`；
- 发布间隔 P90 不超过 `60ms`；
- 最大间隔不长期超过 `100ms`；
- 不通过重复旧帧来填充 FPS；
- `stale_drop=0`、`flow_error=0`，RTSP push 成功率保持接近 100%。

## 9. 最终判断

本批次的 IPM 低 FPS 和波动，主故障边界在：

```text
camera source 的 10 Hz compressed 供给
    +
camera_merge 的三路时间同步和串行图像处理
```

针对“先让当前 IPM 稳定工作”的目标，**优先只改 `camera_merge` 即可**，
不需要同步修改 `ztd_rtsp`。

但需要明确目标频率：

```text
目标约 10 FPS：camera_merge 优化是当前最小闭环
目标 20 FPS：还必须调整输入频率或切换到 20 Hz 原图路径
```

当前结论仍为 `analysis/unverified`，待实现后在目标车辆重新采集相同诊断
指标并完成回归。
