# 2026-09-03 MRC、e2e 重启与 EPB 释放分析

分析日期：`2026-09-09`

事件日期：`2026-09-03`

目标时间：`1788370914`（北京时间 `2026-09-03 01:41:54`）

状态：`observed / joystick timeout / e2e restarted / partial recovery`

本报告参考 `.github/observability/13-mrc-e2e-recovery-analysis-20260901.md`
的分析方式，独立分析 2026-09-03 的 cloud_driving 与两次 e2e 进程窗口。

## 1. 结论先行

本片段的直接根因是：

```text
R/REMOTE 模式下 remotejoystick 业务消息中断
    -> cloud 检测到 857ms 未收到有效手柄帧
    -> JOYSTICK_IDLE_TIMEOUT
    -> cloud MRC 状态 0→2
    -> e2e 收到 pd=2，进入 MRC1
```

这不是 e2e 自身崩溃。旧 e2e 在 MRC1 中持续运行到
`1788370982.589786085`，随后由 `Ctrl-C/SIGINT` 正常退出；新 e2e 进程在
`1788371000.3643246` 创建。

重启 e2e 本身也没有立即恢复远控。新进程启动后首先收到的仍是 cloud 转发的旧
`pd=2` 状态，继续进入 MRC1。随后 e2e/车辆状态从 R 切到 A，cloud 才清除
joystick MRC；再次进入 R 是约 190 秒后的另一条页面模式指令。

对手刹问题，本片段最关键的证据是：

- MRC 前最后一条有效 R 模式手柄输入带 `epb_cmd=1`；
- MRC 触发时车速为 `0.0`，e2e 的 MRC 静止安全路径具备主动请求拉起 EPB 的条件；
- 重启后 cloud 虽然收到过 44 条 `epb_cmd=0`，但它们都处于非 R 模式并被明确
  丢弃，不能作为“释放命令已经到达 e2e”的证据；
- 再次进入 R 后，下一批真正被 R 模式控制路径接受的 remotejoystick 首帧仍为
  `epb_cmd=1`。

因此，本片段更支持：

```text
MRC/输入侧持续要求或保持拉起 EPB，
而可见的 epb_cmd=0 没有通过有效 R 模式手柄路径进入 e2e。
```

现有日志不能证明 `epb_cmd=1` 是用户误触，也不能证明底盘 EPB 执行器拒绝释放。

## 2. 分析文件与时间基准

本节使用：

```text
/Users/minyi/Downloads/ztd_cloud_driving_20260902201745.log
/Users/minyi/Downloads/e2e_control_20260902201744.log
/Users/minyi/Downloads/e2e_control_20260903014320 (1).log
```

目标时间：

```text
1788370914 = 2026-09-03 01:41:54 CST
```

日志中的 cloud 内部 MRC 状态值和 e2e 仲裁结果不能直接按数字等同：

- cloud `status 0→2`：表示 joystick MRC 状态进入
  `JOYSTICK_IDLE_TIMEOUT`；
- e2e `result=2`：在本项目定义中对应 e2e MRC1；
- `drive_mode=2`：表示 R/REMOTE 模式，不表示 MRC2。

## 3. MRC 触发时间线

| 时间戳 | 北京时间 | 证据 | 判断 |
|---:|---|---|---|
| `1788370913.776846790` | `01:41:53.777` | cloud 最后一条连续手柄输入，`epb_cmd=1`、`gear=1`、`bt_up=59`、`bt_others=0` | 当时仍在收到 R 模式控制帧 |
| `1788370914.076987029` | `01:41:54.077` | cloud `detecting loss gap=300ms` | 开始判定手柄流中断 |
| `1788370914.409822049` | `01:41:54.410` | e2e 收到 `drive_mode=2, joystick_status=255, stop_flag=32` | cloud keepalive/制动保持帧仍在，不代表真实手柄流存在 |
| `1788370914.634079635` | `01:41:54.634` | cloud `MRC1 triggered gap=857ms` | joystick 超时达到触发条件 |
| `1788370914.640597870` | `01:41:54.641` | cloud MRC `0→2`，原因 `JOYSTICK_IDLE_TIMEOUT`，`mode=2 speed=0.0 gear=1` | 根因和车辆状态明确 |
| `1788370914.653432179` | `01:41:54.653` | e2e `result=2 (pd=2 health=1)` | e2e 收到手柄侧 MRC1 |
| `1788370914.653494223` | `01:41:54.653` | e2e `MRC1 is triggering` | e2e 安全控制路径开始生效 |

原始位置：

```text
ztd_cloud_driving_20260902201745.log:220640
ztd_cloud_driving_20260902201745.log:220642-220644
e2e_control_20260902201744.log:1459652
e2e_control_20260902201744.log:1459678-1459679
```

同一窗口内 cloud 的 `cloudLinkPing` 持续获得回复，RTT 约
`49ms~109ms`。所以证据指向的是 remotejoystick 业务流中断，不能仅凭 ping
正常把手柄业务链路判为正常，也不能把这次事件归因成整个 cloud 连接完全断开。

## 4. e2e 是人工停止后重启，不是崩溃自恢复

旧实例：

```text
Created: 1788351465.0080566
PID:     2912
```

它在 MRC1 中继续运行到：

```text
1788370982.589786085  signal_handler(SIGINT/SIGTERM)
process has finished cleanly [pid 2912]
```

日志同时明确记录：

```text
[launch]: user interrupted with ctrl-c (SIGINT)
```

对应位置：

```text
e2e_control_20260902201744.log:1470132-1470136
```

新实例：

```text
Created: 1788371000.3643246
PID:     224085
初始化完成: 1788371004.077503949
```

对应位置：

```text
e2e_control_20260903014320 (1).log:4
e2e_control_20260903014320 (1).log:12-13
```

旧实例收到 SIGINT 到新实例创建相隔约 `17.77s`。这组证据只能确认 e2e
进程被停止并重新启动，不能证明 IPC、cloud_driving 或整机同时重启。

## 5. 新 e2e 启动后先继承 MRC，随后靠 `R→A` 清除

新 e2e 初始化后首先收到：

```text
1788371006.024767964
PDriving: drive_mode=2 joystick_status=255 gear=2 stop_flag=32

1788371006.043568380
MRC active result=2 (pd=2 health=0)
```

即新进程没有因为自身重启而自动得到正常手柄状态，而是先继承 cloud 当前维护的
`pd=2`，继续执行 MRC1。

随后：

```text
1788371006.137368640
cloud: R→A transition detected, reset cached_drive_mode to 0 + clear MRC

1788371006.248674728
cloud MRC status: 2→0, mode=1

1788371007.723568678
e2e effective_mrc=0
```

对应位置：

```text
ztd_cloud_driving_20260902201745.log:220699-220700
e2e_control_20260903014320 (1).log:24-25
e2e_control_20260903014320 (1).log:122
```

所以这次 MRC 清除的直接时序是：

```text
新 e2e 启动
    -> 仍收到 pd=2
    -> driving mode 从 R 退出到 A
    -> cloud 重置 joystick monitor/MRC
    -> e2e 仲裁值回到 0
```

不能简化成“重启 e2e 后手柄链路立即恢复”。

## 6. 重启后收到 111 条积压 remotejoystick，但全部被丢弃

cloud 在以下窗口成批收到 remotejoystick：

```text
1788371069.385361128 ~ 1788371116.700096676
```

统计结果：

```text
remotejoystick 总数: 111
epb_cmd=0:           44
epb_cmd=1:           67
payload 时间落后接收时间: 178.288s ~ 222.597s
非 R 模式 drop:      111
```

第一条示例：

```text
接收时间:          1788371069.385361128
payload timestamp: 1788370890671
epb_cmd:           0
随后日志:          drop: cached_drive_mode_=0, joystick only valid in R mode
```

最后一条：

```text
接收时间:          1788371116.700096676
payload timestamp: 1788370916713
epb_cmd:           1
bt_others:         1
随后日志:          drop: cached_drive_mode_=0, joystick only valid in R mode
```

原始位置：

```text
ztd_cloud_driving_20260902201745.log:220741-221104
```

事件前最后一条连续手柄帧及后续下一条 R 模式手柄帧的 payload 时间通常比接收
时间落后约 `37s`；上述批次则落后 `178s~223s`，且在极短时间内集中到达，
明显不是正常实时控制节奏，更符合积压、回放或跨链路缓存数据的特征。

代码也解释了为什么这些帧不能用于证明远控或 EPB 已恢复：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:870-881
收到任意 remotejoystick 时先刷新通用接收存活状态 pd_js_status_

aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:951-969
cached_drive_mode_ != 2 时直接 return，不发布给 e2e，
也不刷新 R 模式 MRC 监控使用的 last_joystick_steady_ms_
```

所以 cloud/HUD 的“近期收到过手柄消息”和“e2e 收到了有效 R 模式控制帧”是两件
不同的事。当前 handler 也没有根据 payload `timestamp` 对旧帧做新鲜度拒绝，
因此旧消息仍可进入 handler 并短暂刷新通用接收状态。

## 7. `joystick recovered` 不代表实时手柄流已经恢复

后续模式指令：

```text
1788371187.730940555  drive_mode=1
1788371196.886542789  drive_mode=2
1788371196.939737040  cloud: MRC1 cleared — joystick recovered
```

对应位置：

```text
ztd_cloud_driving_20260902201745.log:221149-221163
```

但 cloud 在：

```text
1788371116.700096676 ~ 1788371416.363101073
```

之间没有记录新的 remotejoystick 输入。也就是说，
`1788371196.939737040` 的 recovered 日志出现在重新进入 R 后约 `53ms`，
而不是紧跟一条实时手柄帧。

新 e2e 同期状态为：

```text
1788371196.886969460  PDriving drive_mode=2, joystick_status=0
1788371196.903709061  mode switched 1 -> 2
1788371196.983519892  result=1 (pd=0 health=1)
```

对应位置：

```text
e2e_control_20260903014320 (1).log:685-689
```

因此：

- joystick 的 `pd` 状态当时已经是 `0`；
- 但 health 仍为 `1`，e2e 总体仍是 MRC0，而不是完全 NORMAL；
- cloud 的 recovered 更接近模式切换/状态机清除后的状态日志，不能解释为
  “实时手柄控制流已经恢复”。

下一条可见 remotejoystick 直到：

```text
1788371416.363101073
epb_cmd=1, bt_others=32, gear=0
payload timestamp=1788371379164
```

才出现，距离 recovered 约 `219.42s`。

## 8. 手刹为什么可能没有解除

#### MRC 前和重新建立手柄流后，输入都要求拉起

MRC 前最后一条有效输入：

```text
1788370913.776846790  epb_cmd=1
```

再次进入 R 后下一条可见手柄输入：

```text
1788371416.363101073  epb_cmd=1
```

普通远控映射为：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:1334-1341
epb_cmd=1 -> epb_requested_mode=PD_ON, parking_brake_percent_cmd=100.4
epb_cmd=0 -> epb_requested_mode=0,    parking_brake_percent_cmd=0.0
```

因此，这两处可确认的有效输入都不是释放语义。

#### MRC 静止路径会主动请求拉起 EPB

cloud 在 MRC 触发时记录 `speed=0.0`。e2e 的 MRC 安全路径在
`effective_mrc >= MRC1` 且速度绝对值小于 `0.3` 时执行：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:731-767
requested_gear = Neutral
parking_brake_percent_cmd = 100.4
```

这证明本事件满足“安全路径主动请求拉起 EPB”的代码条件；但 e2e 日志没有打印
最终发布值，仍不能把它当作底盘已经执行拉起的闭环证据。

#### 可见的 `epb_cmd=0` 没有通过有效 R 模式手柄路径

积压批次中确实有 44 条 `epb_cmd=0`，但 111 条消息全部紧跟：

```text
drop: cached_drive_mode_=0, joystick only valid in R mode
```

因此只能证明 cloud handler 收到过这些值，不能证明它们发布到
`/zeron/parallel_driving/control_info`，更不能证明 e2e 或底盘收到释放请求。

另外，cloud 的 PD keepalive 使用 `joystick_status=0xFF`，其设计目的是刷新连接
时间而不执行真实手柄控制；e2e 对非活动 joystick 帧进入制动保持分支：

```text
aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:1527-1565
aura/src/control/e2e_control/src/e2e_control_v2.cc:1216-1228
```

当前日志没有打印该分支最终携带或保留的
`epb_requested_mode/parking_brake_percent_cmd`。同时
`SetDefaultValueForPDCtrl()` 只明确清零 `epb_control_active`，没有显式清零上述
两个值：

```text
aura/src/control/e2e_control/src/e2e_control_v2.cc:1037-1052
```

这属于需要修正和补充观测的状态残留风险，但仅凭本片段不能认定它就是实际手刹
未解除的根因。

## 9. 是否属于误触

现有日志不能证明误触。

能够确认的是：

1. cloud 接收到的有效 R 模式手柄输入明确携带 `epb_cmd=1`；
2. MRC 安全路径在静止条件下也会请求拉起 EPB；
3. 重启后出现的 `epb_cmd=0` 都是明显滞后的积压帧，并在非 R 模式被丢弃；
4. 重新进入 R 后下一条实际手柄输入仍为 `epb_cmd=1`。

仍然无法区分：

- 用户是否实际点击或按下了手刹；
- 页面/手柄是否残留了上一次 `epb_cmd=1` 状态；
- 上游是否发送过实时 `epb_cmd=0`，但在日志覆盖范围外丢失；
- e2e 最终发布值是什么；
- chassis 是否下发了 EPB CAN 请求；
- VCU 是否接受、拒绝或因释放条件不满足而抑制请求。

本片段最终应定性为：

```text
remotejoystick 业务流中断触发 MRC1；
e2e 被人工停止并重启，但 MRC 的清除依赖后续退出 R；
重启后可见的释放帧是积压旧帧且全部被非 R 模式丢弃；
有效 R 模式输入仍为 epb_cmd=1。

所以现有证据更支持“释放请求没有形成可验证的有效控制闭环”，
不支持直接定案为用户误触，也不支持直接定案为底盘手刹故障。
```

## 10. 建议补充的观测

1. cloud 同时记录 `raw_epb_cmd`、`cached_epb_cmd_`、`merged_epb_cmd`、
   payload timestamp、接收时间、消息来源和是否发布；
2. cloud 对 remotejoystick 增加 payload timestamp 新鲜度、单调性和最大滞后
   校验，旧帧不能刷新“手柄在线/控制中”状态；
3. e2e 分别记录 remotejoystick、driveMode、keepalive 和 MRC safety 对
   `epb_control_active`、`epb_requested_mode`、
   `parking_brake_percent_cmd` 的最终赋值；
4. `SetDefaultValueForPDCtrl()` 显式清零 EPB mode/percent，非活动 joystick
   分支也应显式设定安全且无歧义的 EPB 输出；
5. chassis 记录 `T04_ADCU_EPB` 下发值，并同步记录 VCU EPB 状态、错误码和
   release-inhibit 字段，形成输入、e2e 输出、CAN 请求、VCU 反馈的闭环。
