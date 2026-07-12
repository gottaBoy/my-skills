# ZOTA Architecture — Design (Production Grade)

> 量产车生产级别设计。目标：10,000+ 车辆，99.9% OTA 成功率，安全关键系统兼容。

---

## 架构决策

### ADR-001: 三模式更新架构 — docker / swupdate / mcu

**方案**: `aura-ota-agent` 支持三种更新模式，通过配置切换，共享同一 DDI 客户端。

| mode | 目标 | 传输 | 回滚 | 适用车型 |
|------|------|------|------|---------|
| `docker` | 容器镜像 | Harbor pull | 旧 tag 重启 | 数采车 |
| `swupdate` | Linux 系统镜像 (.swu) | HTTP 下载 | Bootloader A/B 切回 | L4 智驾车 |
| `mcu` | MCU 固件 (.bin/.hex) | CAN UDS (ISO 14229) | MCU 双 Bank | 所有车型 |

**关键设计**: 三种模式走同一个 `UpdateHandler` 接口，HawkBit 不感知车端用什么模式——统一通过 DDI `deploymentBase.chunks[]` 下发，chunk 的 `name` 和 `version` 字段携带类型信息。

**理由**:
- SWUpdate 只管 Linux 分区，MCU 走 CAN/UDS 独立通道，两者完全解耦
- Docker 模式已有成熟实现，保持兼容
- 统一 DDI 协议，HawkBit Side 零改动

### ADR-002: HawkBit 高可用 — 无状态 + 共享 DB + RabbitMQ 事件总线

**方案**: HawkBit 多实例部署（K8s Deployment），无状态服务 + 共享 PostgreSQL + RabbitMQ 集群事件同步。

```
                   ┌── NGINX Ingress ──┐
                   │   (sticky session) │
                   └──┬────────────┬───┘
                      ▼            ▼
              ┌──────────┐ ┌──────────┐
              │ HawkBit-0│ │ HawkBit-1│  ← 无状态，任意扩缩
              └────┬─────┘ └────┬─────┘
                   │            │
                   └─────┬──────┘
                         ▼
              ┌──────────────────┐
              │ PostgreSQL (HA)  │  ← 共享状态
              │ Patroni + etcd   │
              └──────────────────┘
                         │
              ┌──────────────────┐
              │ RabbitMQ Cluster │  ← 事件通知（可选）
              └──────────────────┘
```

**配置要点**:
- `hawkbit.cache.ttl=0s` — 多实例场景禁用本地缓存
- `hawkbit.server.ddi.security.authentication.gatewaytoken.enabled=true` — Gateway Token 认证，车端不感知后端实例
- `hawkbit.events.remote.enabled=true` — 启用集群事件同步

### ADR-003: 端到端安全链 — Secure Boot → mTLS → 签名验证

**方案**: 建立从硬件到应用层的完整信任链。

```
Secure Boot (UEFI)
  │  shim → GRUB → Linux Kernel (签名验证)
  ▼
Vault PKI (mTLS 设备证书)
  │  DDI API / MQTT / NetBird — 全部 mTLS 双向认证
  ▼
Cosign (Artifact 签名)
  │  Docker 镜像 / .swu 包 / 标定包 — 全部签名验证
  ▼
SWUpdate (内建验签)
  │  .swu 包自带 CMS/PKCS#7 签名，swupdate 内核态验签
```

**最小安全基线（Phase 1）**:
1. Artifact 签名: 所有更新包 MUST 经过签名验证
2. 传输加密: DDI API MUST HTTPS + mTLS（复用 pki_fleet 证书）
3. 证书管理: Vault PKI 自动签发/续期/吊销，CRL 定期同步
4. Secure Boot: 量产车 MUST 启用 UEFI Secure Boot

### ADR-004: 诊断通道 — MQTT + mTLS（生产加固）

| 环境 | 传输 | 认证 | QoS |
|------|------|------|-----|
| 开发 | TCP + Token | ZOTA Token | 0 |
| 生产 | TLS 1.3 + mTLS | pki_fleet 设备证书 | 1 |

**诊断安全约束**:
- 命令白名单：仅预定义 10 个命令，参数仅允许特定枚举值
- HMAC 签名：云端诊断命令携带 HMAC-SHA256 签名
- 频率限制：同 VIN 同命令 60s 内不可重复执行
- 并发控制：更新期间拒绝诊断命令

### ADR-005: 离线韧性 — Store-and-Forward + 断点续传

**方案**: HawkBit action 无过期时间，车辆离线积压，上线后按序执行。

**断电保护**:
- SWUpdate: 写入 B 分区期间断电 → A 分区完整 → bootloader 从 A 启动
- Docker: pull 期间断电 → 重启后从缓存 layer 继续
- MCU: UDS 刷写期间断电 → MCU Bootloader 检测不完整 → 从默认 Bank 启动

### ADR-006: 可观测性 — Metrics + Alerting + Audit

```
L1 — Metrics (Prometheus)
  hawkbit_target_online_count / hawkbit_update_success_rate
  hawkbit_update_duration_seconds / zota_diag_command_latency_seconds

L2 — Alerting (PrometheusRule)
  OTA 成功率 < 95% → P1 / 证书 30 天内到期 → P2
  HawkBit 实例 Down → P0 / 诊断超时率 > 10% → P2

L3 — Audit (Elasticsearch / Loki)
  更新操作 / 诊断命令 / 标定变更 / ISO 21434 合规
```

### ADR-007: 配置版本管理 — whl-conf (车端) + Git (源头) + HawkBit (分发)

**三层架构**：三个方案分层互补，不是替代关系。

```
┌─────────────────────────────────────────────────────────────────┐
│                    配置版本管理三层架构                            │
│                                                                   │
│  Layer 1: Source of Truth (Git)                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  calibrations/                     ← FLYNC 理念：配置即代码   │ │
│  │  ├── camera/                                                │ │
│  │  │   ├── v1.2.0/  camera_params.yaml  extrinsics.yaml       │ │
│  │  │   └── v1.3.0/  ...                                       │ │
│  │  ├── lidar/                                                 │ │
│  │  ├── chassis/                                               │ │
│  │  └── perception/                                            │ │
│  │                                                              │ │
│  │  每次提交 → Git Hash → 完整状态可复现                         │ │
│  │  (参考 Perception Platform 方法论)                            │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                             │ CI/CD Pipeline                      │
│                             ▼                                     │
│  Layer 2: Distribution (HawkBit)                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  vehicle_calib Software Module                               │ │
│  │  ├── camera_calib v1.2.0 (tar.gz + cosign sig)              │ │
│  │  ├── lidar_calib  v3.0.1                                    │ │
│  │  └── ...                                                     │ │
│  │                                                              │ │
│  │  DDI → 车端下载 → 校验签名                                    │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                             │ DDI Poll                            │
│                             ▼                                     │
│  Layer 3: Activation (whl-conf)                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  /etc/vehicle/calibrations/                                  │ │
│  │  ├── store/                                                  │ │
│  │  │   ├── camera_v1.2.0/    ← 已下载的版本                    │ │
│  │  │   └── camera_v1.3.0/                                     │ │
│  │  ├── active → store/camera_v1.2.0   ← 原子符号链接           │ │
│  │  └── versions.yaml                   ← 当前激活版本记录      │ │
│  │                                                              │ │
│  │  whl-conf list         → 列出所有版本                         │ │
│  │  whl-conf diff v1.2.0 v1.3.0 → 对比差异                      │ │
│  │  whl-conf activate v1.3.0 → 原子切换（ln -sfn）               │ │
│  │  whl-conf rollback     → 切回上一版本                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**方案分工**:

| 工具 | 层 | 职责 | 对标 |
|------|:---:|------|------|
| **Git + CI** | Source | 配置源头版本化，每次变更关联 Git Hash | FLYNC（配置即代码）+ Perception Platform（Git Hash 可复现） |
| **HawkBit** | Distribution | 包分发、灰度、回滚 | 现有 OTA 基础设施 |
| **whl-conf** | Activation | 车端原子切换、diff、回滚 | whl-conf（配置生命周期管理） |

**whl-conf 集成方式**:
```bash
# whl-conf 是车端工具（Go 二进制），集成到 zota-cli 或独立部署
# 核心命令：
whl-conf list                                    # 列出所有已下载标定版本
whl-conf info camera                             # 查看 camera 模块当前版本
whl-conf diff camera v1.2.0 v1.3.0              # 对比两版本差异
whl-conf activate camera v1.3.0                 # 原子切换（ln -sfn + 通知 aura reload）
whl-conf rollback camera                         # 回滚上一版本
```

**原子切换机制**（whl-conf 核心价值）:
```
active → store/camera_v1.3.0    # 当前
                                  # whl-conf activate camera v1.4.0
active → store/camera_v1.4.0    # ln -sfn 原子操作，无中间状态
                                  # → aura 检测 symlink 变更 → 热重载参数
```

**为什么不直接用 HawkBit 原生的下载→覆盖？**
- 覆盖式更新有中间状态窗口（文件写入中崩溃 → 损坏）
- whl-conf 的 symlink 切换是原子操作，不存在"写了一半"的问题
- 保留历史版本在 `store/`，支持 instant rollback
- `diff` 命令对标定工程师调试至关重要

**FLYNC 借鉴点**: 网络配置（ECU、SOME/IP）也纳入同一版本管理体系，目录结构扩展为:
```
calibrations/
├── perception/     # 感知标定（camera, lidar）
├── chassis/        # 底盘标定
└── network/        # 网络配置（FLYNC 理念）
    └── v1.0.0/
        ├── someip_config.yaml
        └── ecu_topology.yaml
```

### ADR-008: 版本管理平台 — zota-repo 填补 HawkBit 与 Harbor 之间的空白

**问题**: HawkBit 管「应该部署什么」，但不知道「实际部署了什么」和「什么版本能一起工作」。

**方案**: 新增 `zota-repo` 平台，解决四层问题：

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERSION MANAGEMENT PLATFORM                    │
│                          (zota-repo)                              │
├───────────────┬────────────────┬────────────────┬────────────────┤
│ 1. BINARY     │ 2. DEPLOYMENT  │ 3. RECONCILIATION│ 4. INVENTORY  │
│    STORAGE    │    STATE       │    (REALITY)     │   (HARDWARE)  │
├───────────────┼────────────────┼────────────────┼────────────────┤
│ Harbor ✅     │ HawkBit ✅     │ zota-repo ✅    │ zota-repo ✅  │
│ (containers,  │ (target→SM,    │ (漂移检测,       │ (传感器型号,   │
│  firmware,    │  distribution, │  车辆上报实际    │  MCU 类型,     │
│  calibrations)│  rollout)      │  版本 vs 期望)  │  硬件变体)     │
└───────────────┴────────────────┴────────────────┴────────────────┘
```

**开源工具集成分析**:

| 工具 | 用途 | zota-repo 集成 |
|------|------|---------------|
| **HawkBit** MGMT API | 部署期望来源 | 只读查询 target → Distribution Set 映射 |
| **Harbor** API | 二进制存储 | 查询 artifact 列表、hash、签名状态 |
| **whl-conf** | 车端标定激活 | 车端 `whl-conf info` → 上报 zota-repo |
| **cosign** | Artifact 签名 | CI 签名后注册 hash + signature |
| **CycloneDX** | SBOM 生成 | 版本记录 `sbom` JSON 字段 |
| **Dependency Track** | CVE 扫描 (Phase 2) | webhook → 漏洞告警 |
| **Uptane** | 安全框架 (Phase 2) | 管理 Director metadata |

### ADR-009: Artifact 存储策略 — Harbor (容器) + TOS (非容器) + HawkBit (元数据)

**当前状态**: HawkBit 仅支持 `hawkbit-artifact-fs`（本地文件系统），无 S3 后端。

**方案**: 分层存储，HawkBit 不直接存储二进制大文件。

```
┌─────────────────────────────────────────────────────────────────┐
│                    Artifact 存储策略                              │
│                                                                   │
│  Artifact 类型          存储层           HawkBit 存什么            │
│  ─────────────────────────────────────────────────────────────   │
│  Docker 镜像            Harbor          image:tag 引用            │
│  MCU 固件 (.bin)        TOS/S3          presigned URL             │
│  SWUpdate (.swu)        TOS/S3 + CDN    presigned URL             │
│  标定包 (.tar.gz)       TOS/S3          presigned URL             │
│  配置文件 (< 1MB)       HawkBit 内置    直接存储                   │
└─────────────────────────────────────────────────────────────────┘
```

**上传流程**（CI 负责）:
```bash
# 1. CI 构建产物
make build-mcu-firmware    # → mcu_chassis_v2.1.bin

# 2. 上传 TOS + 签名
tos upload mcu_chassis_v2.1.bin  s3://zota-artifacts/mcu/chassis_v2.1.bin
cosign sign-blob --key cosign.key mcu_chassis_v2.1.bin

# 3. 注册到 HawkBit（URL 引用，非上传二进制）
curl -X POST $HAWKBIT_URL/rest/v1/softwaremodules \
  -H "Content-Type: application/json" \
  -d '[{
    "name": "chassis-mcu",
    "version": "2.1",
    "type": "mcu_firmware",
    "description": "url=https://zota-artifacts.tos.com/mcu/chassis_v2.1.bin digest=sha256:abc123"
  }]'
```

**车端下载**（DDI 协议原生支持）:
```
HawkBit DDI Response:
  deploymentBase.deployment.chunks[0].part = "tos"
  deploymentBase.deployment.download = "https://zota-artifacts.tos.com/mcu/chassis_v2.1.bin"

aura-ota-agent:
  1. 解析 download URL
  2. HTTP GET（支持 Range 断点续传）
  3. 校验 SHA256（从 chunk metadata 获取）
  4. 校验 cosign 签名（.sig 文件从 TOS 同路径获取）
```

**为什么不能用 HawkBit 本地文件系统**:
- 多实例 HA：Node A 磁盘上的文件 Node B 访问不到
- K8s 重启：Pod 漂移后本地磁盘丢失
- 大文件性能：SWUpdate .swu 可能 2-4GB，本地磁盘 IO 是瓶颈
- 分发效率：TOS + CDN 边缘节点加速，10,000 辆车不会打爆单点

**注意**: HawkBit DDI 协议中 `deployment.download` URL 是完全可配置的，不需要 HawkBit 自己托管二进制。
这与 Docker 模式一致——HawkBit 从来不管 Docker 镜像的二进制存储（那是 Harbor 的事）。

**为什么需要自定义平台而非直接用现有工具**:
- HawkBit 无法回答「VIN-XYZ 的 LiDAR 是什么型号，该用哪个标定版本」
- Harbor 无法回答「相机标定 v1.3 需要感知镜像 >= v2.1」
- 没有任何开源工具同时解决「硬件清单 + 兼容矩阵 + 漂移检测」
- 10,000+ 辆车、不同传感器供应商、不同 MCU → 必须有一个统一目录

**平台位置**: `autodrive/zota-repo/`，详见 [zota-repo/README.md](../../../../zota-repo/README.md)

## 生产级系统全景

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Cloud / K8s (Production)                         │
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ HawkBit-0│ │ HawkBit-1│ │ HawkBit-N│ │ Vault    │ │ hawkbit-    │ │
│  │ DDI+MGMT │ │          │ │          │ │ PKI (HA) │ │ updater-ui  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┘ └─────────────┘ │
│       └──────┬──────┴───────────┘                                       │
│              ▼                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐                    │
│  │ PostgreSQL HA        │  │ MQTT Broker (Cluster)│                    │
│  │ (Patroni + etcd)     │  │ NetBird Control      │                    │
│  └──────────────────────┘  └──────────────────────┘                    │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    NetBird VPN (WireGuard, mTLS)
                                    │
┌────────────────────────────────────────────────────────────────────────┐
│                     🚗 Vehicle (Production Grade)                       │
│                                                                         │
│  aura-ota-agent (PID 1 supervisor)                                      │
│  ├─ DDI Poller (30s)    ├─ Diag Listener (MQTT sub)                    │
│  ├─ Cert Renewer (24h)  ├─ Metrics Exporter (:9090)                    │
│  └─ UpdateEngine: docker.Manager / swupdate.Manager / mcu.Manager      │
│                                                                         │
│  Docker Engine / SWUpdate (A/B) / CAN UDS / /etc/fleet/                │
└────────────────────────────────────────────────────────────────────────┘
```

## 数据流（生产级细节）

### OTA 更新流 — 完整生命周期

```
1. 工程师 → hawkbit-updater-ui
   ├─ 上传 Artifact → 创建 Software Module
   ├─ 创建 Distribution Set
   └─ 创建 Rollout（灰度 1%→5%→25%→50%→100%）

2. HawkBit → 车端 (DDI Poll)
   GET /{tenant}/controller/v1/{controllerId}
   → deploymentBase { id, deployment: { download, update, chunks } }

3. 车端 agent → 执行
   ├─ Pre-flight: 磁盘 / 车辆状态（P档） / 电池 > 50%
   ├─ 下载: 断点续传 + 进度上报
   ├─ 验证: cosign verify / PKCS#7 / SHA256
   ├─ 安装: stop→start→health (docker) / swupdate -i→reboot / UDS flash
   └─ Feedback: execution=closed, finished={success|error|none}

4. 回滚（自动触发）
   健康检查 3 次失败 → 自动回滚
   SWUpdate bootloader 检测失败 → 切回 A
   MCU 自检失败 → 切回默认 Bank

5. 灰度自动决策: 错误率 > 阈值 → 暂停 Rollout
```

### 诊断流 — 生产级

```
运维 → hawkbit-updater-ui → 诊断 API
  ├─ 命令白名单校验 + HMAC 签名
  └─ MQTT publish → zota/diag/{vin}/cmd (QoS 1)

车端 agent
  ├─ 签名验证 / 并发检查 / 频率限制
  ├─ 执行命令 (超时 30s)
  └─ MQTT publish → zota/diag/{vin}/rsp

诊断 API → 存储 → 趋势分析 → 异常告警
```

### 配置/标定更新流 — whl-conf 集成

```
1. 标定工程师 → PR to calibrations/ Git repo
   ├─ 修改 camera_params.yaml
   ├─ CI 自动校验格式 + 生成版本号 (semver)
   ├─ CI 打包: calibration_camera_v1.4.0.tar.gz
   ├─ CI 签名: cosign sign
   └─ CI 上传: POST HawkBit /rest/v1/softwaremodules (type=vehicle_calib)

2. 运维 → hawkbit-updater-ui
   ├─ 创建 Distribution Set（可合并系统镜像 + 标定）
   └─ 创建 Rollout（灰度 1%→5%→25%→100%）

3. 车端 agent (DDI Poller)
   ├─ 下载 calibration_camera_v1.4.0.tar.gz
   ├─ 校验: cosign verify + SHA256
   ├─ 解压到 /etc/vehicle/calibrations/store/camera_v1.4.0/
   └─ 上报 Feedback: DOWNLOADED

4. whl-conf 激活（关键：原子操作）
   ├─ whl-conf diff camera v1.3.0 v1.4.0 → 人工/自动确认差异
   ├─ whl-conf activate camera v1.4.0
   │     → ln -sfn store/camera_v1.4.0 active   ← 原子，无中间状态
   │     → 更新 versions.yaml
   ├─ aura 检测 symlink 变更 → 热重载参数（不重启容器）
   └─ 健康检查: sensor 频率/延迟 正常 → 确认成功

5. 回滚（自动或手动）
   ├─ 健康检查失败 → whl-conf rollback camera → 原子切回 v1.3.0
   └─ 手动: whl-conf rollback camera → 立即生效

6. 版本追溯
   ├─ whl-conf list → 所有已下载版本
   ├─ whl-conf info camera → 当前激活版本 + 历史
   └─ Dashboard → 按 VIN 查询各模块标定版本分布
```

## 模块变更

### 新增文件

| 文件 | 职责 | 生产级要点 |
|------|------|-----------|
| `aura-ota-agent/internal/updater/swupdate.go` | SWUpdate handler | 断电保护、bootloader 通信 |
| `aura-ota-agent/internal/updater/mcu.go` | MCU UDS 刷写 handler | CAN 超时、Block 重传、Bank 校验 |
| `aura-ota-agent/internal/diag/handler.go` | 诊断命令执行引擎 | 命令白名单、HMAC 验证、频率限制 |
| `aura-ota-agent/internal/diag/commands.go` | 预定义诊断命令集 | 参数枚举校验、超时控制 |
| `aura-ota-agent/internal/calib/manager.go` | 标定包下载 + whl-conf 调用 | 原子 symlink 切换、自动回滚 |
| `aura-ota-agent/internal/metrics/exporter.go` | Prometheus metrics 暴露 | :9090/metrics |
| `tools/whl-conf/` | 配置版本管理工具（Go 二进制） | list/info/diff/activate/rollback |
| `hawkbit-updater-ui/src/features/diagnostics/` | 诊断 Dashboard | 实时状态、历史趋势 |
| `hawkbit-updater-ui/src/features/calibrations/` | 标定管理页面 | 版本树、灰度进度、diff 预览 |
| `.github/workflows/calib-ci.yml` | 标定 CI/CD 流水线 | 自动打包签名上传 |
| `hawkbit-updater-ui/src/features/calibrations/` | 标定管理页面 | 版本树、灰度进度 |
| `.github/workflows/calib-ci.yml` | 标定 CI/CD 流水线 | 自动打包签名上传 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `aura-ota-agent/internal/updater/manager.go` | 三模式路由 + Pre-flight 检查 |
| `aura-ota-agent/internal/config/config.go` | 新增 Mode/Diag/Calib/Metrics/Preflight 段 |
| `aura-ota-agent/cmd/agent/main.go` | 启动 diag + calib + metrics |
| `hawkbit/hawkbit-monolith/.../application.properties` | 集群配置（RabbitMQ 启用） |
| `ota/scripts/build-sign-publish.sh` | 支持 `--type swupdate | mcu | calibration` |

## 数据模型变更

### HawkBit Software Module Types

```sql
INSERT INTO sp_software_module_type (name, key, max_assignments) VALUES
  ('SWUpdate OS Image', 'swupdate_os', 1),
  ('SWUpdate App Bundle', 'swupdate_app', 1),
  ('MCU Firmware', 'mcu_firmware', 1),
  ('Vehicle Calibration', 'vehicle_calib', 3),
  ('Vehicle Config', 'vehicle_config', 1),
  ('Diagnostic Script', 'diag_script', 1);
```

### 诊断数据库

```sql
-- UP
CREATE TABLE diag_commands (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vin VARCHAR(64) NOT NULL,
  command VARCHAR(128) NOT NULL,
  params JSON,
  signature VARCHAR(128) NOT NULL,
  status ENUM('PENDING','SENT','RUNNING','SUCCESS','FAILED','TIMEOUT','BUSY') DEFAULT 'PENDING',
  result JSON,
  created_by VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL,
  INDEX idx_vin (vin),
  INDEX idx_status (status)
);

CREATE TABLE diag_reports (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vin VARCHAR(64) NOT NULL,
  report_type VARCHAR(64) NOT NULL,
  passed BOOLEAN,
  total INT, pass_count INT, fail_count INT,
  details JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_vin_report (vin, report_type)
);

CREATE TABLE vehicle_health_snapshots (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vin VARCHAR(64) NOT NULL,
  snapshot_type VARCHAR(64) NOT NULL,
  snapshot_data JSON NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_vin_type (vin, snapshot_type)
);

-- DOWN
DROP TABLE IF EXISTS vehicle_health_snapshots;
DROP TABLE IF EXISTS diag_reports;
DROP TABLE IF EXISTS diag_commands;
```

## 生产级非功能需求

### NFR-P01: 容量与性能

| 指标 | 目标 |
|------|------|
| 并发 DDI 轮询 | 10,000 车辆 × 30s |
| Artifact 下载 | 2GB+ 断点续传 |
| DDI API P99 | < 200ms |
| 诊断命令 P95 | < 30s |
| 数据库容量 | 1,000,000+ action 记录 |

### NFR-P02: 安全基线

| 要求 | 实现 |
|------|------|
| Artifact 签名 | Docker: cosign / SWUpdate: PKCS#7 / MCU: SHA256+HMAC |
| 传输加密 | TLS 1.3 + mTLS (pki_fleet) |
| 证书生命周期 | 签发 3 年，续期 < 30 天，CRL < 24h |
| 诊断安全 | 命令白名单 + HMAC + 频率限制 |
| 审计日志 | 所有操作记录，保留 1 年 |
| Secure Boot | 量产 MUST 启用 |

### NFR-P03: 韧性矩阵

| 场景 | 行为 |
|------|------|
| 车辆离线 | 退避重试 (30→60→120→300s)，action 保留 |
| 更新中断电 | 检测不完整 → 自动恢复或回滚 |
| HawkBit 宕机 | K8s 自愈 + 其他实例接管 |
| PostgreSQL 故障 | Patroni 自动 failover < 30s |
| MQTT 宕机 | 诊断命令排队，恢复后补发 (QoS 1) |

### NFR-P04: 合规

| 标准 | 相关要求 |
|------|---------|
| ISO 21434 | 网络安全：签名、安全启动、审计 |
| GB/T 32960 | 新能源远程监控：OTA 状态上报 |
| UN R156 | 软件更新：记录可追溯、用户确认 |
| UN R155 | 网络安全：安全更新、漏洞管理 |

### ADR-010: 标定值域验证引擎 — 上传时自动校验

**方案**: 在 CI 流水线和 zota-repo API 两层实现值域验证。

```
1. CI 阶段（PR 提交时）
   parse validation_rules.yaml → 逐字段比对 data/ 中的实际值
   └─ fx=1500 ∉ [800,1200] → CI 失败 + 阻止合并

2. API 阶段（上传 HawkBit 前）
   zota-repo POST /catalog/modules/{name}/versions
   └─ 校验 validation_rules.yaml 格式合法性
   └─ 校验参数值在范围内 → VALIDATED
   └─ 否则 → REJECTED + 具体违规项
```

**值域规则语法**（YAML）:
```yaml
camera:
  fx: { min: 800, max: 1200 }
  fy: { min: 800, max: 1200 }
  cx: { min: 300, max: 700 }
  cy: { min: 200, max: 500 }
  distortion.k1: { max_abs: 0.5 }
  distortion.k2: { max_abs: 0.3 }
lidar:
  transform.translation.x: { min: -1.0, max: 1.0 }
  transform.translation.y: { min: -1.0, max: 1.0 }
  transform.translation.z: { min: -2.0, max: 2.0 }
  num_channels: { enum: [16, 32, 64, 128] }
```

### ADR-011: 灰度自动化决策 — sensor 指标驱动的推进/回滚

**方案**: 每个灰度阶段完成后，采集车辆 sensor 指标，自动化决策。

```
Stage N (e.g. 5%) 完成
  │
  ├─ 等待观察期（30min）
  │
  ├─ 采集指标（Prometheus）:
  │   ├─ camera: fps 偏差 < 10%
  │   ├─ lidar: point_cloud_density 偏差 < 5%
  │   └─ perception: detection_latency_p99 < 100ms
  │
  ├─ 全部正常 → 自动推进到 N+1 阶段
  ├─ 任一异常 → 自动暂停 Rollout + 回滚已推送车辆 + P1 告警
  └─ 超时（24h 指标未恢复）→ 标记 ROLLED_BACK
```

**不做的**: 第一期不实现全自动——运维在 HawkBit UI 人工确认推进。自动化二期根据实际运营数据调参。

### ADR-012: 合规落地路径 — ISO 21434 + GB/T 32960

**方案**: 分层合规，Phase 3 交付。

| 标准 | 具体措施 | 产出 |
|------|---------|------|
| **ISO 21434** | TARA 分析 + 安全 Case + 渗透测试 | 安全 Case 文档 |
| **GB/T 32960** | OTA 状态上报格式对齐国标 | 上报字段映射表 |
| **UN R156** | 更新记录可追溯 + 用户确认机制 | 审计日志 + UX 流程 |
| **UN R155** | SUMS 安全更新管理体系 | CSMS 合规清单 |

**ISO 21434 落地步骤**:
1. Item Definition: ZOTA OTA 系统边界 + 资产清单
2. TARA: 威胁分析（OTA 数据篡改、诊断越权、证书泄露）
3. Security Goals: 对应 NFR-P02 安全基线
4. Security Case: 论证「安全目标已满足」

## 风险 & 缓解矩阵

| 风险 | 影响 | 缓解 | 残留 |
|------|:---:|------|:---:|
| SWUpdate 安装失败变砖 | 极高 | A/B + bootloader 回退 + 灰度 | 低 |
| MCU 刷写失败 (CAN 干扰) | 中 | 3 次重试 + Block 重传 + 双 Bank | 低 |
| 诊断通道被攻击 | 极高 | mTLS + HMAC + 白名单 + 审计 | 极低 |
| 标定错误致传感器异常 | 高 | 自动回滚 + 灰度 + 自检 | 低 |
| DB 故障中断更新 | 高 | PG HA + 车端离线 resilience | 中 |
| 大量车辆同时 OTA | 中 | 灰度 + CDN + P2P (Phase 2) | 中 |
| 证书大规模到期 | 极高 | 自动续期 + 到期告警 | 极低 |
