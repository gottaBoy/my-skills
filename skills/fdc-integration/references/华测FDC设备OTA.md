# 华测FDC设备OTA

## 目标

FDC 这块有三个比较重要的事项：

1. 现有 FDC 升级方案和操作流程，华测和零一都需要在 A 样上验证通过，并提供升级
   文档。原计划于 **2026年8月3日** 完成升级验证；该日期已过，需要补录实际完成状态。

2. FDC 服务端部署在零一火山云，并与 A 样联调测试，满足零一需求并提供部署文档。
   原计划于 **2026年8月6日** 完成部署验证；该日期已过，需要补录实际完成状态。
   `100.65.*.*` 使用 NetBird 组网。

3. 根据零一提供的 FDC 车端 MQTT 升级方案，结合华测 TCP 协议确定具体通信契约并提供
   TCP 协议文档，计划于 **2026年8月15日** 联调测试，**2026年8月31日前** 上线。



## Topic 规范

OTA 是平台通用能力，并在具体产品上声明和启用。FDC 产品在物模型中定义
`ota_upgrade` 功能，ZIOT 通用 OTA 服务通过该功能发起升级，FDC 协议模块负责转换为
MQTT 消息。

`hc_fdc` 只是当前 FDC 产品 ID，也是当前 FDC MQTT Topic 前缀。它不属于通用 OTA
任务、状态机或关联字段。其他 MQTT 产品可以使用自己的 `{productId}` 复用本消息
契约；TCP 或厂商私有协议可以使用不同报文格式，由协议 codec 映射相同的
`ota_upgrade` 和 `ota_status` 语义。

通用 Topic 模板如下：

```text
上行（设备 -> 云端）:
  {productId}/{deviceId}/status/up     # 设备在线状态、当前固件版本
  {productId}/{deviceId}/data/up       # 网络、带宽、RTT 等遥测数据
  {productId}/{deviceId}/ota/up        # OTA 接受、执行进度和最终结果

下行（云端 -> 设备）:
  {productId}/{deviceId}/command/down  # 普通控制指令
  {productId}/{deviceId}/ota/down      # OTA 升级指令
```

华测 FDC 产品 ID 为 `hc_fdc`：

```text
上行:
  hc_fdc/{deviceId}/status/up
  hc_fdc/{deviceId}/data/up
  hc_fdc/{deviceId}/ota/up

下行:
  hc_fdc/{deviceId}/command/down
  hc_fdc/{deviceId}/ota/down
```

例如设备 `FDC001` 的 OTA 下行 Topic 为：

```text
hc_fdc/FDC001/ota/down
```

FDC 上下行消息使用 UTF-8 JSON 和 QoS 1。MQTT 认证会话中的设备 ID 是权威设备 ID；
payload 中的 `deviceId` 必须与认证设备一致，否则服务端拒绝消息。

## 消息格式（JSON）

### 通用消息封装

上行和下行统一使用以下 envelope：

```json
{
  "deviceId": "FDC001",
  "type": "message-type",
  "messageId": "unique-message-id",
  "ts": 1786118400000,
  "data": {}
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `deviceId` | 是 | 设备 ID，必须与 MQTT 认证设备一致 |
| `type` | 是 | 消息类型，如 `status`、`data`、`ota_check`、`ota_check_reply`、`ota`、`command`、`ota_upgrade` |
| `messageId` | 是 | 单条消息唯一 ID，用于消息去重和日志追踪 |
| `ts` | 是 | 消息产生时间，Unix 毫秒时间戳 |
| `data` | 是 | 当前消息的业务数据 |

`messageId` 标识单条 MQTT 消息；`upgradeId` 标识一次设备 OTA attempt，二者不能互相
替代。OTA 关联字段 `upgradeId`、`taskId`、`historyId`、`firmwareId` 和 `attempt`
只放在 `data` 中，不在 envelope 根节点重复。

任务和升级关联 ID 使用以下统一格式：

```text
taskId:    TASKyyyyMMddHHmmssSSS-NNN
upgradeId: UPGRADEyyyyMMddHHmmssSSS-NNN
```

例如：

```text
taskId:    TASK20260808182534123-001
upgradeId: UPGRADE20260808182534123-001
```

`TASK` 表示批量升级任务，`UPGRADE` 表示单设备单次升级 attempt。时间部分为服务端
本地时间，格式是 `yyyyMMddHHmmssSSS`；三位序号从 `001` 开始。同一服务进程内达到
`999` 后使用下一个逻辑毫秒，系统时钟短暂回拨时也保持 ID 单调且不重复。已有旧格式 ID
继续有效，不做数据迁移。当前规则面向单实例；集群部署前需要在时间和序号之间增加节点
标识，并保证所有节点使用相同的时区。

业务代码不得解析 ID 获取时间或状态，只能将其作为不透明关联值使用，以便后续增加节点
标识时不影响 OTA 状态机和协议。

### 字段命名规则

JSON 协议本身同时支持 camelCase 和 snake_case，`data` 也不会限制自定义字段使用
下划线。但平台不会自动把两种名称互相转换，`bw_up` 和 `bwUp` 是两个不同的属性 ID。

本协议按字段归属固定命名方式：

| 字段范围 | 命名方式 | 示例 |
|---|---|---|
| 通用 envelope 字段 | camelCase | `deviceId`、`messageId` |
| 通用设备状态字段 | camelCase | `fwVersion`、`uptimeS` |
| 通用 OTA 字段 | camelCase | `upgradeId`、`taskId`、`fwUrl`、`reportedVersion` |
| FDC 自定义遥测字段 | snake_case 或既有小写字段 | `bw_up`、`bw_down`、`rtt_ms`、`packet_loss`、`kl15` |

设备上报、协议编解码器、产品物模型和后端查询必须使用完全一致的字段名。已确定使用
snake_case 的 FDC 遥测字段不得在其他环节改写为 camelCase，也不要为同一含义同时建立
`bw_up` 和 `bwUp` 两套属性。

### 上行：设备状态

Topic：

```text
hc_fdc/{deviceId}/status/up
```

设备上线或周期心跳示例：` new Date().getTime() `

```json
{
  "deviceId": "FDC001",
  "type": "status",
  "messageId": "FDC001-1786118400000",
  "ts": 1786118400000,
  "data": {
    "state": "online",
    "fwVersion": "1.0.0",
    "uptimeS": 86400
  }
}
```

`fwVersion` 是设备当前实际运行版本，`uptimeS` 单位为秒。字段使用 camelCase，不再使用
旧示例中的 `fw_version` 和 `uptime_s`。

MQTT 连接建立时，平台可能已根据会话生成一次不带业务字段的上线事件。协议包会将设备
随后发送的 `status/up` 解码为可继续处理的业务上线消息，确保其中的 `fwVersion` 能同步
到设备实例。客户端仍必须在 MQTT 连接成功后再发送该消息。

### 上行：遥测数据

Topic：

```text
hc_fdc/{deviceId}/data/up
```

```json
{
  "deviceId": "FDC001",
  "type": "data",
  "messageId": "FDC001-1786118460000",
  "ts": 1786118460000,
  "data": {
    "bw_up": 1024,
    "bw_down": 2048,
    "rtt_ms": 35,
    "packet_loss": 0.5,
    "kl15": 0
  }
}
```

遥测字段说明：

| 字段 | 单位/取值 | 说明 |
|---|---|---|
| `bw_up` | Kbit/s | 上行带宽 |
| `bw_down` | Kbit/s | 下行带宽 |
| `rtt_ms` | ms | 网络往返时延 |
| `packet_loss` | % | 丢包率，例如 `0.5` 表示 0.5% |
| `kl15` | `0` 或 `1` | `0` 表示低电平 0V，`1` 表示高电平 12V |

`data` 内可以增加产品自定义遥测字段，并允许使用 snake_case。产品物模型必须按上表
原样定义 `bw_up`、`bw_down`、`rtt_ms`、`packet_loss` 和 `kl15`；已发布字段的名称、
类型和单位不能随意变更。

### 下行：控制指令

Topic：

```text
hc_fdc/{deviceId}/command/down
```

KL15 控制示例：

```json
{
  "deviceId": "FDC001",
  "type": "command",
  "messageId": "FDC001-1786118520000",
  "ts": 1786118520000,
  "data": {
    "kl15": 0
  }
}
```

`kl15=0` 表示设置为低电平 0V，`kl15=1` 表示设置为高电平 12V。目前华测 FDC 仅支持
`0` 和 `1`，不支持直接指定 0V、12V 或 24V。

设备应按 `messageId` 对重复控制消息做幂等处理。普通控制命令的业务响应格式由对应
功能定义；不能把 MQTT PUBACK 当作设备已经执行成功。

### 下行：OTA 升级指令

Topic：

```text
hc_fdc/{deviceId}/ota/down
```

完整下行示例：

```json
{
  "deviceId": "FDC001",
  "type": "ota_upgrade",
  "messageId": "UPGRADE20260808182534123-001",
  "ts": 1786118580000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "fwVersion": "1.0.0",
    "fwUrl": "https://download.example.com/fdc/firmware-1.0.0.bin?signature=...",
    "fwSize": 2097152,
    "fwSha256": "92b6c3e0d8c2f4b5a33ce46d77ee89065e40cb3f4c8ab3b3f8b6716f7e98b8af",
    "force": false,
    "deadlineS": 3600
  }
}
```

OTA 下行字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `upgradeId` | 是 | 本设备本次升级 attempt 的全局关联 ID |
| `taskId` | 是 | 批量升级任务 ID |
| `historyId` | 是 | 当前设备升级记录 ID |
| `firmwareId` | 是 | ZIOT 固件记录 ID |
| `attempt` | 是 | 尝试序号，从 1 开始；重试时递增 |
| `fwVersion` | 是 | 目标固件版本 |
| `fwUrl` | 是 | HTTPS 固件下载地址，生产环境应使用短期签名 URL |
| `fwSize` | 是 | 固件大小，单位为字节 |
| `fwSha256` | 是 | 固件 SHA-256 摘要，64 位十六进制字符串 |
| `force` | 是 | 是否允许覆盖相同版本等非默认升级条件 |
| `deadlineS` | 是 | 本次升级总执行期限，单位为秒 |

V1 兼容 `fwMd5`，但生产固件至少使用 SHA-256。高安全场景还必须验证厂商数字签名。
`deadlineS` 是总执行期限，不是单次 HTTP 下载请求的超时时间。

设备收到重复的同一 `upgradeId` 时，不得重新擦写固件，应返回该 attempt 的当前状态或
最终结果。设备正在执行其他 `upgradeId` 时，应上报 `rejected` 和
`errorCode=DEVICE_BUSY`。

重试下行必须生成新的 `upgradeId` 和 `messageId`，同时递增 `attempt`：

```json
{
  "deviceId": "FDC001",
  "type": "ota_upgrade",
  "messageId": "UPGRADE20260808182600000-001-a2",
  "ts": 1786119000000,
  "data": {
    "upgradeId": "UPGRADE20260808182600000-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 2,
    "fwVersion": "1.0.0",
    "fwUrl": "https://download.example.com/fdc/firmware-1.0.0.bin?signature=...",
    "fwSize": 2097152,
    "fwSha256": "92b6c3e0d8c2f4b5a33ce46d77ee89065e40cb3f4c8ab3b3f8b6716f7e98b8af",
    "force": false,
    "deadlineS": 3600
  }
}
```

### 设备主动检查升级（pull）

pull 和 push 共用同一套任务、history、状态机、超时和重试逻辑。区别只在触发方式：

- push：任务创建后由平台主动下发 `ota_upgrade`。
- pull：任务创建后保持 `queued`，设备发送 `ota_check` 时领取任务。

设备检查请求由 FDC codec 解码为 JetLinks Core 标准 `RequestFirmwareMessage`，服务端
回复标准 `RequestFirmwareMessageReply`，再由 FDC codec 编码为 `ota_check_reply`。
`firmware-component` 不依赖 `hc_fdc`、MQTT Topic 或 FDC 私有 JSON。

#### 上行：检查可领取任务

Topic：

```text
hc_fdc/FDC001/ota/up
```

```json
{
  "deviceId": "FDC001",
  "type": "ota_check",
  "messageId": "ota-check-FDC001-0001",
  "ts": 1786118500000,
  "data": {
    "currentVersion": "0.0.1",
    "requestVersion": "0.0.2"
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `currentVersion` | 否 | 设备当前实际运行版本；等于目标版本时服务端可直接完成该记录 |
| `requestVersion` | 否 | 希望领取的目标版本；为空时领取服务端已为该设备创建的匹配任务 |

设备因未收到回复而重试同一次检查时，必须复用原 `messageId`。服务端使用该
`messageId` 幂等返回已经领取的同一分配。使用新 `messageId` 表示发起一次新的检查。

#### 下行：返回升级分配

Topic：

```text
hc_fdc/FDC001/ota/down
```

回复必须复用检查请求的 `messageId`：

```json
{
  "deviceId": "FDC001",
  "type": "ota_check_reply",
  "messageId": "ota-check-FDC001-0001",
  "ts": 1786118501000,
  "data": {
    "success": true,
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "force": false,
    "deadlineS": 3600,
    "fwVersion": "1.0.0",
    "fwUrl": "https://download.example.com/fdc/firmware-1.0.0.bin?signature=...",
    "fwSize": 2097152,
    "fwSha256": "92b6c3e0d8c2f4b5a33ce46d77ee89065e40cb3f4c8ab3b3f8b6716f7e98b8af"
  }
}
```

领取成功后，该 history 从 `queued` 进入 `dispatching/dispatched`，并从领取时刻开始
计算响应超时和升级总超时。领取前的 queued 等待时间不计入升级执行时间。

#### 下行：没有可领取任务

```json
{
  "deviceId": "FDC001",
  "type": "ota_check_reply",
  "messageId": "ota-check-FDC001-0002",
  "ts": 1786118502000,
  "data": {
    "success": false,
    "errorCode": "NO_PENDING_UPGRADE",
    "errorMessage": "当前设备没有可领取的固件升级任务"
  }
}
```

`NO_PENDING_UPGRADE` 是正常的“当前无任务”业务结果，不表示 MQTT 连接异常，也不会由
服务端隐式创建 OTA 任务。设备可按产品策略定期使用新的 `messageId` 再次检查。

### 上行：OTA 状态

Topic：

```text
hc_fdc/{deviceId}/ota/up
```

客户端标准状态：

```text
accepted -> preparing -> downloading -> downloaded
         -> verifying -> verified -> installing
         -> rebooting -> post_checking -> success
```

客户端失败终态：

```text
rejected
download_failed
verify_failed
install_failed
reboot_failed
post_check_failed
failed
```

`dispatching`、`dispatched`、`dispatch_failed`、`ack_timeout`、`status_timeout`、
`execution_timeout` 和 `cancelled` 属于服务端状态，设备不得上报。客户端可以跳过不支持
的中间阶段，但状态和 `progress` 不能回退；`success` 必须上报设备重启后实际运行版本。

每一条 OTA 状态消息都必须使用新的 `messageId`，并在 `data` 中携带同一 attempt 的
`upgradeId`、`taskId`、`historyId`、`firmwareId` 和 `attempt`。

每个状态存在的理由和是否允许跳过：

| 状态 | 存在理由 | 生产 FDC 要求 |
|---|---|---|
| `accepted` | 明确设备已解析并接受任务，不能用 MQTT PUBACK 替代 | 必须；或上报 `rejected` |
| `preparing` | 表示正在检查型号、电量、存储空间和升级条件 | 可跳过 |
| `downloading` | 区分固件获取阶段，支持下载进度和下载超时诊断 | 必须 |
| `downloaded` | 明确文件已完整落盘，便于区分下载和校验耗时 | 可跳过 |
| `verifying` | 表示正在校验大小、摘要、签名和兼容性 | 必须 |
| `verified` | 明确校验通过，便于定位安装前故障 | 可跳过 |
| `installing` | 表示正在写分区、解包或安装固件 | 必须 |
| `rebooting` | 告知平台设备即将离线，避免把预期断连误判为普通掉线 | 必须 |
| `post_checking` | 重启后检查实际版本、进程和关键功能健康状态 | 必须 |
| `success` | 唯一成功终态，证明新版本已实际运行且健康检查通过 | 必须 |
| `rejected` | 设备在开始执行前拒绝任务，返回可诊断原因 | 与 `accepted` 二选一 |
| `download_failed` | 下载阶段失败终态 | 下载失败时必须 |
| `verify_failed` | 大小、摘要、签名或兼容性校验失败终态 | 校验失败时必须 |
| `install_failed` | 写入、解包或安装失败终态 | 安装失败时必须 |
| `reboot_failed` | 无法发起重启或 bootloader 明确报告失败 | 能识别时必须 |
| `post_check_failed` | 已重启但版本或健康检查未通过 | 重启后检查失败时必须 |
| `failed` | 无法归类到上述阶段的兼容失败终态 | 仅无法分类时使用 |

允许跳过只表示客户端不必上报该细化里程碑，不表示可以省略对应的实际安全动作。例如
可以不报 `verified`，但不能跳过固件校验。FDC 最小成功上报链为：

```text
accepted -> downloading -> verifying -> installing
         -> rebooting -> post_checking -> success
```

#### 设备接受升级

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0001",
  "ts": 1786118581000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "accepted",
    "fwVersion": "1.0.0",
    "progress": 0,
    "eventTime": 1786118581000
  }
}
```

#### 准备升级

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0002",
  "ts": 1786118590000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "preparing",
    "fwVersion": "1.0.0",
    "progress": 5,
    "eventTime": 1786118590000
  }
}
```

#### 下载进度

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0003",
  "ts": 1786118640000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "downloading",
    "fwVersion": "1.0.0",
    "progress": 50,
    "eventTime": 1786118640000
  }
}
```

#### 下载完成

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0004",
  "ts": 1786118700000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "downloaded",
    "fwVersion": "1.0.0",
    "progress": 70,
    "eventTime": 1786118700000
  }
}
```

#### 正在校验

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0005",
  "ts": 1786118720000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "verifying",
    "fwVersion": "1.0.0",
    "progress": 75,
    "eventTime": 1786118720000
  }
}
```

#### 校验完成

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0006",
  "ts": 1786118760000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "verified",
    "fwVersion": "1.0.0",
    "progress": 80,
    "eventTime": 1786118760000
  }
}
```

#### 正在安装

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0007",
  "ts": 1786118800000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "installing",
    "fwVersion": "1.0.0",
    "progress": 90,
    "eventTime": 1786118800000
  }
}
```

#### 准备重启

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0008",
  "ts": 1786118860000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "rebooting",
    "fwVersion": "1.0.0",
    "progress": 95,
    "eventTime": 1786118860000
  }
}
```

#### 重启后检查

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0009",
  "ts": 1786118920000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "post_checking",
    "fwVersion": "1.0.0",
    "progress": 98,
    "eventTime": 1786118920000
  }
}
```

#### 设备拒绝升级

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0003",
  "ts": 1786118582000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "rejected",
    "fwVersion": "1.0.0",
    "progress": 0,
    "errorCode": "DEVICE_BUSY",
    "errorMessage": "another upgrade is running",
    "eventTime": 1786118582000
  }
}
```

#### 固件校验失败

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0004",
  "ts": 1786118760000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "verify_failed",
    "fwVersion": "1.0.0",
    "progress": 75,
    "errorCode": "SHA256_MISMATCH",
    "errorMessage": "firmware SHA-256 does not match",
    "eventTime": 1786118760000
  }
}
```

失败状态必须同时携带稳定的 `errorCode` 和可读的 `errorMessage`。推荐拒绝错误码：

```text
DEVICE_BUSY
MODEL_MISMATCH
VERSION_NOT_ALLOWED
INSUFFICIENT_STORAGE
INSUFFICIENT_POWER
INVALID_REQUEST
UNSUPPORTED_DELIVERY_MODE
```

下载、校验、安装和重启阶段应使用对应的稳定错误码，例如 `HTTP_DOWNLOAD_FAILED`、
`SHA256_MISMATCH`、`INSTALL_WRITE_FAILED` 和 `REBOOT_FAILED`。

#### 其他失败终态完整示例

下载失败：

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-failure-FDC001-download",
  "ts": 1786118680000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "download_failed",
    "fwVersion": "1.0.0",
    "progress": 42,
    "errorCode": "HTTP_DOWNLOAD_FAILED",
    "errorMessage": "firmware download returned HTTP 503",
    "eventTime": 1786118680000
  }
}
```

安装失败：

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-failure-FDC001-install",
  "ts": 1786118840000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "install_failed",
    "fwVersion": "1.0.0",
    "progress": 90,
    "errorCode": "INSTALL_WRITE_FAILED",
    "errorMessage": "failed to write inactive firmware partition",
    "eventTime": 1786118840000
  }
}
```

重启失败：

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-failure-FDC001-reboot",
  "ts": 1786118880000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "reboot_failed",
    "fwVersion": "1.0.0",
    "progress": 95,
    "errorCode": "REBOOT_FAILED",
    "errorMessage": "device could not enter reboot sequence",
    "eventTime": 1786118880000
  }
}
```

重启后检查失败：

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-failure-FDC001-post-check",
  "ts": 1786118930000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "post_check_failed",
    "fwVersion": "1.0.0",
    "progress": 98,
    "errorCode": "VERSION_MISMATCH",
    "errorMessage": "device restarted but is still running version 1.0.0",
    "eventTime": 1786118930000
  }
}
```

无法分类的兼容失败：

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-failure-FDC001-generic",
  "ts": 1786118850000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "failed",
    "fwVersion": "1.0.0",
    "progress": 90,
    "errorCode": "OTA_INTERNAL_ERROR",
    "errorMessage": "unexpected OTA client error",
    "eventTime": 1786118850000
  }
}
```

#### 升级成功

```json
{
  "deviceId": "FDC001",
  "type": "ota",
  "messageId": "ota-event-FDC001-0005",
  "ts": 1786118940000,
  "data": {
    "upgradeId": "UPGRADE20260808182534123-001",
    "taskId": "TASK20260808182534123-001",
    "historyId": "history-FDC001-001",
    "firmwareId": "firmware-fdc-1.0.0",
    "attempt": 1,
    "state": "success",
    "fwVersion": "1.0.0",
    "progress": 100,
    "eventTime": 1786118940000
  }
}
```

`fwVersion` 是该条事件产生时设备实际运行的版本：重启前通常仍是旧版本，重启并启动
新固件后才应变为目标版本。`reportedVersion` 是通用 OTA 事件可选的同义字段；FDC
统一使用 `fwVersion` 即可，服务端会将其保存为 history 的 reported version。下载完成、
校验通过、安装完成或 `progress=100` 都不能替代最终 `success`。

服务端收到上线状态中的 `fwVersion` 或最终 `success` 后，会把当前运行版本保存到设备
实例配置 `firmwareVersion`，设备实例详情通过 `firmwareInfo.version` 展示。因此客户端
重启上线时必须上报新固件实际版本；不能只在升级指令中接收目标版本而不进行版本确认。

### OTA 完整交互顺序

push 模式：

```text
ZIOT                                 FDC
 |                                    |
 |-- ota/down: ota_upgrade ---------->|
 |<-- ota/up: accepted ---------------|
 |<-- ota/up: preparing --------------|
 |<-- ota/up: downloading ------------|
 |<-- ota/up: downloaded -------------|
 |<-- ota/up: verifying --------------|
 |<-- ota/up: verified ---------------|
 |<-- ota/up: installing -------------|
 |<-- ota/up: rebooting ---------------|
 |       MQTT connection interrupted   |
 |<-- reconnect with same deviceId ----|
 |<-- ota/up: post_checking -----------|
 |<-- ota/up: success -----------------|
```

pull 模式：

```text
ZIOT                                 FDC
 |                                    |
 |<-- ota/up: ota_check ---------------|
 |-- ota/down: ota_check_reply -------->|
 |<-- ota/up: accepted -----------------|
 |<-- ota/up: downloading --------------|
 |<-- ota/up: verifying ----------------|
 |<-- ota/up: installing ---------------|
 |<-- ota/up: rebooting ----------------|
 |       MQTT connection interrupted    |
 |<-- reconnect with same deviceId -----|
 |<-- ota/up: post_checking ------------|
 |<-- ota/up: success ------------------|
```

服务端可观察状态在两种模式下统一为：

```text
queued -> dispatching -> dispatched -> accepted -> ... -> success
```

push 的 `queued -> dispatching` 由平台调度触发；pull 的该迁移由设备 `ota_check` 领取触发。
`dispatch_failed`、`ack_timeout`、`status_timeout`、`execution_timeout` 和 `cancelled`
只由服务端产生，不存在对应的设备上报报文。

MQTT PUBACK 只表示 Broker 已接收下行消息，不能替代设备上报的 `accepted`。设备重启前
必须持久化 `upgradeId`、`attempt`、目标版本和当前阶段，重连后继续使用原
`upgradeId` 上报。

三个任务超时字段单位均为秒，默认值为：

```text
responseTimeoutSeconds = 30
statusTimeoutSeconds   = 300
timeoutSeconds         = 3600
```

- 响应超时：平台成功发送 push 命令或 pull 分配回复后，等待客户端
  `accepted/rejected` 的时间。
- 状态上报超时：从 `accepted` 或最后一条有效客户端状态开始计算。
- 升级总超时：push 从平台 claim 开始，pull 从设备领取任务开始计算。
- pull 任务领取前保持 queued，不计算上述三个执行超时。

### 联调前实现一致性检查

本文以 `hc_fdc` 作为真实 FDC 产品 ID 和 MQTT Topic 前缀。协议路由、下行 codec、
产品配置和设备模拟器必须统一使用该值。该约束只适用于 FDC MQTT 适配器，不得传入
`firmware-component` 的通用任务、状态机或数据库模型。协议模块目录名
`hc-fdc-protocol` 和 Java 类名 `HcFdc*` 也沿用该命名。

联调前必须在设备产品详情页启用产品 `hc_fdc`，使其状态为已激活。设备显示在线仅说明
MQTT 会话和上行链路可用，不代表产品已经注册到 JetLinks `DeviceRegistry`。push 下发
和 pull 分配回复都需要从已激活产品加载协议及物模型；产品未激活时不得绕过校验，平台
应拒绝创建或重试任务，并返回 `PRODUCT_NOT_ACTIVATED - 产品[hc_fdc]未激活`。激活产品
后，已有 `dispatch_failed` 记录可从任务详情中重试，无需重新创建固件。

当前实现还把 `hc_fdc` 用作 JetLinks `ProtocolSupport` ID 和内置 metadata ID。这是
现有 FDC 接入的兼容值，不是通用 OTA 契约。后续如果一个 MQTT codec 要绑定多个产品，
应保留稳定协议 ID，并从产品或网关配置读取 `productId/topicPrefix`；不能让设备通过
payload 自行指定产品。

当前协议代码已按以下规则实现，联调时必须逐项验证：

1. 普通 `command/down` 必须携带根节点 `messageId`。
2. KL15 控制消息的 `data` 应使用本文定义的 JSON 对象，不能下发 JetLinks 参数对象数组。
3. 状态上报使用 `fwVersion`、`uptimeS`，不能继续发送 `fw_version`、`uptime_s`。
4. OTA 上报的关联字段必须放在 `data`，模拟器不能继续放在根节点。


## **认证链路（三级）**

```Plain Text
1. MQTT 层: EMQX Redis 认证 (clientId + password)
2. zeroniot 层: HcFdcAuthenticator (clientId 前缀 FDC-)
3. API 层: zeroniot RBAC (用户权限)
```



## **设备注册流程**

```Plain Text
1. 管理员在 zeroniot 录入 FDC 设备（SN + clientId）
2. zeroniot 自动同步设备凭证到 Redis（mqtt_user:{clientId}）
3. FDC 设备上线，携带 clientId + password
4. EMQX 查 Redis 验证 → 通过
5. MQTT Broker 接入网关收到 MQTT 消息
6. HcFdcAuthenticator 校验 clientId 白名单 → 通过
7. 设备上线
```

## 本地测试结果
