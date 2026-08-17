# 平行驾驶远控生产问题分析与整改基线

> 分析日期：2026-08-09
> 状态：Aura 车端第一阶段整改已实施并通过静态检查；ROS 构建、台架、实车和端到端验收待执行
> 范围：ZIOT 服务端、zeron-cloud-web、Aura 车端远控客户端、JetLinks 实时消息链路
> 已知事实：车端 RTSP 视频服务正常；该事实可以降低“车辆整体断网”的可能性，但不能证明远控 TCP、EventBus、Redis、WebSocket 和数据库链路正常。

## 0. 车端整改实施状态

实施分支：

```text
aura: feature/chassis_mrc
```

本次修改文件：

```text
aura/src/control/e2e_control/include/e2e_control_v2.h
aura/src/control/e2e_control/src/e2e_control_v2.cc
aura/src/messages/parallel_driving_msgs/CMakeLists.txt
aura/src/messages/parallel_driving_msgs/srv/SetDrivingMode.srv
aura/src/ztd/ztd_network/ztd_cloud_driving/CMakeLists.txt
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp
aura/src/ztd/ztd_network/ztd_cloud_driving/config/vehicle_params.yaml
aura/src/ztd/ztd_network/ztd_cloud_driving/src/cloud_driving_client.cpp
```

已实施能力：

1. 页面请求模式 `requested_drive_mode` 与 e2e 实际模式 `drive_mode` 分离保存，普通手柄、车身和 EPB 控制要求两者都为 R。
2. M→R、A→R 和已有 ACTIVE 会话内的模式切换均由显式模式帧触发，不要求重新点击“开始接管”。
3. 人工制动超过 4% 时立即 R/A→M；踏板低于 2% 并连续 5 个周期稳定后，才允许显式 A/R 指令重新进入。
4. 制动接管锁存后，普通手柄帧和 PD 保活不能自动恢复 R，必须重新下发显式 A/R 模式指令。
5. e2e 的 `/zeron/e2e_control/driving_mode` 发布端使用 `QoS(1).transient_local()`；
   车云节点为兼容旧 `volatile` 发布端，仍以 `QoS(10)` 订阅，不依赖历史回放。
   e2e 每 100ms 发布一次实际模式，因此新启动车云节点会在下一次实时发布时完成同步。
6. `onTakeover` 和 `onRelease` 会清理旧会话缓存、手柄监督和 MRC，并显式通知 e2e 进入 M。
7. 页面持久型车身/EPB 预置可在请求 R 后缓存，实际 R 确认后的首个保活帧应用；喇叭 ON 不跨模式延迟执行。
8. `PD_HEARTBEAT` 仅刷新 e2e 的 PD 健康时间并更新车身/EPB状态，不覆盖最近一次运动控制量。
9. e2e 的 500ms PD 超时安全路径已启用，车云节点以 150ms 周期发送保活；云链路或车云进程失效时允许 e2e 进入 MRC1。
10. 长时间停车采用条件豁免：底盘数据新鲜、车速不高于 0.5km/h、最后一帧无油门/制动/转向输入时，手柄断流可进入 `PARKED_IDLE`，不新建 `JOYSTICK_IDLE_TIMEOUT`。
11. 车辆移动、底盘数据陈旧、最后一帧仍有运动/转向输入或已有 MRC1 时，停车豁免不生效。
12. `remotejoystick` 在请求模式或实际模式不是 R 时返回 `REMOTE_MODE_NOT_READY`，不再静默返回成功。
13. `chassis_status` 新增请求模式、远控就绪、手柄监督和健康状态等可观测字段；原有字段保持不变。
14. 新增车内 ROS2 `SetDrivingMode` service，模式请求必须得到 e2e 的 `accepted + actual_mode` 确认后，车云节点才更新请求模式缓存。
15. 模式 service 使用云端 `messageId` 作为 `request_id`，e2e 保留最近 64 条结果用于幂等重放，并拒绝同一 ID 对应不同模式。
16. e2e 每次启动生成新的 `instance_id`；车云状态上报携带该值，可识别 e2e 重启和旧状态污染。
17. 显式 M 建立人工模式锁存，ADS 活跃不能自动把显式 M 恢复为 A；内部参数写回通过 guard 与外部模式命令区分。
18. `INVOKE_FUNCTION_REPLY.success` 与 handler 返回的 `output.success` 保持一致，拒绝和超时不再被错误包装成外层成功。

新增状态字段：

```text
requested_drive_mode
remote_mode_ready
e2e_instance_id
actual_mode_feedback_received
mode_service_supported
joystick_supervision_armed
joystick_health_state
last_joystick_motion_active
parked_idle_safe
```

手柄健康状态：

```text
normal
detecting
mrc1
suppressed
parked_idle
```

### 0.1 车端场景覆盖矩阵

下表的“已覆盖”表示源码分支和安全语义已经实现，不表示已经完成 ROS 构建、台架或实车验证。

| 场景 | 当前源码行为 | 状态 |
|---|---|---|
| 新接管会话 | 清缓存、清 MRC、显式进入 M，等待后续 R | 已覆盖 |
| ACTIVE 会话 M→R | 显式 R 可直接进入，不要求先经过 A 或重新接管 | 已覆盖 |
| ACTIVE 会话 A→R | 显式 R 进入远控 | 已覆盖 |
| 请求 R、实际仍为 M/A | 手柄和即时控制返回 `REMOTE_MODE_NOT_READY` | 已覆盖 |
| 实际 R 后人工踩制动 | 立即进入 M并锁存人工接管 | 已覆盖 |
| 制动未稳定释放时请求 A/R | 拒绝进入并保持安全默认控制 | 已覆盖 |
| 制动稳定释放后普通手柄持续到达 | 不允许普通帧自动恢复 R | 已覆盖 |
| 制动稳定释放后显式 R | 清除锁存并重新进入 R | 已覆盖 |
| R 下持续收到中性手柄帧并长时间停车 | 保持正常监督，不产生空闲误报 | 已覆盖 |
| R 下停车后不再收到手柄帧 | 满足新鲜底盘、低车速和中性末帧时进入 `PARKED_IDLE` | 已覆盖 |
| R 下行驶中手柄断流 | 连续超时后进入 MRC1 | 已覆盖 |
| 最后一帧仍有转向后断流 | 不允许停车豁免，进入超时检测 | 已覆盖 |
| 底盘状态超过 500ms 未更新 | 不允许停车豁免，进入超时检测 | 已覆盖 |
| 驾驶舱显式 `bt_others=2` | 已安全停车则 `PARKED_IDLE`，否则立即 MRC1 | 已覆盖 |
| 驾驶舱 `bt_others=1` 主动退出 | 进入 `SUPPRESSED`，收到正常帧后恢复监督 | 已覆盖 |
| 车云进程或 ROS PD 消息停止 | e2e 超过 500ms 进入 PD MRC1 | 已覆盖 |
| 页面在实际 R 前预置灯光/EPB | 先缓存，实际 R 后应用 | 已覆盖 |
| 页面在实际 R 前按喇叭 ON | 返回未就绪，不延迟到以后鸣笛 | 已覆盖 |
| 页面只发车身/EPB、不动手柄 | 实际 R 下立即发布心跳型控制，不覆盖运动量 | 已覆盖 |
| 会话释放 | 清状态并显式回 M | 已覆盖 |
| 旧 volatile 模式订阅者 | 可继续接收新发布的实时模式；不具备晚加入历史值能力 | 兼容 |
| e2e 重启、车云节点不重启 | 新实例从 M 上报；旧请求 R 不再放行手柄，必须重新显式请求 R | 已覆盖 |
| 相同 `request_id` 重试相同模式 | 返回缓存结果；若实际模式后来变化则要求新 ID | 已覆盖 |
| 相同 `request_id` 改为另一模式 | 返回 `REASON_REQUEST_ID_CONFLICT` | 已覆盖 |
| 新车云节点连接旧 e2e | 自动降级旧 Topic，并等待实际模式反馈；不发送新 heartbeat sentinel | 过渡兼容 |
| 旧车云节点连接新 e2e | 新 e2e 保留旧 Topic 订阅，沿用旧行为 | 兼容 |

### 0.2 发布兼容约束

#### 0.2.1 车云线协议兼容

当前改动兼容现有 JetLinks 服务端和前端，兼容依据如下：

1. 车云功能 ID 未改变，仍为 `onTakeover`、`onRelease`、`parallelDrivingControl`、
   `driveMode`、`remotejoystick` 和 `emergencystop`。
2. `parallelDrivingControl` 的原字段未删除、改名或改变语义，仍使用
   `drive_mode`、`hbh_li_cmd`、`lbh_li_cmd`、`horn_cmd`、`hazard_li_cmd`、
   `epb_cmd` 和 `aux_li_cmd`。
3. `SetDrivingMode.srv` 只存在于车内 ROS2 通信，不进入车辆 TCP 与 JetLinks 协议，
   云端不需要识别该 service。
4. `chassis_status` 只增加字段，原有底盘字段保持不变。JetLinks 和旧前端使用 Map/JSON
   接收状态，可以忽略未知字段。
5. `INVOKE_FUNCTION_REPLY` 的消息外壳、`functionId`、`requestMessageId`、`messageId`、
   `output` 和 `timestamp` 均保持不变；仅修正外层 `success` 与执行结果一致。
6. 当前房间转发对控制功能设置 `Headers.async=true` 并使用 `sendAndForget`；
   `remotejoystick` 还设置 `noReply=true`。因此现有主链路通常不会等待新增回复，
   新错误码不会阻断或改变旧云端下发流程。

这里的“兼容”表示旧云端可继续发送原消息、接收原状态，不表示旧页面已经具备车辆执行
确认。当前 HTTP `sendControlCommand` 成功只代表平台完成异步投递，车辆是否真正进入 R
仍必须以 `chassis_status.drive_mode=2` 且 `remote_mode_ready=true` 为准。

#### 0.2.2 混合版本矩阵

| 车云节点 | e2e | 行为 | 发布建议 |
|---|---|---|---|
| 新 | 新 | 使用 `SetDrivingMode` 获取执行确认，并启用安全 PD heartbeat | 目标生产组合 |
| 新 | 旧 | 降级 `/zeron/parallel_driving/control_info`，等待实际模式反馈，不发送 `PD_HEARTBEAT=255` | 可短期过渡 |
| 旧 | 新 | 新 e2e 继续订阅旧 Topic，保持原有模式切换行为 | 可兼容运行 |
| 旧 | 旧 | 完全保持旧行为，不具备本次修复 | 不建议继续生产使用 |

很旧的 e2e 不识别 `PD_HEARTBEAT=255`，可能把它当作手柄空闲帧并周期性覆盖运动控制。
新车云节点以 `SetDrivingMode` service 是否存在作为能力标识，仅在新 e2e 可用时发送该
heartbeat，避免新车云节点与旧 e2e 混跑时引入控制回退。

#### 0.2.3 发布和回滚顺序

新增 service 是编译期接口依赖，推荐按以下顺序构建和发布：

```text
1. parallel_driving_msgs
2. e2e_control_v2
3. cloud_driving_vehicle
```

运行态推荐先升级 e2e，再升级车云节点。回滚时顺序相反：先回滚车云节点，再回滚 e2e。
这样不会出现旧 e2e 收到新 heartbeat sentinel 的窗口。

配置文件新增参数均有代码默认值，旧配置文件不包含这些键时仍可启动：

```text
mode_service_discovery_timeout_ms = 150ms
mode_service_response_timeout_ms = 800ms
legacy_mode_feedback_timeout_ms = 1200ms
```

模式失败码：

```text
MODE_SWITCH_TIMEOUT
MODE_SWITCH_REJECTED
REMOTE_MODE_NOT_READY
```

service 拒绝原因：

```text
REASON_INVALID_MODE
REASON_BRAKE_ACTIVE
REASON_BRAKE_RELEASE_PENDING
REASON_INTERNAL_REJECTED
REASON_REQUEST_ID_CONFLICT
```

### 0.3 当前结论边界

车端源码已经覆盖本次 M→R 失败、制动接管恢复、长停车和 PD/手柄超时的主要场景，
但当前环境没有 ROS/colcon 构建环境，也没有台架和实车输入，因此不能声明“所有 case
均已动态验证”或“整个远控系统已经可直接生产发布”。

以下服务端和前端问题仍未在本次车端修改中解决：

```text
CloudDrivingClient TCP 半开和致命 errno 的统一重连
服务端手柄高并发队列的顺序、过期和 latest-only 语义
前端/服务端车辆执行确认与 REMOTE_READY 握手
WebSocket 生命周期和状态覆盖
Redis 活跃房间固定 TTL
同步 report_property 对单线程 ROS 回调的潜在阻塞
```

后续章节保留问题发现时的全链路分析基线；其中与车端旧实现冲突的描述，以本节实施状态为准。

### 0.4 2026-08-12 远控消息空档复核与待整改项

复核日志：

```text
/Users/minyi/Downloads/ztd_cloud_driving_20260812100356.log
/Users/minyi/Downloads/ziot_8848.log.2026-08-12.43
```

本次通过 `messageId`、消息内层 `id` 和源 `timestamp` 对齐车端与云端日志，确认了 4 次
MRC1 对应的车端收包空档：

| MRC1 触发时间 | MRC 日志 gap | 车端实际相邻收包空档 |
|---|---:|---:|
| `1786500678.611` | 875ms | 约 877ms |
| `1786500723.573` | 923ms | 约 1022ms |
| `1786500756.075` | 868ms | 约 1299ms |
| `1786500767.702` | 875ms | 约 1082ms |

#### 0.4.1 已确认事实与结论边界

1. 4 次空档后均出现消息集中到达；对应时间窗口未发现车辆 TCP 断开或重连记录。
2. 驾驶舱消息在 JetLinks TCP 入口、路由和车辆下行事件形成附近仍持续处理，未发现与
   车端空档等长的统一停顿。第三次事件中，两条消息在 JetLinks 同一毫秒形成下行事件，
   Aura 接收时间却相差约 1.299 秒。
3. 因此当前只能把延迟范围定位在：

```text
JetLinks 形成车辆下行事件/编码附近
  -> Netty 实际 write/flush、TCP/网络、Aura socket 读取和线程调度
  -> Aura remotejoystick handler 收到
```

现有日志中的“已下发第 N 条”只说明消息进入或接近编码路径，不能证明 Netty
`write/flush` 已完成，更不能证明 Aura 已收到。当前证据不足以直接认定“JetLinks 消息
堆积”为根因。

4. 车端共处理 `14656` 条 `remotejoystick`，但仅有 `6386` 个不同源 `timestamp`；
   同一采样最多被发送 6 次，实际入口约 50～60 条/秒。重复在 JetLinks TCP 入口前已经
   存在，主要问题位于驾驶舱发送侧。
5. 所有消息的 `seq` 均固定为 `"1"`，当前无法依靠该字段可靠识别丢包、重复和乱序。
6. Aura 实际处理顺序中存在源 `timestamp` 回退，主要为 1～101ms 的局部乱序；现有证据
   不能证明约 1 秒的旧指令倒灌直接触发了上述 4 次 MRC1。
7. 第二、第四次 MRC1 清除后约 100ms 又进入 `detecting loss`。批量到达的同一采样重复
   包可能满足了当前恢复条件，但稳定、连续的新鲜控制流尚未真正恢复。
8. 第三次 MRC1 附近同时出现 `cloudLinkPing rtt_ms=3444`。JetLinks 收到该 ping 后
   `platformProcessMs=0`，并约 28ms 完成响应编码，说明该窗口还存在车辆共享连接、网络
   或 Aura socket/线程调度延迟，不能只从远控下行业务队列解释。
9. Router 持续把车辆下行
   `/device/parallel-driving-vehicle/*/message/send/function` 事件重新按“车辆到云端”
   处理，357 秒内产生 `12156` 条“未找到激活房间”失败，约 34 条/秒。该日志不是 Aura
   ACK，而是下行事件被错误自消费。
10. 云端日志约 593 行/秒、286KiB/秒，大量完整 payload、协议转换过程和 Router WARN
    会增加日志 I/O 与线程调度压力，但现有证据不能证明日志压力就是 MRC1 的直接根因。

#### 0.4.2 待整改项

**P0：驾驶舱发送侧**

1. 恢复为每个手柄采样只发送一帧，目标保持 10Hz；禁止同一采样生成 5～6 个不同消息 ID。
2. `seq` 改为会话内单调递增；重新接管时同时更新会话标识或明确重置规则。
3. 保留唯一消息 `id` 和源采样 `timestamp`，用于端到端关联。

**P0：云端车辆下行**

1. 同一车辆使用严格串行的下发通道，不能由多个
   `remotejoystick-downstream-*` 线程并发决定最终发送顺序。
2. 普通控制帧采用有界 `latest-only` 语义：发生积压时只保留最新帧，恢复后不得补发旧帧。
3. 基于 `session + seq` 去重并拒绝旧序号。在驾驶舱递增 `seq` 上线前，可临时根据源
   `timestamp + 控制值` 丢弃完全重复帧。
4. “编码完成”和“socket 写完成”分别统计；补充 Netty write/flush completion 的耗时、
   失败和车辆级待发送队列指标。

**P0：Router 消息方向**

1. Router 订阅排除车辆下行 `/message/send/function`，或在入口按消息方向明确过滤。
2. 不再把下行 `INVOKE_FUNCTION` 标记为“车辆到云端”并重新路由。
3. 修复后，“未找到激活房间”不应再由车辆下行控制帧持续触发。

**P0：Aura MRC 恢复条件**

1. MRC1 不得由同一源采样的重复包累计满足恢复条件。
2. 恢复应依据不同且递增的 `seq`；过渡期可依据不同且递增的源 `timestamp`，要求连续
   新鲜帧后再清除 MRC1。连续帧数量和时间窗口配置化，并通过台架验证确定。
3. 对旧序号、源时间戳明显回退或已超过有效期的控制帧不执行，避免积压释放后执行旧控制。

**P1：低影响定位日志**

1. 不增加逐帧 Aura ACK。正常路径按每 10 条或每秒聚合一次，异常路径记录完整明细。
2. 关联字段统一为：

```text
sessionId
seq
innerId
outerMessageId
sourceTimestamp
cloudIngressAt
routeAt
encodeAt
writeCompleteAt
auraReceiveAt
queueWaitMs
frameAgeMs
thread
```

3. 按车辆记录队列深度、替换旧帧数、重复/过期/乱序丢弃数、write 失败数和 write 耗时。
4. Aura 仅在收包间隔超过检测阈值、MRC 触发/清除、源时间戳倒退时输出逐帧关联信息。

#### 0.4.3 本轮验收标准

1. 驾驶舱入口稳定在目标约 10Hz，同一采样重复数为 0，`seq` 在会话内单调递增。
2. 同一车辆下发严格有序，积压恢复后不补发旧控制帧。
3. Router 对车辆下行控制事件的自消费错误为 0。
4. 日志可以区分云端入口、路由、编码、write 完成和 Aura 接收阶段。
5. MRC1 不会被一批重复帧错误清除，也不会在清除后约 100ms 因数据流未恢复再次进入
   `detecting loss`。
6. 完成 write completion 和 Aura receive 阶段埋点后，再根据新增证据判定最终延迟发生
   在 Netty、网络还是 Aura socket/线程调度。

## 1. 问题概述

当前生产运行中主要出现以下问题：

1. Aura 车端底盘状态有上报，但前端远控页面频繁不显示或停止更新。
2. 远控过程中 `JOYSTICK_IDLE_TIMEOUT`、`VEHICLE_RECEIVE_TIMEOUT` 较以前明显增多。
3. 车辆在远控模式下长时间停车后，驾驶舱手柄无法继续控制车辆，但前端页面离散指令仍可下发。
4. 已有远控会话保持 ACTIVE 时，车辆实际模式为 M；司机只在页面切换 M→R，罗技手柄和 EPB 仍不生效，随后只切换 A→R 即立即恢复，全程没有重新点击“开始接管”。
5. 当前 PostgreSQL 规格约为 1C2G，同时承担业务数据、设备日志和 TimescaleDB 时序写入，数据量持续增长。

涉及代码：

| 层级 | 目录或文件 |
|---|---|
| 服务端远控业务 | `jetlinks-community/jetlinks-manager/parallel-driving-manager` |
| 服务端远控协议 | `jetlinks-community/dev/zeron-parallel-protocol` |
| JetLinks 核心链路 | `jetlinks-core`、`jetlinks-community/dev/jetlinks/jetlinks-supports` |
| 前端远控页面 | `zeron-cloud-web/src/modules/parallel-driving-manager-ui/views/vehicle-list/VehicleRemoteDeck.vue` |
| 前端 WebSocket | `zeron-cloud-web/src/modules/parallel-driving-manager-ui/utils/websocket.ts` |
| Aura 车端接入 | `aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp` |
| Aura 控制执行 | `aura/src/control/e2e_control/src/e2e_control_v2.cc` |
| Aura TCP 客户端 | `aura/src/ztd/ztd_network/ztd_cloud_driving/src/cloud_driving_client.cpp` |

## 2. 总体判断

当前问题不是单一数据库性能问题，而是实时链路中多处正确性和稳定性风险叠加：

1. **P0：车端远控 TCP 存在假在线和无法可靠重连的风险。**
2. **P0：手柄控制帧经过多级高并发、大队列，无法保证同一车辆的顺序和时效性。**
3. **P0/P1：WebSocket 前后端均存在连接互相覆盖或状态静默丢失的条件。**
4. **P0：模式指令只有异步提交成功，没有车辆执行确认；Aura 的目标模式缓存和 e2e 实际模式还存在旧状态回报覆盖新 R 指令的竞态。**
5. **P0/P1：车辆退出 R 模式后会静默丢弃手柄帧，Redis 房间又会固定 12 小时过期。**
6. **P1：1C2G PostgreSQL 是重要的延迟放大器，但不能单独解释所有现象。**

RTSP 正常说明车辆视频链路可用，不等于以下链路可用：

```text
驾驶舱 TCP
  -> JetLinks 解码
  -> EventBus
  -> 平行驾驶路由
  -> 车辆消息编码
  -> 车辆远控 TCP
  -> Aura ROS 控制发布

Aura chassis_status
  -> 车辆远控 TCP
  -> JetLinks 解码/EventBus
  -> WebSocket Handler
  -> 浏览器 WebSocket
  -> Vue 状态合并与渲染
```

RTSP 与远控业务通常使用不同端口、连接、线程、缓冲区和服务进程，因此仍需单独验证远控链路。

## 3. 现象一：底盘状态上报但前端不显示

### 3.1 前端 WebSocket 是模块级全局单例

`parallel-driving-manager-ui/utils/websocket.ts` 使用：

```ts
let ws: WebSocket | null = null
```

远控页、车辆详情页和其他组件共用同一连接状态，存在以下风险：

- 一个组件卸载时调用 `closeParallelDrivingWebSocket()`，会关闭另一个仍在使用的页面连接。
- 新调用方发现已有 `OPEN` WebSocket 时直接返回，不会注册新调用方的 `onMessage`。
- 缓存路由、抽屉和页面生命周期重叠时，容易出现连接被错误复用或关闭。

这与“底盘状态偶发整块不显示”高度吻合。

### 3.2 WebSocket 服务端允许静默丢包

`ParallelDrivingWebSocketHandler.WebSocketSessionInfo` 当前使用：

```java
Sinks.many().multicast().directBestEffort();
statusSink.asFlux().sample(Duration.ofMillis(200));
statusSink.tryEmitNext(status);
```

风险：

- `directBestEffort` 在慢消费者或部分并发场景下允许丢消息。
- `tryEmitNext` 的结果未检查，`FAIL_OVERFLOW`、`FAIL_NON_SERIALIZED`、`FAIL_ZERO_SUBSCRIBER` 等情况不可见。
- 所有属性消息统一 `sample(200ms)`，后到的部分属性包可能替代完整 `chassis_status` 包。
- 每个浏览器会话分别订阅 `local + broker`，集群场景需要确认是否重复订阅或重复推送。

### 3.3 前端 RAF 状态覆盖

`VehicleRemoteDeck.vue` 在同一个 `requestAnimationFrame` 窗口内执行：

```ts
pendingStatusPatch = mapped
```

后到的部分状态包会整体覆盖前一个尚未刷新的 patch。正确语义应为字段合并，并按消息时间戳拒绝旧状态。

此外：

```ts
const soc = Number(raw.vcu_soc || 0.0)
```

当消息没有 `vcu_soc` 时会错误写入 `0`。缺失字段应保持旧值，而不是使用业务默认值覆盖。

### 3.4 车端同步发送可能阻塞 ROS 回调

车端默认每 100ms 调用一次：

```cpp
vehicle_->report_property("chassis_status", payload);
```

当前调用方忽略返回值，socket 发送也没有明确发送超时。如果远控 TCP 发送缓冲区阻塞，同一个 `spin_some` 线程中的 ROS timer 和 callback 都可能被拖慢。

## 4. 现象二：远控中的 Timeout 增多

### 4.1 车端 TCP 假在线

`CloudDrivingClient::is_link_ready()` 当前仅判断：

```cpp
return authenticated_ && sock_ != INVALID_SOCKET;
```

连接异常处理存在缺口：

- `send()` 仅在 `EPIPE` 时标记连接关闭。
- `recv()` 仅在返回 `0` 时标记连接关闭。
- `ECONNRESET`、`ETIMEDOUT`、`ENOTCONN` 等错误不会统一触发断链和重连。
- 没有明确的发送超时、TCP keepalive、应用层连续失败熔断。
- 主循环只检查 `is_connection_closed_by_peer()`，其他失败可能长期不重连。
- `sock_`、`authenticated_`、关闭标识跨线程访问的同步边界不完整。

因此可能出现：

```text
RTSP 正常
远控 TCP 已半连接或单向失效
is_link_ready() 仍返回 true
控制下发和 chassis_status 上报同时异常
```

### 4.2 控制帧多级并发、乱序和陈旧积压

服务端当前配置：

| 层级 | 调度配置 |
|---|---|
| `ParallelDrivingMessageRouter` | boundedElastic 32 线程、100000 队列 |
| Router Flux | `publishOn(..., 512)`、`flatMap(..., 128, 512)` |
| `ParallelTcpDeviceMessageCodec` | boundedElastic 16 线程、50000 队列 |

这类配置偏向“保证吞吐并尽量不拒绝”，不符合实时控制要求。

远控控制帧必须满足：

- 同一驾驶舱到同一车辆严格有序。
- 新帧优先于旧帧。
- 超过有效期的控制帧必须丢弃，不能排队后补发。
- 队列必须极小且严格有界。
- 紧急停车应有独立高优先级通道。

当前多级大队列可能造成平台仍在处理旧帧，而车端已经因为新帧间隔过大进入 MRC。

### 4.3 Timeout 实际语义

车端默认参数：

```text
joystick_ping_interval_s = 0.1
joystick_msg_timeout_ms = 300
joystick_mrc1_consecutive = 6
pd_keepalive_interval_s = 0.15
```

`JOYSTICK_IDLE_TIMEOUT` 可能由以下条件触发：

- R 模式下 `remotejoystick` 消息间隔持续超过阈值。
- 驾驶舱主动发送 `bt_others=2`，车端立即进入手柄空闲安全处理。

`VEHICLE_RECEIVE_TIMEOUT` 来源于远控业务链路状态，不代表 RTSP 视频接收超时。当前名称容易被误解为车辆整体网络异常。

当前 Aura 分支的 `e2e_control_v2.cc` 中，PD 连接丢失检测条件写成：

```cpp
if (false && pd_age > kPdConnectionLossTimeoutSec && ...)
```

因此该分支的 e2e PD 超时安全路径实际被禁用。当前看到的
`VEHICLE_RECEIVE_TIMEOUT` 主要由 `cloud_driving_vehicle.cpp` 在
`!vehicle_->is_link_ready()` 时写入 `chassis_status`，不能将它解释为
`e2e_control_v2` 已因控制帧超时进入 MRC。该禁用逻辑在生产发布前必须重新评审，
但不能在未修复链路状态机前直接打开并假定问题解决。

不应在修复排队、乱序和连接状态机之前简单放宽 300ms 阈值，否则只会推迟安全降级并掩盖实时链路问题。

## 5. 现象三：长时间停车后手柄失效

### 5.1 车辆已退出 R 模式

车端订阅到驾驶模式从 R 切换至 M/A 时，会执行：

```cpp
cached_drive_mode_ = 0;
```

后续 `remotejoystick` 到达时先更新时间和统计计数，但当 `cached_drive_mode_ != 2` 时直接返回成功，不发布 ROS 控制消息。

这会产生误导性表象：

- 平台可能认为指令处理成功。
- 车端日志显示持续收到手柄帧。
- 实际没有发布车辆控制。
- 前端离散命令仍可能通过另一条车辆直达路径成功。

恢复控制前必须重新建立 R 模式。生产日志应重点检查：

```text
[driving_mode] R
[driving_mode] R->M/A
[remotejoystick] drop: cached_drive_mode_
cloud must re-send driveMode(R)
```

### 5.2 ACTIVE 会话内 M→R 不生效，A→R 后恢复

现场复现：

```text
远控会话已经 ACTIVE
车辆实际模式 M
  -> 司机只在远控页面选择 R
  -> 罗技手柄、EPB 等控制不生效
  -> 页面只切换 A -> R
  -> 手柄立即恢复
```

全程没有重新点击“开始接管”，因此“接管前 R 指令被拒绝”或“后到的
`onTakeover` 把 R 重置为 M”不能作为本次复现的直接根因。接管握手不足仍是通用
生产风险，但本次应聚焦已有会话内的模式切换链路。

#### 5.2.1 M→R 在 e2e 状态机中本来就受支持

`DriveStateMachine` 的 `MANUAL` 分支明确处理：

```cpp
case DriveEvent::CMD_SWITCH_TO_R:
    transition(DriveState::REMOTE, true);
```

`PDrivingControlCallback` 也把页面模式命令识别为显式云端命令：

```cpp
const bool is_explicit_cloud_cmd = (msg->joystick_status == 0);
```

`handle_driveMode` 发布的正是 `joystick_status=0`。所以直接 M→R 不需要先经过 A；
A→R 能恢复说明 A 更像一次额外的同步、等待和重试，而不是状态机要求的必经路径。

#### 5.2.2 前端和服务端都没有证明 R 已执行

前端 `handleDriveModeChange` 在请求完成前先更新：

```ts
uiDriveMode.value = mode
remotePrefDriveMode.value = mode
```

失败时只执行 `console.warn`，没有可见错误、命令超时、重试或“等待车辆确认”状态。
虽然 `uiDriveMode` 后续会被 `chassis_status.drive_mode` 拉回实车模式，但这只能看到
最终状态，不能区分指令未送达、Aura 未发布、e2e 拒绝或进入 R 后又被打回 M。

服务端又给所有功能调用设置：

```java
Headers.async = true
```

随后使用 `device.messageSender().sendAndForget(forwarded)`。因此 HTTP 成功只证明消息
被异步提交，不证明 Aura 收到，更不证明 e2e 已经执行 M→R。

#### 5.2.3 Aura 存在目标模式缓存被旧状态回报覆盖的竞态

Aura 同时维护两套状态：

```text
cached_drive_mode_   页面/云端期望模式，决定手柄帧是否发布
latest_driving_mode_ e2e 实际模式回报，用于底盘状态上报
```

`handle_driveMode(R)` 在远控 TCP 后台监听线程中先把
`cached_drive_mode_=2`，再向 e2e 发布 R。e2e 的模式回报则由主线程每约 100ms
执行一次 `rclcpp::spin_some` 后处理。两条线程和两个队列之间没有模式命令序号。

模式订阅回调当前执行：

```cpp
if (prev == 2 && (msg->mode == 0 || msg->mode == 1))
{
    if (cached_drive_mode_ == 2)
    {
        cached_drive_mode_ = 0;
    }
}
```

如果旧的 R→M/A 回报排队期间司机下发了新的 R，旧回报可能在新命令之后才执行，
从而把刚写入的 `cached_drive_mode_=2` 重置成 0。此时可能形成：

```text
e2e actual mode = R
Aura cached mode = M
```

随后所有手柄帧都在 Aura 第一层门控被丢弃。司机先切 A、等待页面/车端状态收敛，
再切 R，等价于重新建立一次较清晰的模式顺序，因此可能恢复。

这是静态代码可确认的竞态条件，但是否命中本次现场仍需以时间顺序日志验证。

#### 5.2.4 物理制动可能让 R 刚生效就立即退回 M

e2e 每次收到 chassis 信息都会检查：

```cpp
vcu_vcu_manual_brk_pedal_pos > 4.0
```

满足条件时立即发送 `BRAKE_TAKEOVER`，执行 R→M，并设置
`brake_takeover_permanent_=true`。页面显式 R 可以暂时清除该标志，但只要下一帧
制动踏板仍大于 4%，就会再次进入 M。

因此另一个符合现场的时序是：

```text
页面 R 到达并执行
  -> e2e 短暂进入 R
  -> 下一帧制动踏板仍 > 4%
  -> Brake takeover R→M
  -> Aura 收到 M 回报并把 cached_drive_mode_ 清零
  -> 手柄持续被丢弃
```

A→R 之间的人工操作间隔可能刚好让制动踏板值回落，而不是 A 模式本身修复了 R。
当前没有踏板进入/退出阈值的滞回、持续周期确认或“R 请求被制动阻止”的明确反馈。

#### 5.2.5 Aura 收到手柄帧，但返回成功后丢弃

`handle_remotejoystick` 先更新接收时间和计数，然后检查：

```cpp
if (cached_drive_mode_ != 2)
{
    return {{"success", true}, {"ack", "ok"}};
}
```

因此在 M/A 状态下：

- Aura 日志能够看到 `remotejoystick` 到达。
- 平台异步发送链路可以记录成功。
- Aura 返回值仍是 `success=true`。
- `/zeron/parallel_driving/control_info` 不会发布该控制帧。
- EPB、转向、油门和制动都不会进入 `e2e_control_v2`。

这不是链路丢包，而是车端模式门控后的静默业务丢弃。

#### 5.2.6 e2e_control_v2 存在第二层 R 门控

`PDrivingControlCallback` 仅在 `msg->drive_mode == DRIVE_R` 时应用远控命令。
非 R 消息会调用 `SetDefaultValueForPDCtrl()` 后返回；EPB 的实际赋值也位于 R
分支内部。

此外，人工制动接管会设置 `brake_takeover_permanent_=true`。普通手柄帧不能覆盖该
状态，页面显式 R 可以清除标志，但不能阻止仍然有效的制动踏板在下一帧再次触发接管。

#### 5.2.7 当前状态模型不够

生产系统必须区分：

```text
SESSION_ACTIVE
TAKEOVER_DELIVERED
MODE_COMMAND_SENT
VEHICLE_MODE_CACHED_R
E2E_ACTUAL_MODE_R
REMOTE_READY
```

当前只有服务端 ACTIVE 和页面乐观模式，无法证明远控已经可执行。建议由服务端编排接管顺序，
为每次接管生成 `sessionId/sessionEpoch`，为每次模式切换生成单调递增
`modeCommandSeq`，并要求车辆上报：

```text
sessionId
modeCommandSeq
requestedDriveMode
cachedDriveMode
actualDriveMode
remoteControlReady
modeRejectReason
brakePedalPosition
lastJoystickSeq
lastControlAppliedAt
```

只有车辆确认当前会话、Aura 缓存和 e2e 实际模式均为 R 后，才能进入
`REMOTE_READY` 并允许手柄控制。非 R 模式收到手柄帧时不得返回无条件成功，应返回
`REMOTE_MODE_NOT_READY`，同时产生指标、日志和前端告警。

本次现场优先验证以下三条链路：

```text
1. 服务端是否确实把第一次 R 写入车辆 TCP
2. Aura 是否收到 R，随后是否被旧 M/A 回报覆盖 cached_drive_mode_
3. e2e 是否进入 R 后因 brake_pedal_pos > 4.0 立即 R→M
```

### 5.3 Redis 房间固定 12 小时过期

`ParallelDrivingRoomManager` 创建以下键时固定设置 12 小时 TTL：

```text
pd:room:info:{cockpitId}-{vehicleId}
pd:room:idx:cockpit:{cockpitId}
pd:room:idx:vehicle:{vehicleId}
```

活跃控制消息不会续租这些键。`RoomCleanupScheduler` 只给没有 TTL 的键补 TTL，不会刷新正常倒计时。

另外，本地索引缓存仅 2 秒。缓存过期后，`getRoomByCockpit` 和 `getRoomByVehicle` 会查询 Redis，没有优先扫描仍然活跃的 `localRooms`。

如果故障集中在接管后约 12 小时，这是直接根因。数据库会话仍可能显示 `ACTIVE`，但手柄高频路径已经找不到房间。

## 6. PostgreSQL 与数据量

PostgreSQL 不是 WebSocket 实时状态转发的直接必经点，但会通过 CPU、IO、连接池、GC 和回调调度间接放大延迟。

当前风险：

- `chassis_status` 默认 10Hz，单车每天约 864000 条原始上报。
- 协议层强制所有消息 `ignoreLog=false`、`ignoreStorage=false`。
- TimescaleDB 与业务数据库共享 Spring R2DBC 连接池。
- R2DBC `max-size=64`，对 1 核 PostgreSQL 可能增加连接竞争和上下文切换。
- TimescaleDB 默认写缓冲为 1000、并行度为 4。
- 手柄热路径每 500ms 对活动会话执行一次“查询后 save”的 `lastActiveTime` 更新。

结论：

- 1C2G 不应作为生产远控数据库的长期配置。
- 建议至少以 4C8G 作为压测起点，最终规格必须根据车辆数量、属性包大小、保留周期和慢 SQL 数据决定。
- 扩容只能降低资源竞争，不能修复 TCP 假在线、控制帧乱序、WebSocket 丢包和房间过期。

## 7. 整改优先级

### P0：实时链路正确性

1. 重构车端 TCP 连接状态机。
   - 所有致命 send/recv errno 统一进入断链状态。
   - 增加发送超时、TCP keepalive、应用层 ping 和连续失败熔断。
   - 断链后关闭旧 socket，完成认证和远控注册后再恢复业务。
   - `report_property` 等调用必须处理失败结果。
   - 连接状态使用明确的线程安全状态机。

2. 重构手柄控制通道。
   - 按 `cockpitId + vehicleId` 串行处理。
   - 使用极小严格有界队列或 latest-only mailbox。
   - 帧必须携带单调递增 `seq`、产生时间和有效期。
   - 服务端及车端拒绝乱序、重复和过期控制帧。
   - 紧急停车独立于普通手柄队列。

3. 修复 WebSocket 生命周期和状态语义。
   - 不再使用跨页面模块级单例，改为每调用方实例或连接管理器加多订阅者。
   - 服务端按车辆维护最新完整 `chassis_status` 快照。
   - 检查所有 `tryEmitNext` 结果并记录指标。
   - 前端合并 RAF 内 patch，按时间戳拒绝旧状态。
   - 字段缺失时保持原值。

4. 修复长时间会话。
   - 活跃房间持续续租信息键和两个索引键。
   - TTL 到期前必须有告警。
   - 本地活跃房间与 Redis 索引应可自愈。
   - R 模式退出后，页面和驾驶舱明确显示“需要重新接管”，恢复时重新下发 `driveMode(R)`。

5. 建立接管和模式切换就绪握手。
   - 接管前选择 R 只保存为 `desiredDriveMode`，不得显示成车辆实际模式。
   - 服务端完成房间创建后，按当前会话顺序发送 `onTakeover` 和 `driveMode(R)`。
   - `onTakeover`、模式切换和关键控制不得用无确认的业务成功替代车辆执行确认。
   - ACTIVE 与 REMOTE_READY 分离；前端在 REMOTE_READY 前禁用手柄控制并显示等待状态。
   - 前端不得依据通用设备列表中的占位状态静默跳过安全关键的 R 指令。
   - 已有 ACTIVE 会话内的每次 M/A/R 切换也必须携带 `modeCommandSeq`，车辆回报相同序号后才算完成。
   - Aura 不得使用无序的旧 M/A 回报覆盖更新的 R 目标；目标模式和实际模式必须分别建模。
   - 制动接管导致 R→M 时必须上报 `modeRejectReason=BRAKE_TAKEOVER` 和踏板值，不能只回报最终 M。
   - Aura 非 R 丢弃手柄帧时必须返回明确失败原因，不能返回 `success=true`。

### P1：隔离持久化与补齐可观测性

1. 10Hz 状态继续走实时链路，数据库按 1Hz 或变化阈值降采样。
2. 故障、MRC、模式变化和接管事件完整保存，不做普通采样。
3. 手柄热路径不执行单条数据库查询和保存，改为内存聚合后异步批量刷新。
4. 对每一帧记录阶段指标：

```text
cockpit_generated_at
server_received_at
room_resolved_at
encode_started_at
socket_write_completed_at
vehicle_received_at
ros_published_at
```

5. 增加以下指标和告警：

- 控制帧端到端 P50/P95/P99。
- 乱序、重复、过期和队列拒绝计数。
- 每车辆最近控制帧年龄。
- 车端 send/recv errno 和重连次数。
- WebSocket emit 失败、发送延迟、连接数和客户端消费延迟。
- Redis 房间剩余 TTL。
- R2DBC 活跃/空闲/等待连接数和获取连接耗时。
- TimescaleDB buffer backlog、写入失败和重试。

### P2：容量与运维治理

1. 根据实测扩容 PostgreSQL，并评估业务数据与时序数据连接池隔离。
2. 设置设备原始数据保留周期、压缩策略和历史降采样。
3. 建立远控 SLO、运行看板、告警分级和故障复盘模板。
4. 对远控安全参数建立版本化配置和变更审批。

## 8. 无需改代码的现场取证

### 8.1 车端

- 检查 RTSP 和远控 TCP 的目标地址、端口、进程是否独立。
- 保存远控 TCP `send/recv` errno、连接建立、认证、注册和重连日志。
- 检查 `remotejoystick_fps`、`remotejoystick_total`、`pd_msg_age_ms`。
- 检查 `cloud_link_rtt_ms`、`cloud_link_network_rtt_ms`。
- 搜索 R/M/A 模式变化和 `cached_drive_mode_` 丢弃日志。
- 比对“收到手柄帧”和“ROS control_info 实际发布”的数量。
- 同时记录 `driveMode` 到达时间、`cached_drive_mode_` 写入时间、e2e 模式回报时间和实际 `driving_mode_`。
- 搜索 `Brake takeover R->M`、`brake_takeover_permanent`，并同步记录 `vcu_vcu_manual_brk_pedal_pos`。
- 检查第一次 M→R 后是否出现“e2e 已为 R，但 cached_drive_mode_ 又被旧 M/A 回报清零”。

### 8.2 服务端

- 按 `messageId/seq` 比对路由入口、房间解析、编码开始和 socket 写完成时间。
- 观察两个 remotejoystick boundedElastic 调度器的活跃线程和队列深度。
- 检查 EventBus 发布速率、处理延迟、重复和错误计数。
- 区分“业务方法返回成功”“socket 写入成功”“车辆确认执行成功”。

### 8.3 浏览器

- 在 Network/WebSocket Frames 中确认 `vehicle-status` 是否持续到达。
- 记录远控页面、车辆详情页和 `ControlPanel` 的 mount/unmount 时间。
- 检查页面切换或抽屉关闭时是否触发共享 WebSocket 的 `close`。
- 对比 WebSocket 收到的 properties 与 Vue 最终写入的 `vehicleStatus`。
- 在已有 ACTIVE 会话内记录第一次 M→R 和后续 A→R 的 HTTP 请求、响应时间和 `chassis_status.drive_mode` 收敛时间。
- 确认第一次 R 后页面是否短暂显示 R 又回到 M，或始终停留 M；两者对应“执行后被打回”和“未执行/未送达”两类问题。

### 8.4 Redis

检查三个房间键是否同时存在，以及 TTL 是否持续下降：

```text
TTL pd:room:info:{cockpitId}-{vehicleId}
TTL pd:room:idx:cockpit:{cockpitId}
TTL pd:room:idx:vehicle:{vehicleId}
```

### 8.5 PostgreSQL

- CPU、内存、磁盘延迟和 IOPS。
- 活跃连接、等待连接、事务等待和锁等待。
- 慢 SQL、Top SQL、表膨胀和 WAL 速率。
- R2DBC 获取连接耗时。
- TimescaleDB 写缓冲积压和失败重试。

## 9. 故障注入与回归矩阵

| 场景 | 注入方式 | 必须满足的结果 |
|---|---|---|
| RTSP 正常、远控 TCP 单独中断 | 仅阻断远控端口 | 车端在限定时间识别断链、进入安全状态并自动重连 |
| TCP 半开 | 丢弃 ACK 或静默断开服务端 | 不允许长期 `is_link_ready=true`；应用 ping 必须触发重连 |
| TCP reset/timeout | 注入 `ECONNRESET`、`ETIMEDOUT` | 所有致命 errno 进入统一断链流程 |
| 服务端控制队列拥塞 | 人工降低消费能力 | 旧帧被丢弃，不允许恢复后连续补发 |
| 控制帧乱序 | 交换相邻 `seq` | 服务端或车端拒绝旧序号 |
| WebSocket 慢消费者 | 浏览器暂停或限速 | 只保留最新完整快照，有明确丢弃指标，不出现字段倒退 |
| 页面生命周期冲突 | 同时打开远控页和详情页 | 各页面连接/订阅互不关闭，状态均持续更新 |
| Redis TTL 加速 | 将 TTL 缩短至数分钟 | 活跃房间自动续租；停止活动后按策略过期 |
| R 切换到 M/A | 模拟制动接管或模式退出 | 页面明确提示退出远控；重新接管后重新发送 `driveMode(R)` |
| ACTIVE 会话内直接 M→R | 不重新接管，只在页面切换 M→R | 必须收到匹配 `modeCommandSeq` 的车辆确认并进入 REMOTE_READY，否则显示明确失败原因 |
| 旧 M/A 回报晚于新 R 指令 | 延迟 e2e 模式回报后下发新的 R | 旧回报不得清零较新的 R 目标，Aura 缓存和 e2e 实际模式最终一致 |
| R 指令后制动踏板仍大于 4% | 保持制动输入并切换 M→R | 明确返回/上报 `BRAKE_TAKEOVER`，页面不得显示远控就绪 |
| 接管通知与 R 指令乱序/丢失 | 延迟或丢弃 `onTakeover`、`driveMode(R)` 任一消息 | 不得显示远控就绪；重试必须带当前 session epoch 且最终状态一致 |
| Aura 非 R 收到手柄帧 | 令 `cached_drive_mode_` 为 M/A 后发送手柄和 EPB | 返回 `REMOTE_MODE_NOT_READY`，不允许记录成执行成功，前端立即告警 |
| 人工制动导致 R→M | R 模式踩制动并继续发送普通手柄帧 | 普通帧不能静默恢复；显式重新接管并确认 R 后才允许控制 |
| PostgreSQL 限流或暂停 | 限制 CPU/连接或暂停写入 | 控制和 WebSocket 实时链路不被数据库拖死 |
| 长时间停车 | R 模式持续静止数小时 | 手柄连接、房间、模式和 keepalive 均保持可观测且可恢复 |

## 10. 生产验收标准

整改完成后至少满足：

1. 控制帧端到端延迟、车辆接收间隔和丢弃原因均可观测。
2. 同一车辆控制帧不存在乱序执行和超时后补发。
3. 远控 TCP 单向失效、半开、reset 和 timeout 均能自动检测并恢复。
4. RTSP 正常而远控 TCP 中断时，系统能准确显示为“远控链路异常”，不显示为车辆整体离线。
5. WebSocket 页面切换、组件卸载和多页面打开不会互相关闭连接。
6. 前端状态不会因部分属性包、缺失字段或 RAF 覆盖而错误清零或停止更新。
7. 活跃房间不会在固定 12 小时后过期；异常过期可以自动恢复或明确告警。
8. 车辆退出 R 模式后不得静默接受但丢弃手柄控制，页面必须提示并要求重新接管。
9. 服务端会话 ACTIVE 不得直接等同远控就绪；车辆确认 Aura 和 e2e 均为当前会话的 R 后才进入 REMOTE_READY。
10. ACTIVE 会话内 M→R、旧模式回报乱序、接管通知乱序和车辆制动退出 R 等场景均不得产生页面假 R 或控制假成功。
11. 数据库降速或短时不可用不影响安全控制通道的时效性。
12. 在目标车辆规模和上报频率下完成持续压测、故障注入和长稳测试后，才能进入生产发布。

## 11. 当前禁止项

在 P0 问题完成前，不应：

- 仅通过放宽 `joystick_msg_timeout_ms` 解决告警。
- 继续扩大 remotejoystick 调度器线程数和队列容量。
- 将“消息已提交异步任务”当成“车辆已收到并执行”。
- 将服务端会话 ACTIVE 当成 Aura/e2e 已进入 R 或远控已就绪。
- 在非 R 模式丢弃手柄帧后仍返回 `success=true`。
- 通过关闭安全降级或 MRC 检测掩盖链路问题。
- 仅凭 RTSP 正常认定远控网络和业务链路正常。
- 仅通过扩容 PostgreSQL 宣告问题已解决。
