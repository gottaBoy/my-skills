# Spec Done — 自检报告

> 按 spec-generator 六项标准逐条检查 ZOTA 规格完整性。

## 1. 所有 REQ 都有 GWT 场景？⚠️ 部分缺失

| REQ | GWT 完整？ | 缺失 |
|-----|:---:|------|
| OTA-001 | ✅ | — |
| OTA-002 | ✅ | — |
| OTA-003 | n/a | 配置规范，无需 GWT |
| OTA-004 | ✅ | — |
| DIAG-001 | ✅ | — |
| DIAG-002 | ❌ | 安全表格不是 GWT 格式，缺：错误签名→拒绝、重放攻击→拒绝、越权访问→403 |
| DIAG-003 | n/a | 命令清单，无需 GWT |
| DIAG-004 | ❌ | 缺：档案查询 GWT、趋势分析触发条件 |
| CALIB-001 | n/a | 格式定义 |
| CALIB-002 | ✅ | — |
| CALIB-003 | ⚠️ | 缺：不兼容时 Rollout 创建失败的异常 GWT |
| CALIB-004 | ⚠️ | 缺：灰度期间车辆新增（新注册 VIN）的行为 |
| CALIB-005 | ✅ | — |
| CALIB-006 | ⚠️ | 缺：diff 结果为空（版本完全相同）的边界场景 |
| CALIB-007 | n/a | 安全规范 |

### 需补充的异常 GWT

```markdown
### REQ-DIAG-002 补充场景:
- **Given** 诊断命令 HMAC 签名无效, **When** agent 验证, **Then** 拒绝执行 + 记录安全事件 + 告警
- **Given** 同一 VIN 60s 内重复相同命令, **When** 再次下发, **Then** 返回 429 Too Many Requests
- **Given** 未授权用户（无诊断权限）, **When** 下发诊断命令, **Then** API 返回 403

### REQ-CALIB-003 补充:
- **Given** 标定 Rollout 创建时部分车辆不兼容, **When** 提交 Rollout, **Then** 列出不兼容车辆清单，允许跳过或取消

### REQ-CALIB-004 补充:
- **Given** 灰度期间新注册 VIN, **When** 该 VIN 匹配 Rollout 条件, **Then** 按当前灰度比例决定是否分配（如 100% 阶段则分配，25% 阶段则随机决定）
```

---

## 2. 所有 MUST/SHALL 需求可测试？✅ 基本通过

| 类别 | 可测试？ | 备注 |
|------|:---:|------|
| OTA 三模式 | ✅ | 实车测试 SWUpdate/MCU |
| Pre-flight 检查 | ✅ | 模拟 DISK_FULL/LOW_BATTERY |
| 健康检查回滚 | ✅ | 注入故障触发 |
| 诊断命令 | ✅ | MQTT 收发测试 |
| 诊断安全 | ✅ | 错误签名/重放测试 |
| 标定值域验证 | ✅ | 越界值输入→REJECTED |
| 标定灰度 | ⚠️ | 需设计自动化测试框架 |
| NFR 性能指标 | ✅ | Prometheus 可量化 |
| NFR 合规 | ⚠️ | ISO 21434 需外部审计，但内部清单可自检 |

---

## 3. design.md 覆盖所有 specs.md 决策？⚠️ 有间隙

| Specs REQ | Design ADR | 覆盖？ | 缺失 |
|-----------|-----------|:---:|------|
| OTA-001 三模式 | ADR-001 | ✅ | — |
| OTA-002 Pre-flight | ADR-001 | ⚠️ | ADR-001 提及但无 Pre-flight 专门章节 |
| OTA-003 SM Types | ADR-001 | ✅ | — |
| OTA-004 健康回滚 | ADR-001 | ✅ | — |
| DIAG-001 诊断通道 | ADR-004 | ✅ | — |
| DIAG-002 诊断安全 | ADR-004 | ✅ | — |
| CALIB-001 标定格式 | ADR-007 | ✅ | — |
| CALIB-002 值域验证 | ❌ | ❌ | 缺 ADR 覆盖值域验证引擎 |
| CALIB-004 灰度回滚 | ❌ | ❌ | 缺灰度自动化决策逻辑 ADR |
| NFR-001 容量 | ADR-002 | ✅ | — |
| NFR-003 安全 | ADR-003 | ✅ | — |
| NFR-004 韧性 | ADR-005 | ✅ | — |
| NFR-005 合规 | ❌ | ❌ | 缺合规实施 ADR |
| NFR-006 可观测性 | ADR-006 | ✅ | — |
| Artifact 存储 | ADR-009 | ✅ | — |
| zota-repo 平台 | ADR-008 | ✅ | — |

### 需补充的 ADR

**ADR-010: 标定值域验证引擎** — 上传时解析 `validation_rules.yaml`，与 `data/` 中实际值比对，不通过则 REJECT。
**ADR-011: 灰度自动化决策** — 每阶段完成后检查 sensor 指标（频率/延迟/误检率），通过自动推进，异常自动暂停+回滚。
**ADR-012: 合规落地路径** — ISO 21434 安全 Case + GB/T 32960 OTA 上报格式 + 审计日志保留策略。

---

## 4. tasks.md 有验证方式？✅ 通过

每个 Task 都标注了验证方法（实车测试 / CAN 抓包 / Prometheus 指标 / 合规清单）。

---

## 5. Non-Goals 明确列出？❌ 完全缺失

### 新增 Non-Goals 声明

以下功能**不在** ZOTA 范围内（避免 scope creep）：

| Non-Goal | 原因 | 替代方案 |
|----------|------|---------|
| 自建消息中间件 | 复用已有 MQTT Broker | CloudDrive MQTT |
| 自建 VPN | NetBird 已满足需求 | — |
| 自建 CA | Vault PKI 已部署 | — |
| 自建容器 Registry | Harbor 已运行 | — |
| 实时视频推流 | 不属于 OTA/诊断范畴 | 已有独立方案 |
| 车辆远程控制（控车） | 安全关键，独立系统 | 不在 OTA 范围 |
| 地图/高精定位更新 | 独立数据管道 | 数据闭环系统 |
| Android/iOS App | Web Dashboard 已满足 | hawkbit-updater-ui + zota-repo-ui |
| 第三方车辆集成 | 仅支持自有车型 | — |
| AI 模型训练/部署 | ML Pipeline 独立 | 数据闭环 + 训练平台 |

---

## 6. 人工确认 "这个规划值得执行"？

### 风险提示

| 风险 | 严重度 | 说明 |
|------|:---:|------|
| SWUpdate 工具链 | 🟡 | 如果 Yocto/Buildroot 构建链尚未就绪，SWUpdate Handler 需要等 |
| CAN UDS 驱动 | 🟡 | 不同 MCU 厂商的 UDS 实现有差异，调试周期可能超过 4d |
| MQTT Broker 生产化 | 🟢 | 已有 CloudDrive MQTT，仅加 Topic |
| 标定灰度自动化 | 🔴 | 依赖 sensor 监控指标接入，这是另一个系统（Prometheus + 数据闭环） |

### 推荐执行策略

1. **Phase 0 立即启动**（零车端依赖，纯云端）
2. **Phase 1 SWUpdate 部分** — 先确认 Yocto 构建链就绪，否则先做 MCU（CAN 硬件已就绪）
3. **Phase 2 诊断** — 先做 5 个核心命令（doctor/status/eol/systemctl/trigger_update），其余后续迭代
4. **Phase 2 标定灰度** — 第一期手动灰度（运维在 HawkBit UI 操作），自动化二期做

---

## 总结：需补充的工作

| 优先级 | 动作 | 文件 |
|:---:|------|------|
| P0 | 补充 DIAG-002 安全 GWT 场景 | `specs.md` |
| P0 | 添加 Non-Goals 章节 | `specs.md` 或 `design.md` |
| P0 | 新增 ADR-010（值域验证） | `design.md` |
| P1 | 新增 ADR-011（灰度自动化） | `design.md` |
| P1 | 新增 ADR-012（合规落地） | `design.md` |
| P2 | 补充 CALIB-003/004/006 边界 GWT | `specs.md` |
| P2 | 补充 DIAG-004 档案查询 GWT | `specs.md` |
