# MRC 从页面指令到 e2e 安全输出

更新时间：`2026-09-07`

状态：`implemented/unverified`

本文以当前代码为准，梳理 MRC 指令从远控页面、ziot 后端、车端远控节点到
`e2e_control_v2` 的完整路径，并标出确认边界、现存协议风险和后续优化方向。
本文描述的是代码现状，不等同于实车已经完成端到端验收。

车端自恢复实现以 `aura` 的
`origin/feature/mrc_self_recover@f9ca2a07e` 为证据基线。当前工作区检出的
`llm/on-vehicle-0818@f28c5c481` 尚未包含该实现，因此部署和联调前必须确认
目标车辆使用了包含该专用分支提交的构建。

## 1. 当前结论

页面下发的 MRC 主路径是：

```text
VehicleRemoteDeck.vue
  -> POST /parallel-driving/control/command
  -> ParallelDrivingControlController
  -> ParallelDrivingControlService
  -> ParallelDrivingRoom.forwardCockpitToVehicle
  -> FunctionInvokeMessage(functionId=parallelDrivingControl,
                            inputs.controlType=mrc,
                            inputs.mrc_status=0..3)
  -> cloud_driving_vehicle::handle_parallelDrivingControl
  -> handle_mrc -> mrc_cloud_
  -> /zeron/mrc/status @ 50Hz
  -> e2e_control_v2::RecvMrcStatusPdInfo
  -> max(mrc_status_, mrc_status_pd_)
  -> ApplyMrcSafetyResponse
  -> /zeron/e2e_control/logical_control_info
```

需要特别区分以下结果，它们不是同一个确认：

| 结果层级 | 能证明什么 | 不能证明什么 |
|---|---|---|
| 页面 `request.post` 返回 2xx | HTTP 请求被接口受理 | 不能证明消息到车端 |
| Room `sendAndForget` 完成 | ziot 发送路径完成 | 不能证明车端 handler 已运行 |
| 车端 `handle_mrc` 返回 `success/ack=ok` | 车端 handler 接收并写入 `mrc_cloud_` | 不能单独证明 e2e 已输出制动 |
| `/zeron/mrc/status` 出现 `2/3` | 车端 MRC 输入已发布 | 不能单独证明车辆已停止 |
| `logical_control_info` 出现 MRC 安全输出 | e2e 已生成安全控制指令 | 不能单独证明底层执行器已达到停车结果 |
| `chassis_status` / `mrc_event` 反映停止和 MRC 状态 | 有车辆侧状态证据 | 仍需结合底盘、档位、EPB 和速度确认 |

### 1.1 图类型选择

本专题使用两种图：

- [Sequence：MRC 指令到 e2e 安全输出](diagrams/mrc-command-to-e2e.sequence.html)
  表达页面、后端、Room、车端和 e2e 的调用顺序、异步边界和状态回传。
- [Lifecycle：MRC 状态与安全输出生命周期](diagrams/mrc-command-lifecycle.lifecycle.html)
  表达 `NORMAL -> MRC0 -> MRC1/MRC2 -> braking -> stopped` 以及恢复路径。

Sequence 适合排查“请求走到哪里、在哪一层丢失”；Lifecycle 适合排查“状态是否
进入、保持、释放或错误恢复”。当前不单独画 Architecture 图，因为主要问题是
调用链和状态链，而不是组件边界不清。

## 2. 页面入口和请求模型

代码：

- [`parallel-driving.ts`](../../zeron-cloud-web/src/modules/parallel-driving-manager-ui/api/parallel-driving.ts#L162-L245)
- [`VehicleRemoteDeck.vue`](../../zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue#L205-L220)
- [`VehicleRemoteDeck.vue` 的 MRC 处理](../../zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue#L2986-L3224)

### 2.1 手动 MRC

页面目前提供以下入口：

| 入口 | 当前动作 |
|---|---|
| MRC radio | `正常=0`、`MRC0=1`、`MRC1=2`；`MRC2=3` 当前 disabled |
| MRC1 圆形按钮 | 根据车辆状态在 `mrc_status=2` 和 `mrc_status=0` 之间切换 |
| 自恢复按钮 | 当 `selfRecoverStatus == 2` 时可点；该值由车端状态机判定 |
| emergency-stop | 页面模板中 `v-if="false"`，当前不可见，但 API 和 handler 仍保留 |

普通 MRC 请求：

```http
POST /parallel-driving/control/command
  ?cockpitDeviceId=<驾驶舱设备>
  &vehicleDeviceId=<车辆设备>
  &controlType=MRC

Content-Type: application/json

{
  "mrc_status": 2
}
```

恢复请求：

```json
{
  "mrc_status": 0,
  "self_recover_status": 3
}
```

页面 API 层会为每次请求生成：

```text
X-Correlation-ID: control-...
traceparent: 00-<trace-id>-<span-id>-01
```

同时记录 `control_command/send_start`、成功或失败以及耗时。该关联 ID 目前
主要存在于浏览器观测事件和 HTTP header，后端转发到车端的 `messageId`、
`requestId`、`requestMessageId` 需要在日志和协议中继续统一。

### 2.2 视频异常自动 MRC

页面中的“视频保护”是另一条页面侧触发器，不改变后端接口：

```text
监控流：cam_f_12、cam_b_18
采样周期：500ms
连续异常：约 2000ms 后请求 MRC1
确认条件：vehicleStatus.mrcStatus >= 2
确认超时：10000ms
```

它只在以下条件同时满足时生效：

```text
视频保护开关开启
已进入远控
已选择驾驶舱
车辆设备已就绪
车辆绑定的驾驶舱与当前驾驶舱一致，或车辆未声明绑定驾驶舱
```

自动 MRC 调用的 body 是 `{ "mrc_status": 2 }`。页面将 incident 先置为
`pending`，收到车辆状态 `mrcStatus >= 2` 才置为 `confirmed`，10 秒内没有
车辆状态确认则置为 `timeout`。因此页面的自动 MRC 已经具备“请求”和“车辆状态
确认”两个阶段，但确认仍是状态字段确认，不是底盘停车确认。

### 2.3 页面状态回传

页面从状态流中解析：

```text
mrc_status
self_recover_status
mrc_error_name
mrc_timestamp
pd_msg_age_ms
cloud_link_rtt_ms
```

页面显示的 `vehicleStatus.mrcStatus` 应理解为车端上报的当前 MRC 状态，不能
用上一次 HTTP 成功替代。

## 3. ziot 后端链路

代码：

- [`ParallelDrivingControlController.java`](../../ziot/ziot-manager/parallel-driving-manager/src/main/java/org/ziot/parallel/driving/web/ParallelDrivingControlController.java#L23-L65)
- [`ParallelDrivingControlService.java`](../../ziot/ziot-manager/parallel-driving-manager/src/main/java/org/ziot/parallel/driving/service/ParallelDrivingControlService.java#L30-L129)
- [`ParallelDrivingControlMessage.java`](../../ziot/ziot-manager/parallel-driving-manager/src/main/java/org/ziot/parallel/driving/message/ParallelDrivingControlMessage.java#L18-L85)
- [`ParallelDrivingRoom.java`](../../ziot/ziot-manager/parallel-driving-manager/src/main/java/org/ziot/parallel/driving/room/ParallelDrivingRoom.java#L384-L555)

### 3.1 Controller

`POST /parallel-driving/control/command` 做的事情很少：

1. 接收 `cockpitDeviceId`、`vehicleDeviceId`、`controlType` 和 JSON body。
2. 将 `controlType` 转换成 `ParallelDrivingControlMessage.ControlType`。
3. 非法控制类型直接返回错误。
4. 构造 `ParallelDrivingControlMessage`，将 body 作为 `controlParams`。
5. 交给 `ParallelDrivingControlService`。

MRC 的 `controlType` 最终按枚举转换为 `ControlType.MRC`。请求 body 仍是可变
Map，当前没有在 Controller 层约束 `mrc_status` 必须是 `0..3`；实际范围校验
发生在车端 `handle_mrc()`。

### 3.2 Service 门禁

Service 在 Room 转发前依次执行：

```text
驾驶舱设备存在
  -> 车辆设备存在
  -> 等待 active session
  -> 获取 active room
  -> 再次确认 session.isActive()
  -> 注入 session / room / operator
  -> 设置目标车辆和 force=true
  -> prepareInputs()
  -> Room forwardCockpitToVehicle()
  -> 更新最后活动时间、日志、指标、Trace
```

`waitActiveSession()` 每 `200ms` 检查一次，最多 `12` 次，等待窗口约
`2.4s`。因此 takeover 刚完成时可能短暂等待；设备、session 或 room 任何一项
失败都不会进入车辆发送阶段。

### 3.3 MRC 的 wire mapping

`ParallelDrivingControlMessage` 默认：

```text
functionId = parallelDrivingControl
```

执行 `prepareInputs()` 后，MRC 的输入为：

```text
inputs.controlType        = "mrc"
inputs.mrc_status         = 0 | 1 | 2 | 3
inputs.self_recover_status = 可选，当前页面恢复请求为 3
```

这里的 `controlType=MRC` 是 Java 枚举值，发给车端的 `inputs.controlType` 是
小写协议值 `"mrc"`。两者不是同一个字段，后续应在共享协议定义中统一命名。

### 3.4 Room 转发和关联键

Room 会创建新的 `FunctionInvokeMessage`，设置：

```text
deviceId = vehicleDeviceId
targetDeviceId = vehicleDeviceId
sourceDeviceId = cockpitDeviceId
sourceType = cockpit
roomId = <room>
messageType = parallel-driving-control
functionId = parallelDrivingControl
function = parallelDrivingControl
forwardTime = currentTimeMillis
force = true
async = true
requestId = messageId
requestMessageId = messageId
```

MRC 作为 FunctionInvokeMessage 且有 `async=true`，走：

```text
device.messageSender().sendAndForget(forwarded)
```

这条路径的 `doOnSuccess` 只表示 ziot 的发送器完成了发送操作。它不等待车端
handler response，也不等待 `/zeron/mrc/status`，更不等待 e2e 和底盘。

当前建议把一条指令的关联键固定为：

```text
browser correlationId
  + traceparent
  + backend messageId
  + requestId
  + requestMessageId
  + vehicle handler message_id
```

不要把车辆设备 ID 或 room ID 当作单条指令 ID；它们只能用于分组。

## 4. 车端远控节点

代码：

- [`cloud_driving_vehicle.cpp` 的初始化和 handler 注册](../../aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp#L433-L484)
- [`handle_mrc()` 和分派](../../aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp#L659-L705)
- [`MRC 发布与状态上报`](../../aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp#L433-L441)
- [`chassis_status` 和 `mrc_event`](../../aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp#L1250-L1345)

以上工作区链接用于定位通用 MRC 主路径；当前 checkout 不包含下述自恢复改动。
自恢复结论应使用固定提交读取，避免把分支差异误判为文档错误：

```bash
git -C ../../aura show \
  f9ca2a07e:src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp
git -C ../../aura show \
  f9ca2a07e:src/health_manager/health_arbitrator/src/health_arbitrator.cpp
git -C ../../aura show \
  f9ca2a07e:src/health_manager/health_arbitrator/include/health_arbitrator/mrc_status_manager.hpp
```

### 4.1 消息入口

车端注册：

```text
parallelDrivingControl -> handle_parallelDrivingControl
```

当 `inputs.controlType == "mrc"`，再进入：

```text
handle_mrc(inputs, message_id)
```

`handle_mrc()` 当前行为：

1. 先读取 `self_recover_status`。
2. 值为 `3` 时写入 `self_recover_command_`，作为 one-shot 恢复命令并直接返回。
3. 非恢复命令再读取 `mrc_status`，拒绝小于 `0` 或大于 `3` 的值。
4. 将普通 MRC 值写入原子变量 `mrc_cloud_`。
5. 返回 `{ success: true, messageId, ack: "ok" }`。

它本身不直接设置制动扭矩、不直接调用 e2e、不直接拉 EPB。车端远控节点是
MRC 输入缓存和发布者，真正的安全控制输出由 e2e 生成。

### 4.2 50Hz MRC topic

车端每 `20ms` 发布一次：

```text
/zeron/mrc/status
```

发布值为：

```cpp
max(mrc_cloud_, joy_sm_.mrc_level())
```

因此页面云端 MRC 和手柄超时 MRC 在该 topic 汇聚。`mrc_cloud_` 与手柄状态机
分开保存，避免清除一个来源时误清除另一个来源。

同一消息还携带 `self_recover_status`。普通周期发送 `0`；收到页面恢复命令后，
通过 `exchange()` 恰好发送一次 `3`，随后恢复为 `0`。这条 one-shot 消息由
`health_arbitrator` 订阅和消费。

### 4.3 车端 MRC 来源

当前车端能观察到的来源至少有：

| 来源 | 当前实现 | 结果 |
|---|---|---|
| 页面云端 MRC | `handle_mrc()` 写 `mrc_cloud_` | 通过 `/zeron/mrc/status` 发布 |
| 手柄消息超时 | `JoyMrcStateMachine` | 生成 MRC1 |
| 车云链路不可用 | `vehicle_->is_link_ready()` | `chassis_status.mrc_status=2`，来源 `VEHICLE_RECEIVE_TIMEOUT` |
| 车辆/health arbitrator 结果 | `latest_arbitration_decision_` | 写入 `chassis_status` 的 MRC 字段 |

`chassis_status` 中还会携带：

```text
mrc_status
self_recover_status
mrc_error_name
mrc_error_level
mrc_unique_id
mrc_timestamp
drive_mode
pd_msg_age_ms
cloud_link_rtt_ms
pd_js_status
```

MRC 状态变化时额外上报 `mrc_event`，用于记录前态、当前态、来源、模式、速度、
档位和时间戳。页面确认自动 MRC 时使用的是车辆状态流，不是 handler 的 ACK。

## 5. e2e_control_v2 仲裁和输出

代码：

- [`e2e_control_v2.cc` 的订阅和回调](../../aura/src/control/e2e_control/src/e2e_control_v2.cc#L65-L73)
- [`GetArbitratedMrcStatus()`](../../aura/src/control/e2e_control/src/e2e_control_v2.cc#L379-L474)
- [`ApplyMrcSafetyResponse()`](../../aura/src/control/e2e_control/src/e2e_control_v2.cc#L717-L771)
- [`TimerCallback()` 优先级](../../aura/src/control/e2e_control/src/e2e_control_v2.cc#L773-L890)
- [`e2e_control_v2.h` 的状态和阈值](../../aura/src/control/e2e_control/include/e2e_control_v2.h#L168-L216)

### 5.1 输入

e2e 订阅两条 MRC 输入：

```text
/zeron/health_manager/health_arbitrator/mrc_status
  -> mrc_status_

/zeron/mrc/status
  -> mrc_status_pd_
```

当前实现的主仲裁是：

```cpp
effective_mrc = max(mrc_status_, mrc_status_pd_)
```

也就是说，代码实现会让任意非零的 `mrc_status_pd_` 参与 `max`。头文件注释写成
“仅在 `=2` 时参与仲裁”，与实现不一致；后续应统一注释、枚举定义和测试预期。

### 5.2 自恢复状态机和消费者

`health_arbitrator` 维护独立的 `self_recover_status` 状态机：

```text
0 = SELF_RECOVER_NOT_IN_MRC
1 = SELF_RECOVER_IN_MRC
2 = SELF_RECOVER_CAN_RECOVER
3 = SELF_RECOVER_DO_RECOVER
```

MRC1/MRC2 生效时，状态进入 `1`。仲裁结果恢复正常并持续至少 `5000ms` 后，
状态从 `1` 进入 `2`。因此页面收到 `selfRecoverStatus == 2` 时，车端已经给出
“允许下发恢复命令”的状态机结论，前端不应再用另一个可能不同步的
`mrcStatus > 1` 重复门禁。

页面下发 `3` 后，车端远控节点将其 one-shot 发布到 `/zeron/mrc/status`；
`health_arbitrator::mrc_self_recover_status_callback()` 消费该命令，并将自恢复
状态从 `2` 转为 `0`。

但该 callback 当前只更新 `MRCSelfRecoverStatusManager`，没有同步把
`MRCStatusManager` 从 MRC1/MRC2 转为 NORMAL/MRC0；同时 `handle_mrc()` 在处理
`self_recover_status=3` 时提前返回，同一请求中的 `mrc_status=0` 不会写入
`mrc_cloud_`。所以“恢复命令已有消费者”已经确认，但“MRC 主状态和 e2e 安全
输出完成退出”仍需补齐代码或通过目标车证据确认其他清零来源。

### 5.3 MRC1/MRC2 安全输出

当 `effective_mrc >= 2` 时，`ApplyMrcSafetyResponse()` 生成专用的 `mrc_msg_`：

```text
驱动轮请求扭矩 = 0
xbr_deceleration = 按车辆质量计算的紧急减速度
前进/倒车方向保持
转向回正
车速绝对值 < 0.3m/s 时：
  requested_gear = Neutral
  parking_brake_percent_cmd = 100.4
```

随后在 `TimerCallback()` 中发布到：

```text
/zeron/e2e_control/logical_control_info
```

这一步才是从 MRC 状态进入 e2e 安全控制输出的边界。

### 5.4 TimerCallback 的优先级

每个控制周期的大致优先级为：

```text
1. M 模式，或启动安全窗口：发布安全默认值
2. A/R 模式且 MRC 有效：发布 MRC 安全输出
3. A 模式：发布自动驾驶输出
4. R 模式：发布远控输出
```

当前头文件中的启动安全窗口为 `5000ms`，不是短暂的单个控制周期。启动窗口内
即使配置为 A/R，也先发布安全默认值。

MRC 可以由页面在 M/A/R 任意模式下设置，但在 e2e 的输出分支中：

- A/R 模式才进入 `ApplyMrcSafetyResponse()`。
- M 模式首先走手动安全默认输出。
- 人工制动接管会把模式切到 M、清除 `mrc_status_pd_`，并设置
  `brake_takeover_permanent_`，避免自动回到 A。

因此，“页面允许任意模式触发”与“e2e 只有 A/R 发布专用 MRC 输出”必须分别描述。

### 5.5 当前未启用的 e2e 断链触发

`GetArbitratedMrcStatus()` 中设计了 R 模式下远控消息超时转 MRC1 的逻辑，但当前
条件为：

```cpp
if (false && pd_age > kPdConnectionLossTimeoutSec && ...)
```

所以这条 e2e 内部“远控消息断开 -> MRC1”的逻辑目前不会执行。文档、测试和
验收不能把它当成已启用能力。车端远控节点自己的链路检测和手柄超时逻辑仍然是
另一条路径，不能与此条件混为一谈。

## 6. 恢复、停止和异常分支

### 6.1 MRC 状态语义

当前代码使用：

```text
0 = NORMAL
1 = MRC0
2 = MRC1
3 = MRC2
```

e2e 的安全输出阈值是 `>= 2`。因此 MRC0 会进入状态链，但不会触发
`ApplyMrcSafetyResponse()`。

### 6.2 页面自恢复

页面直接以车端上报的 `selfRecoverStatus == 2` 作为按钮启用条件，并发送：

```json
{
  "mrc_status": 0,
  "self_recover_status": 3
}
```

后端 `prepareInputs()` 会把两个字段都放入车端 inputs。专用车端分支中的
`handle_mrc()` 已读取 `self_recover_status=3`，将其排队并通过
`/zeron/mrc/status` one-shot 发布；`health_arbitrator` 随后消费该命令。

当前准确结论是：

```text
implemented：页面、后端、车端远控节点和 health_arbitrator 已形成命令消费链
implemented：self_recover_status=2 是车端状态机给出的可恢复信号
unverified：目标车辆是否部署了 origin/feature/mrc_self_recover 的对应构建
blocked：当前代码证据未显示恢复命令把 MRC 主状态完整清零
```

页面按钮应直接信任状态 `2`，避免文案显示“可恢复”但按钮仍被 `mrcStatus`
禁用。车端后续应明确由谁执行 MRC 主状态清零，并增加恢复完成、拒绝和超时状态，
不能把“命令已消费”等同于“车辆已恢复”。

### 6.3 独立 emergency-stop 分支

页面 API 仍有：

```text
POST /parallel-driving/control/emergency-stop
```

但该按钮当前在模板中 `v-if="false"`，且 Service 的
`emergencyStop()` 复用了 `ParallelDrivingControlMessage.emergencyStop()`。
该消息构造函数默认 `functionId=parallelDrivingControl`，而车端同时注册的是：

```text
parallelDrivingControl -> handle_parallelDrivingControl
emergencystop -> handle_emergencystop
```

`EMERGENCY_STOP` 在 `prepareInputs()` 中没有单独映射到
`functionId=emergencystop` 或 `inputs.controlType=emergencystop`。因此当前实现
存在以下协议风险：

```text
HTTP emergency-stop
  -> generic parallelDrivingControl
  -> inputs 可能没有 controlType
  -> 车端可能返回 unsupported controlType
```

这条接口不能在修复前被描述为“已完成紧急停车”。如果产品决定统一使用 MRC1
作为紧急停车，应直接复用 MRC 的状态链并删除/废弃这条重复协议；如果保留
`emergencystop`，则应让后端明确生成自定义消息并为其建立独立的执行确认。

## 7. 需要优先处理的问题

| 优先级 | 问题 | 影响 | 建议 |
|---|---|---|---|
| P0 | `sendAndForget` 没有执行完成语义 | 页面成功提示可能被误读为车辆已制动 | 增加 command state，以车端 ACK、MRC topic、e2e output、底盘停止分阶段确认 |
| P0 | 自恢复命令已消费，但 MRC 主状态清零路径不完整 | 页面可下发恢复，车辆可能仍保持 MRC 安全输出 | 由 health/e2e 明确完成 MRC1/MRC2 -> NORMAL/MRC0 转移，并增加恢复 ACK/超时/拒绝原因 |
| P0 | emergency-stop 与车端 `emergencystop` handler 不一致 | 独立接口可能走到 generic handler 并返回 unsupported | 统一成 MRC 协议或修正后端 functionId/自定义消息 |
| P1 | e2e PD timeout 条件为 `false &&` | 断链自动 MRC1 设计存在但实际不触发 | 用配置开关替代硬编码，并补断链实车测试 |
| P1 | 头文件和实现对 `mrc_status_pd_` 参与条件不一致 | MRC0 的仲裁语义可能被误解 | 固化枚举和优先级表，代码、注释、测试同源 |
| P1 | 页面 MRC1 按钮只用 `=== 2` 判断 active | 状态为 MRC2 时按钮文案是退出，但点击会再次发送 2 | 统一使用 `>= 2` 或按 MRC2 单独处理 |
| P1 | 状态值和来源字段分散 | 无法快速区分页面、手柄、链路和 health 触发 | 在 MRC status/event 中增加 `source`、`severity`、`command_id` |
| P2 | MRC 请求体在 Controller 使用裸 Map | 非法字段和缺失字段较晚才失败 | 引入强类型 DTO、范围校验和幂等策略 |

## 8. 推荐的后续目标模型

### 8.1 把 MRC 指令和 MRC 状态分开

建议建立显式契约：

```text
MrcCommand
  command_id
  source = page | video_auto | joystick | health | vehicle_link
  requested_level = 0 | 1 | 2 | 3
  recovery_action = none | request
  issued_at
  expires_at

MrcState
  effective_level
  source
  source_priority
  state_since
  error_code
  command_id
  vehicle_speed
  gear
  epb_state
```

`requested_level` 是某个来源的请求，`effective_level` 是 e2e 仲裁后的结果，
二者不应继续共用一个没有来源的 `mrc_status` 字段。

### 8.2 用显式状态机替代“HTTP 成功”

建议页面和后端至少追踪：

```text
CREATED
  -> GATED
  -> FORWARDED
  -> VEHICLE_ACKED
  -> MRC_STATUS_CONFIRMED
  -> E2E_OUTPUT_CONFIRMED
  -> VEHICLE_STOP_CONFIRMED
```

异常分支：

```text
GATE_TIMEOUT
FORWARD_FAILED
VEHICLE_ACK_TIMEOUT
MRC_STATUS_TIMEOUT
E2E_OUTPUT_TIMEOUT
STOP_TIMEOUT
CANCELLED
```

恢复也必须是独立状态机，至少区分：

```text
RECOVERY_REQUESTED
RECOVERY_ACCEPTED
RECOVERY_REJECTED
RECOVERY_STATUS_CONFIRMED
```

### 8.3 统一来源优先级

当前代码使用 `max`，但后续应明确“数值大小”和“安全优先级”是否完全等价。
推荐把优先级写成可测试的规则：

```text
health safety fault
  > vehicle link fault
  > joystick loss
  > page/video request
  > normal/recovery request
```

如果业务确实要求 MRC2 一定高于 MRC1，应在共享消息定义中固定，而不是让每个
节点自行解释 `max(0..3)`。

## 9. 可观测性和验收建议

### 9.1 最小关联字段

每一层至少记录以下字段：

```text
command_id / correlation_id
trace_id
cockpit_device_id
vehicle_device_id
room_id
message_id
request_id
request_message_id
requested_mrc
effective_mrc
mrc_source
event_time_monotonic
event_time_wall
```

其中车辆安全计时和超时判断使用单调时钟；墙上时间只用于跨系统对账。

### 9.2 建议指标

```text
mrc_command_total{source,result}
mrc_command_stage_duration_seconds{stage,result}
mrc_vehicle_ack_total{result}
mrc_status_confirmation_total{source,result}
mrc_e2e_output_total{level,result}
mrc_stop_confirmation_total{result}
mrc_recovery_total{result}
```

不要把 `vehicleDeviceId`、`messageId`、`commandId` 作为 Prometheus label；这些
字段应进入结构化日志或抽样事件，避免高基数。

### 9.3 测试验收矩阵

| 场景 | 必须验证的证据 |
|---|---|
| 页面 MRC0 | HTTP、车端 handler、`/zeron/mrc/status=1`、e2e 不进入 MRC1 安全输出 |
| 页面 MRC1，R 模式 | `mrc_cloud_=2`、topic=2、e2e output、扭矩为零、速度下降 |
| 页面 MRC2，A/R 模式 | topic=3、e2e 按 `>=2` 处理、报警等级符合预期 |
| 页面 MRC1，M 模式 | 页面请求可见，e2e 按 M 模式默认输出，确认产品预期 |
| 视频持续异常 | 500ms 采样、约 2s 触发、10s 状态确认超时 |
| 视频瞬时异常 | 不触发 MRC |
| 车云链路断开 | 验证车端 `is_link_ready()` 路径和状态上报；单独验证 e2e `false &&` 未启用 |
| 手柄超时 | 验证 `JoyMrcStateMachine` 进入 MRC1 以及保持/恢复规则 |
| health arbitrator 更高等级 | 验证与页面 MRC 取最大值时的来源和输出 |
| 自恢复 | 验证状态 `2` 启用按钮、命令 `3` 被消费，并确认 MRC 主状态、e2e 输出和底盘状态完成恢复 |
| emergency-stop | 先验证实际 functionId 和车端 handler，再决定保留或删除该接口 |
| R->M 人工刹车接管 | 验证 `mrc_status_pd_` 清零、模式保持 M、不会自动回 A |
| e2e 冷启动 | 验证 `5000ms` 安全窗口内不会输出 A/R 控制 |

## 10. 状态定义

本文使用以下状态词：

| 状态 | 含义 |
|---|---|
| `implemented` | 代码或配置已经存在 |
| `verified` | 有日志、端点、测试或实车证据证明行为成立 |
| `approved` | 设计已经评审，但不代表代码或部署完成 |
| `unverified` | 代码路径存在，但尚缺端到端或目标车验证 |
| `blocked` | 当前依赖缺失或协议未闭合，不能完成该项验收 |

截至 `2026-09-07`，本文专题的整体状态是：

```text
implemented/unverified
```

页面请求、ziot 门禁和 Room 异步发送、车端 MRC 缓存/50Hz 发布、自恢复命令
消费、e2e 订阅和安全输出代码均已存在；真实设备上的消息到达、执行时延、底盘
停车、自恢复主状态清零闭环和 emergency-stop 协议仍需按验收矩阵验证或修复。
