# ZOTA 平台 — L4 量产就绪全面差距分析

> 分析日期：2026-07-12 | 基于代码实际状态 + roadmap + specs + spec-done-review 综合评估

## 总体状态

```
████████████████████░░░░  80% 完成
```

| 域 | 完成度 | 剩余工作 |
|---|:---:|---|
| 车端 OTA 引擎 | 85% | SWUpdate/MCU 实车验证 |
| 远程诊断 | 60% | 4/10 命令 + Dashboard |
| 标定管理 | 70% | 值域验证引擎 + CI/CD + 灰度 |
| 云端基础设施 | 75% | HawkBit HA + TOS 存储 |
| 版本管理 (zota-repo) | 95% | 差分包 + 合规提醒 |
| 安全与合规 | 80% | Secure Boot + 外部审计 |
| CI/CD | 50% | 标定 CI + 兼容性 CI |
| 可观测性 | 90% | 已搭建，生产环境调优 |

---

## 一、P0 — 生产阻断项（不完成无法 L4 量产）

### 1.1 SWUpdate A/B 分区更新 — 实车验证

| 项 | 状态 |
|---|:---:|
| 代码 | ✅ `internal/swupdate/` 已实现 |
| 单元测试 | ❌ |
| 实车端到端验证 | ❌ **阻塞项** |
| 前置条件 | Yocto/Buildroot 构建链就绪 |

**需验证场景**：
- 下发 .swu → PKCS#7 验签 → `swupdate -i` → 重启 → bootloader 验证
- B 分区 3 次启动失败 → 自动切回 A 分区
- 断电保护：更新中途断电 → 重启自动恢复

### 1.2 MCU CAN UDS 刷写 — 实车验证

| 项 | 状态 |
|---|:---:|
| 代码 | ✅ `internal/mcu/uds.go` 已实现 |
| CAN 硬件 | ⚠️ 不同 MCU 厂商 UDS 实现差异 |
| 实车验证 | ❌ **阻塞项** |

**风险**：不同 MCU（NXP、Infineon、TI）UDS 协议有差异，调试周期可能远超 4d 估时。

### 1.3 HawkBit 生产化 HA 部署

| 项 | 状态 |
|---|:---:|
| K8s Deployment 3 副本 | ❌ 当前单实例 docker-compose |
| PostgreSQL HA (Patroni+etcd) | ❌ |
| RabbitMQ 集群 | ❌ |
| Gateway Token 认证 | ⚠️ 代码支持，未生产验证 |

**关键数字**：10,000 车 × 30s DDI 轮询 = ~333 req/s，单实例不可承受。

### 1.4 标定值域验证引擎

| 项 | 状态 |
|---|:---:|
| `validation_rules.yaml` 解析 | ❌ 未实现 |
| 上传时自动校验 | ❌ |
| CI 集成（PR 阻止合并不合规标定） | ❌ |

**场景**：`camera.fx ∈ [800,1200]`，上传 fx=1500 → **REJECTED**。

---

## 二、P1 — 高优先级（影响售后运维效率）

### 2.1 远程诊断 — 完成剩余 4 个命令

当前实现：**6/10 命令**。

| 命令 | 状态 | 说明 |
|------|:---:|------|
| `diag.doctor` | ✅ | |
| `diag.status` | ✅ | |
| `diag.eol` | ✅ | |
| `diag.systemctl` | ✅ | |
| `diag.container_logs` | ✅ | |
| `diag.trigger_update` | ✅ | |
| `diag.ros2_node_list` | ❌ | 需补 |
| `diag.ros2_topic_hz` | ❌ | 需补 |
| `diag.disk_usage` | ❌ | 需补 |
| `diag.calib_versions` | ❌ | 需补 |

**此外需完成**：诊断 Dashboard（前端选择 VIN → 一键诊断 → 实时结果 + 历史）。

### 2.2 标定 CI/CD 流水线

| 项 | 状态 |
|---|:---:|
| PR → 打包 → 签名 → 上传 HawkBit | ❌ |
| 兼容性检查 CI 步骤 | ❌ |
| `--type calibration` 构建发布脚本 | ❌ |

当前 `.github/workflows/ci.yml` 仅覆盖 Agent 基础 CI，缺少标定专项流水线。

### 2.3 标定灰度自动推进

| 项 | 状态 |
|---|:---:|
| 1%→5%→25%→100% 自动推进 | ❌ |
| sensor 指标异常自动暂停+回滚 | ❌ |
| 依赖 Prometheus + 数据闭环 sensor 指标 | 🔴 外部依赖 |

---

## 三、P2 — 中优先级（安全合规 + 运维增强）

### 3.1 UEFI Secure Boot 量产启用

| 项 | 状态 |
|---|:---:|
| Secure Boot 配置 | ❌ 需在量产镜像中启用 |
| 未签名内核拒绝启动 | ❌ |

当前开发环境未启用，量产 MUST 打开。

### 3.2 端到端安全链验证

需要从底层到应用层逐层验证：

```
UEFI Secure Boot → mTLS (DDI) → cosign/SWUpdate PKCS#7 签名 → 运行时校验
```

每层都要测试"错误场景"：未签名内核拒绝、错误证书拒绝、错误签名拒绝。

### 3.3 ISO 21434 + GB/T 32960 合规文档

| 标准 | 状态 | 产出 |
|------|:---:|------|
| ISO 21434 网络安全 | ⚠️ 清单已有，缺外部审计 | 安全 Case |
| GB/T 32960 OTA 上报 | ❌ | OTA 状态上报格式 |
| UN R156 软件更新 | ⚠️ 部分满足（审计日志） | 追溯记录 |
| UN R155 网络安全 | ❌ | CSMS 认证 |

### 3.4 离线韧性测试

| 场景 | 状态 |
|------|:---:|
| 断网 7 天 → action 保留 → 上线按序执行 | ❌ 未测试 |
| 更新中断电 → 自动恢复或回滚 | ❌ 未测试 |
| PostgreSQL 主库宕机 → Patroni failover | ❌ 依赖 Phase 0 HA |

### 3.5 zota-repo 差分包 + 合规提醒

| 项 | 状态 |
|---|:---:|
| 差分包生成管道 | ❌ |
| 合规认证到期自动提醒 | ❌ |
| 门禁 Webhook 触发 | ❌ |
| 升级路径可视化 DAG | ❌ |

---

## 四、已完成项 ✅

| 域 | 项目 | 验证状态 |
|---|------|:---:|
| OTA | Docker 容器更新（cosign + SafeSwitch + 健康检查） | ✅ 生产就绪 |
| OTA | HawkBit DDI 对接（5 次重试 + sleep 自适应） | ✅ 生产就绪 |
| OTA | Pre-flight 检查（磁盘/状态/电池/并发） | ✅ 完成 |
| OTA | 多模块管理 + 暂停/恢复/回滚 | ✅ 完成 |
| PKI | Vault Bootstrap + 证书管理 CLI | ✅ 完成 |
| 产线 | EOL 电检（8 种检测） | ✅ 完成 |
| 产线 | USB 配置盘（online/offline/auto-issue） | ✅ 完成 |
| 云端 | zota-repo 版本管理平台（92 API + 16 页面） | ✅ 完成 |
| 云端 | zota-repo-web React UI（StatCards + 中文标签） | ✅ 完成 |
| 云端 | K8s ArgoCD 部署 | ✅ 完成 |
| 可观测 | Prometheus + Grafana（8 面板 + 8 告警规则） | ✅ 完成 |
| 安全 | Cosign 签名验证 + HMAC 诊断安全 | ✅ 完成 |

---

## 五、路线图与估时

```
Phase 0 (2w)    Phase 1 (3w)     Phase 2 (4w)     Phase 3 (2w)
基础设施         OTA 增强          诊断+标定         生产加固
────────        ────────          ────────         ────────
HawkBit HA      SWUpdate 实车      诊断 4 命令补全    Secure Boot
TOS 存储        MCU 实车           标定 CI/CD       韧性测试
                标定值域验证        灰度自动化       合规文档
                诊断 Dashboard
```

**总估时**：~53 天（约 11 周），部分可并行。

### 关键风险

| 风险 | 严重度 | 说明 |
|------|:---:|------|
| 🔴 SWUpdate 工具链未就绪 | 阻塞 | Yocto/Buildroot 构建链需确认，否则 Phase 1 无法启动 |
| 🔴 标定灰度自动回滚 | 依赖 | 需要 Prometheus + 数据闭环 sensor 指标接入 |
| 🟡 MCU UDS 厂商差异 | 延期 | 不同 MCU 厂商调试周期可能远超估时 |
| 🟡 ISO 21434 外部审计 | 延期 | 审计机构排期不可控 |
| 🟢 HawkBit HA | 可控 | K8s 部署属纯云端操作，不依赖车端 |

### 建议执行策略

1. **立即启动 Phase 0**（零车端依赖）：HawkBit HA + TOS 存储，2 周内可完成
2. **Phase 1 前提**：先确认 Yocto 构建链就绪 → 再做 SWUpdate 实车；MCU 需确认 CAN 硬件
3. **Phase 2 诊断**：剩余 4 个命令可快速补齐（ros2 命令已有 ROS2 封装），Dashboard 依赖前端开发
4. **Phase 3**：合规文档可与开发并行进行，Secure Boot 需与系统镜像团队协调
