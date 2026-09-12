# 更换驾驶仓退出与未切换驾驶仓触发 MRC1 分析

分析日期：`2026-09-09`

方案补充日期：`2026-09-10`

事件日期：`2026-09-09`、`2026-09-10`

状态：`observed / cabin-switch not required / joystick-stream lifecycle failure`

## 1. 事件描述

用户反馈：

```text
车辆不更换，只更换驾驶仓。
旧驾驶仓操作结束后更换新的驾驶仓。
新驾驶仓进入远控，正常操作后点击手柄退出。
退出后车端双闪，并触发 MRC。
该现象可稳定复现。
```

本次分析的车辆标识相同：

```text
VIN: L584C4VC5SD001331
旧驾驶仓: JYS002
新驾驶仓: GQ004
```

输入日志：

```text
/Users/minyi/Downloads/ztd_cloud_driving_20260909185341.log
/Users/minyi/Downloads/e2e_control_20260909185341.log
/Users/minyi/Downloads/ztd_cloud_driving_20260910094955.log
```

其中 `20260910094955` 为 GQ002、未切换驾驶仓的新增对照样本，仅提供
`ztd_cloud_driving` 日志，没有配套 e2e 日志。

## 2. 结论先行

原 GQ004 事件不是“退出动作正常触发 MRC”，也没有证据表明是用户误触双闪。

车端在 GQ004 点击退出时，没有执行预期的 `bt_others=1` 驾驶员主动退出逻辑，
而是先检测到 `remotejoystick` 数据流停止，随后因 `JOYSTICK_IDLE_TIMEOUT` 触发
MRC1。双闪是 MRC1 安全输出的结果。

核心因果链为：

```text
GQ004 退出时未被车端识别为 bt_others=1
  -> remotejoystick 数据流停止
  -> 车端检测到手柄超时
  -> cloud_driving MRC 内部状态 0 -> 2
  -> e2e 收到 pd=2，result=2
  -> e2e 进入 MRC1 安全输出
  -> 安全输出强制打开双闪
```

新增 GQ002 对照日志进一步证明：**切换驾驶仓不是触发该类问题的必要条件**。
GQ002 未发生驾驶仓切换，但 `remotejoystick` 从进程启动到日志结束累计始终为 `0`，
每次进入 `drive_mode=2` 后仍在约 `0.84~0.93s` 触发
`JOYSTICK_IDLE_TIMEOUT`。

这还暴露出现场运行版本不一致：当前源码和 9 月 9 日同车日志都表现为“首帧到达
前不启动 idle watchdog”；9 月 10 日 GQ002 日志却从进入 R 直接计时。两次日志均
来自 `szsc_ipc`、`/aura/`、`dp006` 和同一 VIN，因此应优先核查镜像回退、
overlay/install 选错或节点重启后加载了另一份旧二进制。

两组样本的共同根因条件是：

```text
远控模式已经进入或仍保持
  + remotejoystick 数据流未建立或已停止
  + 有效主动退出信号没有在超时前到达车端
  -> 车端 joystick watchdog 触发 MRC1
```

两组样本的差异是：

1. GQ004 的数据流曾正常建立，之后多次中断，最后退出时停止且未见
   `bt_others=1`；
2. GQ002 的数据流从未建立，问题发生在 `bt_others` 解析之前，车端连一条
   `remotejoystick` 都没有收到。

因此，原先“只排查 GQ004 的 `bt_others` 字段兼容”的范围过窄。应将根因定位扩大到
驾驶仓发布、云端路由/订阅、会话建立和退出整个 `remotejoystick` 数据流生命周期。

现有日志可以确认车端侧的触发原因，但不能单独区分：

1. 驾驶仓根本没有发送对应 `remotejoystick` 或退出帧；
2. 驾驶仓发送了，但云端没有路由到目标车辆；
3. 云端已转发，但消息未到达车端；
4. GQ004 退出帧到达车端，但报文结构与解析约定不一致，导致
   `bt_others` 被解析为默认值 `0`。

GQ004 仍需重点核对退出流程的报文发送顺序和字段结构；GQ002 则优先排查
远控数据流是否成功发布、订阅和绑定到目标 VIN。

## 3. 驾驶仓切换证据

同一 VIN 在日志中先后出现 JYS002 和 GQ004：

| 时间戳 | 北京时间 | 驾驶仓 | 事件 |
|---:|---|---|---|
| `1788954513.437` | `19:48:33.437` | `JYS002` | `onRelease` |
| `1788954528.686` | `19:48:48.686` | `GQ004` | `onTakeover` |

两次 GQ004 接管记录均明确打印：

```text
onTakeover 已重置缓存 + MRC, drive_mode=0(M)
```

原始日志：

```text
ztd_cloud_driving_20260909185341.log:2577-2593
```

因此，当前证据不支持“旧驾驶仓遗留 MRC 状态，切换后直接带入新驾驶仓”的判断。
GQ004 接管时车端已经执行过缓存和 MRC 重置。

## 4. GQ004 最后一次退出时间线

### 4.1 最后一帧手柄数据正常到达

GQ004 最后一帧被车端接收、解析并发布：

```text
1788954809.677829683
transport_seq=10501
message_id=60f71970-f36a-414e-be42-dfcad5c964a6
frame_bytes=1818

1788954809.677917749
handler_start ... input_fields=8

1788954809.678045194
handler_end result=published
```

原始日志：

```text
ztd_cloud_driving_20260909185341.log:3001-3005
```

之后累计消息数一直保持 `10501`，车端没有再收到新的
`remotejoystick` 数据帧。

### 4.2 先出现数据流中断，再触发 MRC1

```text
1788954810.013355564
[joystick] detecting loss gap=335ms last_joystick_age_ms=335

1788954810.451895492
[remotejoystick] 本窗 127 累计 10501 (25.4 msg/s)

1788954810.539259764
[cloudLinkPing] rtt_ms=87

1788954810.562009227
[joystick] MRC1 triggered gap=884ms ... link_ready=true

1788954810.563623165
[MRC] status: 0→2 (→JOYSTICK_IDLE_TIMEOUT)
```

原始日志：

```text
ztd_cloud_driving_20260909185341.log:3006-3011
```

这里有两个重要事实：

1. `remotejoystick` 计数停止在 `10501`，证明超时是由手柄数据流停止造成的；
2. 同时 `cloudLinkPing` 返回 `87ms` 且 `link_ready=true`，说明不是整个云连接断开，
   更像是远控数据发布、转发或退出帧处理链路异常。

### 4.3 e2e 确认是真正的 MRC1

E2E 在 MRC 触发后记录：

```text
1788954810.342636216
PDriving msg: drive_mode=2, joystick_status=255,
gear=2, stop_flag=32, hazard=0

1788954810.578204564
MRC active result=2 (pd=2 health=1 ...)

1788954810.578287366
MRC1 is triggering... (effective_mrc=2)
```

原始日志：

```text
e2e_control_20260909185341.log:154241
e2e_control_20260909185341.log:154265-154266
```

本次真正的 e2e MRC1 判断依据是：

```text
result=2
pd=2
effective_mrc=2
MRC1 is triggering
```

此前大量出现的：

```text
MRC active result=1 (pd=0 health=1)
```

是 e2e MRC0，不是本次 MRC1。

## 5. 双闪来源

MRC 触发前的 PDriving 输入中明确记录：

```text
hazard=0
```

因此，现有 e2e 日志不支持“用户退出时主动打开双闪”的判断。

E2E 的 MRC 初始化代码会强制设置：

```cpp
mrc_msg_.hazard_light_enable = true;
```

代码位置：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:717-723
```

所以双闪是 MRC1 安全策略的输出，不是退出操作本身的正常结果。

## 6. 为什么判断为“退出帧未生效”

车端对 `bt_others` 的约定为：

| `bt_others` | 语义 |
|---:|---|
| `0` | 正常手柄帧，恢复手柄失联检测 |
| `1` | 驾驶员主动退出，清除 MRC，暂停失联检测 |
| `2` | 手柄空闲超时，立即触发 MRC1 |

车端代码中，只有 `bt_others=1` 才会打印：

```text
[joystick] driver exit, clear MRC, hold brake
```

并执行：

```cpp
mrc_cloud_.store(0, std::memory_order_relaxed);
control_msg.stop_flag = 32;
joy_sm_.on_packet(1);
```

代码位置：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:925-975
```

JYS002 的远控过程中，车端曾多次正确识别主动退出：

```text
1788953472.503650880
1788953516.277460139
1788953902.792010796
```

原始日志：

```text
ztd_cloud_driving_20260909185341.log:1322
ztd_cloud_driving_20260909185341.log:1435
ztd_cloud_driving_20260909185341.log:2284
```

但 GQ004 最终退出窗口中没有任何同类日志，反而直接出现：

```text
MRC1 triggered ... JOYSTICK_IDLE_TIMEOUT
```

因此可以确认：这次车端没有按主动退出路径处理。

## 7. `onRelease` 不是本次触发原因

GQ004 的 `onRelease` 到达车端的时间为：

```text
1788954854.304898461
```

MRC1 触发时间为：

```text
1788954810.562009227
```

两者相差约 `43.74s`。

车端收到 `onRelease` 后才打印：

```text
onRelease 已重置缓存 + MRC, drive_mode=0(M)
```

原始日志：

```text
ztd_cloud_driving_20260909185341.log:3030-3036
```

因此 `onRelease` 是 MRC 触发后的清理动作，不能阻止前面的手柄超时。
日志中 `onRelease` 请求体的业务时间戳为 `2026-09-09 19:53:37.248`，
但不能直接用它与车端日志时间计算传输耗时。新增样本表明驾驶仓业务时间与车端
日志时间稳定相差约 `37s`，更符合设备时钟偏差，而不是每条消息固定传输 `37s`。

应使用车端同一时钟下的时间关系判断先后：

```text
车端 MRC1:          2026-09-09 19:53:30.562
车端收到 onRelease: 2026-09-09 19:54:14.305
同一时钟差值:       43.743s
```

该差值只证明 `onRelease` 到达车端时 MRC1 已经发生，不能仅凭现有日志把
`43.743s` 全部归因于云端传输延迟。

## 8. 新驾驶仓在退出前已经存在手柄流不稳定

GQ004 接管后，最终退出之前已经出现多次相同类型的手柄超时：

| 时间戳 | gap | 结果 |
|---:|---:|---|
| `1788954560.103` | `869ms` | MRC1 |
| `1788954712.045` | `851ms` | MRC1 |
| `1788954729.011` | `859ms` | MRC1 |
| `1788954810.562` | `884ms` | MRC1 |

原始日志：

```text
ztd_cloud_driving_20260909185341.log:2681-2682
ztd_cloud_driving_20260909185341.log:2875-2876
ztd_cloud_driving_20260909185341.log:2903-2904
ztd_cloud_driving_20260909185341.log:3010-3011
```

其中前三次随后自动恢复，最后一次在退出后没有新的手柄帧，因此保持 MRC1。

这说明 GQ004 的问题不只是最后一次点击退出时的偶发丢包；新驾驶仓在整个远控
期间就存在手柄数据流间断，退出动作只是让该问题最终暴露为不可恢复的 MRC1。

## 9. GQ002 未切换驾驶仓对照样本

### 9.1 驾驶仓和车辆身份

新增日志中的车辆仍为：

```text
VIN: L584C4VC5SD001331
驾驶仓: GQ002
```

生命周期消息中只出现 GQ002，没有出现 JYS002、GQ004 或其他驾驶仓：

```text
ztd_cloud_driving_20260910094955.log:313-318  onRelease GQ002
ztd_cloud_driving_20260910094955.log:323-328  onTakeover GQ002
```

因此，这份日志支持用户描述的“未切换驾驶仓”。它同时否定了“必须先从旧驾驶仓
切换到新驾驶仓才会触发”的假设。

### 9.2 `remotejoystick` 从未到达车端

进程在 `2026-09-10 09:49:57` 启动。从第一条计数日志到最后一条计数日志，
始终是：

```text
[remotejoystick] 本窗 0 累计 0 (0.0 msg/s)
```

原始日志：

```text
ztd_cloud_driving_20260910094955.log:24-216
ztd_cloud_driving_20260910094955.log:225-293
ztd_cloud_driving_20260910094955.log:309-389
```

整份日志也没有任何 `remotejoystick-observation handler_start/handler_end`，
没有任何有效 `message_id/source_seq`，并且没有：

```text
[joystick] driver exit, clear MRC, hold brake
```

这不是 `bt_others` 被解析为 `0` 的直接证据，而是更早一层的问题：
`handle_remotejoystick()` 根本没有被调用，无法进入 `bt_others` 解析分支。

### 9.3 四次进入 R 后稳定触发 cloud 侧 MRC1

| 北京时间 | 进入 `drive_mode=2` | `detecting loss` | MRC1 | 从进入 R 到 MRC1 |
|---|---:|---:|---:|---:|
| `09:57:06~09:57:07` | `1789005426.375` | `1789005426.681` | `1789005427.218` | `843ms` |
| `09:57:50~09:57:51` | `1789005470.847` | `1789005471.166` | `1789005471.709` | `862ms` |
| `09:58:07~09:58:08` | `1789005487.338` | `1789005487.723` | `1789005488.264` | `926ms` |
| `09:58:43~09:58:44` | `1789005523.798` | `1789005524.168` | `1789005524.706` | `908ms` |

原始日志：

```text
ztd_cloud_driving_20260910094955.log:218-225
ztd_cloud_driving_20260910094955.log:252-259
ztd_cloud_driving_20260910094955.log:274-281
ztd_cloud_driving_20260910094955.log:323-344
```

四次 MRC 日志都有相同特征：

```text
last_message_id=
last_source_seq=unknown
last_correlation_id=unknown
link_ready=true
```

这证明 watchdog 的计时基准不是最后一帧手柄消息，而是本次进入 R 的时间。

由于新增样本没有配套 `e2e_control` 日志，这里能确认的是
`cloud_driving` 内部 `mrc_joy=2 / JOYSTICK_IDLE_TIMEOUT`。不能仅凭该文件继续
确认 e2e 是否收到 `pd=2`、是否进入最终 MRC1 输出或是否实际打开双闪。

前三次进入 R 前，本进程内没有出现 `onTakeover`。在
`1789005523.309~1789005523.371` 收到一组新的 GQ002 `onTakeover` 后，第四次
进入 R 仍然复现。因此：

1. 当前车端允许在没有已确认活动会话的情况下接受 `drive_mode=2`；
2. 即使重新执行 GQ002 `onTakeover`，也没有建立 `remotejoystick` 数据流；
3. `onTakeover` 只重置车端缓存和 MRC，不代表驾驶仓到车辆的数据流已经 ready。

### 9.4 普通控制通道正常，不等于 joystick 数据流正常

第四次进入 R 后，车端仍能收到：

```text
epb_cmd=0
horn_cmd=0
lbh_li_cmd=0
hbh_li_cmd=0
aux_li_cmd=0
green_light_cmd=0
hazard_li_cmd=0
```

同时 `cloudLinkPing` 大部分 RTT 约为 `46~122ms`。这说明普通
`parallelDrivingControl` 和云链路探活仍可用，但 `remotejoystick` 业务流为零。
不能用 ping 正常或普通控制指令可达来推断 joystick 路由正常。

`1789005508.001` 确实出现过一次：

```text
Failed to receive full body
Connection marked unhealthy
VEHICLE_RECEIVE_TIMEOUT
```

约 `5s` 后重连成功。但它发生在前三次 joystick MRC1 之后，不是前三次触发的原因；
重连后第四次仍然在 `remotejoystick=0` 的情况下触发 MRC1。

### 9.5 `mrc_status=0` 不能清除 joystick MRC

第三次 MRC1 后，云端发送：

```text
1789005491.749  inputs={"controlType":"mrc","mrc_status":0}
1789005491.749  [处理] MRC cloud=0 joy=2
```

这说明页面或云端只清除了 `mrc_cloud_`，但 joystick 状态机仍为 `2`。
因此在数据流未恢复、未退出 R 模式的情况下，单独下发 `mrc_status=0` 不是有效恢复
手段。日志中真正清除前两次 joystick MRC 的动作是退出 R：

```text
drive_mode=1
  -> 离开远控模式
  -> reset_joystick_monitor()
  -> MRC status 2->0
```

### 9.6 运行二进制与当前源码行为不一致

当前工作区代码明确规定：进入 R 只建立监控条件，首帧有效 joystick 到达前直接
返回，不应触发 `JOYSTICK_IDLE_TIMEOUT`：

```cpp
if (!joystick_rx_seen_.load(std::memory_order_relaxed) || last_ms <= 0)
{
    return;
}
```

代码位置：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:1479-1487
```

该保护由提交引入：

```text
c7e087e5126c73fdd18dd49a6b0048232f662409
fix: pd mrc1
2026-09-04 13:28:55 +0800
```

而提交前的实现会在没有首帧时使用 `remote_mode_start_steady_ms_` 作为计时基准：

```cpp
const int64_t health_base_ms = last_ms > 0 ? last_ms : mode_start_ms;
gap = health_base_ms > 0 ? std::max<int64_t>(0, now_ms - health_base_ms) : 0;
```

当前源码中 `last_joystick_steady_ms_` 和 `joystick_rx_seen_` 只会在
`handle_remotejoystick()` 收到有效 R 模式帧时同时更新，重置时则分别置为 `0`
和 `false`。GQ002 日志没有一次 handler 调用，却仍从 R 模式开始计时。

9 月 9 日同一车辆的 GQ004 日志提供了更强的反向证据：

```text
1788954528.718  GQ004 onTakeover，重置缓存和 MRC
1788954529.085  drive_mode=2，进入 R
1788954530.447  remotejoystick 本窗 0，累计 8459
1788954535.436  remotejoystick 本窗 0，累计 8459
1788954540.434  remotejoystick 本窗 0，累计 8459
1788954545.418  remotejoystick 本窗 0，累计 8459
1788954545.433  新会话首帧到达，transport_seq=8460
```

从进入 R 到新会话首帧到达相隔 `16.348s`。这期间没有出现
`JOYSTICK_IDLE_TIMEOUT`。若运行的是提交前逻辑，应在进入 R 后约 `0.8~0.9s`
触发，而不可能等待 16 秒。首帧到达后，后续数据流中断又在
`1788954560.104` 正常触发 `JOYSTICK_IDLE_TIMEOUT`，说明该进程的 watchdog
并未失效，而是明确执行了“首帧前不检测、首帧后才检测”的新逻辑。

对应证据：

```text
ztd_cloud_driving_20260909185341.log:2588-2598  onTakeover 后进入 R
ztd_cloud_driving_20260909185341.log:2630-2635  连续无新帧，16.348s 后首帧到达
ztd_cloud_driving_20260909185341.log:2682       首帧后的真实断流触发 MRC
```

两份日志的进程环境又完全指向同一车端：

```text
Machine: szsc_ipc
cwd: /aura/
stream app: dp006
VIN: L584C4VC5SD001331
```

因此，同一车辆/机器在 9 月 9 日表现为包含首帧保护的新逻辑，9 月 10 日却表现为
提交前的旧逻辑。GQ002 日志中的四个 `gap` 与旧逻辑完全吻合，优先级最高的判断
不再只是“可能没有升级”，而是现场运行产物在两次启动之间发生了变化：

1. 9 月 10 日部署镜像相对 9 月 9 日发生回退；
2. 容器或主机存在多个 overlay/install 工作区，节点启动时 source 到旧产物；
3. `ros2 launch` 找到的包路径与人工核查源码/构建目录不是同一份；
4. 节点重启后加载了不同镜像、包或挂载目录；
5. 若实际 ELF 确认已包含该提交，再排查两个原子变量被异常写入
   或实际执行文件与检查文件不是同一构建目标。

当前日志没有打印 build SHA，无法仅凭日志确认 9 月 9 日和 9 月 10 日实际运行版本。
现场复现时必须同时留存以下结果，不能只查看工作区源码：

```text
容器/部署镜像 digest
ros2 pkg prefix ztd_cloud_driving
/proc/<pid>/exe 的真实路径
实际 ELF 的 SHA256
AMENT_PREFIX_PATH/COLCON_PREFIX_PATH
/aura/install 下同名可执行文件及其 SHA256
```

节点启动日志应固定打印 Git SHA、构建时间、镜像 digest、包 prefix 和 ELF SHA256，
使日志本身可以完成版本闭环。

### 9.7 两组样本对比

| 维度 | GQ004 切换后退出 | GQ002 未切换 |
|---|---|---|
| 是否切换驾驶仓 | 是，JYS002 -> GQ004 | 否，只出现 GQ002 |
| joystick 流是否建立 | 建立过，正常约 `30 msg/s` | 从未建立，累计始终为 `0` |
| 触发基准 | 最后一帧 joystick | 进入 R 的时间 |
| MRC gap | `851~884ms` | `843~926ms` |
| 最后一帧 ID | 有 message ID/source seq | 空/unknown |
| `bt_others=1` | 最终退出窗口未见 | 无数据到 handler，无法解析 |
| 云连接 | MRC 时 ping 正常 | MRC 时 ping 正常；另有一次较晚断连 |
| 直接问题 | 数据流中断且退出信号未生效 | 数据流未建立且车端仍进入 R |

共同点不是“换驾驶仓”，而是：

```text
remotejoystick 不可用
  + 远控会话/模式状态仍允许 watchdog 生效
  + 车端未在超时前获得有效退出或未建立状态
```

### 9.8 驾驶仓与车端存在约 37 秒时钟偏差

GQ002 生命周期消息的 payload 时间与车端接收时间稳定相差约 `37s`：

| 消息 | payload 时间 | 车端接收时间 | 差值 |
|---|---|---|---:|
| `onRelease` | `09:57:56.728` | `09:58:33.762` | `37.034s` |
| `onTakeover` | `09:58:06.281` | `09:58:43.309` | `37.028s` |

GQ004 的 `onTakeover/onRelease` 也约相差 `37.057s`。这更符合驾驶仓与车端时钟
未同步，不能把 payload 时间和车端 epoch 的差直接当作网络延迟。

后续应统一 NTP/PTP，或至少在全链路使用同一个 `correlation_id` 并分别记录
单调时钟耗时。跨设备墙钟只能用于粗略定位，延迟判断必须基于同节点单调时钟或
服务端收发时间。

## 10. 当前根因定位

### 已确认

1. 车辆 VIN 未变，只发生驾驶仓从 JYS002 到 GQ004 的切换。
2. GQ004 `onTakeover` 时已经清理缓存和 MRC。
3. 最后一帧手柄数据后，`remotejoystick` 计数停止。
4. 云链路探测仍正常，最终 `rtt_ms=87`，`link_ready=true`。
5. 车端触发原因为 `JOYSTICK_IDLE_TIMEOUT`。
6. e2e 进入 `result=2 / pd=2` 的 MRC1。
7. 双闪来自 MRC 安全输出，触发前普通输入的 `hazard=0`。
8. 车端没有执行 `bt_others=1` 主动退出分支。
9. GQ002 未切换驾驶仓也能触发同类 joystick MRC。
10. GQ002 的 `remotejoystick` 从未到达车端，累计始终为 `0`。
11. GQ002 的运行行为与当前源码及 9 月 9 日同车行为均不一致，现场运行产物发生
    回退或启动路径选中旧 overlay 的可能性高。

### 尚不能仅凭现有三份日志确认

1. GQ004 是否实际发送了 `bt_others=1`；
2. 云端是否收到并转发了该退出帧；
3. 退出帧是否因报文结构、字段类型或字段嵌套不兼容而被车端解析成 `0`。
4. GQ002 驾驶仓是否实际开始发布 `remotejoystick`。
5. 云端是否为 GQ002 建立了正确的 VIN 路由/订阅。
6. 现场运行二进制是否包含提交 `c7e087e51`。

当前代码先选择 `joystickdata` 嵌套对象：

```cpp
const json& jd = inputs.contains("joystickdata")
    ? inputs["joystickdata"]
    : inputs;
const uint8_t bt_others_raw =
    static_cast<uint8_t>(jd.value("bt_others", 0));
```

代码位置：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:894-895
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:930
```

如果 GQ004 的报文同时存在 `joystickdata`，但将 `bt_others` 放在外层，
当前代码就可能取不到该字段并默认解析为 `0`。这是需要重点核对的协议兼容风险，
但现有车端日志没有打印完整 JSON，因此暂不能直接定案。

## 11. 建议补充的观测

为区分“未发送、转发丢失、解析不兼容”，建议在三段链路分别补充：

1. GQ004 驾驶仓：
   - 退出按钮事件时间；
   - `bt_others` 原始值；
   - 完整报文结构；
   - 发送结果、消息 ID、发送序号；
   - 停止周期 joystick 发布与发送退出帧的先后关系。
2. 云端转发层：
   - 收到的原始报文；
   - 转发目标 VIN；
   - 转发结果和 ACK；
   - 消息 ID、source sequence、correlation ID。
3. 车端 `cloud_driving`：
   - `bt_others` 原始值；
   - 是否存在 `joystickdata`；
   - `bt_others` 所在层级；
   - 解析后的 `bt_others_raw`；
   - 每次退出帧的完整 message ID。
   - 节点启动时打印 Git SHA、构建时间、包版本和镜像摘要；
   - `onTakeover` 后记录 session、订阅建立状态和首帧等待状态；
   - 首帧到达时记录 `JOYSTICK_STREAM_READY` 及端到端 correlation ID。

建议将主动退出判定改为兼容且可观测的方式：同时检查顶层和
`joystickdata` 内的 `bt_others`，并在日志中打印最终采用的来源和值。

## 12. `onRelease` 优先级结论

### 12.1 应当优先，但不是简单提高线程优先级

`onRelease` 应作为当前远控会话的权威结束信号。车端确认它属于当前活动会话后，
应优先于该会话后续的 `JOYSTICK_IDLE_TIMEOUT` 判定，立即进入安全释放状态。

这里的“优先”是会话状态机上的语义优先：

```text
紧急停车/车辆健康安全状态
  > 当前会话的有效 onRelease 或 bt_others=1
  > 当前会话的 joystick 超时判定
  > 普通 remotejoystick 控制帧
```

`onRelease` 不能无条件清除车辆健康、紧急停车等其他来源的 MRC，只能结束对应的
远控会话，并清理该会话产生的 joystick 失联状态。

### 12.2 本次仅调整车端响应优先级仍然不够

本次时间关系为：

| 事件 | 时间戳 |
|---|---:|
| 最后一帧 `remotejoystick` | `1788954809.677829683` |
| `JOYSTICK_IDLE_TIMEOUT` 触发 MRC1 | `1788954810.562009227` |
| 车端收到 `onRelease` | `1788954854.304898461` |

`onRelease` 比 MRC1 晚到约 `43.74s`。因此，即使车端在收到 `onRelease` 后立即
执行，也无法阻止此前已经发生的 MRC1。

修复必须同时保证：

1. 前端点击结束后立即生成释放请求；
2. 云端优先、可靠地转发释放请求；
3. 前端在收到车端释放 ACK 前不能直接停止全部退出信号；
4. 车端收到有效释放请求后原子地关闭当前会话的 joystick watchdog。

### 12.3 当前车端实现的两个缺口

当前 `handle_onRelease()` 只修改缓存并重置 MRC：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:614-636
```

它没有立即向 e2e 发布一帧明确的安全退出指令，例如：

```text
drive_mode=0
joystick_status=0
stop_flag=32
```

此外，`ping_joystick()` 在持有 `vehicle_cmd_mutex_` 时计算 `gap`，随后释放锁，
再调用 `joy_sm_.on_tick(gap)`：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:1448-1490
```

因此存在以下竞争窗口：

```text
watchdog 计算出超时 gap
  -> watchdog 暂时释放 vehicle_cmd_mutex_
  -> onRelease 重置会话和 joystick 状态
  -> 已在途的 watchdog 再调用 on_tick(gap)
  -> 状态可能重新进入 DETECTING/MRC1
```

释放动作和 watchdog 判定需要通过会话状态或 generation 做一致性保护。

## 13. 修复方案

### 13.1 退出协议职责

建议明确三个信号的职责：

| 信号 | 职责 |
|---|---|
| `onRelease` | 当前会话的权威、可靠结束信号 |
| `bt_others=1` | 随 joystick 数据发送的低延迟退出冗余信号 |
| `JOYSTICK_IDLE_TIMEOUT` | 前两个退出信号均未到达时的安全兜底 |

正常主动退出不应依赖“停止 joystick 数据后让车端自行猜测”。停止数据只能被解释
为失联，不能区分主动退出、驾驶仓故障和链路异常。

### 13.2 推荐退出时序

```text
驾驶员点击结束
  -> 前端进入 EXITING，停止输出驱动量并保持制动
  -> 连续发送若干帧 bt_others=1 + stop_flag=32
  -> 同时立即发送 onRelease(session_id, cabin_id, release_seq)
  -> 云端通过可靠控制通道优先转发，超时自动重试
  -> 车端校验请求属于当前活动 session
  -> 车端原子切换 ACTIVE -> RELEASING/RELEASED
  -> 关闭当前 session 的 joystick watchdog
  -> 发布 drive_mode=0、joystick_status=0、stop_flag=32
  -> 返回包含 session_id/release_seq 的 vehicle ACK
  -> 前端收到 ACK 后停止 joystick 数据流并完成页面退出
```

如果在约定时间内未收到 ACK，前端应继续发送安全退出帧并重试 `onRelease`，而不是
直接停止所有消息。建议将正常退出端到端 ACK 目标控制在 `200ms` 内，并确保明显
小于当前约 `800ms` 的 joystick MRC1 触发窗口。

### 13.3 车端修改

1. 引入远控会话状态：

```text
session_id
cabin_id
session_generation
session_state = IDLE / ACTIVE / RELEASING / RELEASED
```

`onTakeover` 创建新 generation，`onRelease` 只能释放匹配的活动 session。
重复的 `onRelease` 应幂等返回成功；旧驾驶仓延迟到达的 release 应记录并忽略，
不能清除新驾驶仓的控制状态。

2. 将 `onRelease` 改为原子安全转换：

```text
校验 session
  -> session_state=RELEASED
  -> cached_drive_mode_=0
  -> joystick watchdog=SUPPRESSED
  -> 清空当前会话控制缓存
  -> 发布安全退出帧
  -> 返回 ACK
```

释放时应将 joystick 状态置为 `SUPPRESSED`，而不是先重置为可再次检测的
`NORMAL`。只有下一次有效 `onTakeover` 才重新初始化为 `NORMAL`。

3. 消除 watchdog 竞态，可选择以下一种实现：

```text
方案 A：在 vehicle_cmd_mutex_ 保护范围内完成 active-session 检查和 on_tick；
方案 B：计算 gap 时记录 session_generation，on_tick 前再次确认 generation
        未变化且 session_state 仍为 ACTIVE；
方案 C：让 JoyMrcStateMachine::on_tick 接收 generation/active 条件并原子校验。
```

推荐方案 B，锁持有时间短，也能明确拒绝旧会话已经在途的 timeout tick。

4. `onRelease` 收到后立即发布一帧：

```text
drive_mode=0
joystick_status=0
stop_flag=32
```

不能只修改 `cached_drive_mode_`，否则 joystick 数据已经停止时，e2e 未必能立即
收到退出模式和制动意图。

5. 按来源清理 MRC：

```text
允许清理：当前 session 的 JOYSTICK_IDLE_TIMEOUT
禁止覆盖：health/arbitrator/emergencystop 等独立安全原因
```

当前 `onRelease` 无条件执行 `mrc_cloud_.store(0)`，需要结合 MRC 来源拆分状态，
避免释放远控会话时同时取消仍然有效的安全停车请求。

6. 兼容 `bt_others` 的顶层和嵌套格式：

```text
优先读取 joystickdata.bt_others
缺失时回退读取 inputs.bt_others
记录字段来源、原始类型、解析值和 message_id
```

7. 增加远控首帧状态机，不把“数据流尚未建立”当成“控制中失联”：

```text
IDLE
  -> onTakeover/session accepted
  -> WAITING_FIRST_FRAME
  -> first valid remotejoystick
  -> ACTIVE
```

在 `WAITING_FIRST_FRAME`：

- 车辆保持制动，不执行驱动量；
- 不触发 `JOYSTICK_IDLE_TIMEOUT`；
- 使用单独的 `JOYSTICK_STREAM_START_TIMEOUT` 上报启动失败；
- 启动失败后拒绝进入 ACTIVE，并要求前端重新建链或退出；
- 只有 ACTIVE 状态下的帧中断才使用 `JOYSTICK_IDLE_TIMEOUT`。

当前 `c7e087e51` 已避免首帧前误触发 MRC1，但会无限等待。应在该保护基础上增加
明确的首帧启动超时和失败 ACK，而不是恢复提交前的 R 模式计时逻辑。

8. 增加会话准入校验：

```text
无活动 onTakeover/session -> 拒绝 drive_mode=2
session 已建立但 joystick 未 ready -> 保持 WAITING_FIRST_FRAME
session + first frame 均确认 -> 才允许 ACTIVE
```

这可以直接阻止 GQ002 日志中“本进程未收到 onTakeover，仍接受前三次
`drive_mode=2`”的状态组合。

### 13.4 前端和云端修改

1. 前端点击结束后立即发送 `onRelease`，不能等待页面销毁、定时清理或其他业务
   收尾完成后再发送。
2. 在收到 vehicle ACK 前保持 `EXITING` 状态，重复发送制动退出帧，禁止继续输出
   油门、转向和挡位指令。
3. 云端将 `onRelease` 放到独立可靠控制通道或高优先级队列，不应排在历史
   joystick 消息之后。
4. `onRelease` 必须带 `session_id/cabin_id/release_seq`，云端和车端均进行
   去重、幂等和活动会话校验。
5. 全链路记录四个时间点：

```text
ui_exit_clicked_at
cloud_release_received_at
vehicle_release_received_at
vehicle_release_acked_at
```

同时记录 `session_id`、驾驶仓、VIN、release sequence、消息 ID 和重试次数。

6. 前端不能只以 `drive_mode=2` 请求成功作为“远控已进入”。必须等待车端返回：

```text
session accepted
joystick subscription/routing established
first valid joystick received
JOYSTICK_STREAM_READY
```

在 ready ACK 前禁用油门、挡位和转向操作，并显示建链失败状态。

7. 云端分别监控控制面和数据面：

```text
control plane: onTakeover/onRelease/parallelDrivingControl/cloudLinkPing
data plane:   remotejoystick publish/route/send/vehicle-handler
```

控制面正常不能掩盖数据面 `0 msg/s`。

### 13.5 验收用例

| 场景 | 预期结果 |
|---|---|
| 正常点击结束 | 无 `JOYSTICK_IDLE_TIMEOUT`，无 MRC 双闪，车端返回 release ACK |
| `bt_others=1` 丢失但 `onRelease` 到达 | 正常安全退出，不触发 joystick MRC1 |
| 首次 `onRelease` 丢失 | 云端重试成功，前端在 ACK 前保持安全退出帧 |
| 两种退出信号均丢失 | watchdog 仍按设计触发 MRC1 |
| 旧驾驶仓 release 延迟到达 | 因 session 不匹配被忽略，不影响新驾驶仓 |
| release 与 timeout 同时发生 | 有效 release 后旧 generation 的 timeout tick 不得触发 MRC1 |
| 已存在健康类 MRC | release 不得清除该安全状态 |
| 连续重复点击结束 | 幂等处理，只完成一次状态迁移 |
| 未 `onTakeover` 直接请求 R | 车端拒绝，不进入远控活动态 |
| `onTakeover` 后无首帧 | 保持制动，报 `JOYSTICK_STREAM_START_TIMEOUT`，不报控制中失联 |
| 首帧到达后持续控制 | 返回 `JOYSTICK_STREAM_READY`，随后允许 ACTIVE |
| GQ002 无 joystick 数据 | 前端不得显示远控已就绪，车端不得按旧逻辑约 0.9s 触发 idle MRC |
| 部署版本校验 | 启动日志 SHA 与目标提交/镜像摘要一致 |

建议增加自动化压力用例：在 joystick 超时阈值前后反复注入 `onRelease`，验证
`RELEASED` 后不会再出现同一 session 的 `JOYSTICK_IDLE_TIMEOUT`。

## 14. 最终判断

原 GQ004 现象应归类为：

```text
GQ004 的远控数据流和退出报文链路或协议兼容问题，
导致主动退出信号 bt_others=1 未在车端生效；
车端误将退出后的手柄数据停止判定为 JOYSTICK_IDLE_TIMEOUT，
从而触发 MRC1 和双闪。
```

GQ002 未切换对照样本则应归类为：

```text
远控控制面可用，但 remotejoystick 数据面从未建立；
现场运行逻辑仍从进入 R 开始计算首帧超时，
约 0.9s 后错误归类为 JOYSTICK_IDLE_TIMEOUT 并触发 MRC1。
```

因此，“换驾驶仓后点击退出就双闪”不是车辆正常设计行为，也不是当前证据能够
支持的用户误触。驾驶仓切换与原事件相关，但不是该类 MRC 的必要条件。共同故障
条件是 `remotejoystick` 未建立或中断，而车辆会话/远控模式仍让 joystick
watchdog 生效。

修复优先级应为：

1. 立即固定 9 月 10 日现场镜像 digest、进程 `/proc/<pid>/exe`、实际 ELF SHA256
   和 `ros2 pkg prefix`，确认是否相对 9 月 9 日回退或加载了旧 overlay；
2. 排查 GQ002/GQ004 的 `remotejoystick` 发布、云端路由、VIN 绑定和车端接收；
3. 增加 `WAITING_FIRST_FRAME -> ACTIVE` 握手，未收到首帧不得宣告远控成功；
4. 将匹配当前活动 session 的 `onRelease` 作为权威退出信号；
5. 保留 `bt_others=1` 作为低延迟冗余，并消除 release 与 watchdog 的竞态。

从系统设计上，应将匹配当前活动 session 的 `onRelease` 作为权威退出信号，
`bt_others=1` 作为低延迟冗余信号，并以 `JOYSTICK_IDLE_TIMEOUT` 作为退出信号
全部丢失时的安全兜底。首帧之前则应使用独立的启动失败状态，不能与控制中的
joystick 失联混为一类。三者不能只依赖同一条 joystick 数据链路。
