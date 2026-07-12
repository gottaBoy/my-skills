# Specs: ZOTA 架构演进 (Production Grade)

> 量产车生产级别规格。用 SHALL/MUST/MUST NOT 描述可验证需求。GWT 场景覆盖正常/边界/异常/安全。

---

## 一、OTA 核心能力

### REQ-OTA-001: 三模式更新引擎
**优先级**: P0

**描述**: aura-ota-agent SHALL 支持三种更新模式，通过 `mode` 配置切换：`docker`（容器镜像）、`swupdate`（A/B 分区系统镜像）、`mcu`（MCU 固件 CAN UDS 刷写）。三种模式 MUST 共用同一 DDI 客户端和 `UpdateHandler` 接口。

**场景**:
- **Given** mode=docker, **When** HawkBit 下发镜像 tag, **Then** agent 执行 docker pull → cosign verify → SafeSwitch → health check
- **Given** mode=swupdate, **When** HawkBit 下发 .swu 文件, **Then** agent 执行 PKCS#7 验签 → swupdate -i → reboot → bootloader 验证
- **Given** mode=mcu, **When** HawkBit 下发 MCU .bin, **Then** agent 执行 CAN UDS RequestDownload → TransferData → RequestTransferExit → MCU 自校验
- **Given** 更新期间车辆断电, **When** 重新上电, **Then** agent 检测不完整状态 → 自动恢复或回滚上一版本

### REQ-OTA-002: 更新前置条件检查 (Pre-flight)
**优先级**: P0

**描述**: agent MUST 在执行任何更新前完成以下检查，任一不满足则拒绝更新并上报 `REJECTED`：

| 检查项 | 条件 | 拒绝原因 |
|--------|------|---------|
| 磁盘空间 | > Artifact 大小 × 1.5 | DISK_FULL |
| 车辆状态 | P 档 / 驻车 | VEHICLE_NOT_PARKED |
| 电池电量 | > 50% 或外接电源 | LOW_BATTERY |
| 更新中 | rec_state_ 空闲 | UPDATE_IN_PROGRESS |
| 诊断中 | diag 空闲 | DIAG_IN_PROGRESS |

### REQ-OTA-003: Software Module 类型标准化
**优先级**: P0

| Key | 名称 | 用途 | maxAssignments |
|-----|------|------|:---:|
| `aura_system` | Aura System Image | Docker 容器镜像 | 1 |
| `swupdate_os` | SWUpdate OS Image | A/B 分区系统镜像 .swu | 1 |
| `swupdate_app` | SWUpdate App Bundle | 应用层 .swu | 1 |
| `mcu_firmware` | MCU Firmware | MCU 固件 .bin/.hex | 1 |
| `vehicle_calib` | Vehicle Calibration | 标定参数包 .tar.gz | 3 |
| `vehicle_config` | Vehicle Config | 车辆配置包 | 1 |
| `diag_script` | Diagnostic Script | 诊断脚本包 | 1 |

### REQ-OTA-004: 健康检查与自动回滚
**优先级**: P0

**场景**:
- **Given** 更新完成, **When** 健康检查连续 3 次失败, **Then** agent MUST 自动回滚到上一版本
- **Given** 容器启动超时 120s, **When** 超时, **Then** agent MUST 自动回滚并上报 ERROR
- **Given** SWUpdate B 分区启动失败, **When** bootloader 检测到 3 次启动失败, **Then** bootloader MUST 自动切回 A 分区
- **Given** MCU 自检失败, **When** MCU bootloader 检测到固件校验失败, **Then** MUST 切回默认 Bank

---

## 二、远程诊断平台

### REQ-DIAG-001: 诊断命令通道
**优先级**: P0

**描述**: 系统 SHALL 建立车端↔云端双向诊断通道，生产环境 MUST 使用 mTLS 认证。

**场景**:
- **Given** 车辆在线, **When** 运维下发诊断命令, **Then** 车端 30s 内返回结果 (P95)
- **Given** 车辆离线, **When** 下发诊断命令, **Then** 命令排队，车辆上线后自动执行
- **Given** 诊断命令超时 > 30s, **Then** 平台标记 TIMEOUT 并告警
- **Given** 更新进行中, **When** 下发诊断命令, **Then** agent 返回 BUSY，拒绝执行

### REQ-DIAG-002: 诊断命令安全
**优先级**: P0

| 要求 | 实现 |
|------|------|
| 命令白名单 | MUST 仅允许 10 个预定义命令 |
| 参数校验 | MUST 仅允许特定枚举值，拒绝自由输入 |
| 签名验证 | MUST HMAC-SHA256（密钥在 bootstrap 时注入） |
| 频率限制 | MUST 同 VIN 同命令 60s 内不可重复 |
| 审计日志 | MUST 记录所有诊断操作（谁、何时、什么命令、结果） |

**异常场景**:
- **Given** 诊断命令 HMAC 签名无效, **When** agent 验证, **Then** 拒绝执行 + 记录安全事件 + 触发告警
- **Given** 同一 VIN 60s 内重复相同命令, **When** 再次下发, **Then** 返回 429 Too Many Requests
- **Given** 未授权用户下发诊断命令, **When** API 校验权限, **Then** 返回 403 Forbidden

### REQ-DIAG-003: 诊断命令集
**优先级**: P1

| 命令 | 说明 | 超时 |
|------|------|:---:|
| `diag.doctor` | 全量健康检查 | 30s |
| `diag.status` | 模块状态（镜像版本/运行状态） | 10s |
| `diag.eol` | EOL 检测（全部分组） | 60s |
| `diag.ros2_node_list` | ROS2 节点列表 | 10s |
| `diag.ros2_topic_hz` | 指定 Topic 频率 | 15s |
| `diag.disk_usage` | 磁盘使用情况 | 5s |
| `diag.systemctl` | systemd 服务状态 | 5s |
| `diag.container_logs` | Docker 容器日志 (tail 100) | 10s |
| `diag.calib_versions` | 当前标定版本 | 5s |
| `diag.trigger_update` | 触发 HawkBit 下发更新 | 30s |

### REQ-DIAG-004: 车辆健康档案
**优先级**: P2

**描述**: 系统 SHALL 为每辆车建立长期健康档案，存储历史 EOL 报告、诊断结果、版本变更记录，支持趋势分析。

---

## 三、标定版本管理 — 量产 L4 全生命周期

### 标定生命周期状态机（7 状态）

```
engineer PR → DRAFT → VALIDATED → STAGING → GRADUAL_ROLLOUT → PRODUCTION
                ↓         ↓           ↓            ↓                ↓
            REJECTED  (参数验 (兼容性检查) (1%→5%→25%→100%)    (稳定运行)
                       证通过)                sensor异常→ROLLED_BACK
```

### REQ-CALIB-001: 标定包标准格式
**优先级**: P0

| 文件 | 说明 | 必填 |
|------|------|:---:|
| `metadata.yaml` | 模块名、版本、适用车型/传感器型号、依赖版本 | ✅ |
| `checksums.sha256` | 所有文件 SHA256 | ✅ |
| `cosign.sig` | Cosign 签名 | ✅ |
| `validation_rules.yaml` | 参数值域约束（如 camera.fx ∈ [800, 1200]） | ✅ |
| `changelog.md` | 变更说明（改了哪个参数，为什么） | ✅ |
| `data/` | 标定参数文件（YAML/JSON） | ✅ |

### REQ-CALIB-002: 标定参数值域验证
**优先级**: P0

**描述**: 系统 MUST 在上传时验证标定参数是否在合理范围内。

**场景**:
- **Given** camera 标定 fx=1500, **When** validation_rules 定义 fx∈[800,1200], **Then** 拒绝上传并返回违规项
- **Given** lidar 标定缺少必填字段 transform, **When** CI 校验, **Then** PR 被阻止合并
- **Given** 标定通过验证, **When** 上传 HawkBit, **Then** 状态变为 VALIDATED

### REQ-CALIB-003: 标定依赖与兼容性
**优先级**: P0

**场景**:
- **Given** lidar_calib v3.0 依赖 perception_image≥v2.1, **When** 创建 Rollout, **Then** 检查目标车辆 perception 版本，不兼容则阻止
- **Given** camera_calib v1.3 仅适用 LiDAR LS-128, **When** 分配给 LS-64 车辆, **Then** 拒绝并提示硬件不兼容
- **Given** Rollout 创建时部分车辆不兼容, **When** 提交, **Then** 列出不兼容车辆清单，可选择跳过或取消

### REQ-CALIB-004: 灰度发布与自动回滚
**优先级**: P1

**场景**:
- **Given** 标定进入 STAGING, **When** 灰度 1%, **Then** 观察 30min → 无异常自动推进 5%→25%→50%→100%
- **Given** 5% 阶段 sensor 频率偏差>10%, **When** 检测到异常, **Then** 自动暂停 Rollout + 回滚 + 告警
- **Given** 应用后 24h sensor 指标稳定, **When** 自动检测通过, **Then** 标记 PRODUCTION

### REQ-CALIB-005: 车辆-标定绑定追溯
**优先级**: P1

**场景**:
- **Given** 查询 VIN ZSD-DP001, **When** 在 Dashboard 查询, **Then** 显示所有标定版本及变更历史
- **Given** 售后反馈 sensor 异常, **When** 查询标定版本分布, **Then** 快速定位哪些车辆在用问题版本

### REQ-CALIB-006: 标定对比 diff
**优先级**: P2

**场景**:
- **Given** v1.2 和 v1.3, **When** 执行 diff, **Then** 显示结构化参数差异（旧值→新值）

### REQ-CALIB-007: 标定安全
**优先级**: P0

- 标定包 MUST 经过 cosign 签名 + SHA256 校验
- 标定参数 MUST NOT 包含可执行代码（YAML/JSON only）
- 标定变更 MUST 有完整审计记录
- 标定回滚 MUST 保留审计记录

---

## 四、生产级非功能需求

### NFR-001: 容量
- 支持 10,000+ 车辆并发 DDI 轮询（30s 间隔）
- Artifact 下载支持 2GB+ 断点续传
- 数据库存储 1,000,000+ action 记录

### NFR-002: 性能
- DDI API 响应 P99 < 200ms
- 诊断命令响应 P95 < 30s
- HawkBit 故障恢复 < 30s（K8s 自愈）

### NFR-003: 安全
- Artifact 签名 MUST NOT 跳过（生产环境）
- 传输 MUST TLS 1.3 + mTLS
- 诊断命令 MUST 白名单 + HMAC 签名
- 审计日志 MUST 保留 1 年
- Secure Boot MUST 量产启用

### NFR-004: 韧性
- 车辆离线：action 保留，上线后自动执行
- 更新中断电：自动恢复或回滚
- HawkBit 宕机：其他实例接管（无状态）
- PostgreSQL 故障：Patroni 自动 failover < 30s

### NFR-005: 合规
- ISO 21434 网络安全
- GB/T 32960 新能源远程监控
- UN R156 软件更新法规
- UN R155 网络安全法规

### NFR-006: 可观测性
- Prometheus metrics: OTA 成功率、延迟、证书到期天数
- Alerting: OTA 成功率 < 95% → P1
- Audit: 所有更新/诊断操作全量记录

---

## 五、Non-Goals（明确不做）

| 不做的事 | 原因 | 替代方案 |
|----------|------|---------|
| 自建消息中间件 | 已有 CloudDrive MQTT | 复用 |
| 自建 VPN | NetBird 已满足 | — |
| 自建 CA | Vault PKI 已部署 | — |
| 自建容器 Registry | Harbor 已运行 | — |
| 车辆远程控制（控车） | 安全关键，独立系统 | 不在 OTA 范围 |
| 地图/高精定位更新 | 独立数据管道 | 数据闭环 |
| Android/iOS App | Web Dashboard 满足需求 | hawkbit-updater-ui + zota-repo-ui |
| AI 模型训练/部署 | ML Pipeline 独立 | 数据闭环 + 训练平台 |

---

## 六、软件版本管理平台 — zota-repo

> zota-repo 是 ZOTA 生态的版本管理平台，填补 zota-server（部署期望）与 Harbor（二进制存储）之间的空白。
> 核心职责：版本目录、兼容矩阵、硬件清单、漂移检测。不与车端直连——车端唯一入口是 zota-server DDI。

### 标定版本生命周期状态机（5 状态）

```
dev → staging → validation → production
  ↓        ↓         ↓           ↓
  └────────┴─────────┴───→ revoked
```

### REQ-REPO-001: 版本目录 (Catalog)
**优先级**: P0

**描述**: zota-repo SHALL 提供软件模块和版本的 CRUD API，支持 `container`、`firmware`、`calibration`、`config` 四种模块类型。版本 MUST 关联 artifact 元数据（URL、SHA256、构建信息）。

**场景**:
- **Given** CI 构建完成, **When** POST `/api/v1/catalog/modules/{module}/versions`, **Then** 版本记录创建，状态为 `dev`
- **Given** 模块不存在, **When** 创建版本, **Then** 返回 404 并提示先创建模块
- **Given** 同模块同版本重复创建, **When** POST, **Then** 返回 409 Conflict
- **Given** 版本状态从 `dev` 提升, **When** POST promote, **Then** 按 `dev→staging→validation→production` 顺序推进，跳级拒绝

### REQ-REPO-002: 兼容性矩阵 (Compatibility Matrix)
**优先级**: P0

**描述**: zota-repo SHALL 管理模块间版本依赖规则。SHALL 支持 `Check(v1, v2)` 查询两个版本是否兼容。

**场景**:
- **Given** camera_calib >=1.2.0 依赖 perception_image>=2.1.0, **When** 创建兼容规则, **Then** 系统存储依赖关系
- **Given** 查询 camera_calib@1.3.0 与 perception_image@2.0.0 兼容性, **When** GET `/compatibility/check`, **Then** 返回 incompatible + 原因
- **Given** 删除模块, **When** 该模块有关联兼容规则, **Then** 级联删除规则或阻止删除并提示

### REQ-REPO-003: 车辆硬件清单 (Inventory)
**优先级**: P0

**描述**: zota-repo SHALL 管理车辆硬件配置（传感器型号、MCU 类型等），支持按 VIN 查询和注册。

**场景**:
- **Given** 产线下线新车, **When** POST `/api/v1/inventory/vehicles` 注册 VIN + 硬件配置, **Then** 返回 201 Created
- **Given** VIN 已存在, **When** 再次注册, **Then** 更新硬件配置（upsert）
- **Given** 查询 VIN-ZSD, **When** GET `/api/v1/inventory/vehicles/ZSD`, **Then** 返回完整硬件 profile（JSON）

### REQ-REPO-004: 漂移检测 (Reconciliation)
**优先级**: P1

**描述**: zota-repo SHALL 通过 zota-server MGMT API（只读）获取车辆实际版本（target attributes）和期望版本（assigned DS），计算漂移状态。车辆通过 DDI configData 上报实际版本到 zota-server，zota-repo 不与车端直连。

**场景**:
- **Given** VIN-XYZ 实际 camera_calib=1.0.0, 期望=1.1.0, **When** 同步完成, **Then** 标记 `is_drifted=true`
- **Given** 车辆所有模块版本匹配, **When** 同步完成, **Then** `is_drifted=false`
- **Given** 车辆有模块不在 zota-repo 注册表中, **When** 同步, **Then** 保留实际版本但 expected_version 为空
- **Given** zota-server 不可达, **When** 触发同步, **Then** 返回 502 并保留上一次同步状态

### REQ-REPO-005: Release Bundle
**优先级**: P1

**描述**: zota-repo SHALL 支持将多个模块版本打包为 Release Bundle，生命周期：`draft→validated→released→revoked`。

**场景**:
- **Given** 创建 Bundle "2026-Q3-L4" 包含 camera_calib@1.2.0 + perception@2.4.1, **When** POST, **Then** Bundle 状态为 `draft`
- **Given** Bundle 内版本通过兼容性检查, **When** PUT status=validated, **Then** 状态变更
- **Given** Bundle 内版本存在冲突, **When** 验证, **Then** 拒绝并列出冲突项

### REQ-REPO-006: 文件管理系统 (FileStore)
**优先级**: P1

**描述**: zota-repo SHALL 提供独立的版本化文件管理，支持 Local 和 TOS（S3 兼容）双后端。支持目录浏览、上传/下载、移动、删除和 ZIP 批量导入。

**场景**:
- **Given** 上传标定文件 calibration.tar.gz, **When** POST `/api/v1/files`, **Then** 文件存储并创建版本记录
- **Given** 同路径文件再次上传, **When** POST, **Then** 创建新版本（version++），保留历史
- **Given** 删除目录 `meta/extrinsic`, **When** DELETE `/api/v1/files/dir?path=meta/extrinsic`, **Then** 目录及内容全部删除
- **Given** 上传 ZIP 包含 100 个文件, **When** POST `/api/v1/files/upload-zip`, **Then** 流式解压并逐个创建版本（不 OOM）

### REQ-REPO-007: API 认证与安全
**优先级**: P0

**描述**: zota-repo API MUST 要求认证。生产环境 MUST 验证 Authorization header（Bearer token 或 API Key）。开发环境可配置跳过。

**场景**:
- **Given** 未携带 Authorization header, **When** 访问任意 API（除 /health）, **Then** 返回 401 Unauthorized
- **Given** token 无效或过期, **When** 访问 API, **Then** 返回 403 Forbidden
- **Given** GET /health, **When** 无认证访问, **Then** 返回 200（健康检查豁免认证）

### REQ-REPO-008: 分页与性能
**优先级**: P1

**描述**: 所有列表类 API MUST 支持分页（`?page=1&limit=20`），默认 limit=20，最大 limit=100。List 响应 MUST 包含 `total`、`page`、`limit` 元数据。

**场景**:
- **Given** 10,000 个模块, **When** GET `/api/v1/catalog/modules?page=1&limit=20`, **Then** 返回 20 条 + total=10000
- **Given** 请求 limit=500, **When** 超过最大限制, **Then** 自动截断为 limit=100
- **Given** 不传分页参数, **When** GET list API, **Then** 默认 page=1, limit=20

### REQ-REPO-009: Artifact 上传下载
**优先级**: P1

**描述**: zota-repo SHALL 支持 artifact 上传（含相对路径子目录）、下载（含 Range 断点续传）、列表、删除。上传限制 512MB。

**场景**:
- **Given** 上传 camera_calib@1.2.0 的标定文件到 `meta/extrinsic/cam.json`, **When** POST multipart, **Then** 文件存储到 `{base}/camera_calib/1.2.0/meta/extrinsic/cam.json`
- **Given** 下载 500MB artifact, **When** GET 携带 `Range: bytes=100000000-`, **Then** 返回 206 Partial Content
- **Given** 删除单个 artifact 文件, **When** DELETE, **Then** 同时清理磁盘文件和 DB 记录（事务性）

### Non-Goals（zota-repo 不做）
| 不做的事 | 原因 |
|----------|------|
| 直接与车端通信 | 车端唯一入口是 zota-server DDI |
| 替代 zota-server 分发 | zota-server 管分发，zota-repo 管版本元数据 |
| 替代 Harbor 存储 | Harbor 存二进制，zota-repo 存 metadata 关联 |
| CVE 扫描 | 由 Dependency Track 负责（Phase 2 webhook 集成） |
