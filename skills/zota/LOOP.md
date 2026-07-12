# LOOP.md — ZOTA 运行态

> Harness = 单次会话配置。Loop = Harness + Schedule + State + Verification。
> 本文件描述 ZOTA 体系内并发 loop 的协调规则。

## 运行的 Loop

### 车端 Loop

| Loop | 角色 | Harness | Schedule | State | 风险 |
|------|------|---------|----------|------|------|
| **ddi-poll** | DDI 轮询更新 | `ddi/poller.go` | 30s（可自适应） | HawkBit actionId + `currentImage` | L2: 会拉镜像 |
| **cert-renew** | 证书自动续期 | `bootstrap/renew.go` | 24h | `/etc/fleet/certs/device.crt` NotAfter | L1: 只读检查 |
| **health-watch** | 容器健康监测 | `health/checker.go` | 更新后触发 | 容器状态 + ROS2 topic | L1: 只读 |
| **diag-listen** | 诊断命令监听 | 新增 `diag/` | MQTT sub 常驻 | `zota/diag/{vin}/cmd` | L2: 会执行命令 |
| **calib-apply** | 标定包应用 | 新增 `calib/` | DDI 触发 | `/etc/vehicle/calibrations/versions.yaml` | L2: 会覆盖文件 |

### 云端 Loop

| Loop | 角色 | Harness | Schedule | State | 风险 |
|------|------|---------|----------|------|------|
| **hawkbit-ddi** | DDI API 响应 | HawkBit REST | 请求驱动 | Target 状态机 | L1: 无副作用 |
| **hawkbit-mgmt** | 管理 API | HawkBit REST | 请求驱动 | Distribution/ Rollout | L1: 无副作用 |
| **diag-dispatch** | 诊断命令下发 | 新增诊断平台 | 请求/定时 | MQTT Topic | L2: 会下发命令 |
| **calib-publish** | 标定 CI/CD | 新增流水线 | CI 触发 | Harbor + HawkBit SM | L1: 只写 |

## 碰撞检测

```
ddi-poll 正在 SafeSwitch    ←→ health-watch 检查同一个容器    ← 已防护（顺序执行）
ddi-poll 更新系统镜像       ←→ calib-apply 修改标定文件       ← 低风险（不同路径）
cert-renew 替换证书         ←→ ddi-poll 用旧证书 mTLS 轮询    ← 低风险（TLS 握手时选择新证书）
diag-listen 执行诊断命令    ←→ ddi-poll 正在更新容器          ← 需防护（诊断命令串行化）
```

### 碰撞优先级

| 优先级 | Loop | 规则 |
|--------|------|------|
| 1 | **ddi-poll** | 更新中不接受诊断命令（返回 BUSY） |
| 2 | **diag-listen** | 等待 ddi-poll 空闲 |
| 3 | **cert-renew** | 不影响其他 loop |
| 4 | **calib-apply** | 不影响运行中的容器 |

## Schedule 协调

```
ddi-poll:       每 30s ──────────────────────────────────
cert-renew:     每 24h ──────┬──────────────────────────
health-watch:   更新后触发 ───┴── 单次，不重叠 ──────────
diag-listen:    MQTT 常驻 ───────────────────────────────
calib-apply:    DDI 触发 ────┬── 单次，不重叠 ────────────
```

## 升级路径（L0→L3）

```
L1 — Report (当前达成)            L2 — Assisted (当前达成)
  ✅ ddi-poll: DDI 轮询正常          ✅ health-watch: 健康检查
  ✅ cert-renew: 证书续期            ⚠️ diag-listen: 未实现
  ✅ 结构化日志                       ⚠️ calib-apply: 未实现

L3 — Unattended (目标)
  ⬜ SWUpdate A/B 分区更新
  ⬜ 远程诊断命令执行
  ⬜ 标定自动下发
  ⬜ 更新失败自动回滚
```

## Intent Debt Map（没有此文档 AI 会犯的错）

| 如果不写下来 | AI 会怎么做 | 正确做法 |
|------------|-----------|---------|
| HawkBit 是唯一 OTA 服务端 | 引入第二套更新服务 | 统一走 HawkBit DDI |
| Docker 和 SWUpdate 共用 DDI | 新建不同的轮询机制 | `mode: docker|swupdate` 配置切换 |
| 诊断命令不包含任意代码 | 开放 shell 执行 | 预定义命令集，仅参数可变 |
| 标定包复用 HawkBit SM | 新建标定管理系统 | `vehicle_calib` Software Module Type |
| 产线 EOL 结果不上报云端 | 本地执行即丢弃 | 上报到诊断平台，建立车辆健康档案 |
