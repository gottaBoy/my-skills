# feature/pd_test_0818 IPM FPS 波动与 cam_f_12 断流分析

分析日期：`2026-09-12`

日志时间：`2026-09-12 10:22` 至 `10:46` 左右

分支：`feature/pd_test_0818`

HEAD：`0880d4f55 IPM 接收 rtsp_raw_image 20HZ 的输入，输出10HZ ipm`

状态：`analysis/unverified`

本记录只分析本批日志和当前分支代码。没有修改业务代码，也没有完成目标车辆上的
部署和实车回归。本记录不能与 9 月 11 日 `feature/llm-on-vehicle-0818-pd-test`
分支约 `5.22 FPS` 的结论混用。

## 1. 日志范围

- `/Users/minyi/Downloads/cam18_20260912102209.log`
- `/Users/minyi/Downloads/cam10_20260912102209.log`
- `/Users/minyi/Downloads/cam7_20260912102209.log`
- `/Users/minyi/Downloads/cam4_20260912102209.log`
- `/Users/minyi/Downloads/cam13_20260912102209.log`
- `/Users/minyi/Downloads/cam12_20260912102209.log`
- `/Users/minyi/Downloads/cam11_20260912102209.log`
- `/Users/minyi/Downloads/ztd_rtsp_20260912102209.log`
- `/Users/minyi/Downloads/camera_merge_20260912102208.log`

## 2. 结论

本批 IPM 正常运行时基本稳定在设计值 `10 Hz`。用户观察到的主要 FPS 波动来自
一次明确的 `cam_f_12` 进程中断，而不是 `BuildIpm` 持续随机卡顿，也不是
`ztd_rtsp` 编码或网络推流持续失败。

故障链为：

```text
cam_f_12 收到 SIGINT 并退出
    -> 三路 ApproximateEpsilonTime 缺少前相机输入
    -> HandleSynchronizedImages() 不再产生完整同步组合
    -> latest_sync_generation_ 不再增长
    -> ProcessLatestFrame() 发现没有新 generation，直接 return
    -> /ipm 没有新 ROS 帧
    -> ztd_rtsp /ipm 只能记录低 callback 或长 callback_gap
```

其中，“`user interrupted with ctrl-c`”是 ROS launch 收到 `SIGINT` 时的通用提示。
日志可以证明 `cam_f_12` 收到信号并正常退出，但不能证明一定是现场人员实际按了
`Ctrl-C`，也可能是启动脚本、运维工具或进程管理器发送了同样的信号。信号发送方
需要结合启动平台审计日志继续确认。

## 3. 全量统计

`ztd_rtsp` 中 `/ipm` 的 10 秒窗口汇总如下：

```text
总窗口                    147
有 callback 的窗口         146
active 窗口                144
active callback          14308
active push_attempt      14254
active push_ok           14254
stale_drop                   0
flow_error                   0
pipeline_configure           2
pipeline_destroy             1
```

去掉 `cam_f_12` 中断期间的两个低频窗口：

```text
正常窗口                    142
callback 总数             14234
平均 callback            100.24 / 10s
平均输出                    10.02 Hz
```

全部 `/ipm` timing 窗口的中位统计为：

```text
callback_gap P50 的窗口中位数    99 ms
callback_gap P90 的窗口中位数   111 ms
callback_age P50 的窗口中位数   161 ms
```

因此当前分支的正常状态不是上一批日志中的约 `5.22 FPS`，而是稳定接近
`10 FPS`。本批异常主要由一次约 `12.3s` 的断流拉低局部窗口。

## 4. 故障时间线

| Epoch | 本地时间 | 事件与证据 |
| --- | --- | --- |
| `1789180425.193` | `10:33:45.193` | `/ipm callback=100`，中断前保持约 10 Hz，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8151) |
| `1789180426.494` | `10:33:46.494` | `cam_f_12` 收到 `SIGINT/SIGTERM` 信号处理回调，见 [cam12 日志](/Users/minyi/Downloads/cam12_20260912102209.log:92) |
| `1789180426.503` | `10:33:46.503` | 第二条信号处理记录，见 [cam12 日志](/Users/minyi/Downloads/cam12_20260912102209.log:93)；进程随后 clean exit，见 [退出记录](/Users/minyi/Downloads/cam12_20260912102209.log:94) |
| `1789180434.526` | `10:33:54.526` | `/cam_f_12 callback=40`、`last_callback_age=8050ms`、`pipeline_destroy=1`，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8258) |
| `1789180435.193` | `10:33:55.193` | `/ipm callback=15`、`last_callback_age=8580ms`，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8269) |
| `1789180444.526` | `10:34:04.526` | `/cam_f_12` 已恢复，窗口记录 `callback_gap Max=12540ms`，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8389) |
| `1789180445.202` | `10:34:05.202` | `/ipm callback=59`，记录 `callback_gap Max=12291ms`，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8399) 和 [timing](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8400) |
| `1789180455.212` | `10:34:15.212` | `/ipm callback=100`、`push_attempt=100`、`push_ok=100`，恢复到约 10 Hz，见 [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8517) |

前相机恢复进程的启动日志不在提供的 `cam12` 文件内，因此目前只能从
`ztd_rtsp` 的 callback 恢复确认它重新供帧，不能从本批日志确认是谁、通过什么
机制重新拉起了进程。

## 5. 为什么 IPM 比单相机更明显

`camera_merge` 当前订阅以下三路约 20 Hz 原图：

```text
/zeron/driver/camera/cam_l_11/rtsp_raw_image
/zeron/driver/camera/cam_f_12/rtsp_raw_image
/zeron/driver/camera/cam_r_13/rtsp_raw_image
```

代码使用：

```text
ApproximateEpsilonTime
queue depth = 10
sync tolerance = 25 ms
ProcessLatestFrame wall timer = 100 ms
目标输出 = 10 Hz
```

订阅、同步和定时器配置见
[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:561)。

同步回调只有形成完整三路组合时才更新 `latest_synced_msgs_` 并递增 generation，
见 [camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:596)。
定时器发现 generation 没有变化时直接返回，见
[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:615)。

所以单独的 `cam_l_11` 和 `cam_r_13` 即使仍在持续供帧，也不能形成新的 IPM。
在异常附近，两路日志仍有约 20 Hz callback：

- `/cam_l_11` 在 `1789180436.776` 的窗口 `callback=202`，见
  [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8292)。
- `/cam_r_13` 同一窗口 `callback=202`，见
  [ztd_rtsp 日志](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:8294)。

这排除了“三个 IPM 相机一起断流”，故障入口明确集中在 `cam_f_12`。

数据流和故障传播见：

- [IPM 数据流与断流传播图](diagrams/ipm-pd-test-20260912.dataflow.html)
- [架构图源文件](diagrams/ipm-pd-test-20260912.dataflow.json)

## 6. RTSP 不是本批主根因

本批 active 窗口内：

```text
push_attempt = 14254
push_ok      = 14254
stale_drop   = 0
flow_error   = 0
```

故障恢复后的 `/ipm` 窗口同样为 `push_attempt=100`、`push_ok=100`。正常窗口内
`push_data` 通常为 `0~1ms`。这些事实说明 `ztd_rtsp` 基本成功推送了已经收到的
IPM 帧。

异常窗口中的 `/ipm pipeline_destroy=1` 和后续 `pipeline_configure=1` 是
断流期间的下游 pipeline 生命周期现象，发生在上游 `cam_f_12` 已经停止供帧之后；
它不是本次 12 秒无新 IPM 帧的起点。

## 7. camera_merge 本身是否有性能问题

本批日志不支持“`BuildIpm` 长期算不完”的判断：

1. 排除断流窗口后，IPM 平均为 `100.24 callback/10s`。
2. 相机恢复后，不需要重启 `camera_merge` 就回到 `100 callback/10s`。
3. `camera_merge` 日志没有崩溃、异常退出或初始化失败，启动后只记录地图初始化和
   480x480 裁剪，见
   [camera_merge 日志](/Users/minyi/Downloads/camera_merge_20260912102208.log:25)。

但当前代码仍有一个需要监控的潜在性能边界：三路订阅同步和
`ProcessLatestFrame()` 共用 `MutuallyExclusive` callback group，而后者包含
三路 `cv_bridge` 转换、clone、remap、浮点融合和发布。`BuildIpm` 的逐像素处理见
[camera_merge_node.cc](/Users/minyi/workspace/autodrive/aura/src/drivers/camera_merge/src/camera_merge_node.cc:470)。
如果单帧处理超过 `100ms`，同步输入回调也会被延后。

主中断之外还有两个短抖动窗口：

1. `1789180735` 左右，`cam_f_12 callback_gap Max=264ms`，见
   [相机 timing](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:11819)；
   对应 `/ipm callback_gap Max=230ms`，见
   [IPM timing](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:11828)。
   这是一次可由前相机输入停顿解释的短抖动。
2. `1789180755` 左右，三路输入的 callback gap 最大值分别约为
   `55ms/61ms/66ms`，见
   [cam_l_11](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:12092)、
   [cam_f_12](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:12054) 和
   [cam_r_13](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:12096)，但
   `/ipm callback=98`、`callback_gap Max=360ms`，见
   [IPM diag](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:12066) 和
   [IPM timing](/Users/minyi/Downloads/ztd_rtsp_20260912102209.log:12067)。

第二个窗口没有单路输入 callback 断流证据，更可能位于三路时间戳同步或
`camera_merge` 调度/处理阶段。由于当前同步时间戳日志、同步命中率和处理耗时日志
都被关闭，现有日志不能继续区分“25ms 同步窗口未命中”和“互斥 callback group
被处理阶段占用”。这是需要补诊断的次要问题，不是本次 `12.3s` 主中断的已证实
根因。

## 8. 次要现象

### 8.1 多相机启动资源竞争

启动阶段多个相机出现一次性慢采集：

| 相机 | 最大启动慢采集/间隔 |
| --- | --- |
| `cam_b_18` | capture `858.1ms` |
| `cam_rb_10` | capture `790.7ms` |
| `cam_lb_4` | capture `850.6ms` |
| `cam_f_7` | capture `569.6ms` |
| `cam_f_12` | capture `527.4ms` |
| `cam_l_11` | frame interval `609.6ms` |
| `cam_r_13` | frame interval `673.1ms` |

这说明并行启动时存在 CPU、CUDA、内存或设备初始化竞争，但异常主要集中在启动
阶段，不能解释运行约 11 分钟后由 SIGINT 开始的 12 秒 IPM 空窗。

### 8.2 恢复期左右相机短时 publish 阻塞

`1789180440` 左右：

- `cam_l_11 pub_rtsp=293.2ms`，见
  [cam11 日志](/Users/minyi/Downloads/cam11_20260912102209.log:94)。
- `cam_r_13 pub_rtsp=310.1ms`，见
  [cam13 日志](/Users/minyi/Downloads/cam13_20260912102209.log:90)。

对应 RTSP 窗口最大 callback gap 分别约 `389ms` 和 `419ms`。这是恢复阶段的
次要抖动，但量级远小于 `cam_f_12` 的 `12540ms`，不能解释主异常。

### 8.3 calibration YAML 告警

各相机缺少 `/root/.ros/camera_info/*.yaml`，但相机仍持续发布，`camera_merge`
从车辆 `sensors.json` 读取自己的标定。本批没有证据表明该告警导致 FPS 波动。

## 9. 是否只改 camera_merge

结论分两部分：

```text
防止本次故障再次发生：不能只改 camera_merge
增强故障可见性和降级能力：可以优先改 camera_merge
```

只优化同步队列、OpenCV buffer 或融合耗时，无法阻止 `cam_f_12` 被 SIGINT
终止。要消除本次根因，必须同时查清信号来源，并保证单相机进程被意外终止后能
自动、快速恢复。

`camera_merge` 侧可以改进：

1. 记录每路 `input_count`、`last_input_age_ms` 和实际输入频率。
2. 记录同步命中数、三路时间戳最大偏差、同步丢组数。
3. 当 `300ms` 没有新同步组合时，限频打印明确缺失的相机名。
4. 记录 `toCvCopy/clone`、`InitializeMaps`、`BuildIpm` 和 publish 分阶段耗时。
5. 发布 diagnostics，区分 `input_missing`、`sync_miss` 和 `processing_overrun`。
6. 保持“不重复发布旧 IPM 帧”的默认策略，避免表面 FPS 正常但画面实际冻结。

是否在单路丢失时使用剩余两路生成带遮罩的降级 IPM，属于产品和安全策略变更。
不能直接在本次分析中默认启用；如果需要，应明确缺失区域、最大帧龄、UI 告警和
退出条件，并单独评审。

## 10. 修复建议

### P0：治理相机进程退出

1. 从启动平台、运维脚本和进程管理器日志定位谁在
   `2026-09-12 10:33:46 CST` 向 `cam_f_12` 发送了 SIGINT。
2. 为每个相机进程记录启动原因、停止原因、restart count 和退出码。
3. 验证当前 supervisor 对“SIGINT 后 clean exit”是否会自动重启；如果不会，
   按系统部署方式调整 restart policy。
4. 避免单路相机的维护操作误伤 IPM 必需输入；涉及三路 IPM 相机时明确维护窗口和
   上层告警。

### P1：补 camera_merge 诊断

不改变当前 20 Hz 三路输入、25ms 同步容差和 10 Hz 输出策略，先增加低开销诊断：

```text
camera_merge_input_total{camera}
camera_merge_input_age_ms{camera}
camera_merge_sync_total
camera_merge_sync_gap_ms
camera_merge_no_new_generation_total
camera_merge_process_ms{stage}
camera_merge_publish_total
```

这可以在下一次波动时直接回答“输入断了、同步没命中，还是 IPM 处理超时”。

### P2：再做性能优化

只有诊断证明 `processing_overrun` 后，再评估：

- 将订阅同步回调和耗时处理拆到不同 callback group；
- 减少 `cv::Mat` clone 和逐帧内存分配；
- 复用 `acc`、`weight`、remap 和中间 buffer；
- 对浮点融合循环做向量化或 CUDA 评估；
- 根据最新帧语义评估同步队列从 `10` 调低到 `2~3`。

这些是正常路径的延迟和资源优化，不是本次 SIGINT 根因修复。

## 11. 验收标准

### 正常运行

- `/ipm` 保持 `10 +/- 1 FPS`；
- 10 秒窗口 `push_ok / push_attempt >= 99.5%`；
- `callback_gap P90 <= 150ms`；
- `stale_drop=0`、`flow_error=0`；
- 不通过重复旧帧填充 FPS。

### 单相机异常

- 在 `300ms` 内指出具体缺失相机；
- diagnostics 能区分输入断流和处理超时；
- 相机自动恢复时间有明确目标，建议先验收不超过 `2s`；
- 相机首帧恢复后，IPM 在一个同步周期加一个处理周期内恢复；
- 重启期间不发布伪装成新帧的旧 IPM；
- 记录退出信号来源或至少记录触发该操作的 supervisor/运维事件。

## 12. 最终判断

本批 `feature/pd_test_0818` 的 IPM 正常性能已经达到约 `10 Hz`。最明显的一次
FPS 波动有完整证据链指向：

```text
cam_f_12 SIGINT/clean exit
    -> 三路同步中断
    -> camera_merge 无新 generation
    -> IPM 约 12.3 秒无新帧
    -> 相机恢复后 IPM 自动恢复 10 Hz
```

因此修复优先级应是：

```text
先查并治理 cam_f_12 的信号来源和自动拉起
    -> 再补 camera_merge 输入/同步/处理诊断
    -> 有 processing_overrun 证据后才做性能优化
```

本批不建议先修改 `ztd_rtsp`，也不支持把异常归因到 IPM 算法持续算力不足。
