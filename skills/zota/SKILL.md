---
name: zota
description: 'ZOTA OTA 平台专家 — zota-server + aura-ota-agent + zota-cli 全链路架构、故障排查、演进方案。Use when: debugging OTA failures, designing new update modes (SWUpdate/RAUC), building remote diagnosis features, managing calibration versions, doing OTA code review, or planning ZOTA architecture evolution.'
---

# ZOTA — 整车 OTA + 诊断平台

## 一句话
以 zota-server 为核心，车端 aura-ota-agent + zota-cli 协同，覆盖 Docker 容器更新、A/B 分区系统更新、产线 EOL、远程诊断、标定版本管理的统一平台。

## When to Use
- 调试：OTA 更新失败、DDI 轮询异常、容器启动失败、证书过期
- 开发：修改 `aura-ota-agent/`、`zota-cli/`、`hawkbit/` 任一组件的代码
- 审查：ZOTA 相关 PR review
- 运维：车辆升级、标定下发、远程诊断
- 架构：新增更新模式（SWUpdate/RAUC）、新增诊断能力

## 变更流程

> 大改先提案，小修直接干。改 ZOTA 代码前按此流程走。

| 步骤 | 做什么 | 产物 |
|------|--------|------|
| 1. **explore** | 读 SKILL.md + 相关代码 + 现有架构文档，理解现状 | 方案思路 |
| 2. **propose** | 写清楚：改什么文件、为什么改、如何回滚 | 更新关键文件表 |
| 3. **apply** | 实现 + 验证：`make build-all && ./bin/zota-cli doctor` 确认正常 | 代码变更 |
| 4. **archive** | 沉淀：新故障模式 → FM；新约束 → 更新 references/ | 更新 references/ |

**小修免提案**（typo、日志格式、配置调优）。**大改必提案**（新增更新模式、改 DDI 协议、新增诊断通道）。

## 系统全景

```mermaid
flowchart TB
    subgraph Cloud["☁️ Cloud / K8s (Production HA)"]
        HB["zota-server Cluster<br/>:8090 DDI + MGMT"]
        HBUI["zota-web<br/>React SPA"]
        VAULT["Vault PKI (HA)<br/>pki_fleet"]
        NETBIRD["NetBird<br/>VPN Control"]
        MQTT["MQTT Broker<br/>诊断通道"]
        METRICS["Prometheus + Grafana<br/>监控告警"]
    end

    subgraph Factory["🏭 产线"]
        ZOTA_CLI_PROV["zota-cli provision<br/>签发证书 + USB 配置盘"]
        EOL["zota-cli eol<br/>EOL 电检"]
    end

    subgraph Vehicle["🚗 车辆 (Production Grade)"]
        AGENT["aura-ota-agent<br/>Pre-flight → DDI Poller → UpdateEngine"]
        DOCKER["Docker<br/>mode=docker"]
        SWUPDATE["SWUpdate<br/>mode=swupdate<br/>A/B 分区"]
        MCU["MCU CAN UDS<br/>mode=mcu<br/>双 Bank"]
        CERTS["/etc/fleet/certs/<br/>mTLS 设备证书"]
        CALIB["/etc/vehicle/calibrations/<br/>标定版本管理"]
    end

    HB -->|"DDI API (mTLS)"| AGENT
    HBUI -->|"MGMT API"| HB
    VAULT -->|"签发证书"| ZOTA_CLI_PROV
    VAULT -->|"mTLS 续期"| AGENT
    AGENT -->|"容器管理"| DOCKER
    AGENT -->|"分区更新"| SWUPDATE
    AGENT -->|"CAN 刷写"| MCU
    MQTT -->|"诊断命令 (HMAC)"| AGENT
    AGENT -->|"Metrics"| METRICS
    ZOTA_CLI_PROV -->|"USB 配置盘"| CERTS
    EOL -->|"检测报告"| AGENT
```

## 关键文件

| 文件 | 角色 | 易错点 |
|------|------|--------|
| `aura-ota-agent/cmd/agent/main.go` | Agent 入口，编排 bootstrap → DDI poll → 更新 | bootstrap token 用后必须删除 |
| `aura-ota-agent/internal/ddi/client.go` | zota-server DDI 客户端，Base Poll + Deployment | Feedback 5 次重试，超时策略 |
| `aura-ota-agent/internal/ddi/poller.go` | 轮询循环，支持 sleep 自适应 | `PollOnce` vs `Run` 两种模式 |
| `aura-ota-agent/internal/updater/manager.go` | 更新编排：pull→verify→stop→start→health | `SafeSwitch` 原子操作 |
| `aura-ota-agent/internal/docker/manager.go` | Docker CLI 封装，路径自适应 | `dockerPath()` 兼容 systemd 最小 PATH |
| `aura-ota-agent/internal/docker/cosign.go` | Cosign 签名验证 | pub key 为空时跳过验证（开发模式） |
| `aura-ota-agent/internal/health/checker.go` | 容器/Ros2 健康检查 | topic 列表空数组 = 仅检查容器 |
| `aura-ota-agent/internal/bootstrap/bootstrap.go` | 首次开机 PKI + VPN | `FLEET_CERT_DIR` env 覆盖路径 |
| `aura-ota-agent/internal/integration/integration.go` | systemd 集成 | 必须以 root 运行 |
| `zota-cli/internal/cli/update.go` | 单次 DDI 轮询升级 | 退出码 0/1/2 区分 applied/failed/noop |
| `zota-cli/internal/cli/eol.go` | EOL 命令行入口 | `--mock` 使传感器模拟通过 |
| `zota-cli/internal/eol/eol.go` | EOL 检测引擎（8 种检测） | docker_exec 格式: `"容器名:命令"` |
| `zota-cli/internal/cli/cert.go` | 证书管理（签发/查询/续期/吊销） | fleet-registry.yaml 路径 |
| `zota-cli/internal/cli/provision.go` | 产线 USB 配置盘生成 | online/offline/auto-issue 三种模式 |
| `hawkbit/hawkbit-monolith/.../application.properties` | zota-server 服务端配置 | DDI token auth + gateway token 双模式 |
| `zota-web/src/features/` | 管理 UI | Dashboard / Targets / Distributions / Rollouts |
| `ota/scripts/build-sign-publish.sh` | 镜像构建→签名→注册 zota-server | 自动创建 SM Type 和 Module |
| `zota-repo/` | 软件版本管理平台 | 版本目录、兼容矩阵、硬件清单、漂移检测 |

## 当前能力矩阵（代码实际状态 / 生产目标）

| 能力 | 状态 | 代码位置 | 生产级要点 |
|------|:---:|------|------|
| **Docker 容器 OTA** | ✅ 完成 | `aura-ota-agent/internal/docker/` | cosign 验签 + SafeSwitch + 健康检查 |
| **zota-server DDI 对接** | ✅ 完成 | `aura-ota-agent/internal/ddi/` | 5 次重试 Feedback + sleep 自适应 |
| **Cosign 签名验证** | ✅ 完成 | `aura-ota-agent/internal/docker/cosign.go` | 生产 MUST 配置 pub key |
| **健康检查** | ✅ 完成 | `aura-ota-agent/internal/health/` | 容器 + ROS2 topic + systemd |
| **PKI 证书 Bootstrap** | ✅ 完成 | `aura-ota-agent/internal/bootstrap/` | Vault 直连 + zota-server 代理双模式 |
| **证书管理 (CLI)** | ✅ 完成 | `zota-cli/internal/cli/cert.go` | 签发/查询/续期/吊销 + fleet-registry |
| **产线 USB 配置盘** | ✅ 完成 | `zota-cli/internal/cli/provision.go` | online/offline/auto-issue |
| **EOL 电检 (本地)** | ✅ 完成 | `zota-cli/internal/eol/` | 8 种检测类型 |
| **多模块管理** | ✅ 完成 | `zota-cli update --config a,b,c` | 批量单次升级 |
| **暂停/恢复/回滚** | ✅ 完成 | `zota-cli pause/resume/rollback` | 运维友好 |
| **zota-server 管理 UI** | ✅ 完成 | `zota-web/` | Dashboard/Targets/Rollouts |
| **SWUpdate A/B 分区** | ✅ 代码 | `internal/swupdate/` | 断电保护 + bootloader 3次回退 (待实车) |
| **MCU UDS 刷写** | ✅ 代码 | `internal/mcu/` | CAN 总线 + 双 Bank 保护 (待硬件) |
| **Agent 自升级** | ✅ 代码 | `internal/selfupgrade/` | 原子替换 + systemd 恢复 |
| **远程诊断平台** | ✅ 代码 | `internal/diag/` | MQTT + HMAC + 10命令白名单 (6/10 实现) |
| **Pre-flight 检查** | ✅ 完成 | `internal/preflight/` | 磁盘/电池/车辆状态/更新互斥锁 |
| **标定版本上报** | ✅ 完成 | `internal/calibration/` | DDI configData 自动上报 |
| **Prometheus Metrics** | ✅ 完成 | `internal/metrics/` | 成功率/延迟/预检失败/证书到期 |
| **zota-repo 平台** | ✅ 完成 | `zota-repo/` | 77 API + 14 UI feature + K8s manifests |
| **zota-repo UI (React)** | ✅ 完成 | `zota-repo/web/` | Ant Design 6 + React 19 + TypeScript |
| **JetLinks 集成** | ✅ 代码 | `jetlinks-community/.../zota-integration/` | DMF → 设备属性更新 |
| **K8s 部署 (ArgoCD)** | ✅ 完成 | `cicd/argocd/` | 4 Applications + sync-wave |
| **CI/CD 流水线** | ✅ 完成 | `.github/workflows/` | Agent CI + Calibration CI |
| **Grafana 监控** | ✅ 完成 | `monitoring/` | 8 面板 + 8 告警规则 + ServiceMonitor |
| **安全合规文档** | ✅ 完成 | `doc/security/` | ISO 21434 + GB/T 32960 + UN R156/R155 |
| **RAUC 支持** | 🔮 预留 | `MultiModeHandler` 接口 | 备选方案 |
| **zota-server 集群 HA** | 🔮 Phase 1 | K8s Deployment + PG HA | 3副本 (待生产集群) |
| **实车验证** | ⬜ Phase 1 | SWUpdate/UDS/CAN 端到端 | 需硬件 |

## 核心设计原则

1. **zota-server 是唯一 OTA 服务端**：DDI API 标准协议，不引入第二套更新系统
2. **车端三模式**：Docker 容器（数采车）、SWUpdate 分区（L4 智驾车）、MCU UDS 刷写（所有车型），共享同一 DDI 客户端
3. **签名不可跳过**（生产环境）：所有更新包必须签名验证（Docker: cosign / SWUpdate: PKCS#7 / MCU: SHA256+HMAC）
4. **Pre-flight 检查**：更新前 MUST 检查磁盘/车辆状态/电池/并发，任一不满足则拒绝
5. **自动回滚**：健康检查 3 次失败 → 自动回滚；SWUpdate bootloader 失败 → 切回 A 分区；MCU 自检失败 → 切回默认 Bank
6. **诊断与 OTA 联动**：诊断发现的问题可直接触发 zota-server 下发修复更新
7. **标定 = Software Module**：复用 zota-server 的版本管理、分发、灰度能力
8. **离线韧性**：车辆离线 action 不丢失，上线后按序执行；断电自动恢复或回滚
9. **Agent 常驻 + CLI 按需**：`aura-ota-agent` 后台持续轮询，`zota-cli` 按需手动操作
10. **可观测性**：Prometheus metrics + 告警 + 审计日志（满足 ISO 21434）
11. **zota-repo 只读 zota-server MGMT API**：zota-repo 不与车端直连。车辆通过 DDI configData 上报实际版本到 zota-server 属性，zota-repo 通过 MGMT API 只读查询 target attributes（实际状态）和 assigned DS（预期状态），计算漂移。车端唯一入口是 zota-server DDI。

## 配置速查

> 完整配置在 `aura-ota-agent/configs/config.example.yaml`。

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `zota.url` | `http://10.8.201.14:8090` | zota-server DDI API 地址 |
| `zota.token` | — | Target Security Token |
| `zota.gateway_token` | — | Gateway Token（可选） |
| `zota.poll_interval_seconds` | 30 | DDI 轮询间隔 |
| `docker.container_name` | `zeron` | 目标容器名 |
| `docker.cosign_pub_key` | — | Cosign 公钥路径（空=跳过验证） |
| `health.check_topics` | `[]` | ROS2 Topic 健康检查列表 |
| `health.check_services` | `[]` | ROS2 Service 健康检查列表 |
| `bootstrap.vault_url` | — | Vault PKI 地址 |
| `bootstrap.vault_pki_path` | `pki_fleet` | Vault PKI mount |

## 常用命令

```bash
# ── 车端 ──

# Agent 状态
zota-cli status --all                          # 所有模块状态表
zota-cli status --config /etc/zota-cli/configs/camera.yaml

# 单次更新
zota-cli update --config camera,lidar,planning  # 多模块批量更新
zota-cli update --config /etc/zota-cli/configs/camera.yaml

# 运维操作
zota-cli pause                                   # 暂停轮询
zota-cli resume                                  # 恢复轮询
zota-cli rollback                                # 回滚到上一版本
zota-cli doctor                                  # 全量诊断
zota-cli reload                                  # 热重载配置

# 后台运行
zota-cli run --configs-dir /etc/zota-cli/configs

# ── 产线 ──

# EOL 检测
zota-cli eol --vin TEST001 --config configs/eol.example.yaml --mock
zota-cli eol --vin MYVIN --config /etc/zota-cli/eol.yaml --json

# USB 配置盘
zota-cli provision --vin MYVIN --auto-issue
zota-cli provision --vin MYVIN --offline --cert-dir /tmp/certs

# ── 云端 ──

# zota-server 状态
curl -s -u admin:admin http://localhost:8090/rest/v1/targets | jq '.total'

# 构建发布
cd ota && bash scripts/build-sign-publish.sh 1.2.3

# Agent 部署
cd ota/ansible && ansible-playbook -i inventory/nvidia-10.10.4.112.yml playbooks/deploy-agent.yml
```

## 部署流程

### 涉及组件

| 组件 | 路径 | 部署方式 |
|------|------|---------|
| zota-server | `hawkbit/hawkbit-monolith/` | `docker compose up` 或 K8s |
| zota-web | `zota-web/` | `docker compose` 或 Nginx 静态 |
| aura-ota-agent | `aura-ota-agent/` | Ansible → 车端 |
| zota-cli | `zota-cli/` | Ansible → 车端 |
| Vault PKI | `my-infra/pki/` | K8s Helm |

### 部署顺序

```
Vault PKI ──→ zota-server ──→ zota-web
                              │
                  ┌───────────┘
                  ▼
          车端 Agent + CLI (Ansible)
```

## 参考文档

- [gap-analysis.md](references/gap-analysis.md) — L4 量产就绪全面差距分析（P0/P1/P2 + 路线图 + 风险）
- [roadmap.md](references/roadmap.md) — 量产 L4 全能力交付路线图（5 Phase + 质量门）
- [spec-done-review.md](references/spec-done-review.md) — Spec Done 自检报告（GWT 覆盖 + Non-Goals + ADR 间隙）
- [proposal.md](references/proposal.md) — ZOTA 架构演进提案（代码 vs 文档差异分析）
- [specs.md](references/specs.md) — 功能规格（OTA/诊断/标定，含 GWT 场景）
- [design.md](references/design.md) — 技术设计方案（数据流/模块变更/DB schema）
- [tasks.md](references/tasks.md) — 任务拆分（依赖图/估时/验证方式）
- [product-guide.md](references/product-guide.md) — 产品功能手册（PM/QA/培训用）
- [project-report.md](references/project-report.md) — 项目汇报（里程碑/风险/进度）
- [architecture-evolution.md](references/architecture-evolution.md) — 架构演进（ADR/DB Schema/Roadmap）
- [ux-conventions.md](references/ux-conventions.md) — UX 设计规范（页面布局/统计区/表单/颜色/状态覆盖）
- [LOOP.md](LOOP.md) — ZOTA 运行态 Loop 协调 + 碰撞检测
