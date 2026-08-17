# 平行驾驶分布式改造方案

> 分析日期：2026-08-17
> 状态：方案设计，待评审；本次未实施任何代码改动
> 范围：jetlinks-community（parallel-driving-manager 模块）、zeron-cloud-web（parallel-driving-manager-ui 模块）、JetLinks 实时消息链路
> 基线文档：[parallel-driving-production-issues-2026-08-09.md](./parallel-driving-production-issues-2026-08-09.md)
> 目标：将平行驾驶能力改造为支持多节点分布式部署，不破坏现有单节点行为、TCP 线协议与前后端契约

## 1. 背景与目标

平行驾驶（teleoperation / 远控）当前以单节点假设实现：驾驶舱 TCP 会话、车辆 TCP 会话、转发房间状态均默认落在同一台 jetlinks 节点上。生产环境需要多节点水平扩展以支撑更多并发驾驶舱与车辆，并满足单节点宕机后接管不中断的可靠性要求。

本方案的目标：

1. 在多节点部署下消除消息重复投递与状态竞争，使每帧控制指令只被一个节点处理并转发。
2. 房间状态与权限校验下沉到共享存储，使任意节点宕机后其余节点可恢复接管链路。
3. 不改变车端 TCP 线协议（zeron-parallel-protocol 全部 functionId）、不改变前端 WS/REST 契约、不改变单节点下的既有行为。
4. 全部改动可经配置开关回滚到单节点等价语义。

## 2. 现状架构（单节点假设）

### 2.1 后端 parallel-driving-manager

| 组件 | 文件 | 现状与分布式隐患 |
|------|------|-------------------|
| 消息路由 | `ParallelDrivingMessageRouter.java` | 订阅驾驶舱控制与车端回复 topic，`.features(Subscription.Feature.local, Subscription.Feature.broker)`，**不含 shared**。subscriberId 稳定（`parallel-driving-cockpit-router` / `parallel-driving-vehicle-router`）。已有 messageId 去重缓存（5s TTL、上限 1 万）。 |
| 房间管理 | `ParallelDrivingRoomManager.java` | Redis 房间元数据 + 固定 12h TTL；内存 `localRooms` + 2s L1 索引缓存；`getOrRecoverRoom` 被动恢复。`nodeId` 取 `${jetlinks.server-id:standalone}`。 |
| 房间转发 | `ParallelDrivingRoom.java` | 转发已用 `device.messageSender().sendAndForget()` / `send()`，**已具备跨节点路由能力**（路由到持有设备会话的节点）。 |
| WebSocket 推送 | `ParallelDrivingWebSocketHandler.java` | 浏览器 WS 订阅车辆属性上报，`subscriberId("parallel-driving-websocket-"+sessionId)`，`.features(local, broker)`。 |
| 接管与权限 | `ParallelDrivingRelationService.java` | `takeover` 用 Redis 分布式锁（`pd:lock:vehicle:` + `setIfAbsent`），**集群正确**；但 `checkControlPermission`（line 438）与 `updateLastActiveTime`（line 655）在热路径上做每帧 DB 查询/写回。 |
| 房间清理 | `RoomCleanupScheduler.java` | `@Scheduled(fixedDelay=300_000)`，仅对 `ttl < 0`（无 TTL）的键续期，**不刷新活跃房间**，导致 12h 固定过期。 |
| 集群配置 | `application-cluster.yml` | 集群 profile 整体被注释，`jetlinks.server-id` 默认 `standalone`。 |

### 2.2 前端 parallel-driving-manager-ui

| 组件 | 文件 | 现状 |
|------|------|------|
| WS 客户端 | `utils/websocket.ts` | 模块级 WS 客户端，指数退避重连（1s–30s + 抖动），注释已提及"集群模式下节点重启时自动恢复"。连接 `/parallel-driving/ws?vehicleId=&cockpitId=`。 |
| REST 接口 | `api/parallel-driving.ts` | 接管/释放/绑定/控制走 HTTP；状态走 WS；控制指令经 HTTP 而非 WS。 |
| 媒体面 | `WebRtcPlayer.vue` | 独立于控制面的 WebRTC 媒体通道。 |

### 2.3 集群配置现状

`application-cluster.yml` 的全部内容被注释，意味着默认以 standalone 模式运行：不开 cluster 端口、不发种子节点、`server-id=standalone`。要在多节点运行需先解开该 profile 并设置 `JETLINKS_SERVER_ID` / `CLUSTER_SEED_*`，但解开后会立即暴露第 3 节所述问题。

## 3. 分布式改造核心问题

### 3.1 消息扇出（最严重，必须修复）

`ParallelDrivingMessageRouter` 两个订阅都使用 `{local, broker}` 而**不含 shared**。JetLinks 语义：相同 subscriberId 的订阅，`shared` 才做负载均衡（同一条消息只投递给一个订阅者）；缺省 `DEFAULT_FEATURES` 实际已含 shared，但本模块显式枚举时漏掉了它。

多节点后果：每条驾驶舱控制帧、每条车端回复帧会被**所有节点**同时收到（broker 广播给每个持相同 subscriberId 的节点），导致：

- 同一帧被 N 个节点重复转发，车端收到 N 份重复指令；
- `localRooms` / `getOrRecoverRoom` 在 N 个节点上各自重建并转发，放大重复；
- DB 负载随节点数线性放大（每节点都做 `checkControlPermission`）。

### 3.2 房间状态本地化

`localRooms` 是节点内存，`getOrRecoverRoom` 会让每个收到消息的节点从 Redis 重建房间并本地转发。在 3.1 的扇出未修复前，这会把重复投递进一步放大。`nodeId` 存入 Redis 的值是 HTTP 接管发起节点，并非驾驶舱 TCP 会话所在节点，二者在多节点下不一定是同一台。

### 3.3 热路径 DB 查询

`checkControlPermission` 每帧执行 `sessionRepository.createQuery()...fetch().hasElements()`，`updateLastActiveTime` 每帧执行一次读 + 一次 `save()`。单节点下已是可优化点，多节点下因 3.1 扇出变为 N× 放大。

### 3.4 房间 TTL 固定

`RoomCleanupScheduler.scanAndRefreshTTL` 只对无 TTL（`ttl < 0`）的键续期，活跃房间不会被续期，固定 12h 后房间元数据过期，导致活跃接管中途丢失索引。

### 3.5 WS 跨节点重连无快照

WS 订阅的 `subscriberId` 含浏览器会话 ID，是唯一的，因此 `{local, broker}` 在多节点下**不会重复投递**（只有一个节点持有该订阅），状态推送链路本身是集群安全的。但当浏览器跨节点重连（节点宕机或 LB 重定向）时，新节点的订阅从零开始，断连期间发布的车辆状态会丢失，缺少首帧快照。

## 4. JetLinks 原生集群能力（可直接复用）

核心已验证存在于 `jetlinks-core` 的 `Subscription.java`：

```text
DEFAULT_FEATURES              = {local, broker, shared}
clusterFeatures               = {local, broker}                       // 当前本模块用的就是这个
clusterSharedFeatures         = {local, broker, shared}
clusterSharedLocalFirstFeatures = {local, broker, shared, sharedLocalFirst}
clusterSharedHashFeatures     = {local, broker, shared, sharedHashed}
clusterSharedMinimumLoadFeatures = {local, broker, shared, sharedMinimumLoad}
clusterSharedOldestFeatures  = {local, broker, shared, sharedOldest}
```

语义（来自源码注释）：

- `shared`：相同 subscriberId 只有一个订阅者收到消息 —— 消除扇出的关键。
- `sharedLocalFirst`：集群下相同订阅者本地发布者优先收到 —— 天然提供会话亲和性（驾驶舱 TCP 会话所在节点优先处理驾驶舱→车辆；车端会话所在节点优先处理车端回复）。
- `sharedHashed`：按 `Routable.hash` 负载均衡。
- `sharedMinimumLoad`：路由到最小负载订阅者。

另外两项已验证的原生能力：

- `DeviceSessionManager`：设备会话可分布在集群多台节点，提供 `getCurrentServerId()`，TCP 会话落在网关接入节点。
- `device.messageSender().send()/sendAndForget()`：跨节点路由到持有设备会话的节点（`ParallelDrivingRoom` 已在用，无需改动）。

## 5. 改造方案

按依赖关系分阶段，每阶段独立可回滚。阶段 0 是其余阶段生效的前提。

### 阶段 0：共享订阅（核心，最高杠杆）

改动文件：`ParallelDrivingMessageRouter.java`，`ParallelDrivingVehicleToCockpitProperties.java`。

将两个订阅的 features 从 `{local, broker}` 改为 `{local, broker, shared, sharedLocalFirst}`（直接复用核心常量 `Subscription.Feature.clusterSharedLocalFirstFeatures`），受开关 `parallel-driving.cluster.shared-subscription`（默认 true）控制。subscriberId 已稳定，无需改动。

```java
// 改造前
.features(Subscription.Feature.local, Subscription.Feature.broker)
// 改造后（开关为 true 时）
.features(Subscription.Feature.clusterSharedLocalFirstFeatures)
```

效果：

- 每条消息只投递给一个节点，消除 N× 重复转发与 N× DB 负载。
- `sharedLocalFirst` 让驾驶舱会话所在节点本地优先处理驾驶舱→车辆，车端会话所在节点本地优先处理回复，形成自然会话亲和，降低跨节点 RPC。

随之收紧去重：将现有 messageId 去重升级为 `(sessionId + seq)` 去重，防御 shared 切换瞬间的短暂重复。房间侧：保留 Redis 元数据，移除 `getOrRecoverRoom` 的被动重建转发（改为只读取元数据、不在本节点重建转发），在内存维护序号水位，并在 Redis hash `pd:room:state:{roomKey}` 落一份序号水位用于节点切换时对齐。

单节点等价性：只有一个节点时 shared 退化为本地投递，行为不变。

### 阶段 1：权限与活跃时间下沉 Redis

改动文件：`ParallelDrivingRelationService.java`，新增 Redis 结构 `pd:perm:{vehicleId}` / `pd:active:{sessionKey}`。

`checkControlPermission` 改为读 Redis 标志位（接管时写入、释放时清除），`updateLastActiveTime` 改为 Redis 时间戳 + 5s 异步批量回写 DB。DB 仍是真相源，热路径不再每帧打 DB。与阶段 0 配合：因为只剩一个节点处理每帧，DB 压力回到单节点水平，本阶段进一步把权限校验移出 DB。

### 阶段 2：WS 重连首帧快照

改动文件：`ParallelDrivingWebSocketHandler.java`，新增 Redis `pd:vehicle:snapshot:{vehicleId}`。

WS 建连时先从 Redis 读最近一次车辆属性快照作为首帧推送，再进入实时订阅。该能力增量叠加，旧前端不读首帧也不受影响。节点切换重连后不再从零开始，避免状态断档。

### 阶段 3：活跃房间滑动续期

改动文件：`RoomCleanupScheduler.java` / `ParallelDrivingRoomManager.java`。

`scanAndRefreshTTL` 增加对活跃房间（`localRooms` 非空或 Redis 标记 active）的 TTL 滑动续期，续期窗口设为 TTL 的 1/3。修复 12h 固定过期导致活跃接管中途丢索引的问题。

### 阶段 4：安全信箱与乱序防护

改动文件：`ParallelDrivingMessageRouter.java` / `ParallelDrivingRoom.java`（方向过滤器）。

针对高频 remotejoystick 帧：维护 latest-only 信箱（只保留最新帧）、拒绝旧 seq、按方向过滤路由（cockpit→vehicle 与 vehicle→cockpit 分流）。这与基线文档"未找到激活房间"告警治理一致，需在台架验证后再上量。

### 阶段 5：媒体面解耦（可选）

媒体面（WebRtcPlayer）已独立于控制面，多节点下可按需在 LB 层对媒体流做会话亲和，控制面不依赖媒体面节点选择。本阶段为可选项，不改控制面。

## 6. 兼容性与回滚

| 维度 | 是否受影响 | 说明 |
|------|-----------|------|
| 车端 TCP 线协议 | 不变 | zeron-parallel-protocol 全部 functionId 不动。 |
| 前端 WS/REST 契约 | 不变 | 阶段 2 仅叠加可选首帧，旧前端兼容。 |
| 单节点行为 | 不变 | shared 在单节点退化为本地投递，各阶段开关默认开启但单节点语义等价。 |
| 接管分布式锁 | 已正确 | `takeover` 的 Redis 锁无需改动。 |
| 房间跨节点转发 | 已正确 | `messageSender` 路由已集群感知，无需改动。 |

回滚：每阶段有独立配置开关。关闭 `parallel-driving.cluster.shared-subscription` 即退回 `{local, broker}`（单节点等价）。阶段 1–4 各自开关默认关闭，可独立灰度。

## 7. 验证与灰度

1. 单节点回归：开启全部开关后，与关闭开关行为逐项比对（接管、释放、控制转发、状态推送、房间接管切换）。
2. 双节点台架：解开 `application-cluster.yml`，设两节点，验证 shared 投递唯一性（车端每帧只收一份）、跨节点接管恢复、WS 重连首帧快照。
3. 故障注入：杀掉驾驶舱会话所在节点，验证 `sharedLocalFirst` 重选与房间序号水位对齐，接管不中断。
4. 压测：remotejoystick 10Hz+ 下确认去重生效、DB QPS 回到单节点水平（阶段 1 后）。
5. 灰度顺序：阶段 0 → 1 → 2 → 3 → 4；阶段 5 视媒体面需求决定。

## 8. 待确认项

- 阶段 4 的乱序防护属安全相关，需台架与实车验证后再上量，不可跳过验证直接生产。
- `sharedLocalFirst` 在驾驶舱会话与车端会话同处一节点时最优；跨节点时退化为 shared 的普通负载均衡，仍保证唯一投递，可接受。
- 阶段 2 快照的写入时机需与车端上报频率对齐，避免快照陈旧误导操作员。
