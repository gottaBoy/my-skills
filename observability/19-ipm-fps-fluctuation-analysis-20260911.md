# IPM FPS 波动与车端实时性分析记录

分析日期：`2026-09-11`

分支：`llm/on-vehicle-0729-pd`

状态：`analysis/unverified`

本记录基于以下两份日志：

- `/Users/minyi/Downloads/camera_merge_20260911201929.log`
- `/Users/minyi/Downloads/ztd_rtsp_20260911201929.log`

本轮只完成日志和代码分析，没有修改运行代码，也没有完成目标车辆上的编译、部署和实车回归。

## 1. 结论

IPM FPS 波动不是单一的网络或编码器问题，而是两个问题叠加：

1. `camera_merge` 处理链路接近或略低于相机实时生产速率，导致 IPM 消费的是历史帧，发布时已经落后约 `0.5~0.6s`。
2. `ztd_rtsp` 将 `500ms` 以上的帧判定为旧帧并丢弃；丢弃路径同时清除 GStreamer 的 `need-data` 请求，使后续新帧到达后也可能不再主动推送。

因此实际表现是：

```text
camera_merge 持续发布约20 FPS
    -> IPM帧年龄长期约550~635ms
    -> RTSP stale_drop
    -> gst_data_request_ 被清除
    -> 后续ROS帧不再触发 push_data
    -> 客户端重建 pipeline 后短暂恢复
    -> 再次遇到超龄帧
```

## 2. 日志证据

### 2.1 `camera_merge` 没有完全掉到低 FPS，但存在明显历史帧延迟

从 `Published IPM image` 日志解析得到：

| 指标 | 结果 |
| --- | ---: |
| 发布帧数 | `15422` |
| 覆盖时长 | `780.895s` |
| 平均 wall FPS | `19.748` |
| 发布间隔 P50 | `50.3ms` |
| 发布间隔 P90 | `56.3ms` |
| 发布间隔最大值 | `78.4ms` |
| `wall_time - header.stamp` P50 | `549.9ms` |
| `wall_time - header.stamp` P90 | `599.8ms` |
| `wall_time - header.stamp` 最大值 | `637.3ms` |

首帧墙钟时间为 `1789129176.591695`，图像时间戳为
`1789129176.257143`，已经落后约 `335ms`。例如：
[camera_merge 日志](/Users/minyi/Downloads/camera_merge_20260911201929.log:26)。

末尾仍然是接近 `50ms` 一帧，但墙钟与图像时间戳相差约 `500ms`：
[camera_merge 日志](/Users/minyi/Downloads/camera_merge_20260911201929.log:15428)。

这说明主要问题是实时性和队列积压，不是相机完全停止出帧。

### 2.2 RTSP 收到 IPM 时已经超过旧帧门限

当前配置：

```yaml
max_frame_age_ms: 500
```

代码和配置位置：

- [params.yaml](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_rtsp/config/package_config/ztd_rtsp/params.yaml:19)
- [rtsp_stream.cpp](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/rtsp_stream.cpp:1648)

典型日志：

```text
callback_age=545/557/577ms ... stale_drop=1
callback_age=585/601/628ms ... stale_drop=1
callback_age=595/612/635ms ... stale_drop=1
```

对比原始 `/cam_f_12`：

```text
callback_age 约75~90ms
callback_gap 约50~60ms
push_data 最大约6ms
```

IPM 的 `callback_gap` 仍约 `50~60ms`，但 `callback_age` 长期约
`540~635ms`，而 `image_copy`、`push_buffer`、`push_data` 基本为 `0ms`。
因此没有证据表明 RTSP 编码或网络是首要积压点。

### 2.3 stale drop 后进入长时间不推送

一次正常窗口：

```text
1789129353: push_ok=149
1789129363: push_ok=200
```

随后窗口：

```text
1789129373: push_attempt=95 push_ok=94 stale_drop=1
```

再后续窗口会出现：

```text
need_data=1 push_attempt=1 push_ok=0 stale_drop=1
```

或者：

```text
need_data=0 push_attempt=0 push_ok=0
```

42 个 IPM 诊断窗口累计：

```text
callback=8132
callback_skip=2773
need_data=456
push_attempt=456
push_ok=443
stale_drop=13
pipeline_configure=13
pipeline_destroy=13
```

例如 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260911201929.log:547)
记录了第一次 `stale_drop`，随后 [同一日志](/Users/minyi/Downloads/ztd_rtsp_20260911201929.log:659)
显示 `need_data=0` 且没有继续推送。

## 3. `camera_merge` 的积压来源

当前三个压缩图像通过 `ApproximateEpsilonTime` 同步，队列深度为 `10`，
容差为 `50ms`：

[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:549)

同步回调内串行完成：

```text
三路 JPEG 解码
    -> remap
    -> CV_32FC3 转换
    -> 逐像素浮点融合
    -> 自车图 resize/overlay
    -> ROS publish
    -> 每帧 PNG 编码和同步写盘
```

每帧写盘位置：

[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:617)

同步订阅使用互斥 callback group，即使主程序使用 4 线程 executor，
同步回调本身也不会并发处理多组图像：

[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:530)

`BuildIpm` 还会每帧创建浮点累加矩阵、权重矩阵和中间 remap 图像：

[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:462)

队列深度 `10` 在约 `20 FPS` 下提供了约 `500ms` 的历史帧驻留空间。
这与日志中 IPM 的 `550~600ms` 延迟高度吻合，但仅凭日志不能把全部延迟
精确归因到某一个 OpenCV 调用，需要补充阶段耗时埋点。

## 4. 只改 `camera_merge` 是否足够

### 4.1 对当前样本的短期现象：大概率可以明显改善

如果只做以下 `camera_merge` 优化：

1. 关闭每帧 `cv::imwrite`；
2. 降低逐帧 INFO 日志；
3. 缩小同步队列；
4. 采用“只保留最新帧”的输入策略；
5. 复用中间 `cv::Mat`，减少每帧分配；

那么 IPM 帧龄有机会从当前的 `550~600ms` 降到 `100~200ms`，
当前 `max_frame_age_ms=500` 下的 `stale_drop` 应明显减少甚至消失。

因此，`camera_merge` 是当前主要性能瓶颈，优先优化它是正确的。

### 4.2 对完整故障闭环：只改 `camera_merge` 不够

不能把“只改 `camera_merge` 后当前日志不再波动”定义为完整修复，原因是
RTSP 仍然存在独立的状态处理问题：

```cpp
finish_push_iteration(true, true)
```

其中第二个参数会清除 `gst_data_request_`：

[rtsp_stream.cpp](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/rtsp_stream.cpp:1580)

而新 ROS 帧只有在 `gst_data_request_` 仍为 `true` 时才会立即触发
`push_data()`：

[rtsp_stream.cpp](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/rtsp_stream.cpp:644)

所以只要未来出现一次调度抖动、CPU 瞬时升高、磁盘阻塞或输入延迟超过
`500ms`，即使 `camera_merge` 已经优化，也可能再次进入：

```text
一帧 stale_drop
    -> demand 清除
    -> 后续帧不推送
    -> pipeline 重建后恢复
```

结论：

| 目标 | 只改 `camera_merge` 是否足够 |
| --- | --- |
| 降低当前 IPM 延迟和 FPS 波动概率 | 基本可以 |
| 让当前这批日志不再触发 stale drop | 有较大概率可以 |
| 保证偶发超龄帧不会导致长时间不推流 | 不够 |
| 完整修复 IPM 断续推流问题 | 不够，需要同步修正 RTSP stale-demand 处理 |

## 5. 推荐实施边界

### P0：`camera_merge` 必须修改

1. 删除生产路径中的每帧 `cv::imwrite`，调试保存改为低频、异步、可配置。
2. 将每帧 `Published IPM` INFO 改成 throttle 或 debug。
3. 同步队列先从 `10` 降到 `2~3`，避免消费过旧组合。
4. 输入 QoS 和同步策略以“最新帧优先”为目标，避免 DDS 队列和
   `message_filters` 队列叠加积压。
5. 增加 decode、remap、融合、overlay、publish 前后的耗时和帧龄日志。

### P0：`ztd_rtsp` 需要同步修正

旧帧丢弃时应：

```text
清除当前旧帧快照
保留 gst_data_request_=true
等待下一帧到达后重新 push
```

不能因为一次 stale frame 就把下游 demand 永久清掉。该改动属于 RTSP
推流状态机，不应由 `camera_merge` 代替。

### P1：验证性配置调整

可以临时把 `max_frame_age_ms` 调到 `800~1000ms`，用于确认：

```text
如果 stale_drop 消失且 push 连续恢复，
说明“IPM 帧龄超过 RTSP 门限”判断成立。
```

但不建议只提高门限作为最终方案，否则会用更旧的画面换取表面 FPS，
同时增加远控视频时延。

## 6. 验收标准

优化后至少应满足：

- `camera_merge` 输出保持 `20 +/- 1 FPS`；
- 输出 wall gap P90 不超过 `60ms`，最大值不长期超过 `100ms`；
- IPM `wall_time - header.stamp` P50 小于 `100ms`，P90 小于 `150ms`；
- RTSP `/ipm` 的 `stale_drop=0`；
- `push_ok / push_attempt` 接近 `100%`；
- 不再出现 `stale_drop=1` 后长时间 `need_data=0`；
- 不再因 IPM 供帧问题周期性 `pipeline_destroy/configure`。

## 7. 最终判断

`camera_merge` 是当前 IPM FPS 波动的主要性能根因，应该先改；但只改
`camera_merge` 只能降低触发概率，不能消除 RTSP 在 stale frame 后停止
推送的故障放大路径。

建议按以下最小完整修复范围推进：

```text
camera_merge：消除上游历史帧积压
    +
ztd_rtsp：stale_drop 后保留 demand 并等待最新帧重试
    +
实车验证：确认帧龄、stale_drop、push_ok 和 pipeline 生命周期
```

