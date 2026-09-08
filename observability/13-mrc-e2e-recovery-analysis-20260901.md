# MRC 前后 e2e 与 cloud_driving 恢复分析

分析日期：`2026-09-08`

事件日期：`2026-09-01`

状态：`observed/partial-recovery`

## 1. 结论先行

本次事件不是节点重启导致，关键顺序如下：

```text
cloudLinkPing 应用层请求耗时异常
  -> cloud_driving MRC 0 -> 1
  -> 手柄消息出现 313ms、随后 854ms 间断
  -> cloud_driving MRC 1 -> 2
  -> e2e 收到 pd=2，生成 joystick_status=255 / gear=2 / stop_flag=32
  -> 手柄恢复并持续发送正常消息
  -> cloud_driving 自动清除手柄导致的 MRC2
  -> e2e pd=0，但 health=1 仍保留
  -> effective_mrc 最终为 1
```

因此，“恢复成功”需要分层描述：

| 层级 | 结论 |
|---|---|
| `cloud_driving` 手柄故障状态 | 已恢复：`MRC 2 -> 0` |
| e2e 的手柄相关输入 `pd` | 已恢复：`pd=2 -> 0` |
| e2e 总体安全状态 | 未完全恢复：`health=1`，`effective_mrc=1` |
| 底盘是否完成实际制动、EPB 或轮端扭矩动作 | 两份日志无法证明 |

恢复期间没有在车端日志中发现页面下发的 `parallelDrivingControl`、`mrc_status`
或 `self_recover_status`。现有证据支持的结论是：MRC2 清除来自
`cloud_driving` 检测到手柄恢复后的自动动作，不是页面发送了恢复指令。

## 2. 分析范围与时间

输入日志：

```text
/Users/minyi/Downloads/e2e_control_20260831203824.log
/Users/minyi/Downloads/ztd_cloud_driving_20260831203825.log
https://dataset.intra.zeron.ai/metaclips/687188e9a56c853e8e9e7a3c4a88b8e3
```

主分析窗口：

```text
Unix timestamp: 1788203531.469437597 - 1788203542.162357322
北京时间:      2026-09-01 03:12:11.469 - 2026-09-01 03:12:22.162
时区:          Asia/Shanghai
```

下面的主时间线保留完整 Unix 时间戳，同时使用毫秒精度显示北京时间。日志行号
是原始文件中的行号，便于直接定位。

## 3. 关键事件时间线

| Unix 时间戳 | 北京时间 | 组件/触发者 | 动作与关键数据 | 结果 | 原始日志 |
|---:|---|---|---|---|---|
| `1788203531.469437597` | `03:12:11.469` | `cloud_driving` / 链路探测 | `cloudLinkPing invoke_sent`，`requestMessageId=cloud-ping-1788203531468-4681` | 发起一次云链路探测 | `ztd_cloud_driving...log:391304` |
| `1788203533.462218355` | `03:12:13.462` | `cloud_driving` / 链路探测 | 返回 `rtt_ms=1993`，`network_rtt_est_ms=1993` | 单次高延迟样本被记录 | `ztd_cloud_driving...log:391377` |
| `1788203534.788453395` | `03:12:14.788` | `cloud_driving` / 自动 MRC | `MRC status: 0->1`，原因 `CLOUD_LINK_RTT_EXCESSIVE`，`speed=6.4`，`gear=1` | 云链路异常触发 MRC1 | `ztd_cloud_driving...log:391454` |
| `1788203537.528283037` | `03:12:17.528` | 手柄 -> `cloud_driving` | 收到正常 `remotejoystick`，`joysticksts=1`，`gear=1`，`bt_up=56`，其余操纵量为 0 | 这时仍有手柄消息到达，不能简单判定为完全断链 | `ztd_cloud_driving...log:391631` |
| `1788203537.528613619` | `03:12:17.529` | `e2e_control` | `PDriving msg`：`joystick_status=1`，`gear=1`，`up=56`，`stop_flag=0` | e2e 仍输出正常远控消息 | `e2e_control...log:1940330` |
| `1788203537.841642713` | `03:12:17.842` | `cloud_driving` / 手柄监测 | 检测到消息间隔 `gap=313ms` | 手柄链路开始出现间断 | `ztd_cloud_driving...log:391634` |
| `1788203538.382244090` | `03:12:18.382` | `cloud_driving` / 手柄监测 | 记录 `MRC1 triggered`，`gap=854ms` | 手柄空闲超时达到触发条件 | `ztd_cloud_driving...log:391635` |
| `1788203538.388510526` | `03:12:18.389` | `cloud_driving` / 自动 MRC | `MRC status: 1->2`，原因改为 `JOYSTICK_IDLE_TIMEOUT`，`speed=4.2`，`gear=1` | MRC2 生效，原因以手柄超时为主 | `ztd_cloud_driving...log:391636` |
| `1788203538.402088761` | `03:12:18.402` | `e2e_control` | `MRC active result=2`，`pd=2`，`health=1` | e2e 已仲裁出 MRC2 | `e2e_control...log:1940420` |
| `1788203538.402186018` | `03:12:18.402` | `e2e_control` | 记录 `MRC1 is triggering... (effective_mrc=2)` | e2e 进入 MRC 安全处理循环 | `e2e_control...log:1940421` |
| `1788203538.604203084` | `03:12:18.604` | `e2e_control` | 输出 `joystick_status=255`，`gear=2`，`up/down/left/right=0`，`stop_flag=32` | 已生成 MRC2 对应的安全输出 | `e2e_control...log:1940453` |
| `1788203541.738471884` | `03:12:21.738` | 手柄 -> `cloud_driving` | 收到恢复后的 `remotejoystick`，`joysticksts=1`，`gear=1`，所有按钮量为 0 | 手柄开始持续提供正常消息 | `ztd_cloud_driving...log:391943` |
| `1788203541.739080461` | `03:12:21.739` | `e2e_control` | `PDriving msg`：`joystick_status=1`，`gear=1`，所有操纵量为 0，`stop_flag=0` | e2e 已收到正常手柄输出 | `e2e_control...log:1940940` |
| `1788203541.741338610` | `03:12:21.741` | 手柄 -> `cloud_driving` | 再收到正常 `remotejoystick`，`epb_cmd=0` | 车端继续收到正常手柄数据 | `ztd_cloud_driving...log:391946` |
| `1788203541.762646759` | `03:12:21.763` | `cloud_driving` / 自动恢复 | `MRC1 cleared - joystick recovered` | 清除手柄导致的 MRC1 标志 | `ztd_cloud_driving...log:391949` |
| `1788203541.771113020` | `03:12:21.771` | `cloud_driving` / 自动恢复 | `MRC status: 2->0`，原因 `JOYSTICK_IDLE_TIMEOUT` 清除，`speed=0.0`，`gear=0` | `cloud_driving` 的 MRC2 清除 | `ztd_cloud_driving...log:391950` |
| `1788203541.782118246` | `03:12:21.782` | `e2e_control` | `MRC active result=1`，`pd=0`，`health=1` | 手柄 MRC 已解除，但健康状态仍触发 MRC1 | `e2e_control...log:1940947` |
| `1788203542.162357322` | `03:12:22.162` | `e2e_control` | `effective_mrc=1` | 整体没有回到完全正常 `effective_mrc=0` | `e2e_control...log:1940988` |

### 3.1 时间间隔

从日志时间戳直接计算：

```text
cloudLinkPing:
1788203533.462218355 - 1788203531.469437597
= 1.992780758 s
= 1992.780758 ms

cloud_driving MRC 0 -> 1 到 1 -> 2:
3.600057131 s

cloud_driving MRC 1 -> 2 到 MRC 2 -> 0:
3.382602494 s

cloud_driving MRC 0 -> 1 到 MRC 2 -> 0:
6.982659625 s

cloud_driving MRC 1 -> 2 到 e2e result=2:
13.578176 ms

cloud_driving MRC 2 -> 0 到 e2e pd=0:
11.005402 ms
```

## 4. 手柄在事件前后做了什么

### 4.1 触发前

`cloud_driving` 在目标窗口内持续收到 `remotejoystick`。例如：

- `03:12:11.444` 左右：`joysticksts=1`，`gear=1`，`bt_up=100`。
- `03:12:17.528`：仍收到 `joysticksts=1`，`gear=1`，`bt_up=56`。
- `03:12:17.842`：消息间隔第一次出现 `313ms` 告警。
- `03:12:18.382`：消息间隔达到 `854ms`，触发手柄空闲超时。

因此，MRC2 不是日志中看到的页面手动 MRC2 指令，也不像是手柄显式发送了一个
`mrc_status=2`；日志明确给出的触发源是 `JOYSTICK_IDLE_TIMEOUT`。

### 4.2 MRC2 期间

MRC2 触发后，`cloud_driving` 仍能在 `03:12:18.714` 左右收到
`remotejoystick`，数据仍为 `joysticksts=1`、`gear=1`、`bt_up=56`，之后还能
看到 `bt_up=54/51/47/45` 等消息。

这说明“触发 MRC2”与“后续仍有手柄消息到达”可以同时存在。触发判断使用的是
消息间隔超时，不是简单的“后续每一条消息都丢失”。

### 4.3 恢复时

`03:12:21.738` 和 `03:12:21.741` 左右，车端重新收到连续的正常手柄消息：

```text
joysticksts=1
gear=1
bt_up=0
bt_down=0
bt_left=0
bt_right=0
epb_cmd=0
```

随后 `cloud_driving` 在 `03:12:21.763` 自己记录
`MRC1 cleared - joystick recovered`，没有出现页面恢复命令。

## 5. `cloud_driving` 做了什么

`cloud_driving` 的 MRC 状态变化完整记录为：

```text
03:12:14.788  0 -> 1  CLOUD_LINK_RTT_EXCESSIVE
03:12:18.389  1 -> 2  JOYSTICK_IDLE_TIMEOUT
03:12:21.771  2 -> 0  JOYSTICK_IDLE_TIMEOUT cleared
```

其中：

1. `0 -> 1` 是单次 `cloudLinkPing` 高延迟样本触发。
2. `1 -> 2` 是手柄消息间隔超过阈值触发。
3. `2 -> 0` 是车端检测到手柄恢复后的自动清除。

目标窗口内，`cloud_driving` 共记录 `206` 次
`Received INVOKE_FUNCTION: functionId=remotejoystick`。因此恢复不是依靠重启
进程重新初始化状态，而是依靠原进程继续接收手柄消息并执行内部状态清除。

## 6. `e2e_control` 做了什么

### 6.1 MRC2 安全输出

在 `03:12:18.402`，e2e 观察到：

```text
MRC active result=2
pd=2
health=1
pd_timeout=no
hold=0
stop=off
stable=0
```

在 `03:12:18.604` 输出：

```text
drive_mode=2
joystick_status=255
gear=2
up=0
down=0
left=0
right=0
stop_flag=32
```

这可以证明 e2e 已经生成 MRC2 安全控制输出，不能单凭该行证明车辆底盘已经
完成制动、停车、EPB 拉起或轮端扭矩归零。需要 `chassis_status`、执行器回执、
速度变化和 EPB 状态才能完成闭环确认。

### 6.2 为什么恢复后仍是 MRC1

恢复时 e2e 的输入已经恢复为正常手柄消息：

```text
03:12:21.739  joystick_status=1, gear=1, up/down/left/right=0, stop_flag=0
03:12:21.782  MRC active result=1 (pd=0 health=1)
03:12:22.162  effective_mrc=1
```

这组日志说明：

- 手柄相关的 `pd` 已从 `2` 变为 `0`；
- e2e 的 `health` 仍为 `1`；
- 总体仲裁结果因此仍为 `effective_mrc=1`。

所以页面若只依据 `pd` 或 `cloud_driving` 的 `MRC status=0` 显示“已恢复”，会
掩盖 e2e 仍保留 MRC1 的事实。当前日志没有给出 `health=1` 的具体来源，需继续
结合 e2e health 输入源或对应健康状态日志分析。

## 7. 恢复期间页面有没有下发指令

### 7.1 车端日志中的核对结果

对目标窗口 `1788203534` 到 `1788203543` 检索两份日志，没有发现：

```text
parallelDrivingControl
mrc_status
self_recover_status
CLOUD_PAGE_MRC1_ERROR
```

同时只看到：

```text
remotejoystick
cloudLinkPing
```

统计结果：

| 类型 | 结果 |
|---|---:|
| `remotejoystick` 接收请求 | `206` |
| `cloudLinkPing` 请求 | `2` |
| `cloudLinkPing` 响应 | `2` |
| `parallelDrivingControl` | `0` |
| `mrc_status` / `self_recover_status` 指令标记 | `0` |

### 7.2 证据边界

这两份车端日志可以证明：

> 目标车端在恢复窗口内没有收到可识别的页面 MRC 控制指令。

但它们不能单独证明浏览器绝对没有发起 HTTP 请求，因为浏览器和 ziot 的
HTTP/业务日志不在本次输入中。要证明页面端没有点击或下发，需要同时查询：

```text
浏览器控制台/Network 日志
ziot ParallelDrivingControlController 日志
ParallelDrivingControlService/Room 转发日志
车端 FunctionInvokeMessage 接收日志
```

本次车端日志中的 `MRC 2 -> 0` 原因是
`JOYSTICK_IDLE_TIMEOUT ->`，且紧邻
`MRC1 cleared - joystick recovered`，因此当前证据更支持“车端自动恢复”，
不支持“页面下发 mrc_status=0”。

## 8. 司机反馈关联分析：网络好但视频卡顿，约 2 秒后 MRC 超时

### 8.1 现象与日志的对应关系

司机反馈的“网络好”如果指的是仍有信号、页面仍在线或连接没有断开，与本次日志
并不矛盾。本次更像是：

```text
连接仍在线
  -> 短时高延迟/抖动/排队
  -> 视频实时性下降，出现卡顿
  -> 控制消息在车端出现接收空洞
  -> 手柄超时保护触发 MRC2
```

“在线”只能说明链路仍能收发数据，不能说明每一帧都能在实时控制窗口内到达。
本次异常后 `cloudLinkPing` 仍然收到响应，且后续样本恢复为 `108ms` 和 `77ms`，
所以不能简单描述为“网络完全断了”或“信号完全没有了”。

### 8.2 按时间戳还原司机看到的关键顺序

下表使用车端日志时间戳。`cloud_driving` 时间是收到或处理消息的时间，
`e2e_control` 时间是 e2e 观察输入并输出控制消息的时间。

| Unix 时间戳 | 北京时间 | 触发者/模块 | 现场可见动作变化 | 结论 |
|---:|---|---|---|---|
| `1788203531.469437597` | `03:12:11.469` | `cloud_driving` | 发起 `cloudLinkPing` | 开始探测云链路 |
| `1788203533.462218355` | `03:12:13.462` | 云链路探测 | 返回 `rtt_ms=1993` | 连接未断，但实时性出现严重尖峰 |
| `1788203534.788453395` | `03:12:14.788` | `cloud_driving` 自动仲裁 | `MRC 0 -> 1`，原因 `CLOUD_LINK_RTT_EXCESSIVE` | 先因云链路高延迟进入 MRC1 |
| `1788203536.646757893` | `03:12:16.647` | 云链路探测 | 下一次 ping 恢复为 `108ms` | 异常是尖峰，不是持续断链 |
| `1788203537.528428369` | `03:12:17.528` | `cloud_driving` | 最后一帧正常消息，`bt_up=56` | 此时控制消息仍在到达 |
| `1788203537.841642713` | `03:12:17.842` | `cloud_driving` 手柄监测 | 检测到消息间隔 `313ms` | 控制链路开始出现接收间断 |
| `1788203538.382244090` | `03:12:18.382` | `cloud_driving` 手柄监测 | `MRC1 triggered gap=854ms` | 手柄超时条件达到 |
| `1788203538.388510526` | `03:12:18.389` | `cloud_driving` 自动仲裁 | `MRC 1 -> 2`，原因 `JOYSTICK_IDLE_TIMEOUT` | 约 0.854 秒控制空洞后升级为 MRC2 |
| `1788203538.604203084` | `03:12:18.604` | `e2e_control` | 输出 `joystick_status=255`、`gear=2`、`stop_flag=32` | e2e 已输出 MRC2 安全控制消息 |
| `1788203538.714673289` | `03:12:18.715` | `cloud_driving` | 延迟后的手柄帧开始集中到达 | 支持“消息排队后批量释放” |
| `1788203541.549969238` | `03:12:21.550` | 云链路探测 | ping 恢复为 `77ms` | 链路探测恢复正常 |
| `1788203541.762646759` | `03:12:21.763` | `cloud_driving` 自动恢复 | `MRC1 cleared - joystick recovered` | 车端根据手柄恢复自动清除手柄故障 |
| `1788203541.771113020` | `03:12:21.771` | `cloud_driving` 自动仲裁 | `MRC 2 -> 0` | `cloud_driving` 的 MRC2 清除 |
| `1788203542.162357322` | `03:12:22.162` | `e2e_control` | `effective_mrc=1` | 手柄故障解除，但整体仍保留 MRC1 |

关于“约 2 秒”：日志能够直接确认的约 2 秒，是 `cloudLinkPing` 从
`1788203531.469437597` 到 `1788203533.462218355` 的
`1992.780758ms` 请求-响应耗时。之后 MRC1 在
`1788203534.788453395` 发生，距离 ping 响应约 `1.326s`；MRC2 在
`1788203538.388510526` 发生，距离 ping 响应约 `4.926s`，但距离最后一帧正常
手柄消息 `1788203537.528428369` 只有约 `0.860s`。因此不能把“视频卡顿后约 2 秒”
作为本次 MRC 切换的精确延迟；更准确的说法是，视频卡顿感知、高延迟探测样本和
后续控制消息接收超时发生在同一段异常窗口内。

### 8.3 `1993ms` 与手柄接收空洞不是同一个指标

两组数据要分开解释：

| 指标 | 日志事实 | 能说明什么 |
|---|---|---|
| `cloudLinkPing=1993ms` | 请求 `1788203531.469437597`，响应 `1788203533.462218355`，差值 `1992.780758ms` | 一次应用层请求-响应耗时异常 |
| 手柄接收空洞约 `1186.245ms` | `1788203537.528428369` 后，下一帧在 `1788203538.714673289` 到达 | 车端连续约 1.186 秒没有收到手柄消息 |
| 手柄批量补帧 | 下一帧内部 `timestamp=1788203500456`，之后内部时间戳连续增长到约 `1659`，约 `74.906ms` 内集中到达约 29 帧 | 上游仍在生成数据，但消息可能在链路、代理或队列中延迟后集中释放 |

`1993ms` 是应用层探测耗时，不能直接当作纯 TCP RTT；`1186ms` 是车端日志看到的
消息接收间隔，也不能直接等同于单向网络延迟。二者共同说明这段时间的实时传输
质量异常，但不能仅凭它们计算视频卡顿的具体丢包率或视频端到端延迟。

### 8.4 为什么视频会先卡，而后出现 MRC

两份日志没有视频流的 WebRTC/RTP/RTCP 统计，无法判断卡顿发生在摄像头上行、
移动网络、云端转发、WVP 还是浏览器解码。因此这里的因果关系只能写到：

> 视频卡顿与同一时间窗口内的高延迟和控制消息接收空洞高度相关；如果视频和
> 控制消息共享部分传输路径，瞬时排队、抖动、重传或队头阻塞可以同时造成视频
> 不连续和手柄超时，但当前日志不足以定位具体网络段或视频组件。

本次没有看到“前端完全停止产生手柄数据”的证据。手柄内部时间戳仍连续增长，
而车端随后在短时间内收到一批历史帧，更符合传输或中间转发队列出现延迟后释放。
这也解释了为什么司机可以感觉“网络还是好的”，但视频和控制实时性已经不可用。

### 8.5 恢复期间是否有页面指令

在 `1788203538.388510526` 至 `1788203542.162357322` 的恢复窗口中，两份车端
日志没有发现 `parallelDrivingControl`、`mrc_status`、
`self_recover_status` 或可识别的页面恢复命令。

恢复的直接证据是：

```text
1788203541.738471884  收到恢复后的正常 remotejoystick
1788203541.762646759  MRC1 cleared - joystick recovered
1788203541.771113020  MRC 2 -> 0
```

因此当前结论是：

> MRC2 是 `cloud_driving` 根据手柄消息恢复自动清除的，不是页面点击恢复按钮
> 或下发 `mrc_status=0` 导致的。

这两份车端日志不能排除浏览器发出过但未到达车端的请求。要对页面操作做最终闭环，
还需要浏览器 Network/控制台、ziot 控制器、`ParallelDrivingControlService` 或
Room 转发日志。

### 8.6 Session 过期与“ping 不通”的判断

本次事件不支持“Session 每天过期导致 ping 不通”：

- 车端启动时已出现 `Authentication successful` 和 `Remote ctrl register successful`；
- 目标窗口内没有 `Authentication failed`、`Unauthorized`、`401/403`、断链或重连；
- `1993ms` 的 ping 最终收到响应；
- 随后的 ping 恢复为 `108ms` 和 `77ms`；
- `remotejoystick` 在异常期间和恢复期间仍有消息进入车端。

更符合本次现象的描述是：

> Session/连接仍然存在，但链路出现瞬时高延迟、抖动或队列积压，导致实时视频
> 和实时控制都受到影响；控制侧先后由云链路高延迟和手柄接收超时触发 MRC。

如果确实是 Session 过期，通常应在日志中看到认证失效、权限拒绝、连接关闭、
重连或持续收不到请求；本次没有这些证据。

### 8.7 当前源码阈值与现场行为

当前工作区源码和配置中的默认值为：

```text
cloud_link_rtt_warn_ms  = 800ms
cloud_link_rtt_error_ms = 3000ms
joystick_msg_timeout_ms = 300ms
joystick_mrc1_consecutive = 6
```

但现场 `1993ms` 样本已经触发了 `CLOUD_LINK_RTT_EXCESSIVE` 对应的 MRC
`0 -> 1`。因此不能直接使用当前源码默认 `3000ms` 解释现场行为，至少存在以下
一种可能：

1. 现场参数覆盖了源码默认值；
2. 现场运行的构建版本与当前工作区不同；
3. 现场健康仲裁采用了另一套阈值或等级映射。

这不影响本次现场事实判断，但要继续定位“为什么 1993ms 触发 MRC1”，需要拿
现场启动参数、实际 `vehicle_params.yaml` 或部署构建产物核对。

## 9. `cloudLinkPing` 的 1993ms 是否准确

准确。原始时间戳为：

```text
请求发送: 1788203531.469437597
响应记录: 1788203533.462218355
差值:     1.992780758 秒
```

换算为毫秒：

```text
1992.780758 ms
```

日志按毫秒四舍五入后记录为：

```text
rtt_ms=1993
network_rtt_est_ms=1993
```

但这里应准确称为 `cloudLinkPing` 的应用层请求-响应耗时或链路估算值，不能仅
凭这两份日志把它等同于纯 TCP/IP RTT。该耗时可能包含消息传输、代理/云端排队、
对端处理和回复路径时间。日志没有提供各段拆分数据。

从完整 `cloudLinkPing` 记录看，附近大多数样本约在几十到一百多毫秒范围，
`1993ms` 是单次异常尖峰，不足以证明整个窗口一直处于 2 秒延迟。

## 10. 是否发生节点重启或重连

没有发现本次 MRC 触发和恢复期间发生重启。

两份日志的进程启动信息分别为：

```text
cloud_driving_vehicle  pid=2915
e2e_control_v2         pid=2668
```

两个进程在目标事件前已经启动并持续运行。目标窗口内没有发现新的
`process started`、PID 变化、崩溃后自动拉起或 MQTT/IOT 重连记录。

日志末尾的退出是人工中断，且发生在事件很久之后：

```text
cloud_driving  1788206590.781286481  SIGINT
e2e_control    1788206654.792348785  SIGINT
```

因此：

```text
MRC 触发不是节点重启造成的
MRC2 清除不是节点重启后的初始化造成的
```

## 11. 最终判定

按当前两份日志，最准确的事件描述是：

> 2026 年 9 月 1 日 03:12:11 至 03:12:22，北京时间，车端先探测到一次
> `cloudLinkPing` 应用层耗时约 1992.781ms 的异常样本，`cloud_driving` 自动将
> MRC 从 0 提升到 1。随后手柄消息间隔出现 313ms 和 854ms 异常，车端以
> `JOYSTICK_IDLE_TIMEOUT` 将 MRC 提升到 2。e2e 收到 `pd=2` 并输出
> `joystick_status=255`、`gear=2`、`stop_flag=32` 的安全控制消息。手柄恢复后，
> `cloud_driving` 自动清除手柄导致的 MRC2，e2e 的 `pd` 恢复为 0；但
> `health=1` 仍存在，故 e2e 最终 `effective_mrc=1`，不能称为整体完全恢复。

### 不能从本次日志确认的事项

1. 浏览器是否实际发起过未到达车端的页面 HTTP 请求。
2. `health=1` 的具体来源和清除条件。
3. `stop_flag=32` 在底盘执行器侧对应的实际制动结果。
4. 车辆是否完成 EPB、轮端扭矩归零和稳定停车。
5. `cloudLinkPing` 1993ms 中网络传输、云端处理和消息排队各自占用的时间。
