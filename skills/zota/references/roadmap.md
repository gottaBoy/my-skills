# ZOTA 量产 L4 全能力交付路线图

> 按量产 L4 自动驾驶车标准，从当前状态到 10,000 车全能力就绪的完整路径。

## 当前基线

```
✅ 已完成（11 项）                🔨 进行中（2 项）                ❌ 待实现（7 项）
Docker OTA                      zota-repo API + UI               SWUpdate A/B 分区
HawkBit DDI 对接               标定生命周期设计                   MCU UDS 刷写
Cosign 签名验证                                                 远程诊断平台
健康检查                                                        HawkBit 集群 HA
PKI Bootstrap + VPN                                             Prometheus Metrics
证书管理 CLI                                                    标定值域验证/灰度
产线 USB 配置盘                                                 合规审计(ISO 21434)
EOL 本地检测
多模块管理
暂停/恢复/回滚
HawkBit 管理 UI
```

## 五阶段交付计划

```
Phase 0          Phase 1           Phase 2            Phase 3          Phase 4
基础设施          OTA 增强          诊断+标定           生产加固          高级特性
(2周)            (3周)             (4周)              (2周)            (按需)
───────          ───────           ───────            ───────          ───────
HawkBit HA       SWUpdate Handler  诊断 MQTT 通道      Metrics+告警      RAUC
zota-repo 平台   MCU UDS Handler   诊断命令引擎        安全链加固        Uptane
TOS Artifact     Pre-flight 检查   诊断 Dashboard      离线韧性测试      P2P 分发
CI 流水线适配    集成测试           标定 CI/CD          合规文档         差分更新
                                    标定值域验证
                                    标定灰度回滚
                                    whl-conf 工具
```

---

## Phase 0: 基础设施 — 不动车端，云端先行（2 周）

### 交付标准
- HawkBit 3 副本 K8s 运行，10,000 车 DDI 轮询不卡
- zota-repo API + Dashboard 上线，版本目录/兼容矩阵/硬件清单可用
- TOS 作为非容器 Artifact 统一存储，CI 一键上传+注册

### Task 0.1: HawkBit 生产化部署（3d）
| 子任务 | 验证 |
|--------|------|
| K8s Deployment 3 副本 + Ingress | `kubectl get pods` 3/3 Running |
| PostgreSQL HA (Patroni+etcd) | 主库宕机 30s 自动 failover |
| RabbitMQ 集群事件同步 | 多实例 action 一致性 |
| Gateway Token 认证 | 车端不感知后端切换 |

### Task 0.2: zota-repo 平台上线（4d）
| 子任务 | 验证 |
|--------|------|
| Go 服务 K8s 部署 | `curl /health` → 200 |
| MySQL 生产库迁移（SQLite→MySQL） | 数据迁移无丢失 |
| React UI Nginx 部署 | Dashboard 4 Tab 正常渲染 |
| OpenAPI/Swagger 可访问 | `/api/docs` 正常 |

### Task 0.3: TOS Artifact 存储（2d）
| 子任务 | 验证 |
|--------|------|
| TOS Bucket + IAM 权限 | `tos cp` 上传成功 |
| HawkBit URL 注册脚本 | DDI 返回正确 TOS download URL |
| 车端 HTTP Range 下载 | 2GB 文件断点续传 |

### Task 0.4: CI 流水线适配（2d）
| 子任务 | 验证 |
|--------|------|
| `--type mcu/calibration/config` 扩展 | CI 一键完成 上传→签名→注册 |
| zota-repo 自动注册 | CI 后 `GET /catalog` 可见新版本 |
| 兼容性 CI 检查 | 不兼容版本阻止上传 |

---

## Phase 1: OTA 增强 — 三模式更新引擎（3 周）

### 交付标准
- SWUpdate A/B 分区更新可用（L4 智驾车系统镜像）
- MCU CAN UDS 刷写可用（底盘/传感器 MCU）
- Pre-flight 检查全覆盖（磁盘/状态/电池/并发）
- 数采车 Docker OTA 零回归

### Task 1.1: UpdateHandler 接口重构 + SWUpdate（4d）
| 子任务 | 文件 | 验证 |
|--------|------|------|
| `UpdateHandler` 统一接口 | `updater/handler.go` | Docker/SWUpdate/MCU 同一接口 |
| SWUpdate 下载+验签+安装 | `updater/swupdate.go` | `swupdate -i test.swu` → 重启 → 新版本 |
| Bootloader 通信 | `updater/bootloader.go` | 读取/写入 U-Boot 环境变量 |
| A/B 自动回退 | `updater/swupdate.go` | B 分区 3 次启动失败 → 切回 A |

### Task 1.2: MCU UDS Handler（4d）
| 子任务 | 文件 | 验证 |
|--------|------|------|
| CAN UDS 客户端 | `updater/mcu.go` | `candump` 确认 UDS 序列 |
| Block 重传+超时 | `updater/mcu.go` | CAN 丢包 → 自动重传 |
| 双 Bank 校验+回退 | `updater/mcu.go` | 刷写失败 → 默认 Bank 启动 |

### Task 1.3: Pre-flight 检查（2d）
| 检查项 | 条件 | 拒绝原因 |
|--------|------|---------|
| 磁盘空间 | > Artifact × 1.5 | DISK_FULL |
| 车辆状态 | P 档/驻车 | VEHICLE_NOT_PARKED |
| 电池电量 | > 50% 或外接 | LOW_BATTERY |
| 更新/诊断互斥 | `rec_state_` 空闲 | BUSY |

### Task 1.4: 集成测试 + 回归（3d）
| 测试 | 方法 |
|------|------|
| SWUpdate 端到端 | 实车：下发→安装→重启→验证→回滚 |
| MCU 端到端 | CAN 抓包 + MCU 版本读取 |
| 断电恢复 | 拔电源 → 上电 → 自动恢复 |
| Docker 回归 | 数采车 OTA 全流程不受影响 |

---

## Phase 2: 诊断 + 标定 — 售后可运维（4 周）

### 交付标准
- 远程诊断 10 个命令可用，mTLS + HMAC 安全
- 标定 7 状态生命周期完整（DRAFT→PRODUCTION）
- 标定值域验证 + 灰度发布 + 自动回滚
- whl-conf 车端原子切换可用

### Task 2.1: 诊断 MQTT 通道（3d）
| 子任务 | 文件 | 验证 |
|--------|------|------|
| MQTT Topic 订阅/发布 | `diag/handler.go` | `mosquitto_sub` 收到响应 |
| mTLS（pki_fleet 证书）| `diag/handler.go` | 错误证书 → 拒绝 |
| HMAC 签名验证 | `diag/signature.go` | 错误签名 → 拒绝 |
| QoS 1 离线队列 | `diag/handler.go` | 断网→恢复→积压命令执行 |

### Task 2.2: 诊断命令引擎（3d）
| 命令 | 超时 | 验证 |
|------|:---:|------|
| `diag.doctor` | 30s | 全量健康检查 |
| `diag.status` | 10s | 模块版本/运行状态 |
| `diag.eol` | 60s | 全部 8 种检测 |
| `diag.ros2_node_list` | 10s | 节点列表 |
| `diag.ros2_topic_hz` | 15s | 指定 Topic 频率 |
| `diag.disk_usage` | 5s | 磁盘使用 |
| `diag.systemctl` | 5s | systemd 状态 |
| `diag.container_logs` | 10s | Docker tail 100 |
| `diag.calib_versions` | 5s | 当前标定版本 |
| `diag.trigger_update` | 30s | 触发 HawkBit 下发 |

### Task 2.3: 诊断 Dashboard（4d）
| 子任务 | 文件 | 验证 |
|--------|------|------|
| 车辆选择+命令下发 | `features/diagnostics/` | 选择 VIN → 一键诊断 |
| 实时结果+历史 | 同上 | 历史诊断列表可搜索 |
| OTA 联动 | 同上 | 版本过旧 → 创建 HawkBit DS |

### Task 2.4: whl-conf 工具（3d）
| 命令 | 验证 |
|------|------|
| `whl-conf list` | 列出所有已下载版本 |
| `whl-conf diff v1.2 v1.3` | 结构化差异输出 |
| `whl-conf activate v1.3` | `ln -sfn` 原子切换 |
| `whl-conf rollback` | 切回上一版本 |

### Task 2.5: 标定值域验证 + CI/CD（3d）
| 子任务 | 文件 | 验证 |
|--------|------|------|
| `validation_rules.yaml` 解析引擎 | zota-repo API | fx=1500 越界 → REJECTED |
| 标定 CI: PR→打包→签名→上传 | `.github/workflows/calib-ci.yml` | CI 通过后 HawkBit 可见 |
| 兼容性检查 CI 步骤 | CI | 不兼容 → CI 失败 |

### Task 2.6: 标定灰度 + 自动回滚（3d）
| 子任务 | 验证 |
|--------|------|
| 灰度 Rollout 1%→5%→25%→100% | HawkBit Rollout API + sensor 指标联动 |
| sensor 异常自动暂停+回滚 | 模拟 sensor 频率偏差 >10% → 自动回滚 |
| 回滚审计记录 | 审计日志包含时间/VIN/原因 |

---

## Phase 3: 生产加固 — 10,000 车就绪（2 周）

### 交付标准
- Prometheus Metrics + Grafana 面板 + 告警规则
- 端到端安全链：Secure Boot → mTLS → 签名 → 运行时校验
- 离线韧性：断网 7 天积压不丢，断电自动恢复
- ISO 21434 + GB/T 32960 合规文档

### Task 3.1: Metrics + Grafana（3d）
| 指标 | 面板 | 告警 |
|------|------|------|
| `ota_success_rate` | 按车型/版本 | < 95% → P1 |
| `ota_duration_p95` | 时间序列 | > 600s → P2 |
| `cert_expiry_days` | 按 VIN 列表 | < 30 天 → P2 |
| `diag_command_latency` | 直方图 | P95 > 30s → P2 |
| `drift_count` | 漂移车辆数 | > 0 → P2 |
| `hawkbit_instance_up` | 实例状态 | 0 → P0 |

### Task 3.2: 端到端安全链加固（3d）
| 层次 | 验证 |
|------|------|
| UEFI Secure Boot | 未签名内核 → 拒绝启动 |
| DDI HTTPS+mTLS 强制 | HTTP → 301；错误证书 → 拒绝 |
| cosign 签名强制 | pub key 缺失 → agent 启动失败 |
| SWUpdate PKCS#7 验签 | 未签名 .swu → 拒绝安装 |
| 诊断命令白名单+HMAC | 任意命令 → 拒绝 |

### Task 3.3: 离线韧性测试（2d）
| 场景 | 验证 |
|------|------|
| 断网 7 天 | HawkBit action 保留 → 上线按序执行 |
| 更新中断电 | 重启 → 自动恢复或回滚 |
| HawkBit 宕机 | K8s 自愈 + 其他实例接管 |
| PostgreSQL 主库宕机 | Patroni 30s failover |

### Task 3.4: 合规文档（2d）
| 标准 | 产出 |
|------|------|
| ISO 21434 | 网络安全合规清单 |
| GB/T 32960 | OTA 状态上报格式 |
| UN R156 | 软件更新记录追溯 |
| 内部审计 | 所有更新/诊断操作日志 |

---

## Phase 4: 高级特性（按需启动）

| 特性 | 内容 | 估时 | 前置 |
|------|------|:---:|------|
| RAUC Handler | mode: rauc 支持 | 5d | Phase 1 |
| Uptane 安全框架 | Director + Image Repo 分离 | 10d | Phase 1 |
| Dependency Track | SBOM + CVE 扫描 | 5d | Phase 0 |
| P2P 分发 | 车辆间共享 Artifact | 10d | Phase 1 |
| 差分更新 | binary diff | 8d | Phase 2 |

---

## 总估时与里程碑

| 阶段 | 任务数 | 估时 | 里程碑交付 |
|------|:---:|:---:|------|
| Phase 0 | 4 | 11d | HawkBit 3 副本 + zota-repo 上线 + TOS 存储 |
| Phase 1 | 4 | 13d | SWUpdate + MCU 刷写 + Pre-flight |
| Phase 2 | 6 | 19d | 远程诊断 + 标定全生命周期 |
| Phase 3 | 4 | 10d | Metrics + 安全链 + 合规 |
| **合计** | **18** | **53d** | **~11 周全能力就绪** |

```
Week 1-2   ████████  Phase 0  → 基础设施可运行
Week 3-5   ██████████████  Phase 1  → 三模式 OTA 可用
Week 6-9   ████████████████████  Phase 2  → 诊断+标定可用（与 Phase 1 可部分并行）
Week 10-11 ██████████  Phase 3  → 生产加固完成
Week 12+   ██  Phase 4 按需启动
```

## 每阶段验证门（Quality Gate）

### Phase 0 出门条件
- [ ] `kubectl get pods -l app=hawkbit` 3/3 Running
- [ ] `curl zota-repo/health` → 200
- [ ] zota-repo Dashboard 4 个 Tab 可增删改查
- [ ] TOS 上传 + HawkBit 注册 + DDI 下载 全链路通

### Phase 1 出门条件
- [ ] 实车 SWUpdate 端到端：下发→安装→重启→验证→回滚
- [ ] 实车 MCU UDS 刷写 + 回退
- [ ] Pre-flight 全部 4 项检查通过（磁盘/状态/电池/并发）
- [ ] 数采车 Docker OTA 回归测试通过

### Phase 2 出门条件
- [ ] 10 个诊断命令全部可用，HMAC 签名验证通过
- [ ] 标定 DRAFT→VALIDATED→STAGING→PRODUCTION 全状态流转
- [ ] 标定值域验证（越界拒绝）
- [ ] 灰度 1%→100% 自动推进 + sensor 异常自动回滚
- [ ] whl-conf list/diff/activate/rollback 全部可用

### Phase 3 出门条件
- [ ] Grafana 6 个面板正常展示 + 告警触发
- [ ] UEFI Secure Boot + mTLS + 签名 三层安全链完整
- [ ] 断网 7 天恢复测试通过
- [ ] ISO 21434 合规清单全部打勾
