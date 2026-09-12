# MRC 前后 e2e、health_arbitrator 与 cloud_driving 重启分析

分析日期：`2026-09-09`

事件日期：`2026-09-05`

状态：`observed / three e2e launches / partial recovery`

本报告按照 `.github/observability/13-mrc-e2e-recovery-analysis-20260901.md`
的分析方式重做，但输入日志已替换为 2026-09-05 的三组 e2e 与
health_arbitrator 日志。

## 1. 结论先行

这不是一个可以用“单次重启后全部恢复”概括的事件，而是同一个
`ztd_cloud_driving` 长日志中，先后观察到三个独立的 `e2e_control` 启动实例：

1. 第一实例在 `04:14:13` 发生由 `PNC_MANAGER_VEHICLE_STALL_TIMEOUT`
   导致的 health MRC。该根因由 `health_arbitrator` 明确打印，e2e 观测到
   `health=2`、`result=2`，即 e2e MRC1。
2. 第二实例在 `04:15:17` 发生手柄消息间隔超时。`cloud_driving` 明确记录
   `gap=874ms` 和 `JOYSTICK_IDLE_TIMEOUT`，e2e 观测到 `pd=2`、`result=2`，
   即 e2e MRC1。手柄恢复后 `pd` 清零，但 `health=1` 仍保留，e2e 结果降为
   `result=1`，即 e2e MRC0，并没有回到 NORMAL。
3. 第三实例在 `04:17:19` 收到 `drive_mode=2` 并切换到 R/REMOTE 模式。
   `health_arbitrator` 在相同时间执行 `0 -> 1`，e2e 随后观测到
   `pd=0`、`health=1`、`result=1`，即模式相关的 e2e MRC0。该实例没有
   手柄 `pd` 故障。

因此，当前最准确的总体判断是：

| 分析对象 | 判断 |
|---|---|
| 第一实例的 MRC 根因 | 已确认：`PNC_MANAGER_VEHICLE_STALL_TIMEOUT` |
| 第二实例的手柄 MRC | 已确认：`JOYSTICK_IDLE_TIMEOUT`，手柄消息恢复后 cloud 自动清除 |
| 第二实例恢复后的总体状态 | 未恢复到 NORMAL，`pd=0` 但 `health=1` |
| 第三实例的 MRC | 与进入 R/REMOTE 模式高度同步，`pd=0`，具体 health error_name 未打印 |
| 三次 e2e 退出方式 | 日志显示均为用户 `Ctrl-C/SIGINT`，没有自动崩溃重启证据 |
| cloud_driving 是否在这些窗口重启 | 未发现对应进程重启证据；状态由同一份长日志连续记录 |
| 第一次 MRC 时 EPB 控制背景 | cloud 同窗口记录 `speed=0.0`；e2e MRC1 静止安全路径会请求拉起 EPB |
| 第一次重启后的 EPB 输入 | `remotejoystick` 持续收到 `epb_cmd=1`，直到 `1788552969.954452190` 才首次出现 `epb_cmd=0` |
| 手刹未解除的最直接证据 | 手柄恢复时间 `1788552959.573149314` 到首次 `epb_cmd=0` 相差约 `10.38s` |
| 是否能判定误触或底盘故障 | 不能；可以证明控制输入层仍是拉起状态，但没有用户动作来源、最终发布值和 VCU 执行反馈 |

关于用户反馈的“第一次重启后远控恢复但手刹未解除”，当前最符合日志的解释是：
远控通信已经恢复，但手刹释放输入没有同步恢复，cloud 继续收到并转发语义上为
“拉起”的 `epb_cmd=1`。这不是“已证明用户误触”，也不是“已证明 EPB 执行器故障”；
现有证据只把问题定位到了控制输入/安全输出链路，尚未闭环到实际 EPB 执行器。

## 2. 分析范围与输入日志

本次使用的 7 份输入日志如下：

```text
/Users/minyi/Downloads/e2e_control_20260905041659.log
/Users/minyi/Downloads/e2e_control_20260905041510.log
/Users/minyi/Downloads/e2e_control_20260905033057.log
/Users/minyi/Downloads/ztd_cloud_driving_20260904205049.log
/Users/minyi/Downloads/health_arbitrator_20260905041713.log
/Users/minyi/Downloads/health_arbitrator_20260905033109.log
/Users/minyi/Downloads/health_arbitrator_20260905041527.log
```

三个 e2e 启动时间：

| e2e 日志 | Created 时间戳 | 北京时间 | PID |
|---|---:|---|---:|
| `e2e_control_20260905033057.log` | `1788550257.5590048` | `2026-09-05 03:30:57` | `275009` |
| `e2e_control_20260905041510.log` | `1788552910.9340067` | `2026-09-05 04:15:10` | `303426` |
| `e2e_control_20260905041659.log` | `1788553019.9421198` | `2026-09-05 04:16:59` | `304724` |

对应的 health_arbitrator 日志启动时间：

| health 日志 | Created 时间戳 | 北京时间 | PID |
|---|---:|---|---:|
| `health_arbitrator_20260905033109.log` | `1788550269.122051` | `2026-09-05 03:31:09` | `275194` |
| `health_arbitrator_20260905041527.log` | `1788552927.3145845` | `2026-09-05 04:15:27` | `303655` |
| `health_arbitrator_20260905041713.log` | `1788553033.0037537` | `2026-09-05 04:17:13` | `304923` |

主分析窗口覆盖：

```text
Unix timestamp: 1788550257.5590048 - 1788556510.995299448
北京时间:      2026-09-05 03:30:57 - 2026-09-05 05:15:10
时区:          Asia/Shanghai
```

具体 MRC 事件分别集中在：

```text
第一实例：1788552853.294 - 1788552854.542
          2026-09-05 04:14:13.294 - 04:14:14.542

第二实例：1788552917.390 - 1788552959.592
          2026-09-05 04:15:17.390 - 04:15:59.592

第三实例：1788553039.514 - 1788553039.586
          2026-09-05 04:17:19.514 - 04:17:19.586
```

## 3. MRC 数值定义与证据边界

本报告对 e2e/health 数值采用以下映射：

| e2e `result` / `effective_mrc` | health/e2e 含义 |
|---:|---|
| `0` | `NORMAL` |
| `1` | `MRC0` |
| `2` | `MRC1` |
| `3` | `MRC2` |

必须区分以下三个字段：

1. **e2e `result` 或 `effective_mrc`**：本报告使用上表映射。
   所以 `e2e result=2` 是 MRC1，不是 MRC2。
2. **`drive_mode=2`**：日志明确标注为 `R`，即 R/REMOTE 模式，
   不是 MRC2。
3. **`cloud_driving` 的 `[MRC] status: 0→2`**：这是 cloud_driving
   内部状态机的状态值。它可以表示 cloud 内部进入手柄相关 MRC2，但不能
   直接套用 e2e 的 `result` 映射。

另外，e2e 的：

```text
joystick_status=255
gear=2
stop_flag=32
```

属于 PD heartbeat/安全输出字段，不等于 MRC 等级。MRC 等级应以
`result/effective_mrc` 以及 `pd/health` 仲裁输入为准。

## 4. 三次 e2e 进程总时间线

| 时间戳 | 北京时间 | 组件 | 事件 | 结论 | 原始日志 |
|---:|---|---|---|---|---|
| `1788550257.5590048` | `03:30:57.559` | e2e | 第一实例创建，PID `275009` | 第一轮 e2e 启动 | `e2e_control_20260905033057.log:4` |
| `1788552853.294302900` | `04:14:13.294` | health | 发现 `PNC_MANAGER_VEHICLE_STALL_TIMEOUT`，level 4 | health 根因明确 | `health_arbitrator_20260905033109.log:28606` |
| `1788552853.294401578` | `04:14:13.294` | health | `MRC status transfer from 0 to 2` | health 状态转为 2 | `health_arbitrator_20260905033109.log:28608` |
| `1788552853.398397114` | `04:14:13.398` | e2e | `result=2 (pd=0 health=2)` | e2e MRC1 生效 | `e2e_control_20260905033057.log:187100` |
| `1788552854.432043530` | `04:14:14.432` | cloud | `MRC status: 0→2`，原因同为 PNC stall | cloud 内部进入 MRC2 | `ztd_cloud_driving_20260904205049.log:248373` |
| `1788552854.542129124` | `04:14:14.542` | cloud | `MRC status: 2→0` | cloud 的该状态约 110ms 后清除 | `ztd_cloud_driving_20260904205049.log:248374` |
| `1788552900.511245065` | `04:15:00.511` | e2e | `signal_handler(SIGINT/SIGTERM)` | 第一实例被人工中断 | `e2e_control_20260905033057.log:194403` |
| `1788552910.9340067` | `04:15:10.934` | e2e | 第二实例创建，PID `303426` | 第二轮 e2e 启动 | `e2e_control_20260905041510.log:4` |
| `1788552917.390886085` | `04:15:17.391` | cloud | 手柄消息间隔 `gap=313ms` | 手柄链路出现间断 | `ztd_cloud_driving_20260904205049.log:249846` |
| `1788552917.951476642` | `04:15:17.951` | cloud | `MRC1 triggered gap=874ms` | 手柄空闲超时达到阈值 | `ztd_cloud_driving_20260904205049.log:249847` |
| `1788552917.952177399` | `04:15:17.952` | e2e | `result=2 (pd=2 health=0)` | e2e MRC1，主要来自 pd | `e2e_control_20260905041510.log:41` |
| `1788552917.952842097` | `04:15:17.953` | cloud | `MRC status: 0→2`，原因 `JOYSTICK_IDLE_TIMEOUT` | cloud 手柄 MRC2 生效 | `ztd_cloud_driving_20260904205049.log:249848` |
| `1788552933.183626696` | `04:15:33.184` | health | `MRC status transfer from 0 to 1` | health MRC0 生效 | `health_arbitrator_20260905041527.log:60` |
| `1788552933.212224481` | `04:15:33.212` | e2e | `result=2 (pd=2 health=1)` | pd 与 health 同时存在，仍为 e2e MRC1 | `e2e_control_20260905041510.log:2377` |
| `1788552959.573149314` | `04:15:59.573` | cloud | `MRC1 cleared — joystick recovered` | 手柄恢复，cloud 自动清除 | `ztd_cloud_driving_20260904205049.log:249882` |
| `1788552959.575336942` | `04:15:59.575` | cloud | `MRC status: 2→0` | cloud 手柄 MRC2 清零 | `ztd_cloud_driving_20260904205049.log:249883` |
| `1788552959.592131188` | `04:15:59.592` | e2e | `result=1 (pd=0 health=1)` | 手柄输入恢复，但总体为 e2e MRC0 | `e2e_control_20260905041510.log:6438` |
| `1788553011.669585524` | `04:16:51.670` | e2e | `signal_handler(SIGINT/SIGTERM)` | 第二实例被人工中断 | `e2e_control_20260905041510.log:11901` |
| `1788553019.9421198` | `04:16:59.942` | e2e | 第三实例创建，PID `304724` | 第三轮 e2e 启动 | `e2e_control_20260905041659.log:4` |
| `1788553039.514718510` | `04:17:19.515` | e2e | 收到 `drive_mode=2`，当前模式 1 | 进入 R/REMOTE 模式切换流程 | `e2e_control_20260905041659.log:71` |
| `1788553039.516119390` | `04:17:19.516` | health | `MRC status transfer from 0 to 1` | health MRC0 与模式切换高度同步 | `health_arbitrator_20260905041713.log:67` |
| `1788553039.526469492` | `04:17:19.526` | e2e | `mode switched 1 -> 2` | e2e 完成 R/REMOTE 模式切换 | `e2e_control_20260905041659.log:73` |
| `1788553039.566571003` | `04:17:19.567` | e2e | `result=1 (pd=0 health=1)` | 模式相关 e2e MRC0 | `e2e_control_20260905041659.log:74` |
| `1788553039.586488145` | `04:17:19.586` | e2e | `effective_mrc=1` | 总体仍为 MRC0 | `e2e_control_20260905041659.log:77` |

## 5. 第一实例：PNC stall 导致 health=2

### 5.1 health_arbitrator 给出了明确根因

第一实例附近的 health 日志不是只有状态数字，而是连续打印了具体错误：

```text
1788552853.294302900
Node 30 error PNC_MANAGER_VEHICLE_STALL_TIMEOUT level 4

1788552853.294387338
Rationality error with level CRITICAL_FAILURE found in non-MRC1 node,
node_id: 30, error_name: PNC_MANAGER_VEHICLE_STALL_TIMEOUT

1788552853.294401578
MRC status transfer from 0 to 2
```

原始位置：

```text
health_arbitrator_20260905033109.log:28606-28608
```

这里的因果链比较完整：

```text
PNC_MANAGER_VEHICLE_STALL_TIMEOUT
  -> health_arbitrator 判定 CRITICAL_FAILURE
  -> health MRC 状态 0 -> 2
  -> e2e 读取 health=2
  -> e2e result=2 / effective_mrc=2
```

e2e 紧随其后的记录为：

```text
1788552853.398397114
MRC active result=2 (pd=0 health=2 ...)

1788552853.398488497
MRC1 is triggering... (effective_mrc=2)
```

原始位置：

```text
e2e_control_20260905033057.log:187100-187101
```

按照本报告的数值定义，`result=2` 是 MRC1。e2e 日志本身的
`MRC1 is triggering` 也与该映射一致，不能将它写成 MRC2。

### 5.2 cloud_driving 的同名状态是旁证，但时间稍晚

cloud 日志随后记录：

```text
1788552854.432043530
[MRC] status: 0→2 (→PNC_MANAGER_VEHICLE_STALL_TIMEOUT)

1788552854.542129124
[MRC] status: 2→0 (PNC_MANAGER_VEHICLE_STALL_TIMEOUT→)
```

原始位置：

```text
ztd_cloud_driving_20260904205049.log:248373-248374
```

health_arbitrator 的 `0 -> 2` 比 cloud 的 `0→2` 早约 `1.138s`。这说明
两者记录的是同一个 PNC stall 相关故障在不同模块的观察时刻，不能因为 cloud
使用了内部 status `2`，就把 e2e 的 `result=2` 改写成 MRC2。

### 5.3 第一实例如何结束

第一 e2e 实例在 `04:15:00` 出现：

```text
user interrupted with ctrl-c (SIGINT)
signal_handler(SIGINT/SIGTERM)
process has finished cleanly [pid 275009]
```

原始位置：

```text
e2e_control_20260905033057.log:194401-194405
```

因此，第一实例不是日志显示的自动崩溃重启。之后的第二实例是一次新的
`ros2 launch`，但当前证据更支持人工 Ctrl-C 后重新拉起，而不是 e2e 自己
因故障自动重启。

## 6. 第二实例：手柄 gap 触发 pd=2，恢复后 health=1 保留

### 6.1 进入 R/REMOTE 模式

第二实例启动后先从默认状态切换到自动驾驶模式，随后收到：

```text
1788552915.715509004
PDriving msg: drive_mode=2, joystick_status=1, ...

1788552915.715752470
Received drive_mode: 2 from ParallelDrivingControl,
current driving_mode: 1

1788552915.715782720
driving_mode <- 2 (0=M 1=A 2=R)

1788552915.732442143
mode switched 1 -> 2
```

原始位置：

```text
e2e_control_20260905041510.log:25-30
```

这里的 `drive_mode=2` 是 R/REMOTE 模式值，不是 MRC2。

### 6.2 手柄消息间隔导致 cloud MRC2、e2e pd=2

cloud 日志给出了手柄监测的完整顺序：

```text
1788552917.390886085
[joystick] detecting loss gap=313ms

1788552917.951476642
[joystick] MRC1 triggered gap=874ms

1788552917.952842097
[MRC] status: 0→2 (→JOYSTICK_IDLE_TIMEOUT)
```

原始位置：

```text
ztd_cloud_driving_20260904205049.log:249846-249848
```

e2e 在几乎同一时刻观察到：

```text
1788552917.952177399
MRC active result=2 (pd=2 health=0 ...)

1788552917.952364817
MRC1 is triggering... (effective_mrc=2)
```

原始位置：

```text
e2e_control_20260905041510.log:41-42
```

从 `cloud` 到 e2e 的时间差约为 `0.701ms`。因此这一轮 e2e MRC 的直接
输入是 `pd=2`，而不是 `health`。按照 e2e 数值映射，`result=2` 仍然是
MRC1；cloud 内部的 `status=2` 才是其内部手柄 MRC2 状态。

### 6.3 health_arbitrator 随后把 health 置为 1

第二个 health 日志是 `04:15:27` 才启动的，之后记录：

```text
1788552933.183626696
MRC status transfer from 0 to 1
```

原始位置：

```text
health_arbitrator_20260905041527.log:60
```

e2e 在约 `28.598ms` 后记录：

```text
1788552933.212224481
MRC active result=2 (pd=2 health=1 ...)
```

原始位置：

```text
e2e_control_20260905041510.log:2377
```

这说明新 health 日志确认了 `health=1` 的状态转移，但该日志没有打印具体
`error_name`。因此证据边界应写成：

- 已确认 `health_arbitrator` 在 `1788552933.183626696` 执行了 `0 -> 1`；
- 已确认 e2e 随后读到 `health=1`；
- 未在该 health 日志中看到对应的具体错误名称；
- 结合第三实例相同的 R/REMOTE 模式与 `0 -> 1` 对齐关系，该 health=1
  很可能是进入 R/REMOTE 模式后的模式相关 MRC0，但不能仅凭当前日志给出
  具体内部 error_name。

### 6.4 手柄恢复，但总体没有回到 NORMAL

cloud 在 `04:15:59.573` 收到恢复后的手柄消息后记录：

```text
1788552959.573149314
[joystick] MRC1 cleared — joystick recovered

1788552959.575336942
[MRC] status: 2→0 (JOYSTICK_IDLE_TIMEOUT→)
```

原始位置：

```text
ztd_cloud_driving_20260904205049.log:249882-249883
```

随后 e2e 记录：

```text
1788552959.592131188
MRC active result=1 (pd=0 health=1 ...)
```

原始位置：

```text
e2e_control_20260905041510.log:6438
```

这表示：

| 状态层 | 触发时 | 手柄恢复后 |
|---|---|---|
| cloud 手柄 MRC | `status=2` | `status=0` |
| e2e `pd` | `2` | `0` |
| e2e `health` | `0`，随后变为 `1` | `1` |
| e2e `result/effective_mrc` | `2`，即 MRC1 | `1`，即 MRC0 |

因此只能说手柄相关故障恢复，不能说 e2e 总体已经恢复到 NORMAL。

### 6.5 第二实例退出方式

第二实例在 `04:16:51` 出现：

```text
user interrupted with ctrl-c (SIGINT)
signal_handler(SIGINT/SIGTERM)
process has died ... exit code -2
```

原始位置：

```text
e2e_control_20260905041510.log:11899-11902
```

`exit code -2` 与 Ctrl-C 中断一致，当前日志不支持“因 MRC 导致进程崩溃”
这一结论。

## 7. 第三实例：进入 R/REMOTE 后出现 health=1

第三实例启动后先完成初始化：

```text
1788553022.767208660
mode switched 255 -> 0
```

原始位置：

```text
e2e_control_20260905041659.log:19
```

之后在 `04:17:19`，e2e 收到模式控制：

```text
1788553039.514531119
PDriving msg: drive_mode=2, joystick_status=0, ... stop_flag=32

1788553039.514718510
Received drive_mode: 2 from ParallelDrivingControl,
current driving_mode: 1

1788553039.526469492
mode switched 1 -> 2
```

原始位置：

```text
e2e_control_20260905041659.log:70-73
```

health_arbitrator 在收到模式切换附近记录：

```text
1788553039.516119390
MRC status transfer from 0 to 1
```

原始位置：

```text
health_arbitrator_20260905041713.log:67
```

e2e 在 health 状态转移约 `50.452ms` 后记录：

```text
1788553039.566571003
MRC active result=1 (pd=0 health=1 ...)

1788553039.586488145
effective_mrc=1
```

原始位置：

```text
e2e_control_20260905041659.log:74-77
```

第三实例的可确认事实：

- `pd=0`，没有手柄空闲超时导致的 pd 故障；
- `drive_mode=2` 与 health `0 -> 1` 在毫秒级时间内相邻；
- e2e 最终为 `result=1/effective_mrc=1`，即 MRC0；
- health_arbitrator 日志没有打印具体 `error_name`；
- 因此可以判断为模式相关的 MRC0，但不能从这些日志进一步证明具体的
  内部健康错误对象。

第三实例最后也由 Ctrl-C 结束：

```text
1788556510.995299448
signal_handler(SIGINT/SIGTERM)
process has died ... exit code -2
```

原始位置：

```text
e2e_control_20260905041659.log:268152-268155
```

## 8. cloud_driving 手柄状态与自动恢复

在第二实例事件窗口，cloud 的相关状态可以简化为：

```text
04:15:17.390  检测到手柄 gap=313ms
04:15:17.951  检测到手柄 gap=874ms，触发手柄 MRC
04:15:17.953  cloud MRC status 0→2，原因 JOYSTICK_IDLE_TIMEOUT
04:15:59.573  收到恢复后的手柄消息，记录 joystick recovered
04:15:59.575  cloud MRC status 2→0
```

cloud 的恢复日志直接使用了 `joystick recovered`，并且恢复前后都有
`remotejoystick` 接收记录。因此最符合日志的解释是：

```text
手柄消息间隔超时
  -> cloud 内部设置 JOYSTICK_IDLE_TIMEOUT
  -> e2e pd=2
  -> 后续收到正常 remotejoystick
  -> cloud 自动清除手柄 MRC
```

当前日志没有把恢复动作记录成页面下发的独立 `mrc_status` 或
`self_recover_status` 指令。

需要注意：触发 MRC 后仍然可能继续收到手柄消息。触发条件是消息间隔超过
阈值，而不是要求之后所有手柄消息永久丢失。因此不能因为 MRC 触发后又看到
`remotejoystick`，就否定前面的 gap 触发。

## 9. 对 `1788552781.978855892` 的专项说明

用户之前特别指出的时间点：

```text
1788552781.978855892
= 2026-09-05 04:13:01.978 +0800
```

在 cloud 日志中对应：

```text
1788552781.978855892
[cloudLinkPing] invoke_sent

1788552782.059621141
[cloudLinkPing] rtt_ms=81 network_rtt_est_ms=81
```

原始位置：

```text
ztd_cloud_driving_20260904205049.log:248328-248329
```

这是一个正常的 `81ms` 应用层 ping 样本，不是三次 e2e MRC 事件本身。

它与第一实例的明确 PNC stall 事件相差约 `11.315s`，与第二实例的手柄
gap 事件相差约 `35.413s`。因此不能把这个时间点解释成手柄超时、PNC stall
或 e2e MRC 触发时刻。

## 10. 是否发生节点重启或进程重启

### 10.1 e2e 进程

可以确认存在三个独立的 e2e launch 实例：

```text
PID 275009: 03:30:57 启动，04:15:00 Ctrl-C 结束
PID 303426: 04:15:10 启动，04:16:51 Ctrl-C 结束
PID 304724: 04:16:59 启动，05:15:10 Ctrl-C 结束
```

第一实例显示 `process has finished cleanly`，第二和第三实例显示
`exit code -2`，但都紧邻：

```text
user interrupted with ctrl-c (SIGINT)
signal_handler(SIGINT/SIGTERM)
```

所以可以说 e2e 被人工停止并重新拉起，不能说是 MRC 自动触发了 e2e
崩溃重启。

### 10.2 health_arbitrator 进程

三个 health 日志各自对应不同的启动实例，启动时间分别为：

```text
03:31:09.122
04:15:27.315
04:17:13.004
```

这些启动时间是采集日志的进程创建时间。第二组 health 进程是在第二组
e2e 启动约 16.381s 后才创建，因此第二实例最初的 `pd=2 health=0`
先于该 health 日志，随后才出现 `health 0 -> 1`。

### 10.3 cloud_driving

当前给出的 cloud 文件是一个连续的长日志，在三次 e2e 事件附近看到的是
ping、remotejoystick、MRC 状态变化等业务日志，没有看到与这些事件同时发生的
cloud 进程启动、退出或重新初始化证据。基于当前输入，不能把恢复归因于
cloud_driving 重启。

## 11. 页面恢复指令的证据边界

当前日志可以证明：

- 第二实例开始前后确实有 `ParallelDrivingControl` 的
  `drive_mode=2`，这是进入 R/REMOTE 模式的控制，不是 MRC 恢复指令；
- 第二实例恢复时 cloud 记录的是收到 `remotejoystick` 后自动打印
  `joystick recovered`，随后执行 `status 2→0`；
- 第三实例同样有 `drive_mode=2` 与 health `0→1` 的相邻记录；
- 在当前目标事件窗口中没有看到独立的 `self_recover_status`、
  `mrc_status` 或页面主动清除手柄 MRC 的证据。

因此恢复结论应写为：

```text
第二实例的 cloud 手柄 MRC 清除，证据支持来自正常手柄消息恢复后的
cloud 自动清除；不是当前日志中可见的页面恢复命令。
```

这不等于证明页面绝对没有发过任何指令，只表示给出的 7 份日志没有提供
该指令的可观测证据。

## 12. health 日志中的其他告警

三个 health 日志都反复出现类似：

```text
Executing award for error: nothing,
unique_id: -1,
level: 0,
confidence: 0.00,
mrc_level: MRC_NORMAL
```

同时可以看到 `Very low memory in system` 等系统告警。当前输入中：

- 这些告警没有和三次目标 MRC 状态转移形成明确的一一对应关系；
- 第一实例已经有更直接的 `PNC_MANAGER_VEHICLE_STALL_TIMEOUT` 根因；
- 第二、第三实例的关键状态转移分别与手柄 gap、R/REMOTE 模式切换对齐。

因此本报告不把低内存告警作为三次目标 MRC 的主因。若要确认其是否造成
延迟或丢消息，需要补充系统内存曲线、ROS executor 调度、DDS 传输和
cloud 到 e2e 的消息接收时间。

## 13. 三个实例的最终对照

| 层面 | 第一实例 | 第二实例 | 第三实例 |
|---|---|---|---|
| 主要事件 | PNC stall | 手柄 idle timeout | 进入 R/REMOTE |
| cloud 内部状态 | `0→2` PNC stall，随后 `2→0` | `0→2` `JOYSTICK_IDLE_TIMEOUT`，恢复后 `2→0` | 当前窗口无对应手柄故障 |
| e2e `pd` | `0` | `2 -> 0` | `0` |
| e2e `health` | `2` | `0 -> 1` | `0 -> 1` |
| e2e `result/effective_mrc` | `2`，即 MRC1 | `2` 后变 `1`，即 MRC1 后降为 MRC0 | `1`，即 MRC0 |
| health 根因可见性 | 具体 error_name 可见 | 仅状态转移可见，error_name 未打印 | 仅状态转移可见，error_name 未打印 |
| 是否能证明底盘实际制动 | 不能 | 不能 | 不能 |
| 退出方式 | Ctrl-C | Ctrl-C | Ctrl-C |

## 14. 最终判定与后续建议

### 最终判定

1. 第一实例是明确的 PNC stall health 故障：`PNC_MANAGER_VEHICLE_STALL_TIMEOUT`
   触发 health `0 -> 2`，e2e 进入 `result=2`，即 MRC1。
2. 第二实例是手柄消息间隔超时：cloud 检测到 `gap=874ms`，设置
   `JOYSTICK_IDLE_TIMEOUT`，e2e `pd=2`，进入 `result=2`，即 MRC1。
   手柄恢复后 cloud 和 e2e `pd` 均恢复，但 health=1 仍在，最终只降到
   `result=1`，即 MRC0。
3. 第三实例的 `health=1` 与收到 `drive_mode=2`、切换到 R/REMOTE 模式
   高度同步，且 `pd=0`。当前证据支持模式相关 MRC0，但没有具体
   `error_name`，应保留该证据边界。
4. 三次 e2e 实例均由 Ctrl-C 结束，没有证据表明 MRC 导致 e2e 自动崩溃。
5. `1788552781.978855892` 是 `81ms` 的正常 cloudLinkPing 样本，不是
   三次 e2e MRC 事件本身。

### 后续建议

1. 在 `health_arbitrator` 的 `MRC status transfer` 日志中同时输出触发
   `error_name`、node_id、level、来源消息时间戳，避免只能看到 `0 -> 1`
   而无法追溯根因。
2. 在 e2e 日志中同时打印 `pd`、`health` 的来源时间戳和最近一次变更来源，
   便于区分手柄 MRC 与模式相关 health MRC。
3. 对 `JOYSTICK_IDLE_TIMEOUT` 记录触发前后连续消息的接收时间、序号和
   端到端延迟，区分云侧发送抖动、网络丢包和车端处理延迟。
4. 对 MRC 安全输出补充 `chassis_status`、执行器回执、车辆速度变化、
   EPB 状态和轮端扭矩等日志，才能证明实际制动闭环。
5. 为 e2e、health_arbitrator、cloud_driving 统一记录 launch_id 或
   correlation_id，避免多个进程实例只能通过 PID 和时间窗口人工关联。

## 15. 手刹/EPB专项分析

### 15.1 直接结论

手刹未解除**不能判定为误触**。本次日志能确认的是：在第一次 MRC 之前、第一次
重启后的远控恢复窗口内，以及第二次重启后的第三实例开始阶段，cloud 收到的
`remotejoystick` 数据多次带有 `epb_cmd=1`。按照代码注释，`epb_cmd=1` 表示
拉起手刹，`epb_cmd=0` 表示释放手刹。

第一次重启后的关键时间差如下：

```text
joystick recovered: 1788552959.573149314
首次 epb_cmd=0:     1788552969.954452190
差值:               10.381302876s
```

也就是说，手柄 MRC 已经在 `04:15:59.573` 由 cloud 清除，但直到
`04:16:09.954` 才第一次收到释放手刹输入。在这段窗口内，日志中仍能看到
`epb_cmd=1`。这足以解释“远控可以操作，但手刹无法解除”的表象：远控链路恢复
不等于 EPB 释放命令已经生效。

### 15.2 EPB 事件时间线

| 时间戳 | 北京时间 | 日志证据 | 对 EPB 的含义 |
|---:|---|---|---|
| `1788552695.456155963` | `04:11:35.456` | cloud `remotejoystick`，`epb_cmd=1`、`bt_others=1` | 第一 MRC 前最后一次明确看到拉起状态 |
| `1788552697.012921324` | `04:11:37.013` | `drive_mode=1`，打印“清空灯光/喇叭/手刹缓存 + MRC” | 已有日志证明 `cached_epb_cmd_` 被清零 |
| `1788552854.432043530` | `04:14:14.432` | cloud MRC `0→2`，原因 PNC stall，`speed=0.0` | 车辆在 MRC 触发时已处于静止状态 |
| `1788552865.789754377` | `04:14:25.790` | 重新进入 `drive_mode=2`，只有模式缓存日志 | 没有看到 `driveMode 缓存 epb_cmd=1` 的证据 |
| `1788552869.884154192` | `04:14:29.884` | 第一条恢复后 `remotejoystick` 带 `epb_cmd=1` | 远控手柄输入仍要求拉起 |
| `1788552910.066981085` | `04:15:10.067` | 第二实例启动边界附近 `remotejoystick` 带 `epb_cmd=1` | 第一次重启后输入仍为拉起状态 |
| `1788552959.573149314` | `04:15:59.573` | cloud `joystick recovered` | 手柄 MRC 恢复，不等于 EPB 已释放 |
| `1788552969.954452190` | `04:16:09.954` | 首次出现 `remotejoystick` `epb_cmd=0` | 第一次明确的释放输入，晚于手柄恢复约 `10.38s` |
| `1788552990.795354276` | `04:16:30.795` | 后续 `remotejoystick` 又带 `epb_cmd=1` | EPB 输入随后再次回到拉起，说明输入状态本身还在变化 |
| `1788553042.023181561` | `04:17:22.023` | 第三实例第一条 `remotejoystick` 带 `epb_cmd=1` | 第二次重启后的初始输入仍为拉起 |
| `1788553043.512714957` | `04:17:23.513` | 第三实例首次出现 `epb_cmd=0` | 约 `1.49s` 后收到释放输入，未复现第一次重启后的长时间延迟 |
| `1788553086.190704176` | `04:18:06.191` | 后续 `remotejoystick` 又带 `epb_cmd=1` | 不能仅凭该阶段判断执行器最终保持释放 |

原始日志位置主要为：

```text
ztd_cloud_driving_20260904205049.log:248268
ztd_cloud_driving_20260904205049.log:248276
ztd_cloud_driving_20260904205049.log:248373
ztd_cloud_driving_20260904205049.log:248382-248390
ztd_cloud_driving_20260904205049.log:249631
ztd_cloud_driving_20260904205049.log:249882-250106
ztd_cloud_driving_20260904205049.log:250688
ztd_cloud_driving_20260904205049.log:250728-250777
ztd_cloud_driving_20260904205049.log:252078
```

### 15.3 MRC 安全路径确实可能主动拉起 EPB

e2e 的 `ApplyMrcSafetyResponse()` 在有效 MRC 达到 MRC1 时创建专用安全输出，
并且该输出优先于普通 A/R 远控输出：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:738-750
aura/src/control/e2e_control/src/e2e_control_v2.cc:874-882
```

当 e2e 观测到的车辆速度绝对值小于 `0.3` 时，代码进一步执行：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:763-767
requested_gear = Neutral
parking_brake_percent_cmd = 100.4
```

第一 MRC 对应的 cloud 日志记录了 `speed=0.0`，因此该事件具备触发静止 EPB
安全输出的条件。这里能证明的是“安全控制路径有主动拉起 EPB 的设计，且事件窗口
车辆已为静止”；但当前 e2e 日志没有打印实际发布的
`parking_brake_percent_cmd`，所以不能把它写成已经完成 CAN 下发或执行器已经
拉起的闭环证据。

另外，e2e 对 `epb_cmd` 的普通远控映射是：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:1334-1341
epb_cmd=1 -> epb_requested_mode=PD_ON, parking_brake_percent_cmd=100.4
epb_cmd=0 -> epb_requested_mode=0,    parking_brake_percent_cmd=0.0
```

因此，第一次重启后 cloud 持续收到 `epb_cmd=1`，从控制语义上足以让 e2e 继续
保持拉起请求。当前证据更支持“释放请求迟到/未形成有效的零值控制输入”，而不是
先假定为“手刹硬件拒绝释放”。

### 15.4 为什么当前不能确认是缓存覆盖

cloud 的代码确实存在一个一般性风险：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:977-987
control_msg.epb_cmd = control_msg.epb_cmd == 0
    ? cached_epb_cmd_
    : control_msg.epb_cmd;
```

如果 `cached_epb_cmd_` 为 `1`，上游传来的 `epb_cmd=0` 会在合并时被替换成
`1`；PD keepalive 也会继续携带缓存值：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:1537-1565
```

但是，本次事件不能把这个风险认定为已确认根因，原因有两点：

1. 在 `1788552697.012921324`，cloud 已明确打印离开远控时清空手刹缓存；
2. 第一次重新进入远控时只看到 `drive_mode=2`，没有看到
   `driveMode 缓存 epb_cmd=1`，而随后 `epb_cmd=1` 出现在原始
   `remotejoystick` 输入中。

所以本次日志证明的是“收到的 remotejoystick 本身带 1”，不能证明是
`cached_epb_cmd_` 把原本的 0 覆盖成了 1。该代码仍应作为通用缺陷风险继续修正或
增加观测，但不能作为本次已定案的根因。

### 15.5 `epb_cmd=1` 是误触、状态残留还是底盘拒绝？

现有日志能够确认：

- cloud 收到的输入值为 `1`，这是拉起语义；
- 第一次重启后该值持续存在，且在手柄 MRC 恢复后仍持续约 `10.38s`；
- 后续也出现过 `epb_cmd=0`，说明链路并非永久无法传输释放值；
- 第二次重启后 `epb_cmd=0` 更快出现，未复现第一次的长延迟。

现有日志不能确认：

- `epb_cmd=1` 是用户确实按住/触发了手刹，还是手柄或页面状态残留；
- 页面是否发送过释放动作，以及页面发送值与 cloud 解析值是否一致；
- cloud 合并后的最终值是什么，因为当前日志没有同时打印 raw、cache 和 merged
  三个值；
- e2e 最终发布到 `/control_d_plus` 的
  `epb_control_active`、`epb_requested_mode` 和
  `parking_brake_percent_cmd`；
- chassis 是否真正下发了 T04 EPB CAN 帧，以及 VCU 是否接受、拒绝或禁止释放。

因此对“是不是误触”的结论应保持为：

```text
不能证明是误触。
能证明第一次重启后的控制输入在一段关键窗口内仍是“拉起手刹”。
不能证明底盘执行器故障，也不能证明实际 EPB 已经成功拉起/释放。
```

### 15.6 需要补充的闭环日志

要把这类问题从“输入层可疑”定位到具体根因，至少应补充：

1. cloud 在 remotejoystick 每帧打印 `raw_epb_cmd`、`cached_epb_cmd_`、
   `merged_epb_cmd`、消息来源和 `message_id`；
2. e2e 在收到控制消息和发布安全/普通控制消息时打印
   `epb_control_active`、`epb_requested_mode`、
   `parking_brake_percent_cmd`，并标注来源是 `remotejoystick`、keepalive
   还是 MRC 安全路径；
3. chassis 在 `T04_ADCU_EPB` 下发时记录 enable、auto、mode、位置请求；
4. 同时记录 VCU 的 `vcu_epb_park_brk_st`、`vcu_epb_error_code`、
   `vcu_epb_park_brk_rels_inhibit_sts` 和
   `vcu_epb_park_brk_inhibit_st`，这些反馈字段已在
   `aura/src/chassis_d_plus/src/data_process.cc:575-595` 解析；
5. 检查 `SetDefaultValueForPDCtrl()` 是否应显式清零
   `epb_requested_mode` 和 `parking_brake_percent_cmd`，当前
   `aura/src/control/e2e_control/src/e2e_control_v2.cc:1037-1052` 只明确清零了
   `epb_control_active`，这属于潜在状态残留风险，不能直接认定为本次根因。

