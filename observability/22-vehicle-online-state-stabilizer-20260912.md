# 远控页面车辆在线状态稳定器分析与前端优化

分析日期：`2026-09-12`

前端仓库：`zeron-cloud-web`

前端分支：`master`

基线 HEAD：`59b3c17c8736c2365675127853a1847fed489b72`

状态：`implemented/unverified`

本记录处理远控页面顶部 `pd-remote-focus-app-bar` 的车辆状态周期性在“在线”和
“离线”之间切换的问题。本次只修改前端展示状态，不修改后端设备状态探测、远控
会话协议、e2e 状态机或 watchdog 判定策略，也不改变控制按钮、MRC、视频挂载和
状态 WebSocket 的原有业务判定。

## 1. 现象

车辆实际仍在线，远控页面顶部状态却周期性出现：

```text
在线
  -> 离线
  -> 下一次刷新恢复在线
  -> 后续再次离线
```

状态切换周期与详情页 `5s` 轮询一致。页面在出现单次离线结果时还可能关闭车辆状态
WebSocket，使本来可以证明车辆仍在上报的实时链路被前端主动断开，进一步放大抖动。

## 2. 已证实链路

### 2.1 前端每 5 秒重新查询车辆状态

详情页通过 `setInterval` 每 `5000ms` 执行一次 `loadVehicle(true)`，见：

- [VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:3295)
- [VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:4798)

查询调用：

```text
POST /parallel-driving/vehicles/_query
```

见
[parallel-driving.ts](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/api/parallel-driving.ts:113)。

### 2.2 查询接口执行实时设备状态探测

后端查询不是只读取一个稳定缓存值，而是在组装每辆车时调用
`deviceInstanceService.getDeviceState()`：

- [ParallelDrivingController.java](/Users/minyi/workspace/autodrive/jetlinks-community/jetlinks-manager/parallel-driving-manager/src/main/java/org/jetlinks/community/parallel/driving/web/ParallelDrivingController.java:218)
- [ParallelDrivingVehicleService.java](/Users/minyi/workspace/autodrive/jetlinks-community/jetlinks-manager/parallel-driving-manager/src/main/java/org/jetlinks/community/parallel/driving/service/ParallelDrivingVehicleService.java:135)

`getDeviceState()` 继续调用 `DeviceOperator.checkState()`，并把结果写回设备状态：

- [LocalDeviceInstanceService.java](/Users/minyi/workspace/autodrive/jetlinks-community/jetlinks-manager/device-manager/src/main/java/org/jetlinks/community/device/service/LocalDeviceInstanceService.java:659)

因此，EventBus、RPC、session 或设备探测链路的一次瞬时不可用，有能力进入本次
查询结果。当前没有对应时段的浏览器网络响应和后端探测日志，不能进一步断言具体是
哪一层超时；但“每次轮询都会执行实时探测”已经由代码确认。

### 2.3 原前端把单次探测结果直接变成用户可见状态

原逻辑直接使用本次接口返回的 `vehicle.state`：

```text
接口 state
  -> vehicleStateValue
  -> 顶部 a-tag
  -> isVehicleOnline
  -> WebSocket 连接/关闭决策
```

顶部标签位于
[VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:13)。

这使单次瞬时探测结果同时影响：

1. 用户看到的在线状态。
2. 依赖 `isVehicleOnline` 的页面操作条件。
3. 状态 WebSocket 生命周期。

本次收窄后，只有第 1 项使用确认状态；第 2、3 项继续使用原始轮询状态，
保持改动前行为。

下一次 `5s` 轮询恢复为 `online` 后，页面又立即恢复在线，形成周期性抖动。

## 3. 根因结论

当前能够确认的直接根因是：

```text
后端实时探测结果存在瞬时变化
    -> 前端没有状态确认窗口
    -> 单次 offline/notActive 直接覆盖页面状态
    -> 前端可能关闭状态 WebSocket
    -> 下一次 online 探测又立即恢复
```

前端缺少“原始探测状态”和“用户可见确认状态”的分层，是页面抖动能够直接暴露给
驾驶员的原因。

本记录不把“后端为什么瞬时返回不可用”写成已确定根因。该问题仍需要结合目标时段
的 API 响应耗时、`checkState()` 调用结果和 EventBus/RPC 日志继续定位。

## 4. 本次前端设计

本次把车辆在线状态拆成三层证据：

```text
probeState
  本次 /vehicles/_query 返回的原始探测状态

confirmedState
  页面展示使用的确认状态

rawVehicleState
  控制、视频和状态 WebSocket 生命周期继续使用的原始轮询状态

realtimeLink
  最近一次 vehicle-status WebSocket 消息的新鲜度
```

架构图：

- [在线状态稳定器架构图](diagrams/vehicle-online-state-stabilizer.architecture.html)
- [架构图源文件](diagrams/vehicle-online-state-stabilizer.architecture.json)

### 4.1 状态确认规则

参数：

```text
轮询周期                    5s
离线连续确认次数            3
vehicle-status 新鲜窗口     15s
```

决策规则：

| 当前确认状态 | 本次探测 | WebSocket 证据 | 结果 |
| --- | --- | --- | --- |
| 任意 | `online` | 任意 | 立即确认 `online`，清空离线计数 |
| `online` | 第 1~2 次 `offline/notActive` | 任意 | 保持 `online` |
| `online` | 连续第 3 次及以后不可用 | 最近 `15s` 有消息 | 保持 `online` |
| `online` | 连续第 3 次及以后不可用 | 最近 `15s` 无消息 | 确认不可用状态 |
| 初始未知 | `offline/notActive` | 任意 | 接受初始状态，不伪造在线 |
| 任意 | 空值或未知状态 | 任意 | 不覆盖现有确认状态 |

该规则的含义不是固定延迟所有状态，而是：

- 恢复在线必须快，单次 `online` 立即生效。
- 从在线切换到离线必须有连续探测证据。
- 车辆状态 WebSocket 仍持续上报时，不能仅凭查询接口的一次状态抖动判离线。

状态机实现见
[VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:3770)。

### 4.2 实时证据仅用于展示确认

每次收到 `vehicle-status` 消息都会更新实时证据时间，作为展示状态稳定器判断
“后端查询结果是否可能只是瞬时误判”的辅助证据，见
[VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:5193)。

状态 WebSocket 的连接/关闭仍由原始 `vehicleState` 和远控接管状态决定，不使用
`confirmedVehicleState`，因此本次不会新增保活、关闭、重连或控制权限变化。

切换车辆时会同时清空：

- 原始探测状态。
- 确认状态。
- 离线候选次数和开始时间。
- 上一辆车的 WebSocket 新鲜时间。

避免上一辆车的状态证据进入下一辆车，见
[VehicleRemoteDeck.vue](/Users/minyi/workspace/autodrive/zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue:3795)。

### 4.3 诊断事件

状态变化写入现有前端观测通道：

```text
vehicle_state_probe
vehicle_state_unavailable_candidate
vehicle_state_confirmed
```

记录字段包括：

```text
probeState
previousProbeState
confirmedState
previousConfirmedState
offlineProbeCount
offlineCandidateAgeMs
statusWsFresh
statusWsMessageAgeMs
request durationMs
```

这些字段用于区分：

1. 接口单次误判。
2. 连续接口不可用。
3. WebSocket 仍有实时消息。
4. API 和 WebSocket 同时失去证据后的真实离线确认。

## 5. 本次修改边界

已修改：

- `VehicleRemoteDeck.vue` 的用户可见车辆在线状态计算。
- 展示稳定器的诊断字段。
- 前端状态变化诊断字段。
- 车辆路由切换时的稳定器重置。

未修改：

- `/parallel-driving/vehicles/_query` 接口。
- `DeviceOperator.checkState()` 和设备状态语义。
- 远控开始按钮、MRC1 按钮和离线占位区域的原始状态判定。
- 视频监控区域和状态 WebSocket 的原始状态生命周期判定。
- `sessionState`、页面结束远控和手柄暂退协议。
- e2e 状态机。
- watchdog 判定策略。
- MRC 判定和上报链路。

## 6. Harness 回归序列

按可重放状态序列验收，不依赖人工观察单次标签：

| 序列 | 期望确认状态 | 期望 WebSocket |
| --- | --- | --- |
| `online` | 立即在线 | 按原始状态建立 |
| `online, offline, online` | 展示全程在线 | 按原始状态关闭后再建立 |
| `online, offline, offline, online` | 展示全程在线 | 按原始状态生命周期 |
| `online, offline x3`，无实时消息 | 第 3 次确认离线 | 按原始状态关闭监控连接 |
| `online, offline x3`，每 5s 有实时消息 | 展示保持在线 | 按原始状态生命周期 |
| `online, offline xN`，最后实时消息超过 15s | 下一次探测确认离线 | 按原始状态关闭 |
| 首次加载即 `offline` | 立即离线 | 不建立监控连接 |
| 离线后一次 `online` | 立即恢复在线 | 重新建立 |
| 车辆 A 在线后切到车辆 B 离线 | B 立即显示离线 | 不复用 A 的实时证据 |
| 查询请求失败或无 `state` | 保持最后确认状态 | 不因请求异常主动翻转 |

## 7. 验收标准

### 7.1 功能

1. 实车在线且状态 WebSocket 持续有消息时，单次或周期性接口 `offline` 不再改变
   顶部状态。
2. 连续三次接口不可用且 `15s` 内没有状态消息时，页面可以确认离线。
3. 接口恢复一次 `online` 后，页面立即恢复在线。
4. 展示稳定器不改变控制按钮、MRC、视频挂载和 WebSocket 生命周期。
5. 切换车辆后不继承上一辆车的展示状态或实时消息时间。

### 7.2 可观测性

现场至少保留以下证据：

```text
vehicle_state_unavailable_candidate
  offlineProbeCount
  statusWsFresh
  statusWsMessageAgeMs

vehicle_state_confirmed
  previousConfirmedState
  confirmedState
  reason
```

### 7.3 当前验证状态

- 架构图 showcase 校验：`pass`，`9/9`。
- 架构图自动浏览器检查：`pass`，覆盖 `1440x900`、`1600x1000`、
  `1920x1080` 和 `2048x1320`。
- 前端生产构建：`pnpm build` 通过。
- 前端 `vue-tsc`：未完成。当前本地 `vue-tsc 1.8.27` 与
  `TypeScript 5.9.2` 不兼容，工具在分析项目代码前退出。
- 目标环境回归：`pending`。

因此当前状态为 `implemented/unverified`，不能标记为实车已验证。

## 8. 后续后端建议

本次先在前端阻断用户可见抖动。长期仍建议后端把设备状态证据拆开：

```text
lastReportedOnline
activeProbeState
activeProbeFailureReason
lastMessageAt
probeDurationMs
```

查询接口不应把一次探测超时与“车辆确定离线”完全等价。后端优化需要单独设计和
回归，不属于本次前端修改。
