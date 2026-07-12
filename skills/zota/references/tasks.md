# Tasks: ZOTA 架构演进 — 完整开发计划

> 基于生产级设计（design.md v3），分 4 个 Phase，可独立交付，不阻塞现有数采车 Docker OTA。

## 总体依赖图

```
Phase 0: 基础设施（2 周）
Task 0.1 (HawkBit HA) ──→ Task 0.3 (TOS Artifact)
Task 0.2 (zota-repo) ──→ Task 0.4 (CI 流水线适配)

Phase 1: OTA 增强（4 周）—— 依赖 Phase 0
Task 1.1 (SWUpdate) ──┬──→ Task 1.3 (Pre-flight)
Task 1.2 (MCU UDS)  ──┘      Task 1.4 (集成测试)

Phase 2: 诊断 + 标定（4 周）—— 可并行于 Phase 1
Task 2.1 (诊断通道) ──→ Task 2.2 (命令引擎) ──→ Task 2.3 (Dashboard)
Task 2.4 (whl-conf)  ──→ Task 2.5 (标定 CI/CD) ──→ Task 2.6 (标定应用)

Phase 3: 生产加固（3 周）—— 依赖 Phase 1+2
Task 3.1 (Metrics)  Task 3.2 (安全链)  Task 3.3 (离线韧性)  Task 3.4 (合规审计)

Phase 4: 高级特性（按需）
Task 4.1 (RAUC)  Task 4.2 (Uptane)  Task 4.3 (Dependency Track)
```

---

## Phase 0: 基础设施（2 周）

### Task 0.1: HawkBit 生产化部署 (3d)
- **文件**: `my-infra/platform/hawkbit/`, `application.properties`
- **变更**: K8s Deployment 3 副本 + Ingress + PostgreSQL HA (Patroni + etcd) + 启用 RabbitMQ + Gateway Token 认证
- **验证**: `kubectl get pods -l app=hawkbit` → 3/3 Running；模拟主库宕机 → 30s 内自动切换
- **依赖**: 无

### Task 0.2: zota-repo 平台搭建 (4d)
- **文件**: `zota-repo/`（新 Go 项目）
- **变更**: 版本目录 CRUD API + 兼容性矩阵 API + 车辆硬件清单 API + HawkBit 只读集成 + 前端 Dashboard 骨架
- **验证**: `go build && POST /catalog/modules/camera_calib/versions` → 200
- **依赖**: 无（可与 0.1 并行）

### Task 0.3: TOS Artifact 存储适配 (2d)
- **文件**: `ota/scripts/register-artifact.sh`（新）, `aura-ota-agent/internal/updater/downloader.go`
- **变更**: TOS Bucket 创建 + HawkBit artifact URL 注册脚本 + 车端 agent TOS 下载（HTTP Range 断点续传）
- **验证**: 上传 TOS → 注册 HawkBit → DDI 返回正确 download URL
- **依赖**: Task 0.1

### Task 0.4: CI 流水线适配 (2d)
- **文件**: `ota/scripts/build-sign-publish.sh`
- **变更**: 扩展 `--type mcu|calibration|config` + TOS 上传 + cosign 签名 + HawkBit 注册 + zota-repo 注册
- **验证**: CI 一键完成 上传→签名→注册；`GET /catalog` 可见新版本
- **依赖**: Task 0.3

---

## Phase 1: OTA 增强（4 周）

### Task 1.1: SWUpdate Handler (4d)
- **文件**: `updater/swupdate.go`（新）, `updater/handler.go`（重构）, `config/config.go`
- **变更**: UpdateHandler 统一接口 + SWUpdate 下载/验签/安装 + Bootloader 通信 + A/B 自动回退
- **验证**: `swupdate -i test.swu` → 重启 → 新版本；B 分区启动失败 3 次 → 切回 A
- **依赖**: Phase 0

### Task 1.2: MCU UDS Handler (4d)
- **文件**: `updater/mcu.go`（新）, `config/config.go`
- **变更**: CAN UDS 客户端（0x34/36/37）+ Block 重传 + MCU 双 Bank 校验 + `mode: mcu` 配置
- **验证**: CAN 抓包确认 UDS 序列；模拟 CAN 丢包 → 自动重传；刷写失败 → 从默认 Bank 启动
- **依赖**: Phase 0

### Task 1.3: Pre-flight 检查 (2d)
- **文件**: `updater/preflight.go`（新）
- **变更**: 磁盘/车辆状态（P档）/电池电量/并发检查 → 任一不满足则 REJECTED
- **验证**: 磁盘不足 → REJECTED；行驶中 → REJECTED；电量 < 50% → REJECTED
- **依赖**: Task 1.1, 1.2

### Task 1.4: 集成测试 (3d)
- **验证**: SWUpdate 端到端（下发→安装→重启→验证→回滚）+ MCU 端到端 + 断电恢复 + UI 适配
- **依赖**: Task 1.1-1.3

---

## Phase 2: 诊断 + 标定（4 周，可与 Phase 1 并行）

### Task 2.1: 诊断通道 MQTT + mTLS (3d)
- **文件**: `diag/handler.go`（新）, `diag/signature.go`（新）
- **变更**: MQTT 诊断 Topic 订阅/发布 + mTLS（pki_fleet）+ HMAC 签名 + 命令队列 QoS 1
- **验证**: `mosquitto_sub -t zota/diag/+/rsp` 收到响应；错误证书 → 连接拒绝
- **依赖**: 无

### Task 2.2: 诊断命令引擎 (3d)
- **文件**: `diag/commands.go`（新）
- **变更**: 10 个预定义命令 + 参数枚举校验 + 频率限制 60s + 超时 30s
- **验证**: 每个命令单独测试；非法参数 → 拒绝；超时 → TIMEOUT
- **依赖**: Task 2.1

### Task 2.3: 诊断 Dashboard (4d)
- **文件**: `hawkbit-updater-ui/src/features/diagnostics/`
- **变更**: 车辆选择→命令下发→结果展示→历史记录 + OTA 联动
- **验证**: `npm run build` + 选择 VIN → 下发命令 → 查看结果
- **依赖**: Task 2.2

### Task 2.4: whl-conf 车端工具 (3d)
- **文件**: `tools/whl-conf/`（新 Go 项目）
- **变更**: list/info/diff/activate（ln -sfn）/rollback 命令 + 原子 symlink 切换
- **验证**: `whl-conf activate v1.3` → symlink 无中间状态；`whl-conf rollback` → 切回
- **依赖**: 无

### Task 2.5: 标定 CI/CD 流水线 (2d)
- **文件**: `.github/workflows/calib-ci.yml`（新）, `calibrations/` 仓库模板
- **变更**: PR → 自动打包 → 签名 → 上传 HawkBit → 注册 zota-repo + 兼容性校验
- **验证**: CI 通过后 `GET /catalog` 可见新标定版本
- **依赖**: Task 2.4

### Task 2.6: 车端标定应用 (2d)
- **文件**: `calib/manager.go`（新）
- **变更**: DDI 下载标定包→ whl-conf activate → 自动回滚（sensor 异常检测）→ 版本上报 zota-repo
- **验证**: 标定激活 → sensor 参数生效；sensor 异常 → 自动回滚
- **依赖**: Task 2.4, 2.5

---

## Phase 3: 生产加固（3 周）

### Task 3.1: Prometheus Metrics + Grafana (3d)
- **文件**: `metrics/exporter.go`（新）, `my-infra/platform/grafana/`
- **变更**: agent metrics（:9090）+ HawkBit JMX exporter + Dashboard + Alerting Rules
- **验证**: OTA 成功率 < 95% → P1 告警；Grafana 面板正常展示
- **依赖**: Phase 0-2

### Task 3.2: 端到端安全链 (3d)
- **文件**: 运维文档 + ingress 配置 + `config/config.go`
- **变更**: UEFI Secure Boot 指导 + DDI HTTPS/mTLS 强制 + cosign pub key 强制 + SWUpdate PKCS#7 验签
- **验证**: HTTP → 301；未签名 .swu → 拒绝；cosign key 缺失 → agent 启动失败
- **依赖**: Phase 1

### Task 3.3: 离线韧性测试 (2d)
- **验证**: 离线 7 天 → 积压 action 按序执行；断电恢复；HawkBit 宕机恢复；PG failover
- **依赖**: Phase 1

### Task 3.4: 合规审计 (2d)
- **文件**: `audit/` 模块, `doc/compliance/`
- **变更**: 审计日志 + 更新记录可追溯 + ISO 21434/G.B.32960 合规清单
- **验证**: 逐项合规打勾
- **依赖**: Phase 2

---

## Phase 4: 高级特性（按需）

| Task | 内容 | 估时 | 前置 |
|------|------|:---:|------|
| 4.1 RAUC Handler | mode: rauc 支持 | 5d | Phase 1 |
| 4.2 Uptane 安全框架 | Director + Image Repo 分离 | 10d | Phase 1 |
| 4.3 Dependency Track | SBOM + CVE 扫描 | 5d | Phase 0 |
| 4.4 P2P 分发 | 车辆间 P2P 共享 Artifact | 10d | Phase 1 |
| 4.5 差分更新 | binary diff 仅下发变更 | 8d | Phase 2 |

---

## 估时汇总

| Phase | 任务数 | 核心交付 | 估时 |
|-------|:---:|------|:---:|
| Phase 0: 基础设施 | 4 | HawkBit HA + zota-repo + TOS | 11d |
| Phase 1: OTA 增强 | 4 | SWUpdate + MCU + Pre-flight | 13d |
| Phase 2: 诊断 + 标定 | 6 | 远程诊断 + whl-conf | 17d |
| Phase 3: 生产加固 | 4 | Metrics + 安全链 + 合规 | 10d |
| **合计** | **18** | | **51d (~10 周)** |

> **可并行**: Phase 1 和 Phase 2 可并行（不同模块），实际工期约 **8 周**。

## 里程碑

```
Week 1-2  ████████  Phase 0  →  HawkBit 3 副本 + zota-repo API 可用
Week 3-6  ████████████████████  Phase 1+2 并行 → SWUpdate/MCU + 远程诊断可用
Week 7-8  ████████  Phase 3  →  Grafana + 安全链 + 合规
Week 9+   ██  Phase 4 按需
```

## 风险 & 缓解

| 风险 | 缓解 |
|------|------|
| SWUpdate 工具链适配耗时长 | 优先 Docker 模式，SWUpdate 可降至 Phase 1.5 |
| CAN UDS 驱动兼容性 | 先支持 NXP/Infineon，按需扩展 |
| MQTT Broker 生产化阻力 | 复用现有 CloudDrive MQTT，仅加 Topic |
| 团队人力不足 | Phase 2 降至 5 个核心命令，Dashboard 嵌入 zota-repo |
