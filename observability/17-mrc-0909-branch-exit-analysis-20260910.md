# 0909 新分支远控退出未闭环与 MRC1 分析

分析日期：`2026-09-10`

事件日期：`2026-09-10`

状态：`observed / remote-session-close-incomplete / joystick-watchdog-mrc1`

## 1. 分析范围

本次只分析 0909 新分支当天的独立样本，不复用 16 号文档中的驾驶仓切换
结论，也不把驾驶仓切换作为本次根因。

输入日志：

```text
/Users/minyi/Downloads/ztd_cloud_driving_20260910114242.log
/Users/minyi/Downloads/e2e_control_20260910114622.log
/Users/minyi/Downloads/health_arbitrator_20260910114628.log
```

日志时间戳按车端时钟换算为北京时间。现场没有提供前端日志、云端路由日志或
`onRelease` 发送端日志，因此对 `onRelease` 的判断仅限于车端是否收到并处理。

## 2. 结论先行

本次问题不是“手柄从未工作”，也不是当前证据能够证明的用户误触。

车端在 `1789011834.742` 确实收到了一个 `bt_others=1` 帧，并执行了：

```text
[joystick] driver exit, clear MRC, hold brake
```

但是这条路径只清除了 cloud MRC 并设置当前帧制动，没有同步完成远控会话
释放。日志随后又出现：

```text
drive_mode=1
drive_mode=2
```

车端重新进入远控模式时，`remotejoystick` 数据没有及时恢复，watchdog 按
`JOYSTICK_IDLE_TIMEOUT` 触发 MRC1。第二次复现由 e2e 明确确认：

```text
MRC active result=2 (pd=2 health=1 ...)
MRC1 is triggering... (effective_mrc=2)
```

本次最符合日志的因果链是：

```text
远控数据此前正常
  -> 收到 bt_others=1，仅执行当前帧主动退出处理
  -> 未完成统一 remote session close
  -> 后续仍收到 drive_mode=2，远控状态重新生效
  -> joystick 数据流出现空窗
  -> cloud_driving 按 JOYSTICK_IDLE_TIMEOUT 触发 pd MRC1
  -> e2e 收到 pd=2 并执行 MRC1 安全输出
  -> MRC 安全输出打开双闪并保持制动
```

因此，本次应定位为：

> 主动退出信号与远控会话释放不是同一个原子状态转换。`bt_others=1`
> 虽然被车端识别，但没有阻止后续旧会话或重新下发的 `drive_mode=2` 重新激活
> 远控 watchdog。手柄数据停止后，watchdog 将退出后的状态误判为远控中手柄
> 失联，最终触发 MRC1。

当前日志不能单独证明以下任一项：

1. 前端根本没有发送 `onRelease`；
2. 前端发送了，但云端没有转发；
3. 云端转发了，但车端未收到；
4. 车端收到了 `onRelease`，但因消息乱序、旧 session 或处理竞态没有完成释放。

车端日志中未发现 `onRelease` 的接收和 ACK 记录，但已经确认存在
`bt_others=1` 的内部主动退出处理。因此可以确认“退出没有完成完整会话闭环”，
不能仅凭这三份日志把责任锁定为前端没有发送 `onRelease`。

## 3. 关键时间线

### 3.1 第一次异常窗口：退出处理后远控再次重入

对应车端日志：

```text
ztd_cloud_driving_20260910114242.log
```

| 时间戳 | 北京时间 | 证据 | 判断 |
|---:|---|---|---|
| `1789011825.396` | `11:43:45.396` | 收到 `drive_mode=2`，缓存并通知 e2e | 进入远控 |
| `1789011826.821` | `11:43:46.821` | `handler_end result=published`，累计消息 `651` | 手柄数据正常到达 |
| `1789011831.539` | `11:43:51.539` | `handler_end result=published`，累计消息 `701` | 远控数据仍正常 |
| `1789011834.742` | `11:43:54.742` | `driver exit, clear MRC, hold brake` | 车端识别到 `bt_others=1` |
| `1789011840.983` | `11:44:00.983` | 本窗 `0`，累计仍为 `742` | 退出后手柄数据停止 |
| `1789011878.396` | `11:44:38.396` | 收到 `drive_mode=1` | 离开远控 |
| `1789011881.258` | `11:44:41.258` | 收到 `drive_mode=2` | 又一次进入远控 |
| `1789011881.574` | `11:44:41.574` | `detecting loss gap=316ms` | 开始检测数据空窗 |
| `1789011882.125` | `11:44:42.125` | `MRC1 triggered gap=867ms` | cloud 侧触发手柄 MRC1 |
| `1789011882.127` | `11:44:42.127` | `MRC status: 0->2 ... JOYSTICK_IDLE_TIMEOUT` | MRC 原因明确 |

这组日志说明：

1. 手柄数据在退出前已经正常建立，不能写成“远控没有建立”；
2. `bt_others=1` 被车端处理，但处理后没有立即看到 `drive_mode=0/1` 的完整
   远控释放闭环；
3. 随后车端又接受了 `drive_mode=2`；
4. `drive_mode=2` 生效时没有同步恢复新的 joystick 数据；
5. `cloudLinkPing` 在异常附近仍能正常返回，例如
   `1789011836.072 rtt_ms=88`，因此不是整个云连接断开；
6. 此次 MRC 的直接原因是 joystick 数据空窗，不是 `cloudLinkPing` 断连。

`drive_mode=1 -> drive_mode=2` 是车端实际收到的控制面事件。仅凭车端日志无法
判断这是页面重新点击进入、旧消息重传、会话状态机重入，还是前端退出流程中的
延迟消息。

### 3.2 第二次异常窗口：e2e 明确确认 MRC1

对应日志时间为 `1789012024` 至 `1789012026`，约北京时间 `11:47:04.983`
至 `11:47:06.042`。

车端 cloud 日志：

```text
1789012024.982  收到 drive_mode=2
1789012025.377  detecting loss gap=395ms
1789012025.926  remotejoystick 本窗 0，累计仍为 1357
1789012025.926  MRC1 triggered gap=944ms, link_ready=true
1789012025.927  MRC status: 0->2 (JOYSTICK_IDLE_TIMEOUT)
1789012031.315  新的 joystick 数据到达
1789012031.378  MRC1 cleared - joystick recovered
```

e2e 日志与该窗口对应：

```text
1789012024.983
PDriving msg: drive_mode=2, joystick_status=0, stop_flag=32

1789012024.983
Received drive_mode: 2, current driving_mode: 1

1789012025.002
mode switched 1 -> 2

1789012026.037
PDriving msg: drive_mode=2, joystick_status=255, stop_flag=32

1789012026.042
MRC active result=2 (pd=2 health=1 ...)

1789012026.042
MRC1 is triggering... (effective_mrc=2)
```

这里 `result=2`、`pd=2` 和 `effective_mrc=2` 才是 MRC1 的直接证据。

需要区分：

```text
MRC active result=1 (pd=0 health=1)
```

这是 MRC0，不是 MRC1。不能把日志中大量的 `result=1` 当成这次 MRC1。

第二次窗口在新 joystick 数据恢复后，cloud 侧 MRC1 被清除，说明该次触发符合
joystick watchdog 的“数据恢复后清除”行为，而不是持续存在的底盘故障。

## 4. `bt_others=1` 到底完成了什么

当前 cloud driving 源码对 `bt_others` 的定义是：

```text
0 = 普通手柄帧
1 = 驾驶员主动退出
2 = 手柄空闲超时
```

车端收到 `bt_others=1` 后的当前实现为：

```cpp
mrc_cloud_.store(0, std::memory_order_relaxed);
control_msg.stop_flag = 32;
joy_sm_.on_packet(1);
```

源码位置：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:925-975
```

这条路径的效果是：

1. 清除 cloud MRC；
2. 当前输出帧保持制动；
3. joystick 状态机进入 `SUPPRESSED`；
4. 当前帧继续使用原有的 `cached_drive_mode_` 逻辑；
5. 没有在同一处清除 `cached_drive_mode_`；
6. 没有在同一处完成 remote session 的 `RELEASED` 状态转换；
7. 没有返回面向前端的 `release_ack`；
8. 没有携带 session 版本阻止旧的 `drive_mode=2` 后续重入。

源码中的 `handle_onRelease()` 才会清除 `cached_drive_mode_`、清空功能缓存、
重置 joystick monitor 并返回 ACK：

```cpp
cached_drive_mode_ = 0;
...
reset_joystick_monitor();
return {{"success", true}, {"messageId", message_id}, {"ack", "ok"}};
```

源码位置：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:614-636
```

这说明当前实现中：

```text
bt_others=1
```

只是“当前手柄帧的主动退出/刹车信号”，并不等价于：

```text
onRelease 已到达
remote session 已关闭
cached_drive_mode_ 已清零
e2e 已确认退出 R 模式
旧消息已失效
```

因此，日志里出现 `driver exit` 不能作为“远控已经成功结束”的证据。

## 5. 为什么退出后仍可能触发 MRC1

### 5.1 退出信号和 session 释放是两条路径

当前代码将主动退出处理放在 `handle_remotejoystick()` 的单帧解析路径内，
而 `onRelease()`、`driveMode()` 和 watchdog 又是独立处理路径。

这会产生以下状态组合：

```text
joystick 帧收到 bt_others=1
  -> 当前帧制动、清 cloud MRC
  -> cached_drive_mode_ 仍可能为 2
  -> 后续 drive_mode=2 重新通知 e2e
  -> joystick 数据没有恢复
  -> watchdog 继续认为正在远控
  -> JOYSTICK_IDLE_TIMEOUT -> MRC1
```

本次日志实际出现了该组合的关键部分：

```text
bt_others=1
  -> drive_mode=1
  -> drive_mode=2
  -> remotejoystick 计数不增长
  -> JOYSTICK_IDLE_TIMEOUT
```

### 5.2 `drive_mode=2` 的首帧不是“数据流 ready”

e2e 收到进入 R 的控制消息：

```text
drive_mode=2, joystick_status=0, stop_flag=32
```

源码中 `PDrivingControlCallback()` 会先同步 `drive_mode`，随后对
`joystick_status != PD_DRIVING` 的消息执行制动并返回：

```cpp
if (msg->joystick_status != PD::PD_DRIVING)
{
    requested_wheel_torque = 0.0f;
    requested_gear = 2;
    xbr_deceleration = CaluXbrValueByMass();
    requested_steer = 0.0f;
    return;
}
```

源码位置：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:1216-1228
```

这类 `drive_mode=2, joystick_status=0` 消息只能说明“远控模式请求已经到达”，
不能说明：

```text
remote session 已建立
joystick 数据流已订阅
第一帧 joystick 已到达
```

如果缺少显式的 `WAITING_FIRST_FRAME` 和 `JOYSTICK_STREAM_READY` 状态，系统就
容易把“模式已进入、数据未就绪”和“控制中、数据中断”混在一起处理。

### 5.3 watchdog 看到的是数据空窗，不知道这是用户主动退出

当前 watchdog 的 MRC1 日志为：

```text
MRC1 triggered gap=867ms ... link_ready=true
MRC status: 0->2 ... JOYSTICK_IDLE_TIMEOUT
```

`link_ready=true` 表明控制连接仍在，watchdog 判断的是
`remotejoystick` 数据面是否持续到达，而不是用户是否已经点击了结束。

当退出路径没有把 session 状态改为 `RELEASED`，watchdog 无法区分：

```text
用户主动结束后不再发送 joystick
```

和：

```text
远控仍在进行，但 joystick 链路异常中断
```

于是会按照安全策略把前者也判为手柄失联 MRC1。

## 6. 双闪来源判断

本次双闪不能解释为“点击退出本身主动打开双闪”。

e2e 收到的控制输入中可以看到：

```text
drive_mode=2
joystick_status=255
stop_flag=32
hazard=0
```

也就是输入帧中的 `hazard` 并没有显示为用户主动打开双闪。

e2e 的 MRC 初始化代码明确设置：

```cpp
mrc_msg_.hazard_light_enable = true;
```

源码位置：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:717-728
```

因此，本次更合理的判断是：

```text
退出没有完成 session close
  -> joystick watchdog 触发 pd MRC1
  -> e2e effective_mrc=2
  -> MRC 安全策略打开双闪
```

双闪是 MRC1 安全输出的结果，不是用户误触的直接证据。

## 7. health_arbitrator 中的独立后续故障

在 joystick MRC1 之后，health 日志又出现了独立的 Camera10 topic timeout：

```text
1789012085.256
MRC status: 0 -> 1
PUB_TOPIC_TIMEOUT_CAMERA10_COMPRESSED_IMAGE

1789012085.906
MRC status: 1 -> 2
PUB_TOPIC_TIMEOUT_CAMERA10_COMPRESSED_IMAGE
```

同时还出现：

```text
Very low memory in system
fastlio_mapping cpu usage 163
VehicleRtspServer cpu usage 123
```

这些信息应与首次退出失败分开处理：

1. 首次异常的直接原因是远控会话未闭环后 joystick 数据空窗；
2. 首次 MRC 原因是 `JOYSTICK_IDLE_TIMEOUT`，不是 Camera10 timeout；
3. Camera10 timeout 是后续独立 health MRC，可能叠加或升级整体 MRC；
4. 低内存和高 CPU 是系统风险因素，但当前日志不足以证明它们造成了首次
   `bt_others=1` 或 `onRelease` 处理失败。

主动退出清理远控 joystick MRC 时，不能无条件清理 health、Camera、底盘或
其他独立安全故障。

## 8. 根因分层

### 8.1 已确认根因

```text
远控主动退出没有形成统一、原子的 session close。
```

具体表现：

1. `bt_others=1` 只处理当前 joystick 帧；
2. `cached_drive_mode_`、e2e driving mode 和 watchdog 生命周期没有一起释放；
3. 随后的 `drive_mode=2` 可以重新激活远控；
4. joystick 没有及时恢复时，watchdog 按远控中断流触发 MRC1。

### 8.2 高概率设计缺陷

1. `bt_others=1` 不是可靠的会话释放协议；
2. `onRelease` 没有成为前端可确认的高优先级、幂等释放消息；
3. `drive_mode=2` 没有绑定活动 `session_id`；
4. e2e 没有明确的 `REMOTE_RELEASING/REMOTE_RELEASED` 状态；
5. `joystick_status=0` 同时承担模式切换初始帧和非控制状态语义，边界不清；
6. watchdog 没有使用 session generation 拒绝旧会话的 timeout tick。

### 8.3 当前日志无法区分的链路问题

还需要前端和云端日志确认：

```text
前端点击结束时间
onRelease 发送时间
云端收到时间
云端转发时间
车端收到时间
车端 ACK 时间
```

没有这些日志，不能判断这次是：

```text
onRelease 未发送
onRelease 丢失
onRelease 排队在 joystick 后
onRelease 到达但被旧 session 丢弃
onRelease 与 drive_mode=2 乱序
```

## 9. 修复方案

### 9.1 P0：前端结束动作必须等待车端释放 ACK

前端点击结束后执行：

```text
ACTIVE
  -> EXITING
  -> 停止发送新的 joystick 控制量
  -> 发送可靠 onRelease
  -> 等待 vehicle release_ack
  -> RELEASED
```

`onRelease` 至少携带：

```text
session_id
cabin_id
release_seq
request_id
vin
```

要求：

1. `onRelease` 走高优先级可靠控制通道；
2. 不得排在历史 joystick 队列之后；
3. 失败自动重试；
4. 重复消息幂等返回成功；
5. 未收到 ACK 前前端显示“退出处理中”，不允许开启下一次远控；
6. ACK 超时不能静默销毁页面状态。

正常退出的 ACK 目标应明显小于当前约 `800~900ms` 的 joystick MRC1 窗口。

### 9.2 P0：车端实现统一 release_remote_session()

将以下路径统一到一个会话释放函数：

```text
onRelease
bt_others=1
云连接断开
会话超时
车辆人工接管
```

建议状态：

```text
IDLE -> ACTIVE -> RELEASING -> RELEASED
```

释放函数需要在同一个受控状态转换中完成：

```text
校验 session_id 和 release_seq
  -> session_state = RELEASING
  -> session_generation++
  -> 禁止当前 session 的 joystick watchdog
  -> 清空 joystick、灯光、喇叭、手刹等缓存
  -> cached_drive_mode_ = 0 或明确普通模式
  -> 清理当前 session 的 cloud MRC
  -> 向 e2e 发布 drive_mode=0/1 的安全帧
  -> 等待或确认 e2e 退出 R 模式
  -> 返回 release_ack
  -> session_state = RELEASED
```

重点是 `bt_others=1` 不能只执行：

```cpp
mrc_cloud_.store(0);
control_msg.stop_flag = 32;
```

它必须真正结束当前 session，否则后续模式消息仍然可能把 watchdog 重新打开。

### 9.3 P0：阻止旧消息和旧 watchdog 重入

增加：

```text
session_id
session_generation
release_seq
```

所有 `drive_mode=2` 和 joystick 帧都校验：

```text
消息 session == 当前活动 session
消息 generation >= 当前 generation
当前 session_state == ACTIVE
```

释放后：

1. 旧 session 的 `drive_mode=2` 必须拒绝；
2. 旧 session 的 joystick 帧不能恢复 watchdog；
3. 旧 session 的 timeout tick 不能触发 MRC1；
4. 新 session 必须经过新的 `onTakeover` 和 ready 握手。

### 9.4 P1：增加远控数据流 ready 状态

建议将远控建链拆成：

```text
IDLE
  -> TAKEOVER_ACCEPTED
  -> WAITING_FIRST_FRAME
  -> ACTIVE
  -> RELEASING
  -> RELEASED
```

在 `WAITING_FIRST_FRAME`：

1. 车辆保持制动；
2. 不触发 `JOYSTICK_IDLE_TIMEOUT`；
3. 使用单独的 `JOYSTICK_STREAM_START_TIMEOUT`；
4. 未收到首帧前不向前端报告远控 ready；
5. 只有收到首个有效 joystick 帧后才启动控制中断流 watchdog。

当前 `drive_mode=2, joystick_status=0` 只应表示模式请求或初始安全帧，
不能表示 joystick 数据面已经 ready。

### 9.5 P1：e2e 增加明确的释放语义

e2e 增加：

```text
REMOTE_ACTIVE
  -> REMOTE_RELEASING
  -> REMOTE_RELEASED
```

释放完成至少验证：

```text
driving_mode != 2
joystick_status != 255
旧 session 不再发布 PD 驱动状态
旧 session 不再触发 joystick MRC
```

不要继续让 `joystick_status=0` 同时表示：

```text
刚进入 R 的初始安全帧
用户已经释放远控
无手柄数据但仍在等待
```

建议增加独立字段或独立消息，例如：

```text
session_state = ACTIVE / RELEASING / RELEASED
control_intent = DRIVE / SAFE_HOLD / RELEASE
```

### 9.6 P1：按 MRC 来源隔离清理

主动退出允许清理：

```text
当前 remote session 的 JOYSTICK_IDLE_TIMEOUT
```

主动退出不能覆盖：

```text
health_arbitrator MRC
Camera MRC
底盘故障 MRC
emergency stop
其他独立安全故障
```

建议将 MRC 状态按来源拆分，最终输出取所有安全来源的最高等级，而不是使用
一个 `mrc_cloud=0` 覆盖其他安全状态。

### 9.7 P1：增加全链路可审计日志

前端、云端和车端至少记录：

```text
ui_exit_clicked_at
onRelease_send_at
cloud_release_received_at
cloud_release_forward_at
vehicle_release_received_at
vehicle_release_processed_at
vehicle_release_acked_at
```

每条记录同时包含：

```text
vin
session_id
cabin_id
release_seq
request_id
message_id
retry_count
session_state_before
session_state_after
cached_drive_mode
joystick_rx_seen
last_joystick_age_ms
```

`remotejoystick` 还应记录：

```text
publisher
route
vehicle_handler
drop_reason
transport_seq
source_seq
session_id
```

这样可以直接区分控制面正常、数据面断流和释放消息丢失。

## 10. 验收标准

| 场景 | 预期结果 |
|---|---|
| 正常点击结束 | 车端收到并 ACK `onRelease`，无 `JOYSTICK_IDLE_TIMEOUT`，无因退出导致的 MRC1 |
| `bt_others=1` 到达但 `onRelease` 丢失 | 车端仍完成 session close，不再接受旧 session 的 `drive_mode=2` |
| `bt_others=1` 丢失但 `onRelease` 到达 | 正常释放，ACK 幂等返回 |
| `onRelease` 重复发送 | 只执行一次状态转换，重复请求返回成功 |
| release 与 watchdog 同时发生 | release 成功后旧 generation 的 timeout tick 不得触发 MRC1 |
| 退出后旧 `drive_mode=2` 延迟到达 | 被 session 校验拒绝 |
| 新 session 尚未收到首帧 | 保持制动，报首帧启动失败，不报控制中手柄失联 |
| 首帧到达后断流 | 才允许触发 `JOYSTICK_IDLE_TIMEOUT` |
| health MRC 已存在时退出远控 | 只清理远控来源，不清理独立 health MRC |
| e2e 释放确认 | `driving_mode` 退出 R，旧 session 不再发布 PD 驱动状态 |
| 正常退出双闪 | 不因退出动作自动打开双闪；只有真实 MRC 安全策略才打开 |

## 11. 最终判断

本次 0909 新分支事件可以定性为：

```text
远控退出没有完成完整 session close。
bt_others=1 被车端识别，但只完成了当前帧制动和 cloud MRC 清理；
后续 drive_mode=2 使远控 watchdog 再次生效；
joystick 数据空窗后触发 JOYSTICK_IDLE_TIMEOUT；
e2e 以 pd=2 / result=2 执行 MRC1，双闪是 MRC 安全输出。
```

修复优先级：

1. 前端结束后立即发送带 session 信息的可靠 `onRelease`，等待车端 ACK；
2. 车端统一 `bt_others=1`、`onRelease` 和断链释放路径；
3. `drive_mode=2` 必须绑定当前有效 session，拒绝旧消息重入；
4. e2e 增加明确的 release 状态和释放确认；
5. 首帧之前使用独立的 stream-start 状态，不把未 ready 当作控制中断流；
6. 增加完整的发送、转发、到达、处理、ACK 日志。

在没有前端和云端链路日志前，不应写成“前端一定没有发送 onRelease”。
当前证据已经足够说明系统的退出协议没有闭环，修复重点应放在 session 生命周期、
消息优先级、幂等 ACK 和 watchdog 竞态上。
