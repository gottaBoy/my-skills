# 通用固件 OTA 生产完善方案

## 1. 范围与结论

涉及目录：

```text
zeron-cloud-web/src/modules/device-manager-ui/views/device/Firmware
zeron-cloud-web/src/modules/device-manager-ui/api/firmware.ts
jetlinks-community/jetlinks-components/firmware-component
jetlinks-community/dev/hc-fdc-protocol
jetlinks-community/jetlinks-manager/zota-integration
```

当前事实：

- FDC 已能通过 MQTT 与 ZIOT 通信，普通下行指令已打通。
- OTA 主链路统一使用 `firmware-component`，FDC 不再维护独立升级任务。
- MQTT、TCP 等协议共享任务、设备快照、状态机、超时、重试和统计。
- 当前通用 push 抽象是 `DeviceRegistry` 加
  `FunctionInvokeMessage(functionId="ota_upgrade")`；通用 pull 抽象使用 JetLinks Core
  已有的 `RequestFirmwareMessage` 和 `RequestFirmwareMessageReply`。
- 协议模块负责把通用函数编码为 MQTT topic、TCP 帧或其他私有格式，并把设备状态
  解码为 `ota_status` 事件。
- 代码已经形成生产导向的 V1 基线，但外部安全、迁移、容量和实机验收完成前不能
  直接批准生产上线。

## 2. 实际架构

```text
Firmware UI
    |
    v
firmware-component
  firmware metadata
  task + fixed device snapshots
  device state machine
  dispatch claim
  retry/cancel/timeout/recovery
  task aggregation
    |
    v
DeviceRegistry
    |
    +-- push: FunctionInvokeMessage("ota_upgrade")
    |
    +-- pull: RequestFirmwareMessage <-> RequestFirmwareMessageReply
    |
    +-- hc-fdc MQTT codec -> {productId}/{deviceId}/ota/down
    +-- custom TCP codec  -> vendor TCP frame/session
    +-- another protocol  -> its own transport encoding

device report -> protocol codec -> EventMessage("ota_status")
              -> firmware-component state machine
```

核心层不能保存 MQTT topic、QoS、TCP session 或厂商状态。协议层不能创建第二套固件、
任务或升级历史表。

`hc_fdc` 是当前 FDC 产品 ID，在 FDC MQTT 适配器中将 `{productId}` 展开为
`hc_fdc`。它不是通用 OTA 命令、状态机、任务表或 history 表的一部分。其他产品可以
复用 `ota_upgrade`、`ota_status`、关联字段和状态机，但必须由自己的协议 codec 转换为
对应 MQTT Topic、TCP 帧或厂商报文。

“通用 OTA 协议”指平台内部业务契约和状态语义通用，不表示所有设备必须使用同一种
JSON、Topic 或传输。能够采用统一 MQTT JSON 契约的产品可以复用 Topic 模板；私有
TCP 或厂商 MQTT 协议只需实现等价的编解码映射。

当前 FDC 代码还将 `hc_fdc` 同时用作 `ProtocolSupport` ID、内置 metadata ID 和 Topic
前缀。这不影响单一 FDC 产品联调，但不应被解释为通用 OTA 依赖。若后续要让同一个
MQTT codec 服务多个产品，应拆分稳定的协议 ID 与可配置的 `productId/topicPrefix`。
修改已绑定产品的协议 ID 需要兼容迁移，不能直接替换线上值。

当前代码没有 `OtaProtocolAdapterRegistry`。需要显式能力声明、暂停/恢复或多种传输模式
时，可以后续引入 adapter SPI，但不能在文档中把目标架构写成已实现能力。

## 3. 已实现基线

### 3.1 任务与设备快照

- 创建任务时校验固件存在、产品一致、URL、大小、摘要方式和摘要值。
- 固件版本不能为空。
- `releaseType=all` 查询产品下全部设备并形成固定快照。
- `releaseType=part` 校验指定设备存在且属于任务产品。
- 空设备集合拒绝创建。
- task 和 history 在响应式事务中原子保存。
- 创建成功后自动开始下发。
- 同一设备通过 `active_key=deviceId` 唯一索引只允许一个活动升级。

### 3.2 V1 模式

- 支持 `mode=push` 和 `mode=pull`。
- `push` 表示云端推送升级命令，设备通过 URL 拉取固件，不推送固件二进制。
- `pull` 表示任务设备快照先保持 `queued`，设备主动检查后，服务端原子领取一个匹配的
  升级记录并返回固件信息。
- pull 使用 JetLinks Core 标准 `RequestFirmwareMessage/Reply`，不是 FDC 私有核心模型。
- pull 设备重试检查请求时必须复用同一 `messageId`，服务端才能幂等返回同一分配。
- 默认 ACK 超时 30 秒。
- 默认状态上报超时 300 秒。
- 默认总执行超时 3600 秒。
- 总执行超时不能小于 ACK 或状态超时。
- pull 在设备领取前的 queued 等待时间不计入总执行超时；领取成功后才启动响应和总
  执行计时。

### 3.3 下发与恢复

- 新任务 ID 使用 `TASKyyyyMMddHHmmssSSS-NNN`，单设备每次 attempt 的升级 ID 使用
  `UPGRADEyyyyMMddHHmmssSSS-NNN`；三位序号从 `001` 开始并在单服务进程内保证唯一。
- 集群部署前在时间与序号之间增加节点标识，并确保所有节点使用相同的时区配置。
- 通过条件更新将 `queued` claim 为 `dispatching`。
- `messageId` 由 `upgradeId` 和 attempt 组成。
- push 由服务端生成下发 `messageId`；pull 使用设备检查请求的 `messageId` 关联回复。
- 协议返回成功后，按 `status=dispatching AND messageId=?` 更新为 `dispatched`。
- 下发异常写入 `dispatch_failed`、错误码和错误信息。
- 定时扫描只自动下发 push 的 queued 记录；pull queued 记录等待设备领取。
- 服务重启后 push queued 继续下发，pull queued 继续等待领取，已领取的非终态记录继续
  执行超时判断。

### 3.4 状态与并发

- 状态归一化支持旧别名：`pending/waiting`、`processing/running`、`canceled`。
- 终态不可覆盖，进度限制在 0-100 且不倒退。
- 客户端事件必须携带 `upgradeId`。
- 事件按 `upgradeId + deviceId` 查询，并校验可选的 `taskId/historyId/attempt`。
- 客户端只能上报客户端状态，不能伪造服务端 dispatch、timeout 或 cancelled 状态。
- 状态更新匹配旧 status 和旧 `lastEventTime`，竞争失败后重新加载并验证迁移。
- timeout 更新匹配旧 status；执行阶段还匹配读取时的 `lastReportTime`。
- 任务状态和计数统一由 `refreshTaskStatus` 聚合。

### 3.5 重试、取消和删除

- 重试仅允许失败终态或 `cancelled`。
- 重试增加 attempt，生成新 `upgradeId`，清空旧执行字段并重新进入 queued。
- queued 状态不占用 `active_key`；push 调度 claim 或 pull 设备领取时才写入
  `active_key=deviceId`。
- retry 使用条件更新，防止重复点击产生并发重试。
- V1 仅允许取消 `queued`，不向正在执行的设备发送 cancel。
- 进行中的任务和 history 不允许删除。

### 3.6 前端

- 创建页提供“平台下发（push）”和“设备主动检查（pull）”。
- 响应超时、状态上报超时、升级总超时对两种模式均可配置，单位为秒。
- 默认值为 30、300、3600，并校验总超时不小于响应超时和状态上报超时。
- 显示完整设备状态、attempt、upgradeId、进度、错误码和错误信息。
- 批量 retry/cancel 传 device ID；单条操作传 history ID。
- 按状态限制 retry、cancel 和 delete。
- 旧 `/api/firmware/upload|list` 调用已从正式 Firmware 前端 API 中移除。

### 3.7 FDC

- `hc_fdc` 是当前 FDC 产品 ID；以下 Topic 是通用 MQTT Topic 模板在 FDC 产品上的
  实例，不属于 `firmware-component` 核心契约。
- OTA 下行 topic：`hc_fdc/{deviceId}/ota/down`。
- OTA 主动检查上行 type：`ota_check`；平台回复 type：`ota_check_reply`。
- 普通命令 topic：`hc_fdc/{deviceId}/command/down`。
- QoS 为 1。
- 下行透传 upgrade/task/history/firmware/attempt 关联字段。
- 上行根节点或 data 中的关联字段会合并到标准事件。
- MQTT 认证会话中的设备 ID 为权威值，payload 不允许冒充其他设备。
- FDC 元数据和枚举覆盖 ACK、执行阶段、成功和阶段失败。
- 旧 `/api/firmware/ota/upgrade` 返回 HTTP 410。

## 4. 数据模型与 API

history 关键字段：

```text
upgradeId activeKey taskId deviceId firmwareId status messageId attempt
errorCode errorMessage progress startTime dispatchTime ackTime
lastReportTime lastEventTime reportedVersion completeTime
```

task 关键字段：

```text
firmwareId productId mode releaseType terms
responseTimeoutSeconds statusTimeoutSeconds timeoutSeconds
deviceCount queuedCount runningCount successCount failCount cancelledCount status
```

正式操作 API：

```text
POST /firmware/upgrade/task
POST /firmware/upgrade/task/{taskId}/devices/_retry
POST /firmware/upgrade/task/{taskId}/devices/_cancel
POST /firmware/upgrade/history/{historyId}/_retry
POST /firmware/upgrade/history/{historyId}/_cancel
```

批量接口参数是 device ID 数组，单条接口路径参数是 history ID。

## 5. 数据库迁移

脚本：

```text
jetlinks-components/firmware-component/src/main/resources/db/migration/
  firmware_upgrade_task_fields.sql
  firmware_upgrade_task_fields_mysql.sql
```

`application.yml` 说明 EasyORM 启动时可创建表，但当前仓库没有证明上述 migration 目录会被
自动执行。生产部署必须把脚本作为人工或流水线数据库变更步骤，不得只依赖应用启动。

迁移流程：

1. 停止创建和下发 OTA，确认没有正在执行的升级。
2. 备份 task/history 表。
3. 运行冲突查询，确保一个设备没有多条活动 history。
4. 执行对应数据库脚本。
5. 确认旧状态已归一化，旧记录已回填 `upgrade_id` 和 attempt。
6. 确认活动记录的 `active_key=device_id`，终态记录 active_key 为空。
7. 确认 upgrade_id 和 active_key 唯一索引已创建。
8. 使用预发布任务验证创建、下发、上报、失败、超时、重试和取消。

PostgreSQL 脚本在事务内执行并主动检查冲突。MySQL DDL 会自动提交，因此必须先运行脚本
头部的冲突查询，并且只执行一次。

## 6. 通用协议接入规范

新协议接入不修改 OTA task/history 模型。

通用服务与协议适配层的边界：

```text
通用 OTA 服务:
  push: FunctionInvokeMessage("ota_upgrade")
  pull: RequestFirmwareMessage / RequestFirmwareMessageReply
  status: EventMessage("ota_status")
  upgradeId / taskId / historyId / attempt
  状态机 / 超时 / 重试 / 幂等 / 聚合

协议适配层:
  MQTT Topic / QoS / JSON 字段
  TCP session / 帧格式 / 分片
  厂商命令码 / 私有状态映射
```

协议必须：

1. push 协议在产品物模型暴露 `ota_upgrade`，pull 协议能将设备检查报文解码为
   `RequestFirmwareMessage`。
2. 将 `FunctionInvokeMessage` 或 `RequestFirmwareMessageReply` 编码到协议自己的可靠
   下行通道。
3. 明确“协议发送成功”和“设备接受”不是同一状态。
4. 将设备状态解码为 `EventMessage(event="ota_status")`。
5. 全链路透传 `upgradeId`，并尽量透传 task/history/attempt。
6. 把私有状态映射为标准客户端状态。
7. 保证重复命令和重复状态幂等。
8. 保证重启后仍可使用原 upgradeId 上报结果。

对于采用本文统一 MQTT JSON 的产品，Topic 使用
`{productId}/{deviceId}/ota/down|up` 模板。`productId` 必须来自平台注册产品或协议
配置，不能信任设备 payload 自报值。对于 TCP 等不需要产品 ID 出现在报文中的协议，
无需为了统一而增加该字段。

TCP 可以使用 URL 拉取、分片或厂商协议传输。当前 push/pull 描述的是升级任务触发方式，
两种方式返回的固件交付信息仍以 URL 下载为主。如果要支持平台流式推送或协议分片传输，
需要另行扩展明确的 delivery mode、能力声明和流控，不得把二进制塞入现有 FDC MQTT
payload。

## 7. 生产准入缺口

以下项目不是当前代码已完成能力，生产发布前必须补齐或形成经过批准的外部实现：

### P0

- FDC 当前产品 ID 和 MQTT Topic 前缀使用 `hc_fdc`。协议路由、下行 codec、设备
  模拟器和产品配置必须保持一致，但 `firmware-component` 不能依赖该值。
- 明确 `hc_fdc` 同时作为现有 `ProtocolSupport` ID 的兼容策略。多产品复用 codec 前，
  将协议标识与 `productId/topicPrefix` 配置解耦，并验证已绑定产品迁移。
- FDC 普通下行命令必须补齐 `messageId`，并将 KL15 `data` 编码为协议约定的 JSON
  对象；不能直接序列化 JetLinks `FunctionParameter` 数组。
- FDC 模拟器必须使用 `fwVersion`、`uptimeS`，并把 OTA 关联字段放入 `data`。
- FDC MQTT 通用 envelope、设备状态和 OTA 字段使用 lowerCamelCase；FDC 自定义遥测
  字段保留 `bw_up`、`bw_down`、`rtt_ms`、`packet_loss` 和 `kl15`。产品物模型、
  协议编解码器和设备上报必须使用完全一致的属性 ID，不得依赖 camelCase 与
  snake_case 自动转换。
- 在真实 PostgreSQL 或 MySQL 副本验证迁移、回滚方案和索引冲突处理。
- 固件下载必须使用 HTTPS，禁止生产 URL 使用本地地址或明文 HTTP。
- 使用短期签名 URL，限制有效期、对象范围和重复滥用。
- 建立固件发布审批与不可变策略。
- 至少使用 SHA-256；高安全场景增加厂商数字签名和设备端公钥校验。
- 完成真实 FDC 设备 E2E：断网、重连、重启、迟到消息、重复消息、错误摘要和空间不足。
- 验证 RBAC、组织/租户数据隔离，确认任务目标解析不会越权。

### P1

- 灰度批次、并发上限、每秒速率和失败熔断。
- 指标与告警：queued 积压、dispatch 失败率、ACK 超时率、执行时长、成功率。
- 审计：创建、启动、重试、取消、删除、状态拒绝和超时的操作者与原因。
- 固件存储和下载链路流式化；旧 FDC S3 下载仍会整包读入内存。
- 设备规模和数据库容量测试，特别是批量快照、活动状态扫描和任务聚合。
- 明确 history 当前记录重试覆盖策略，必要时增加不可变 attempt/event 审计表。

### P2

- 协议能力声明。
- 设备端 cancel、pause、resume。
- 版本和健康检查驱动的 post-check。
- 自动回滚、A/B 分区、差分升级。
- 多阶段灰度编排和自动暂停。

## 8. 联调矩阵

至少覆盖：

| 场景 | 预期 |
|---|---|
| 正常完整状态链 | 最终 success，进度 100 |
| pull 无待领取任务 | 返回 `NO_PENDING_UPGRADE`，不创建隐式任务 |
| pull 重复同一 messageId | 幂等返回同一分配，不重复 claim |
| pull queued 长时间未领取 | 不触发执行超时 |
| pull 领取后无 accepted | ack_timeout |
| 客户端跳过可选阶段 | 单调前进并成功 |
| 协议编码或发送失败 | dispatch_failed |
| 设备拒绝 | rejected |
| 无 ACK | ack_timeout |
| 执行中无状态 | status_timeout |
| 超过总时限 | execution_timeout |
| 摘要错误 | verify_failed |
| 安装失败 | install_failed |
| 重启未上线 | reboot_failed 或 status_timeout，按客户端能力确定 |
| 重复事件 | 不重复计数 |
| 乱序事件 | 不回退状态或进度 |
| 缺少 upgradeId | 拒绝更新 |
| 错误 task/history/attempt | 拒绝更新 |
| 客户端伪造 timeout | 拒绝更新 |
| 同设备并行任务 | 唯一索引阻止 |
| 双节点同时下发 | 只有一个 queued claim 成功 |
| 双击重试 | 只有一次 attempt 增加 |
| 服务重启 | queued 和 timeout 扫描恢复 |
| queued 取消 | cancelled 且不下发 |
| 执行中取消 | V1 拒绝 |

## 9. 上线判定

只有在以下结果都有证据时才允许标记生产可用：

- 后端、FDC 协议、zota-integration 编译测试通过。
- 前端构建通过。
- PostgreSQL 或 MySQL 迁移演练通过。
- 真实 FDC E2E 和故障矩阵通过。
- TLS、签名 URL、固件完整性和权限检查通过。
- 灰度、限流、监控、告警和回滚操作手册可执行。

单元测试通过只能证明代码基线，不等于生产准入。
