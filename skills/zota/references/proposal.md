# Proposal: ZOTA 架构演进 — 以 HawkBit 为核心的 OTA + 诊断平台

## 动机 (Motivation)

- **当前痛点**:
  1. OTA 能力分散：`aura-ota-agent` 已对接 HawkBit DDI，但仅支持 Docker 容器更新，缺少系统级（A/B 分区）和 MCU 固件更新能力
  2. 产线 EOL 检测与售后诊断脱节：`zota-cli eol` 仅在产线本地执行，售后无法远程诊断车辆故障
  3. 标定文件无版本化管理：标定参数散落各处，缺少与 CI/CD 集成的统一版本库
  4. 各子系统（PKI/OTA/EOL/标定）独立运作，缺少统一的版本目录和运维入口

- **预期收益**:
  1. HawkBit 成为统一 OTA 服务端（zota-server），同时支持 Docker 容器、A/B 分区系统镜像、MCU 固件三种更新模式
  2. 售后远程诊断平台可主动触发车辆健康检查 + 远程升级，减少现场服务成本
  3. 标定版本库 + CI/CD 集成，实现标定参数的全流程追溯和灰度发布

## 影响范围 (Impact)

- **涉及服务**: hawkbit (zota-server), aura-ota-agent, zota-cli, hawkbit-updater-ui, my-infra
- **涉及模块（新增）**: `zota-repo/`（版本管理平台）, `aura-ota-agent/internal/swupdate/`, `aura-ota-agent/internal/mcu/`, `aura-ota-agent/internal/diag/`, `tools/whl-conf/`
- **涉及数据库变更**: 是（诊断数据库 + 标定元数据库）
- **涉及 API 变更**: 是（诊断 API + 标定管理 API，DDI 协议不变）

## 约束 (Constraints)

- [x] 不改变现有 HawkBit DDI API 接口签名（车端 agent 无需改动 DDI 协议层）
- [x] 兼容现有 aura-ota-agent 的 Docker 更新流程（零回归）
- [x] 复用现有 PKI 体系（Vault pki_fleet）进行诊断通道认证
- [x] 标定管理复用 HawkBit Software Module 机制，不引入新存储系统
- [x] 不引入新的外部消息中间件（沿用现有 CloudDrive MQTT）

## 当前代码 vs 文档差异

| 文档描述 | 代码实际状态 | 差异 |
|---------|------------|------|
| `doc/pki-design.md`: "zota-server (DDI API)" | `hawkbit-monolith` 端口 8090，DDI + MGMT 双 API | ✅ 一致 |
| `doc/vehicle-init-pipeline.md`: SWUpdate A/B 分区 | `updater/` 仅 `docker.Manager` | ❌ SWUpdate 未实现 |
| `doc/specs-my/eol-design.md`: 传感器检测 | `zota-cli/internal/eol/eol.go` 8 种检测 | ✅ 一致，但仅本地 |
| `doc/specs-my/pki-design.md`: Vault PKI | `internal/bootstrap/` 已实现 | ✅ 一致 |
| 标定管理 | 无代码 | ❌ 完全缺失 |
| 远程诊断 | 无代码 | ❌ 完全缺失 |
| MCU 固件升级 | 无代码 | ❌ 完全缺失 |
