# mcu-updater — AURIX MCU UDP 刷写工具

## 背景

域控制器 SoC (Tegra) 需要通过网络升级 MCU (Infineon AURIX TC397) 固件。MCU 已实现 CommonIf UDP 协议，mcu-updater 是车端 Go 刷写工具，支持独立 CLI 和集成到 zota-server DDI 自动升级链路。

## 架构

```
┌─ 云端 ─────────────────────────────────────────────┐
│  zota-server                                        │
│  SoftwareModule: "mcu-aurix" type                   │
│  Artifact: firmware.hex                             │
│  DistributionSet → Rollout → DDI 下发                │
└──────────────────────┬─────────────────────────────┘
                       │ DDI API (mTLS)
┌─ 车端 ───────────────┼─────────────────────────────┐
│                      ▼                              │
│  aura-ota-agent / zota-cli                          │
│  chunk.Part = "mcu_firmware" → ModeMCU              │
│                      │                              │
│                      ▼                              │
│  mcu-updater/pkg/aurix/                             │
│  ├── hex.go          Intel HEX 解析 + 地址归一化     │
│  ├── protocol.go     CommonIf 消息 + CRC + 重试      │
│  └── flasher.go      完整刷写编排 + 进度回调         │
│                      │ UDP (SoC → MCU)              │
│                      ▼                              │
│  AURIX TC397 MCU (CommonIf.c)                       │
│  接收 PROG_BID 命令 → 擦除 → 编程 → 完成            │
└─────────────────────────────────────────────────────┘
```

## 命令速查

所有命令在 `mcu-updater` 和 `zota-cli mcu` 中均可使用。

| 命令 | 做了什么 | 是否修改 MCU |
|------|----------|:--:|
| `version --addr <ip>:14001` | 读 MCU 当前固件版本号（major.minor.rev.snap） | ❌ |
| `info --hex <file>` | 解析 hex 文件，显示有效刷写布局（地址/大小/页数） | ❌ |
| `validate --hex <file> --addr <ip>:14001` | 校验 hex + 连通性，不擦不写 | ❌ |
| `flash --hex <file> --addr <ip>:14001` | 完整刷写：擦除 → 编程 → 写版本号 | ✅ |
| `test --hex <file> --addr <ip>:14001` | 读版本 → 刷写 → 再读版本，确认版本变化 | ✅ |
| `flash --hex <file> --addr <ip>:14001 --dry-run` | 预检模式：解析 hex + 读版本，仅验证可达性 | ❌ |

## 完整刷写流程

`mcu-updater flash` 执行以下 7 步，每一步失败都会立即停止：

### Step 0：完整性校验（不接触 MCU）

在连接 MCU 之前，先校验 hex 文件未被篡改：

| 校验类型 | 参数 | 说明 |
|----------|------|------|
| SHA-256 | `--sha256 <hash>` | 计算文件 SHA-256，与预期值比对（常数时间比较） |
| HMAC-SHA256 | `--sha256 <hash> --hmac <hmac> --hmac-key <key>` | 用密钥计算 HMAC 后比对 |

校验失败则中止，不会发送任何 UDP 包。

### Step 1：解析 hex 文件

- 读取 Intel HEX 格式（`:020000040001F9` 等记录）
- 支持类型：0x00（数据）、0x04（扩展线性地址）、0x01（EOF）、0x05（入口地址）
- 拒绝类型：0x02/0x03（段地址，AURIX 不使用）
- 每行校验 checksum，损坏行立即报错

### Step 2：地址归一化与合并

```
hex 文件中地址 (cached):  0x8000xxxx
AURIX PFLASH 物理地址:    0xA000xxxx
转换: physical = cached + 0x20000000
```

合并逻辑：
- 镜象重复段合并（same address, same data → 去重）
- 同一 16KB 擦除扇区内间隙用 0xFF 填充（否则先擦后擦互相覆盖）
- 段起始地址向下对齐到 256B 页边界

### Step 3：安全检查

| 检查项 | 规则 | 跳过方式 |
|--------|------|----------|
| BMHD 区域（0xA0000000–0xA000001F） | 拒绝擦除 → 防止变砖 | — 永不跳过 |
| UCB 区域（0xAF400000–0xAF40FFFF） | 拒绝擦除 | `--allow-ucb` |
| 地址超出 PFLASH（0xA0000000–0xA1000000） | 拒绝 | — |
| 入口地址不在 PFLASH | 拒绝（刷错 MCU 型号） | — |

### Step 4：建立 UDP 连接

- 解析目标地址 `--addr <ip>:14001`
- 本地绑定随机端口（可指定 `--laddr :60001`）
- 默认 5 秒超时（`--timeout` 可调）

### Step 5：按段编程

对每个段依次执行：

**5a. 擦除扇区** (`PROG_BID=0x12, IFID=0x02`)
- 发送：物理地址(4B) + 擦除大小(4B)
- 大小向上取整到 16KB 扇区边界
- MCU 响应 0x55 = 成功

**5b. 启用编程** (`PROG_BID=0x12, IFID=0x03`)
- 发送：页对齐物理地址(4B)
- 通知 MCU 进入编程模式

**5c. 逐页写入** (`PROG_BID=0x12, IFID=0x04`)
- 每页 256B 数据 + 页地址(4B) + verify_opt(1B=0x00)
- MCU 内部拆为 8×32B burst 写入 PFLASH
- 每页前检查 `ctx.Done()`，支持取消
- 每页失败 → 停止，不继续擦下一个扇区

### Step 6：结束传输 (`PROG_BID=0x12, IFID=0x05`)

通知 MCU 退出编程状态。所有段共享一次 EOT。

### Step 7：完成编程 (`PROG_BID=0x12, IFID=0x06`)

- 发送版本号：`[major, minor, rev, snap]` 各 1B
- 默认版本号来自 hex 文件头部，可通过 `--version M.m.r.s` 覆盖
- MCU 写入版本并完成

## UDP 协议细节

```
请求:  [BLOCK_ID(1)][IF_ID(1)][LEN_H(1)][LEN_L(1)][payload(LEN bytes)][CRC(1)]
响应:  [0xF0][BLOCK_ID][IF_ID][ERRC(0x55=成功)][LEN_H][LEN_L][data...][CRC]

CRC = 所有字节的 XOR（CRC 字节之前的所有字节）
```

**重试策略**：每条命令最多 3 次，退避 100ms/200ms。`ECONNREFUSED` 立即失败（端口不通无需重试）。

## 与 ZOTA DDI 自动升级集成

### 已实现

车端 agent 已完整集成，通过 DDI 自动下载固件并刷写：

```
zota-server → DDI → agent 下载 firmware.hex
                        │
                        ├─ SHA-256 验签（生产环境不可跳过）
                        ├─ mcu.AurixFlasher.Flash()
                        │    ├─ 解析 hex
                        │    ├─ 读刷前版本 → Feedback
                        │    ├─ 擦除 + 编程（进度回调 → DDI Feedback）
                        │    ├─ 读刷后版本 → Feedback
                        │    └─ 完成
                        └─ 上报 Feedback 到 zota-server
```

### 配置

`aura-ota-agent/configs/config.yaml`：

```yaml
mcu:
  protocol: "aurix_udp"           # 当前使用 UDP CommonIf
  aurix_addr: "169.254.1.10:14001" # MCU IP:端口
  timeout_seconds: 5              # 单条命令超时
```

### Dispatch

agent 通过 `chunk.Part = "mcu_firmware"` 识别 MCU 更新，路由到 `AurixFlasher.Flash()`。

## 完整操作流程（降低变砖风险）

```bash
# 1. 先看 hex 内容（不接触 MCU）
mcu-updater info --hex firmware.hex

# 2. 连通性 + 安全性预检（不擦不写）
mcu-updater validate --hex firmware.hex --addr 169.254.1.10:14001

# 3. 记录当前版本
mcu-updater version --addr 169.254.1.10:14001
# → Output: 1.2.3.4

# 4. 正式刷写
mcu-updater flash --hex firmware.hex --addr 169.254.1.10:14001

# 5. 确认版本已变
mcu-updater version --addr 169.254.1.10:14001
# → Output: 2.0.0.1  ✅

# 6. 如版本未变 → 立即排查，勿重复刷写
```

或一键完成（建议仅在确认 hex 正确时使用）：

```bash
mcu-updater test --hex firmware.hex --addr 169.254.1.10:14001
# 自动执行：读版本 → 刷写 → 读版本 → 确认
```

## 已实现的安全防护

| 场景 | 防护机制 |
|------|----------|
| 擦除 BMHD 变砖 | 拒绝 0xA0000000 前 32 字节擦除 |
| 擦除 UCB 配置区 | 拒绝 0xAF400000 区域（`--allow-ucb` 可跳过） |
| 地址超出 PFLASH | `validateSegments()` 拒绝 0xA0000000–0xA1000000 外地址 |
| hex 文件损坏 | 逐行校验 Intel HEX checksum |
| hex 文件被篡改 | `--sha256` / `--hmac` 预校验（DDI 路径强制） |
| UDP 丢包 | 3 次重试 + 退避，单页失败即停止 |
| 刷写中途取消 | 每页前检查 `ctx.Done()`，已擦除扇区不会残留数据 |
| 镜象重复段 | `mergeSegments()` 自动去重，冲突则报错 |
| 同扇区内多段 | 自动填充 0xFF 合并，避免二次擦除覆盖 |

## 极端场景与限制

| 场景 | 当前状态 | 说明 |
|------|:--:|------|
| 刷写中途断电 | ⚠️ | MCU 内置 A/B Bank 支持，但 Boot Chain 切换命令未集成 |
| 写入数据回读校验 | ❌ | CommonIf 无 Read Flash 命令 |
| MCU 自检失败自动回退 | ❌ | 需 MCU 固件配合 |
| CAN UDS 协议 | ❌ | 不同 MCU 型号，已有独立 `mcu/uds.go`（mock 状态） |

## 与现有代码关系

| 模块 | 关系 |
|------|------|
| `aura-ota-agent/internal/mcu/aurix.go` | 已集成：AurixFlasher 封装，DDI 路径自动刷写 |
| `aura-ota-agent/internal/mcu/uds.go` | 互补：CAN UDS 路径（不同 MCU），当前 mock 状态 |
| `zota-cli/internal/cli/mcu.go` | 已集成：`zota-cli mcu flash/version/validate/info` |
| `zota-cli/internal/eol/eol.go` | 无冲突：checkUDS 是 EOL mock 桩 |
