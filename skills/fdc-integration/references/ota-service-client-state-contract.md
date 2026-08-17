# OTA 服务端与客户端状态契约

## 1. 原则

- 状态机属于通用 OTA 服务，不属于 MQTT、TCP 或 FDC。
- 协议层只做通用命令与私有消息之间的编解码。
- `hc_fdc` 等产品 ID 只用于产品识别和协议路由，不进入通用 OTA 状态机与数据模型。
- 下发成功、设备接受、下载完成和最终升级成功必须分开。
- 所有客户端 OTA 状态必须携带 `upgradeId`。
- Topic、TCP session、连接 ID 或“设备当前唯一活动任务”不能替代 upgradeId。
- 服务端状态和客户端状态有明确所有权，客户端不能上报服务端超时或调度状态。

## 2. 关联字段

| 字段 | 说明 |
|---|---|
| `upgradeId` | 单设备本次 attempt 的全局关联 ID，必填 |
| `taskId` | 批量升级任务 ID |
| `historyId` | 当前设备升级记录 ID |
| `attempt` | 重试序号，从 1 开始 |
| `messageId` | 下行指令或上行事件的消息 ID |
| `deviceId` | 认证后的设备 ID |
| `firmwareId` | 固件记录 ID |

新建任务的 `taskId` 使用 `TASKyyyyMMddHHmmssSSS-NNN`，每个设备 attempt 的
`upgradeId` 使用 `UPGRADEyyyyMMddHHmmssSSS-NNN`。时间部分使用服务端本地时区，
三位序号从 `001` 开始并在单服务进程内保证唯一。已有旧格式 ID 保持兼容；集群部署前
需要增加节点标识。

服务端按 `upgradeId + deviceId` 查找 history。上报包含 taskId、historyId 或 attempt 时，
任何一个不匹配都拒绝更新。

重试必须生成新的 upgradeId。旧 upgradeId 的迟到事件不得更新新 attempt。

## 3. 状态集合

### 3.1 服务端阶段

| 状态 | 产生方 | 含义 |
|---|---|---|
| `queued` | 服务端 | 已创建设备快照，等待调度 |
| `dispatching` | 服务端 | 已 claim，正在调用设备协议 |
| `dispatched` | 服务端/协议层 | 协议发送返回成功，不代表设备接受 |

### 3.2 客户端非终态

| 状态 | 含义 |
|---|---|
| `accepted` | 客户端接受升级 |
| `preparing` | 检查电量、空间、型号和升级条件 |
| `downloading` | 获取固件 |
| `downloaded` | 固件接收完成 |
| `verifying` | 校验大小、摘要、签名或兼容性 |
| `verified` | 校验通过 |
| `installing` | 写入或安装 |
| `rebooting` | 重启进入新固件 |
| `post_checking` | 检查实际版本和健康状态 |

### 3.3 成功终态

```text
success
```

`progress=100`、`downloaded`、`verified` 或安装完成都不能单独替代 success。

### 3.4 客户端失败终态

```text
rejected
download_failed
verify_failed
install_failed
reboot_failed
post_check_failed
failed
```

优先使用具体失败状态。`failed` 只用于无法分类的兼容错误。

### 3.5 服务端失败或停止终态

```text
dispatch_failed
ack_timeout
status_timeout
execution_timeout
cancelled
```

客户端上报这些状态时，服务端必须拒绝。它们只能由发送结果、服务端时钟或 queued 取消
产生。

## 4. 允许的迁移

标准完整路径：

```text
queued -> dispatching -> dispatched -> accepted
       -> preparing -> downloading -> downloaded
       -> verifying -> verified -> installing
       -> rebooting -> post_checking -> success
```

规则：

1. `queued` 只允许进入 `dispatching` 或 `cancelled`。
2. `dispatching` 允许进入 `dispatched`、`dispatch_failed`，也允许接收快速设备已经返回的
   accepted 或更后客户端阶段。
3. `dispatched` 可进入 accepted、rejected、任一更后客户端阶段或服务端超时。
4. 客户端可跳过不支持的中间阶段，但不能回退。
5. `rejected` 只发生在接受前。
6. 任一终态不能进入另一个状态。
7. 同状态重复事件只允许刷新服务端接收时间和不下降的进度。
8. 未识别状态、错误关联、旧 attempt 和客户端伪造的服务端状态只记录日志，不更新
   history。

简化客户端可以使用：

```text
queued -> dispatching -> dispatched -> downloading -> installing -> success
```

FDC 推荐至少实现：

```text
accepted -> downloading -> verifying -> installing -> rebooting
         -> post_checking -> success
```

对 FDC 生产客户端，`accepted/rejected` 必须二选一上报，不能使用 MQTT PUBACK 替代。
`downloading`、`verifying`、`installing`、`rebooting`、`post_checking` 和最终
`success` 是最小成功链路；`preparing`、`downloaded`、`verified` 是可选的细化里程碑。
通用状态机允许跳过不支持的中间阶段，但状态和总体 progress 不能回退。

## 5. 下行升级命令

通用核心支持两种任务触发方式：

| 模式 | 通用消息 | 含义 |
|---|---|---|
| `push` | `FunctionInvokeMessage(functionId="ota_upgrade")` | 平台主动向设备下发升级命令 |
| `pull` | `RequestFirmwareMessage` / `RequestFirmwareMessageReply` | 设备主动检查并领取已创建的升级任务 |

通用核心不产生 MQTT Topic，也不依赖产品 ID。协议 codec 根据设备所属产品和传输
配置生成实际报文。采用统一 MQTT JSON 契约时，Topic 模板为：

```text
上行: {productId}/{deviceId}/status/up
      {productId}/{deviceId}/data/up
      {productId}/{deviceId}/ota/up

下行: {productId}/{deviceId}/command/down
      {productId}/{deviceId}/ota/down
```

FDC 产品将 `{productId}` 展开为 `hc_fdc`。`ota_upgrade` 使用 `ota/down`，普通功能
调用和属性命令使用 `command/down`，均使用 QoS 1。TCP 或其他私有协议无需使用该
Topic，只需把同一通用命令和状态映射到自己的报文。

参数：

```json
{
  "upgradeId": "upgrade-id",
  "taskId": "task-id",
  "historyId": "history-id",
  "firmwareId": "firmware-id",
  "attempt": 1,
  "fwVersion": "1.3.0",
  "fwUrl": "https://download.example.com/signed/object",
  "fwSize": 2097152,
  "fwSha256": "sha256-hex",
  "force": false,
  "deadlineS": 3600
}
```

当前 V1 也兼容 `fwMd5`，但生产固件应至少使用 SHA-256；高安全场景必须增加固件数字
签名。`deadlineS` 是总执行期限，不是单次下载请求超时。

FDC MQTT envelope：

```json
{
  "deviceId": "FDC-001",
  "type": "ota_upgrade",
  "messageId": "upgrade-id-a1",
  "ts": 1786118400000,
  "data": {
    "upgradeId": "upgrade-id",
    "taskId": "task-id",
    "historyId": "history-id",
    "firmwareId": "firmware-id",
    "attempt": 1,
    "fwVersion": "1.3.0",
    "fwUrl": "https://download.example.com/signed/object",
    "fwSize": 2097152,
    "fwSha256": "sha256-hex",
    "force": false,
    "deadlineS": 3600
  }
}
```

Topic 为 `hc_fdc/FDC-001/ota/down`，QoS 1。

FDC 消息信封只包含 `deviceId`、`type`、`messageId` 和 `ts`。`upgradeId`、`taskId`、
`historyId`、`firmwareId` 和 `attempt` 是 OTA 业务字段，只放在 `data` 中。

### 5.1 pull 检查与回复

设备主动检查由协议层解码为：

```text
RequestFirmwareMessage
  deviceId
  messageId
  currentVersion
  requestVersion
```

服务端只匹配已经创建、设备快照中包含该设备、模式为 pull、状态为 queued 的任务。
匹配成功后通过条件更新 claim 为 dispatching，并回复：

```text
RequestFirmwareMessageReply
  url version sign signMethod firmwareId size parameters
```

`parameters` 携带 `upgradeId/taskId/historyId/firmwareId/attempt/force/deadlineS`。协议层再
将标准回复编码为设备私有报文。FDC 对应 `ota_check` 和 `ota_check_reply`，两者使用同一
`messageId`。

设备重试同一次检查必须复用原 `messageId`。新 `messageId` 表示新的检查请求，不能用于
重放已领取分配。没有匹配任务时返回 `NO_PENDING_UPGRADE`，服务端不会因为设备检查而
自动创建任务。

## 6. 客户端上报

FDC 上报 topic：

```text
hc_fdc/{deviceId}/ota/up
```

通用 envelope：

```json
{
  "deviceId": "FDC-001",
  "type": "ota",
  "messageId": "ota-status-message-id",
  "ts": 1786118460000,
  "data": {
    "upgradeId": "upgrade-id",
    "taskId": "task-id",
    "historyId": "history-id",
    "attempt": 1,
    "state": "downloading",
    "progress": 50,
    "reportedVersion": "1.2.3",
    "errorCode": null,
    "errorMessage": null,
    "eventTime": 1786118460000
  }
}
```

新客户端必须把关联字段放在 `data`。为兼容旧客户端，FDC codec 可以读取根节点中的
关联字段；如果根节点和 `data` 同时存在且值不一致，必须拒绝整条消息。

接受：

```json
{
  "upgradeId": "upgrade-id",
  "attempt": 1,
  "state": "accepted",
  "progress": 0
}
```

拒绝：

```json
{
  "upgradeId": "upgrade-id",
  "attempt": 1,
  "state": "rejected",
  "errorCode": "DEVICE_BUSY",
  "errorMessage": "another upgrade is running"
}
```

成功：

```json
{
  "upgradeId": "upgrade-id",
  "attempt": 1,
  "state": "success",
  "progress": 100,
  "reportedVersion": "1.3.0"
}
```

失败必须同时上报稳定 errorCode 和可读 errorMessage。

推荐拒绝码：

```text
DEVICE_BUSY
MODEL_MISMATCH
VERSION_NOT_ALLOWED
INSUFFICIENT_STORAGE
INSUFFICIENT_POWER
INVALID_REQUEST
UNSUPPORTED_DELIVERY_MODE
```

## 7. 进度与事件时间

- progress 范围是 0-100。
- 服务端会截断越界值。
- 总体 progress 不允许下降。
- 切换阶段不要求每个阶段从 0 开始。
- 没有精确进度时只上报状态。
- success 会把 progress 设置为 100。
- `eventTime` 用于过滤同一 attempt 的乱序事件。
- 晚于服务端接收时间的 `eventTime` 会被钳制为服务端接收时间，避免异常未来时间阻塞
  后续状态。
- 客户端必须使用毫秒时间戳并保持时钟可用；严重时钟漂移应在联调中检测。
- `lastReportTime` 使用服务端接收时间，用于状态超时，避免完全依赖设备时钟。

## 8. 超时

| 类型 | 起点 | 结果 |
|---|---|---|
| dispatch | 进入 dispatching | `dispatch_failed` |
| ACK | 进入 dispatched | `ack_timeout` |
| status | accepted 或最后一次有效上报 | `status_timeout` |
| execution | history startTime | `execution_timeout` |

默认值：

```text
ACK:       30s
status:   300s
execution: 3600s
```

总执行超时优先级最高。timeout 条件更新必须匹配读取时的状态；执行阶段还必须匹配
`lastReportTime`，防止扫描线程覆盖刚收到的心跳。

push 在服务端 claim queued 记录时设置 `dispatchTime/startTime`。pull 在设备检查并成功
claim 任务时设置 `dispatchTime/startTime`；设备领取前的 queued 等待时间不计入 ACK、
状态上报或总执行超时。

当前 V1 没有独立 reboot grace 配置。rebooting 仍受 status timeout 和 execution timeout
约束。

## 9. 幂等、并发与重启

客户端要求：

- 持久化 upgradeId、attempt、目标版本和当前阶段。
- 重复收到相同 upgradeId 时不得重新擦写固件，应返回当前状态或最终结果。
- 正在升级时收到不同 upgradeId，应以 `DEVICE_BUSY` 拒绝。
- 重启前持久化关联信息，重启后继续上报同一 upgradeId。
- success 必须上报实际运行版本。

服务端要求：

- `active_key=deviceId` 唯一索引阻止同设备并行升级。
- queued 不占用 active_key；push 调度或 pull 领取使用条件 claim 后才设置
  `active_key=deviceId`。
- 事件、retry、cancel 和 timeout 使用条件更新。
- terminal 状态不可覆盖。
- queued 和 timeout 扫描依赖数据库，服务重启后恢复。
- 不带 upgradeId 的状态拒绝，不做“取设备最新活动任务”的兜底。

## 10. Retry 与 Cancel

可重试：

```text
dispatch_failed rejected ack_timeout status_timeout execution_timeout
download_failed verify_failed install_failed reboot_failed
post_check_failed failed cancelled
```

重试行为：

- attempt 加 1。
- 生成新 upgradeId。
- 清空 messageId、执行时间、进度、错误和完成时间。
- 清空 active_key，等待下一次 push 调度或 pull 领取时重新占用。
- 重新进入 queued。

当前实现复用同一 history 行保存最新 attempt。若合规要求保留每次 attempt 的不可变明细，
需要增加独立 attempt/event 审计表，不能仅依赖当前 history 行。

取消行为：

- V1 只允许 queued -> cancelled。
- 已进入 dispatching 或客户端执行阶段时，取消接口返回不可取消。
- V1 不支持设备端 cancel、pause 或 resume。
- 将来增加设备控制时，控制请求状态应独立于真实升级生命周期状态。

## 11. 任务聚合

任务状态由 history 聚合：

```text
pending
running
completed
partial_failed
failed
stopped
```

- 有任何非终态：running。
- 全部 success：completed。
- success 与失败/取消并存：partial_failed。
- 无 success 且有失败：failed。
- 全部 cancelled：stopped。

任务统计字段：

```text
deviceCount queuedCount runningCount successCount failCount cancelledCount
```

- queuedCount：状态为 queued 的设备数。
- runningCount：除 queued 外的全部非终态设备数。
- successCount：状态为 success 的设备数。
- failCount：失败终态设备数，不包含 cancelled。
- cancelledCount：状态为 cancelled 的设备数。

前端任务抽屉和任务详情在打开期间每 1 秒刷新一次；浏览器页面进入后台时暂停，
恢复可见后立即刷新。轮询请求禁止重叠，避免慢请求累积。

### 11.1 设备当前固件版本

设备实例详情中的固件版本表示设备当前实际运行版本，不直接取升级任务的目标版本。
服务端统一将当前版本持久化到设备实例配置 `firmwareVersion`，详情接口返回：

```json
{
  "firmwareInfo": {
    "version": "1.3.0"
  }
}
```

当前版本可以通过以下任一通用入口更新：

1. `DeviceOnlineMessage` 的 `fwVersion` 或 `firmwareVersion` header。
2. JetLinks 标准 `ReportFirmwareMessage.version`。
3. OTA `success` 事件中的 `reportedVersion` 或 `fwVersion`。

协议报文继续使用 `fwVersion` 表示设备当前实际运行版本；`firmwareVersion` 是服务端设备
实例配置的规范字段。历史配置中的 `fwVersion` 只作为读取兼容，新写入统一使用
`firmwareVersion`。`unknown`、空字符串和 `--` 不得覆盖已保存版本。

设备实例信息页打开期间每 5 秒刷新一次；浏览器页面进入后台时暂停，恢复可见后立即
刷新。这样设备已经在线、仅固件版本发生变化时，页面也能自动显示新版本。

## 12. 客户端验收

客户端上线前必须通过：

1. 重复 upgrade command 幂等。
2. upgradeId 和 attempt 持久化。
3. accepted/rejected 正确。
4. 下载、校验、安装、重启和 post-check 状态可区分。
5. 失败错误码稳定。
6. progress 不倒退。
7. 断网重连后继续上报。
8. 重启后仍关联原 upgradeId。
9. 摘要错误不安装。
10. 实际版本不匹配不报告 success。
11. 不上报 dispatch 或 timeout 等服务端状态。
12. payload deviceId 与 MQTT 认证设备一致。
