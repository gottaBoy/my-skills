# SCM 到 War Room 的开源研发、交付与无人值守运营蓝图

> 状态：方案分析与落地蓝图  
> 日期：2026-08-08  
> 适用范围：ZOTA 相关云端服务、仓库服务、Web 前端、边缘节点、车端/ECU、Yocto 镜像、智驾软件与模型  
> 关联文档：`ops-automation-toolchain.md`

## 1. 文档目标

本文单独分析以下端到端能力是否存在可直接采用的开源实现，以及 ZOTA 后续应如何组合、二开和分阶段落地：

```text
SCM / GitLab
  -> CI / Jenkins / GitLab Runner
  -> Yocto 交叉编译
  -> 自动化测试 / 板卡测试 / 仿真平台
  -> Artifact 仓库
  -> Argo CD / ZOTA 发布
  -> 日志、指标、链路和车辆数据采集
  -> 分析、报告和工单
  -> 告警、值班和无人值守处置
  -> War Room 协同
  -> 复盘、知识沉淀和改进 PR
```

术语说明：

- `SCM` 是源代码管理能力，GitLab 是 SCM 和 DevSecOps 平台的一种实现。
- `Artifact` 指构建制品，不仅是容器镜像，还包括 Yocto 镜像、软件包、固件、模型、地图、标定、SBOM、签名和测试证据。
- `Yocto` 是嵌入式 Linux 构建体系，本文将用户描述中的 `yotoc` 按 `Yocto` 理解。
- `War Room` 是重大事件的协同空间，不等同于告警平台、工单系统或聊天室。

## 2. 核心结论

### 2.1 没有成熟的单体开源产品覆盖完整链路

目前不存在一个成熟开源项目，可以同时可靠覆盖：

- 代码托管和评审。
- 云端、嵌入式和智驾多类型构建。
- Yocto 缓存和异构构建集群。
- 软件在环、硬件在环和场景仿真。
- 制品、供应链证据和 OTA 发布。
- 日志、指标、链路、车辆遥测和大文件。
- 告警关联、值班升级、工单、War Room 和自动处置。
- AI 调查、报告、决策辅助和受控自治。

合理方案是构建一个**可组合平台**：

1. 成熟开源项目承担标准能力。
2. GitLab、Backstage 和 ZOTA 提供统一入口。
3. ZOTA Release Control Plane 负责车端发布和证据编排。
4. 通过统一事件模型、制品摘要和关联 ID 打通工具。
5. AI 建立在结构化数据、确定性工作流和权限审计之上。

### 2.2 推荐默认主路径

```text
开发入口
  Backstage + GitLab

代码与评审
  GitLab SCM / Merge Request

流水线
  GitLab CI + GitLab Runner
  Jenkins 仅保留给遗留任务、专用硬件或难迁移插件流程
  Argo Workflows 用于 Kubernetes 内高并发仿真、数据和批处理工作流，不作为默认 CI 入口

容器和交叉编译
  Rootless BuildKit + Buildx Kubernetes driver 负责多架构 OCI 构建
  tonistiigi/xx 辅助 Dockerfile 内 C/C++、CGo、Go、Rust 交叉编译
  Yocto SDK/eSDK 保证量产车端应用 ABI
  Kaniko 仅作为现有无 Daemon 镜像构建的迁移期候选

Yocto
  Yocto / OpenEmbedded + BitBake + kas
  独立构建池 + downloads/sstate/hash server

测试
  pytest / Robot Framework / CTest
  QEMU + Yocto testimage
  LAVA 或 labgrid 板卡农场
  CARLA / SUMO / esmini / openPASS 仿真

报告
  JUnit + Allure
  ReportPortal 用于大规模测试结果聚合和失败分析

制品
  Harbor + ORAS + Cosign
  GitLab Generic Package Registry 或 Pulp 处理通用包/软件源
  TOS/S3 兼容对象存储处理大镜像、大日志和仿真结果

云端部署
  Argo CD + Argo Rollouts

车端发布
  ZOTA Release Control Plane

可观测
  OpenTelemetry Collector + Fluent Bit
  Prometheus/VictoriaMetrics + Loki/OpenSearch + Tempo/Jaeger + Grafana

告警与事件
  Alertmanager + Keep
  GoAlert 或 OneUptime 负责值班和升级

工单
  GitLab Issue / Zammad / OpenProject

War Room
  Mattermost 或 Matrix/Element

自动化处置
  AWX / Rundeck / StackStorm
  Temporal 处理长事务和关键编排

统一门户
  Backstage + ZOTA Ops Portal
```

这套组合不是要求一次性引入全部项目。首要目标是建立稳定主链路，避免出现多个项目重复采集、重复告警、重复保存状态和相互争夺事实来源。

## 3. 总体架构

### 3.1 逻辑架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│                 Backstage / ZOTA Engineering Portal                 │
│ 服务目录 · 模板 · 文档 · 流水线 · 制品 · 发布 · 事件 · 证据 · 成本 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
             ▼                    ▼                    ▼
┌────────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
│ GitLab SCM / MR    │ │ CI Orchestrator    │ │ Policy / Evidence    │
│ Issue / Wiki       │ │ GitLab CI/Jenkins  │ │ OPA/Kyverno + ZOTA   │
└────────────────────┘ └────────────────────┘ └──────────────────────┘
             │                    │                    │
             └────────────────────┼────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Build & Verification Plane                                           │
│ Cloud Build · Yocto/kas · QEMU · Board Farm · HIL · SIL · Simulation│
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Trusted Artifact Plane                                               │
│ Harbor/OCI · Package Registry · TOS · SBOM · Signature · Provenance  │
└─────────────────────────────────────────────────────────────────────┘
                     │                              │
                     ▼                              ▼
       ┌────────────────────────┐     ┌────────────────────────────┐
       │ Argo CD / Rollouts     │     │ ZOTA Release Control Plane│
       │ 云端和边缘 K8s 服务    │     │ 车辆、ECU、模型和配置发布 │
       └────────────────────────┘     └────────────────────────────┘
                     │                              │
                     └──────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Telemetry & Operations Data Plane                                    │
│ OTel/Fluent Bit · Metrics · Logs · Traces · Vehicle Events · Evidence│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Incident Intelligence Plane                                          │
│ Rules · Correlation · AI Triage · On-call · Ticket · War Room        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Controlled Automation Plane                                          │
│ Runbook · Approval · Execution · Verification · Rollback · Audit     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 三个控制平面

不能用一个发布工具控制所有环境，建议明确三个控制平面：

| 控制平面 | 管理对象 | 推荐工具 | 关键特点 |
|---|---|---|---|
| Engineering Control Plane | 代码、流水线、测试、制品和证据 | GitLab、Backstage、Jenkins、测试平台 | 以变更和构建为中心 |
| Cloud Delivery Control Plane | Kubernetes 云端和边缘服务 | Argo CD、Argo Rollouts | 以 Git 期望状态为中心 |
| Vehicle Release Control Plane | ECU、整车、模型、地图、配置和车队 | ZOTA、Uptane/TUF 能力 | 以兼容矩阵、车辆分群和安全门禁为中心 |

Argo CD 不应直接替代 ZOTA：

- Argo CD 擅长 Kubernetes 期望状态收敛。
- 车辆可能长期离线、弱网、跨区域且版本不一致。
- 车端升级涉及 ECU 依赖、整车条件、分批策略、防回滚和恢复。
- 智驾发布还涉及模型、地图、标定、ODD 和场景证据。

ZOTA 也不应复制 Argo CD 的全部能力。云端服务仍应由 GitOps 系统负责，ZOTA 只消费云端服务版本和接口兼容信息。

## 4. 能力与开源项目映射

### 4.1 总表

| 能力域 | 推荐主选 | 可选/补充 | ZOTA 需要二开的部分 |
|---|---|---|---|
| 开发门户 | Backstage | Port 的开源替代需另评估 | ZOTA 插件、发布视图、车辆证据视图 |
| SCM/代码评审 | GitLab | Forgejo、Gitea、Gerrit | 仓库模板、权限和项目规范 |
| CI 编排 | GitLab CI | Jenkins、Tekton、Argo Workflows | Yocto/板卡/仿真 Job Adapter |
| Yocto 构建 | Yocto/OpenEmbedded、BitBake、kas | Toaster | 构建池、缓存治理、可追溯元数据 |
| 容器/OCI 制品 | Harbor、ORAS | GitLab Container Registry | Release Bundle 和证据索引 |
| 通用软件包 | GitLab Generic Package Registry、Pulp | Nexus Repository 社区版本需核验版本许可 | Yocto feed、保留和晋级策略 |
| 对象存储 | MinIO、Ceph RGW、现有 TOS | SeaweedFS | 大文件索引、生命周期和法证保留 |
| SBOM/签名 | Syft、Trivy、Grype、Cosign | ORAS、in-toto、GUAC | 发布门禁和证据关系图 |
| 云端 GitOps | Argo CD | Flux CD | 与 ZOTA 发布状态关联 |
| 渐进式发布 | Argo Rollouts | Flagger | 统一风险门禁和自动暂停 |
| 单元/API/UI 测试 | CTest、pytest、Robot Framework、Playwright | Cypress、Karate | 统一测试结果模型 |
| QEMU/镜像测试 | QEMU、Yocto testimage/ptest | Avocado | 镜像启动和升级回归模板 |
| 板卡/HIL 农场 | LAVA 或 labgrid | OpenHTF | 设备租约、接线资源和证据采集 |
| 测试报告 | Allure | ReportPortal | 测试与制品/发布关联 |
| 智驾仿真 | CARLA、SUMO、esmini、openPASS | SVL 已停止活跃维护，不建议新建依赖 | Scenario Adapter 和统一证据 |
| 指标 | Prometheus、VictoriaMetrics | Thanos、Mimir | 车辆和发布维度模型 |
| 日志 | Loki 或 OpenSearch | ClickHouse、VictoriaLogs | 多租户、冷热层和日志语义 |
| 链路 | Tempo 或 Jaeger | OpenSearch Trace Analytics | trace 与发布/车辆关联 |
| 采集 | OpenTelemetry Collector、Fluent Bit | Vector | 车云边采集规范和脱敏 |
| 告警路由 | Alertmanager | Grafana Alerting | 统一标签和路由规范 |
| 告警关联 | Keep | OpenSearch Alerting | ZOTA 变更关联和抑制规则 |
| 值班升级 | GoAlert | OneUptime、OpsKnight PoC | 企业通信网关、ACK 和审计 |
| 工单/ITSM | GitLab Issue、Zammad | OpenProject、GLPI | 事件模板和自动回写 |
| War Room | Mattermost | Matrix/Element、Zulip | 事件机器人和时间线 |
| Runbook | AWX、Rundeck | StackStorm、Ansible Semaphore | 审批、验证和回滚协议 |
| 长流程编排 | Temporal | Argo Workflows、Camunda 7 社区能力需按版本核验 | 事件状态机和补偿事务 |
| 策略 | OPA、Kyverno | Cedar | 发布策略和动作授权 |
| 密钥 | OpenBao、Vault 社区版 | SOPS、External Secrets Operator | 车端签名和短期凭证 |
| AI/RAG | OpenSearch/pgvector、Langfuse、LiteLLM | Haystack、LlamaIndex | 领域 Agent、MCP Gateway 和评测 |

### 4.2 开源和开放核心边界

选型时必须区分：

- **开源核心**：核心代码可自建，但部分高级能力属于商业版。
- **开放核心/Open Core**：基础功能开放，高级权限、合规或分析能力收费。
- **Source Available**：源码可见不代表满足 OSI 开源定义。
- **托管服务**：即使底层项目开源，云服务自身可能是商业产品。

GitLab、Mattermost、部分制品库和可观测平台存在社区版与商业版差异。正式采用前应固定：

1. 项目版本。
2. 许可证和依赖许可证。
3. 社区版可用功能。
4. 高可用、SSO、审计和合规是否收费。
5. 未来升级是否改变许可证或部署方式。

不能只根据项目首页的 “Open Source” 标签做决策。

## 5. SCM、GitLab、Jenkins 与 Argo CD 的边界

### 5.1 GitLab 应作为变更事实源

GitLab 适合承担：

- 仓库、分支和 Tag。
- Merge Request、Code Owners 和评审记录。
- CI Pipeline 和 Runner 调度。
- Issue、Milestone 和 Release。
- 容器和通用 Package Registry。
- 安全扫描结果入口。
- 构建、测试和部署状态回写。

建议所有生产变更都产生不可变的 `change_id`，并关联：

```text
change_id
  -> repository + commit_sha
  -> merge_request_id
  -> pipeline_id
  -> build_id
  -> artifact_digest
  -> test_run_id
  -> release_bundle_id
  -> deployment_id
  -> incident_id
```

### 5.2 Jenkins 的合理保留范围

Jenkins 不需要因建设新平台而立即移除，但不应继续成为所有能力的中心。

适合保留 Jenkins 的场景：

- 已有复杂流水线且短期迁移风险高。
- 依赖专用插件、实验室硬件或内网 Windows 节点。
- Yocto 构建基础设施已经围绕 Jenkins 建立。
- 某些供应商工具只能通过固定 Jenkins Agent 执行。

不建议继续放入 Jenkins 的状态：

- 制品事实源。
- 发布环境期望状态。
- 长期测试证据。
- 值班、工单和事件状态。
- 车辆 OTA 活动状态。

迁移策略：

```text
GitLab Pipeline
  -> 调用 Jenkins Job
  -> Jenkins 回传 job_id、结果和证据 URI
  -> GitLab 统一展示状态
  -> 逐步把通用 Job 迁回 GitLab Runner
```

### 5.3 Argo CD 的边界

Argo CD 只消费已经通过门禁的不可变制品：

```text
构建并签名镜像
  -> 更新环境配置仓库中的 digest
  -> Merge Request 审批
  -> Argo CD 同步
  -> Argo Rollouts 渐进发布
  -> 指标门禁
  -> 成功或自动暂停/回滚
```

禁止：

- 在 Argo CD 同步阶段重新构建镜像。
- 使用浮动 `latest` Tag 作为生产版本。
- Pipeline 直接 `kubectl apply` 绕过 GitOps 状态。
- 让 Argo CD 管理车辆 OTA 活动。

### 5.4 “用 Argo”必须先区分四个项目

`Argo` 不是一个可以直接与 Jenkins 或 GitLab Runner 等价比较的单一产品：

| 组件 | 核心职责 | 是否属于 CI 执行 | ZOTA 建议 |
|---|---|---:|---|
| Argo CD | Kubernetes GitOps 持续交付和状态收敛 | 否 | 云端服务默认采用 |
| Argo Rollouts | Kubernetes 蓝绿、金丝雀和指标分析 | 否 | 与 Argo CD 配合采用 |
| Argo Workflows | Kubernetes 容器原生 DAG/批处理工作流 | 是，可以承载 CI Job | 作为仿真、数据和大规模并行任务执行后端 |
| Argo Events | Kubernetes 事件源、EventBus、Sensor 和 Trigger | 间接 | 仅在非 GitLab 事件很多时按需引入 |

因此，“Argo CD 还是 Jenkins/GitLab Runner”是错误的比较方式。正确关系是：

```text
GitLab CI                         统一 CI 入口、MR 门禁、状态和权限
  ├─ GitLab Runner               默认通用执行器
  ├─ Jenkins                     遗留、插件、固定硬件和供应商工具适配
  └─ Argo Workflows              Kubernetes 内 DAG、仿真、ML 和批处理

通过门禁的不可变制品
  ├─ Argo CD + Argo Rollouts     云端 Kubernetes 交付
  └─ ZOTA                        车辆、ECU 和边缘 OTA
```

### 5.5 GitLab CI、Jenkins 与 Argo Workflows 对比

以下评分面向 ZOTA，而不是通用产品排名。`5` 表示更适合作为该能力的主实现。

| 维度 | GitLab CI + Runner | Jenkins | Argo Workflows |
|---|---:|---:|---:|
| 与 GitLab SCM、MR 和权限统一 | 5 | 3 | 2 |
| 流水线即代码和评审体验 | 5 | 4 | 4 |
| 普通容器构建和单元测试 | 5 | 4 | 4 |
| 裸机 Yocto 和大容量本地缓存 | 5 | 5 | 2 |
| Windows、供应商 SDK 和固定实验室节点 | 4 | 5 | 1 |
| 板卡、串口、烧录器和 HIL 资源适配 | 4 | 5 | 2 |
| Kubernetes 弹性并行任务 | 4 | 3 | 5 |
| 仿真、数据处理、ML DAG 和 Fan-out/Fan-in | 3 | 3 | 5 |
| 插件和历史系统兼容 | 3 | 5 | 2 |
| 多项目状态统一和开发者可见性 | 5 | 3 | 2 |
| 控制面运维复杂度 | 4 | 2 | 3 |
| 避免新增长期平台负担 | 5 | 3 | 3 |
| 适合作为 ZOTA 默认 CI 入口 | 5 | 2 | 2 |

结论：

1. **默认选择 GitLab CI + GitLab Runner。** ZOTA 已以 GitLab 作为代码和变更事实源，流水线、MR 门禁、权限、审计和执行状态放在同一处，新增系统最少。
2. **Jenkins 不立即删除。** 它对已有 Job、插件、Windows Agent、板卡、烧录器、供应商工具和固定硬件节点仍有价值，但应从“总控制面”收缩为受管执行后端。
3. **Argo Workflows 不替换默认 CI。** 它适合已经容器化、可以在 Kubernetes 内运行的高并发 DAG，特别是仿真切片、场景矩阵、数据转换、ML 评测和批量报告。
4. **云端 Kubernetes 推荐保留 Argo CD。** 它只负责 GitOps CD，不负责编译、单测、Yocto、板卡测试和车辆 OTA；非 Kubernetes 服务不应为了使用 Argo CD 强行容器化。

相邻开源 CI 候选也应记录，但当前不进入默认主链路：

| 候选 | 优点 | 不作为 ZOTA 默认方案的原因 | 何时重新评估 |
|---|---|---|---|
| Tekton Pipelines | Kubernetes 原生 CI/CD CRD、Task 复用和 Pipelines as Code | 与 GitLab CI、Argo Workflows 都有较大重叠，会再增加一套 CRD、结果和运维控制面 | 企业决定以 Tekton 作为跨 SCM 统一 CI 标准时 |
| Concourse CI | Resource/Task/Job 模型清晰，流水线自包含、容器化程度高 | 迁移已有 GitLab/Jenkins 的收益不足以覆盖新平台成本 | 需要高度可移植、与 SCM 解耦的独立流水线平台时 |
| Zuul | 跨仓依赖、推测执行和合并前 Gate 能力强 | 系统和操作模型更复杂，ZOTA 当前问题不是超大规模跨仓合并队列 | 多仓联动变更和长耗时 Gate 已成为交付瓶颈时 |
| Woodpecker CI | 轻量、开源、可接 GitLab 等代码平台 | GitLab 已自带 CI，新增轻量 CI 仍会制造重复状态和权限边界 | 使用不带 CI 的轻量 Git Forge 或边缘独立环境时 |
| BlueKing BK-CI | 插件、构建机、模板和国内企业实践较完整 | 更接近平台级替换，与 GitLab CI/Jenkins/制品系统重叠 | 结合 BK-Turbo、BK-Repo 做完整构建平台 PoC 时 |
| Zadig | 服务、环境、工作流和测试体验较完整 | 是 DevOps 平台层，不是单纯 Runner 替代品，且许可证有附加条件 | 完成法务预审后，评估研发交付门户和多环境编排体验时 |

### 5.6 按工作负载选择执行器

| ZOTA 工作负载 | 默认执行器 | 备选 | 原因 |
|---|---|---|---|
| Web/Go/Java 普通构建和测试 | GitLab Runner Docker/Kubernetes executor | Jenkins | 与 MR 和 Pipeline 原生关联，环境易隔离 |
| 容器镜像构建、安全扫描和 SBOM | GitLab Runner | Argo Workflows | 通用 CI 路径短，结果直接回写 GitLab |
| Yocto 全量构建 | 专用 GitLab Runner Instance executor 或受控专用主机 | Jenkins Agent | 需要大磁盘、稳定 CPU/内存、sstate/downloads 缓存和宿主设备控制 |
| Yocto 增量构建 | 同一受控构建池 | Jenkins Agent | 保持缓存位置、版本和安全域稳定 |
| Windows 工具链和供应商 SDK | GitLab Runner Instance/Docker executor | Jenkins Agent | 新流程优先纳入 GitLab；已有插件任务先保留 Jenkins |
| 板卡烧录、串口、CAN 和 HIL | GitLab Pipeline 调用 LAVA/labgrid | Jenkins Agent | 硬件资源应由实验室调度器管理，不直接锁死在 CI 节点 |
| CARLA/SUMO/esmini 场景矩阵 | Argo Workflows | GitLab Runner Kubernetes executor | 适合 DAG、参数矩阵、并发调度和独立重试 |
| 智驾数据预处理和模型评测 | Argo Workflows | Kubeflow Pipelines | 数据和 ML 批处理更适合 Kubernetes 工作流 |
| 云端 Kubernetes 部署 | Argo CD + Argo Rollouts | Flux CD | GitOps 收敛、漂移检测和渐进式交付 |
| 车辆/ECU 发布 | ZOTA | 无 | 需要车辆 cohort、兼容性、弱网、回滚和活动审计语义 |

截至 `2026-08-08`，GitLab 官方文档将 Shell、SSH 和 Custom executor 标为维护模式，只接收关键安全更新而不再规划新功能。已有 Shell Runner 可以继续作为迁移期方案，但新建弹性 Yocto 构建池应优先评估 `Instance executor`；它允许 Job 直接在完整实例上运行，也支持按需创建实例。Instance executor 是否支持现有私有云和附加设备，必须先核验对应 Fleeting 插件，不能仅根据架构图直接选用。若当前基础设施不适配，则保留成熟 Jenkins Agent，或采用严格隔离的专用 Runner 主机，并把宿主机镜像、权限、缓存和清理策略纳入平台治理。

Yocto 的执行器不应预先强行统一。若现有 Jenkins 构建已经具备稳定的 sstate/downloads 缓存、构建机治理、失败恢复和证据输出，短期继续使用 Jenkins 的风险低于迁移；GitLab CI 仍作为统一入口调用它。只有 GitLab Runner PoC 在复现率、吞吐、缓存命中率、故障恢复和维护成本上达到或超过现状，才迁移 Yocto Job。

### 5.7 推荐的最终组合

```text
第一层：变更和 CI 控制面
GitLab SCM + Merge Request + GitLab CI

第二层：执行后端
GitLab Runner
  - Docker/Kubernetes executor：通用构建和测试
  - Instance executor：适配后用于弹性实例和部分 Yocto 任务
Jenkins
  - 保留成熟 Yocto、遗留插件、固定 Agent 和短期难迁移任务
Argo Workflows
  - 仿真、数据、ML、场景矩阵和 Kubernetes 批处理

第三层：制品和证据
Harbor/TOS + SBOM + Signature + Provenance + Test Evidence

第四层：交付控制面
Argo CD + Argo Rollouts：云端
ZOTA：车辆、ECU 和边缘 OTA
```

推荐所有执行后端遵守同一 Job Adapter 契约：

```text
输入：
change_id
commit_sha
job_spec_uri
artifact_input_digest
execution_class

输出：
execution_id
status
log_uri
artifact_output_digest
test_evidence_uri
sbom_uri
provenance_uri
started_at
finished_at
```

GitLab 只需知道执行结果和证据地址，不需要把 Jenkins、Argo Workflow 或实验室系统的内部状态复制进 CI 脚本。

### 5.8 不建议的方案

- 不用 Argo CD 触发编译或在同步阶段生成制品。
- 不为了“全 Argo”把需要大缓存、USB、串口、CAN 或烧录器的任务强行塞进 Kubernetes。
- 不让 GitLab CI、Jenkins 和 Argo Workflows 各自维护一套等价主流水线。
- 不让 Jenkins 直接修改生产 Kubernetes 集群，生产变更应进入环境配置仓并由 Argo CD 收敛。
- 不让 Argo Events 重复消费所有 GitLab Webhook；GitLab 原生 Pipeline 能处理的事件不再复制一套 EventBus。
- 不把长时间仿真结果、Yocto 镜像和测试证据永久保存在 CI 控制面本地磁盘。
- 不因 Jenkins 插件能快速接入，就允许插件成为制品、凭据、发布状态或审计的唯一事实源。

### 5.9 分阶段迁移和 PoC

**阶段 A：盘点和统一入口**

- 导出所有 Jenkins Job、插件、Agent、凭据引用和触发关系。
- 给 Job 标注 `keep`、`migrate`、`replace` 或 `retire`。
- 新项目默认使用 GitLab CI，停止新增等价 Jenkins 流水线。
- Jenkins 结果必须回写 GitLab Commit/MR，并上报统一 ID 和证据 URI。

**阶段 B：执行器分池**

- 建立通用 Docker/Kubernetes Runner 池。
- 建立 Yocto Instance Runner PoC，验证 sstate/downloads、磁盘吞吐、清理和复现。
- 板卡资源接入 LAVA 或 labgrid，CI 只申请资源和获取结果。
- 保留一组 Jenkins Agent 承担尚未迁移的固定硬件和供应商任务。

**阶段 C：Argo Workflows 专项 PoC**

- 选择一组 CARLA/SUMO/esmini 场景矩阵，不先迁移通用 CI。
- 验证 100/1000 任务 Fan-out、GPU 调度、重试、超时、取消、日志和对象存储。
- 通过 GitLab Job 创建 Workflow，回传 workflow UID、汇总状态和证据 URI。
- 验证 Argo 控制面不可用时，不影响 GitLab 普通构建和 Jenkins 遗留任务。

**阶段 D：交付收口**

- CI 只构建、测试、签名并更新环境配置仓。
- Argo CD/Argo Rollouts 负责云端同步、分析和回滚。
- ZOTA 负责车端活动、策略、审批、灰度和证据。
- 禁止 Pipeline 持有长期生产集群管理员凭据。

PoC 验收指标：

| 指标 | 目标 |
|---|---|
| GitLab MR 可追溯率 | 100% Job、制品、测试和发布可关联 |
| 新增流水线 GitLab CI 覆盖率 | 100% |
| Jenkins 新增等价主流水线 | 0 |
| Yocto 相同输入复现率 | 100%，输出差异必须可解释 |
| Runner/Agent 隔离 | 高风险任务独立安全域 |
| 仿真任务失败重试 | 不重复已成功分片 |
| 云端生产部署 | 100% 经 GitOps 仓和 Argo CD |
| 车辆发布 | 100% 经 ZOTA |

## 6. Yocto 交叉编译平台

### 6.1 推荐基础组件

```text
Yocto / OpenEmbedded
  + BitBake
  + kas
  + GitLab Runner
  + 专用 Linux Builder
  + downloads mirror
  + shared sstate cache
  + hash equivalence server
  + artifact/object storage
```

`kas` 用于声明：

- Yocto layers 和 commit。
- machine、distro 和 target。
- local.conf/bblayers.conf 片段。
- 构建组合和依赖仓库。

这比在 CI 脚本中拼接大量 shell 环境变量更容易复现和审查。

### 6.2 容器和 Kubernetes 交叉编译工具辨析

#### 6.2.1 最可能记得的是哪个项目

根据“一个开源工具或容器，可以在容器/Kubernetes 环境实现交叉编译”的描述，最可能是以下项目之一：

| 记忆特征 | 最可能的项目 |
|---|---|
| Kubernetes Pod 中无需 Docker Daemon，根据 Dockerfile 构建并推送镜像 | `Kaniko` |
| 直接拉一个容器，里面已经有 ARM/AArch64 等 C/C++ 工具链 | `dockcross` |
| Dockerfile 中先写 `FROM --platform=$BUILDPLATFORM tonistiigi/xx AS xx` | `tonistiigi/xx` |
| 使用 `docker buildx build --platform=linux/amd64,linux/arm64` | Docker Buildx/BuildKit |
| BuildKit Builder 直接运行在 Kubernetes 中 | Buildx Kubernetes driver |
| 容器中运行 Poky/BitBake | CROPS `poky-container` |
| 容器中运行 `kas build` | `kas-container` |
| Rust 项目使用类似 Cargo 的命令跨平台构建和测试 | `cross-rs/cross` |
| 通过容器注册多架构模拟器 | `tonistiigi/binfmt`，它是 QEMU/binfmt 安装工具，不是交叉编译器 |

如果记忆重点是“Kubernetes 内不安装 Docker 也能构建镜像”，最可能就是 **Kaniko**。如果重点是“容器本身带交叉编译器”，则更可能是 **dockcross**；如果重点是“Dockerfile 多架构交叉编译辅助”，则是 **tonistiigi/xx**；如果重点是“Kubernetes 里的多架构容器构建池”，则是 **Buildx Kubernetes driver + BuildKit**。

#### 6.2.2 项目能力对比

| 项目 | 本质 | 适合 | 不适合 |
|---|---|---|---|
| Kaniko | 在容器用户态执行 Dockerfile 并生成 OCI 镜像 | Kubernetes 内无 Docker Daemon 镜像构建、遗留流水线 | 单独提供交叉编译器、Yocto BSP、真正跨 CPU 执行 |
| `tonistiigi/xx` | BuildKit/Dockerfile 交叉编译辅助脚本镜像 | C/C++、CGo、Go、Rust 的多架构 OCI 镜像和二进制 | 完整 Yocto BSP、RootFS 和供应商 SDK 管理 |
| `dockcross` | 预装交叉工具链、CMake、Ninja 等工具的 Docker 镜像 | 通用 C/C++ 库、CLI、算法库和快速 PoC | 与量产 Yocto RootFS 严格 ABI 对齐的应用 |
| Buildx/BuildKit | 多架构镜像构建执行引擎和缓存系统 | 生成 amd64/arm64 等多架构 OCI Image Index | 单独提供目标编译器、Sysroot 或 BSP |
| Buildx Kubernetes driver | 在 Kubernetes 中运行和扩展 BuildKit Builder | K8s 构建池、PVC 缓存、架构节点选择和并发镜像构建 | 替代 Argo Workflow、Yocto 或 Release Control Plane |
| `tonistiigi/binfmt` | 在宿主机注册 QEMU 用户态模拟器 | 构建中运行少量目标架构命令和基础验证 | 计算密集型完整编译；它不是编译器 |
| CROPS `yocto-dockerfiles` | 构建 Yocto 基础镜像和 Builder 镜像的 Dockerfile 集合 | 统一维护 Debian、Ubuntu、Fedora、AlmaLinux、openSUSE 等构建基线 | 直接描述产品 Layer、Machine、Distro 和最终构建目标 |
| CROPS `poky-container` | 可运行 Poky/BitBake 的容器环境 | 容器化 Yocto 入门、开发和 CI | 单独治理 Layer、版本矩阵和企业发布证据 |
| `kas-container` | 封装 kas 和 Yocto 构建依赖的容器入口 | 以 kas YAML 为事实源的可复现 Yocto 构建 | 通用非 Yocto 多架构镜像构建 |
| Yocto SDK/eSDK | 由目标 Yocto 配置生成的编译器、Sysroot 和开发环境 | 与量产 RootFS ABI 对齐的车端应用和中间件 | 完整镜像构建和云端多架构 OCI 镜像 |
| `cross-rs/cross` | 基于 Docker/Podman 的 Rust 交叉编译和交叉测试工具 | Rust 多架构二进制和测试 | C/C++ BSP、完整 Yocto 系统 |
| crosstool-NG | GCC/binutils/libc 交叉工具链生成器 | 定制 Linux、bare-metal GCC 工具链 | RootFS、包管理、OTA 和完整 BSP |
| Buildroot | 工具链、内核、RootFS 和轻量嵌入式系统构建 | 小型独立设备和快速产品原型 | 已以 Yocto 为量产事实源的同一产品线 |

需要特别区分：

- **Kaniko** 负责执行 Dockerfile、生成镜像层和推送 Registry，本身不是交叉编译器。
- **Buildx/BuildKit** 决定“在哪里、如何缓存、输出哪些平台的 OCI 镜像”。
- **tonistiigi/xx** 帮 Dockerfile 根据 `BUILDPLATFORM`、`TARGETPLATFORM` 配置交叉编译器和依赖。
- **dockcross** 直接提供预配置工具链容器。
- **Yocto SDK/eSDK** 提供与量产 RootFS 最可靠的 ABI、头文件和库版本一致性。
- **CROPS yocto-dockerfiles** 提供基础和 Builder 镜像配方，**CROPS poky-container** 在其上提供可运行 BitBake/Poky 的容器入口。
- **Yocto + kas-container** 构建完整 BSP、内核、RootFS、包源和 SDK。
- **Argo Workflows** 只负责这些任务的依赖、并发、重试、超时和结果汇总。

#### 6.2.3 推荐给 ZOTA 的组合

```text
GitLab CI
  -> 创建 Argo Workflow
       |
       +-- 通用 Go/C/C++ 多架构容器
       |     Buildx Kubernetes driver
       |       + BuildKit
       |       + tonistiigi/xx
       |       + amd64/arm64 Builder Node
       |
       +-- 通用 C/C++ 二进制和库
       |     dockcross 或 crosstool-NG 工具链镜像
       |
       +-- 量产车端 Linux 应用
       |     Yocto SDK/eSDK OCI 工具链镜像
       |
       +-- 完整车端镜像
       |     kas-container + BitBake + 专用 Yocto Node
       |
       +-- Rust 车端组件
       |     cross-rs 或 Yocto Rust SDK
       |
       +-- MCU/RTOS
             Zephyr SDK 或受控供应商工具链镜像
       |
       +-- Kaniko 遗留任务
             仅保留现有无 Daemon 镜像构建
             评估 Chainguard 分支或迁移 Rootless BuildKit
  -> 测试、SBOM、签名和 provenance
  -> Harbor/TOS
  -> Argo CD 或 ZOTA
```

不同产物采用不同主路径：

| 产物 | 推荐主路径 |
|---|---|
| 云端/边缘 amd64、arm64 容器镜像 | Buildx Kubernetes driver + BuildKit + `tonistiigi/xx` |
| 不依赖量产 RootFS 的通用 C/C++ 工具 | `dockcross` |
| 与车辆 RootFS 动态链接的应用和中间件 | Yocto SDK/eSDK 工具链镜像 |
| Kernel、DTB、RootFS、wic、swu、raucb | kas-container + Yocto/BitBake |
| Rust 独立组件 | `cross-rs`；与 RootFS 强耦合时改用 Yocto SDK |
| MCU 固件 | Zephyr SDK 或供应商工具链容器 |

#### 6.2.4 `tonistiigi/xx` 的定位

`xx` 是一个很小的 Docker 镜像，包含读取 BuildKit `TARGET*` 参数的辅助脚本。典型模式是：

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM tonistiigi/xx AS xx

FROM --platform=$BUILDPLATFORM debian:stable-slim AS build
COPY --from=xx / /
ARG TARGETPLATFORM

RUN xx-apt-get update \
    && xx-apt-get install -y gcc g++ pkg-config
RUN xx-info env
```

它可以帮助：

- 统一 Docker 平台名、GNU Target Triple 和语言工具链目标名。
- 为 Debian/Ubuntu 或 Alpine 安装目标架构依赖。
- 配置 `cc`、`c++`、Clang、Go、Cargo 和 `pkg-config`。
- 用 `xx-verify` 检查输出文件架构。

它不能解决：

- Yocto Layer、Machine、Distro 和 BSP 配置。
- 供应商内核、Bootloader、DTB 和 RootFS。
- 量产系统的 glibc/libstdc++ ABI 一致性。
- 板卡测试、OTA 兼容矩阵和发布审批。

因此，`xx` 适合作为云端/边缘容器和通用组件的交叉编译辅助，不应替代 Yocto SDK。

#### 6.2.5 dockcross 的定位

`dockcross` 提供大量预构建工具链镜像，并预配置：

- `CC`、`CXX`、`LD`、`AS` 等变量。
- CMake Toolchain File。
- Make、CMake、Ninja、Meson。
- 部分目标的 QEMU 模拟器。
- Conan 和部分 Rust 支持。

适合：

- 算法库和基础库快速验证。
- 将旧 CMake 项目快速迁入容器 CI。
- 同一代码构建 ARMv7、AArch64、musl、Android 等多种目标。

限制：

- 官方预构建镜像以 x86_64 Host 为主要运行环境。
- 通用 glibc、musl 和库版本未必与 ZOTA 量产 RootFS 一致。
- 不能直接作为车辆量产工具链的唯一来源。

若使用 dockcross，应把其 Dockerfile 或镜像 Digest 固定下来，并对输出二进制执行：

```text
file / readelf
ELF machine 检查
动态链接器检查
GLIBC/GLIBCXX Symbol Version 检查
目标 RootFS 依赖闭包检查
QEMU smoke test
真实板卡测试
```

#### 6.2.6 Buildx Kubernetes driver 的定位

Buildx 的 Kubernetes driver 可以把 BuildKit 作为 Pod 部署到 Kubernetes，并配置：

- Builder 副本数和负载均衡。
- CPU、内存和临时磁盘资源。
- 每个副本的持久化缓存 PVC。
- `nodeSelector`、Taint/Toleration 和 ServiceAccount。
- Rootless BuildKit。
- amd64、arm64 等不同架构的原生 Builder Node。
- 必要时安装 QEMU 模拟器。

它最适合生成多架构 OCI 镜像，不应承担完整 Yocto 构建控制面。推荐拓扑：

```text
buildkit-amd64
  nodeSelector: kubernetes.io/arch=amd64
  local/PVC cache

buildkit-arm64
  nodeSelector: kubernetes.io/arch=arm64
  local/PVC cache

docker buildx build
  --platform linux/amd64,linux/arm64
  --push
  -> Harbor OCI Image Index
```

策略优先级：

1. 工具链原生支持时使用交叉编译。
2. 有异构节点时使用 amd64/arm64 原生 Builder。
3. 只有少量配置脚本或目标程序需要执行时使用 QEMU。
4. 不使用 QEMU 完成完整 Yocto、TensorRT 或大规模 C++ 编译。

#### 6.2.7 Kaniko 的定位与当前状态

Kaniko 的核心能力是：

```text
Kubernetes Pod
  -> 读取 Build Context 和 Dockerfile
  -> 在用户态依次执行 Dockerfile 指令
  -> 对文件系统变化做 Snapshot
  -> 生成 OCI/Docker 镜像层
  -> 推送 Registry
```

它不需要 Docker Daemon，也不需要在 Pod 中挂载 `/var/run/docker.sock`，这正是它过去在 Kubernetes CI 中广泛使用的原因。

但 Kaniko 不等于交叉编译：

- `--custom-platform` 主要设置目标平台元数据和有限兼容场景。
- 该参数不提供虚拟化，不能让宿主机执行不受支持的目标架构指令。
- Dockerfile 中如果能交叉编译，是因为镜像内安装了 Yocto SDK、GCC/Clang、`xx` 或其他工具链。
- 多架构镜像通常需要在不同架构节点分别构建，再用 Manifest Tool 合并。
- QEMU 可以补充少量目标架构命令执行，但不能改变 Kaniko 本身不是编译器的事实。

维护状态必须单独处理：

- Google 原仓库 `GoogleContainerTools/kaniko` 已在 `2025-06-03` 归档并标记不再开发维护。
- Chainguard 建立了维护分支，继续做安全修复和依赖更新。
- 截至 `2026-08-08`，生产选型必须核验 Chainguard 分支的镜像发布、签名、支持方式和内部构建策略，不能继续无条件拉取旧 Google `gcr.io/kaniko-project` 镜像。

ZOTA 建议：

| 场景 | 处理方式 |
|---|---|
| 已有稳定 Kaniko Pipeline | 暂不强制迁移，固定版本和 Digest，完成风险盘点 |
| 继续使用 Kaniko | 评估 Chainguard 分支，并将源码和镜像同步到内部供应链 |
| 新建 Kubernetes 镜像构建 | 默认验证 Rootless BuildKit |
| Rootless BuildKit 不满足现有安全策略 | 比较 Buildah 和维护中的 Kaniko 分支 |
| 多架构 OCI 镜像 | 优先 BuildKit/Buildx + 原生异构节点或受控 QEMU |
| Yocto/车端交叉编译 | 使用 kas-container、Yocto SDK/eSDK；Kaniko 不进入主构建链 |

建议迁移关系：

```text
现有：
GitLab/Argo -> Kaniko Pod -> Harbor

目标：
GitLab/Argo -> Rootless BuildKit -> Harbor
                    |
                    +-- Buildx multi-platform
                    +-- tonistiigi/xx
                    +-- Registry/PVC cache
                    +-- SBOM/provenance
```

保留 Kaniko 的理由只能是迁移成本、安全模型或已有兼容性，不应把“过去 Kubernetes 中常用”作为新项目继续选择它的理由。

#### 6.2.8 CROPS、`gottaBoy` Fork 与 `kas-container` 的关系

用户提供的两个仓库是 CROPS 上游项目的 Fork：

| Fork | 上游 | 当前关系 | 建议定位 |
|---|---|---|---|
| `gottaBoy/poky-container` | `crops/poky-container` | 截至 2026-08-08，默认分支提交 `cad5d17d3bad6d105adda2be1e398f4fae70e282` 与上游一致，尚无独立提交 | ZOTA 内部定制入口或上游镜像，不作为独立第三方产品判断 |
| `gottaBoy/yocto-dockerfiles` | `crops/yocto-dockerfiles` | 截至 2026-08-08，默认分支提交 `c003de7d22909884c9ddc8b7107b2b40d156ced2` 与上游一致，尚无独立提交 | ZOTA 构建基础镜像的内部 Fork 起点 |

两者不是两个相互替代的交叉编译器，正确层次是：

```text
crops/yocto-dockerfiles
  -> 维护多发行版基础镜像和 Yocto Builder Dockerfile
  -> crops/poky-container
       -> 增加 BitBake/Poky 运行入口
       -> 处理宿主机 UID/GID，避免构建输出权限错乱
       -> 执行 Yocto 构建

ZOTA 推荐生产入口：
ZOTA Toolchain Base Image
  -> 吸收 yocto-dockerfiles 的多发行版和基础镜像模式
  -> 吸收 poky-container 的 UID/GID、目录挂载和入口脚本模式
  -> 固定 kas-container/kas、BitBake 和依赖版本
  -> kas YAML 声明 Layer、Machine、Distro、Target 和 commit
  -> Argo Workflow、GitLab Runner 或 Jenkins 调用
```

推荐选择不是简单二选一：

- `yocto-dockerfiles` 适合维护企业内部 Yocto 基础镜像和 Builder 镜像。
- `poky-container` 适合开发和 CI 中直接运行 Poky/BitBake，并提供成熟的宿主机文件权限处理思路。
- `kas-container` 适合作为量产构建的声明式入口，使 Layer 和构建组合进入 Git 审查。
- ZOTA 可以使用 CROPS 镜像做 PoC，但生产环境应从固定源码 commit 自建镜像，扫描、生成 SBOM、签名后推送 Harbor。

`gottaBoy/*` Fork 的治理要求：

1. 在仓库中记录 `upstream` 地址、同步日期、上游 commit 和 ZOTA Patch 列表。
2. 不只依赖 GitHub Fork 按钮或可变 Tag，发布镜像必须固定源码 commit 和基础镜像 Digest。
3. 建立定期上游差异检查、安全公告检查和 Rebase/Merge 流程。
4. ZOTA 定制优先放在独立 Overlay、Containerfile 或少量可审查 Patch 中，避免长期不可合并 Fork。
5. 对上游 2024 年后的提交和 Release 活跃度持续核验；代码可用不等于供应链可以无人维护。
6. GPL-2.0 许可证、镜像内软件许可证和分发方式需进入统一开源合规扫描。

结论：

> 这两个 `gottaBoy` 仓库可以作为 ZOTA 可控镜像和二次开发的起点，但目前本质上仍是 CROPS 的同步 Fork。生产方案应以 `kas YAML + 内部不可变工具链镜像 + 专用构建节点 + 缓存治理 + 证据输出` 为主，而不是把 Fork 本身当成交叉编译平台。

#### 6.2.9 Yocto 容器化的正确方式

对于完整 Yocto 构建，推荐：

```text
Argo Workflow Pod
  image: 内部镜像仓中的 kas-container@sha256:...
  nodeSelector: workload=zota-yocto
  workspace: 本地 NVMe
  DL_DIR: 共享下载镜像
  SSTATE_DIR: 分安全域共享缓存
  hashserv: 独立服务
  output: TOS/Harbor OCI Artifact
```

不要把 Yocto 当作普通无状态 Kubernetes Job：

- `TMPDIR` 有大量小文件和高 IOPS，优先本地 NVMe。
- Pod 重建不能清空 downloads 和 sstate。
- 缓存需要按 Yocto 大版本、架构、项目和信任域治理。
- 闭源 BSP 和供应商 SDK 需要独立凭据和访问域。
- 构建节点应固定 Host Kernel、容器 Runtime 和资源基线。
- 输出必须包含 License Manifest、SPDX/SBOM、构建配置和签名。

如果现有 Jenkins + 专用构建机已经稳定，推荐先采用：

```text
GitLab CI
  -> Argo Workflow 编排测试和后处理
  -> 调用现有 Jenkins Yocto Job
  -> 获取 Artifact/Evidence URI
```

只有容器化 Yocto PoC 达到缓存命中率、构建时长、复现率和故障恢复目标后，再迁移执行器。

#### 6.2.10 容器安全和供应链约束

- 所有工具链镜像固定不可变 Digest，不直接使用 `latest`。
- 第三方镜像先同步到 Harbor，完成 Trivy 扫描、SBOM、许可证和签名校验。
- 自建 ZOTA Toolchain Catalog，记录 Host、Target、GCC/Clang、libc、Sysroot、来源和生命周期。
- 普通构建使用非特权 Pod 和 Rootless BuildKit。
- 不在普通 Argo Pod 中挂载宿主机 `/var/run/docker.sock`。
- `cross-rs` 若需要 Docker/Podman，应在隔离 Runner 中运行，或直接把其目标镜像转成受控构建 Job。
- QEMU/binfmt 安装需要节点级权限，使用专用 Builder Node 或受控 DaemonSet。
- 签名私钥不进入构建容器；构建完成后由隔离签名服务处理。
- 编译容器无权直接部署生产集群或创建车辆 OTA 活动。

#### 6.2.11 建议 PoC

**PoC 1：Buildx + xx**

- 同一 Git commit 构建 amd64/arm64 的 Go、CGo 和 C++ 示例。
- 输出多架构 OCI Image Index。
- 验证无 QEMU 交叉编译、异构节点原生构建和 QEMU 三种策略。

**PoC 2：dockcross 与 Yocto SDK**

- 用两套工具链编译同一 C/C++ 车端应用。
- 比较二进制大小、动态链接器、GLIBC/GLIBCXX、依赖闭包和板卡结果。
- 证明通用 dockcross 是否满足目标 RootFS ABI，而不是凭“编译成功”判断。

**PoC 3：Argo + kas-container**

- 在专用 Kubernetes Node 上执行完整 Yocto 构建。
- 比较现有 Jenkins 的构建时间、sstate 命中、磁盘吞吐、失败恢复和维护成本。
- 验证 Pod/Node 故障后构建证据和缓存不丢失。

**PoC 4：供应链验证**

- 固定所有基础镜像和工具链 Digest。
- 生成 SBOM、SLSA provenance 和签名。
- 验证镜像、SDK、目标二进制和最终 Release Bundle 可以双向追溯。

**PoC 5：Kaniko 迁移**

- 选择一个现有 Kaniko Pipeline，分别使用旧 Kaniko、Chainguard 分支和 Rootless BuildKit 构建。
- 比较输出镜像摘要、缓存命中、构建时间、权限需求、漏洞和维护成本。
- 验证 BuildKit 多架构输出、Registry Cache、SBOM 和 provenance。
- 形成保留、迁移或淘汰 Kaniko 的 ADR，不做一次性全量替换。

最终建议：

> ZOTA 可以建设一个 Kubernetes 内的交叉编译服务，但不应寻找一个工具覆盖所有目标。使用 Buildx Kubernetes driver + BuildKit + `tonistiigi/xx` 处理多架构容器，使用 Yocto SDK/eSDK 处理量产车端应用，使用 kas-container + BitBake 处理完整车端系统，dockcross/cross-rs 作为专项工具，Argo Workflows 统一编排和收集证据。

### 6.3 构建池设计

Runner 建议按标签隔离：

```text
yocto-x86-large
yocto-arm64-native
yocto-vendor-a
yocto-vendor-b
qemu-test
board-lab
simulation-gpu
signing-isolated
```

每个构建作业必须记录：

- `kas` 配置摘要。
- BitBake 版本。
- Layer 仓库和 commit。
- Machine、Distro、Image Recipe。
- Toolchain 和宿主机镜像摘要。
- downloads/sstate 命中率。
- 构建日志和失败任务。
- 输出文件摘要和大小。
- License manifest。
- SPDX/SBOM。
- 签名和 provenance。

### 6.4 缓存和复现

Yocto 构建农场的核心不是 UI，而是缓存一致性和可复现性。

建议：

- `DL_DIR` 使用只追加或受控清理的共享下载镜像。
- `SSTATE_DIR` 按 Yocto 大版本、架构和安全域治理。
- 启用 hash equivalence 降低等价任务重复构建。
- 定期执行无缓存基线构建，发现隐藏依赖。
- 构建宿主机使用固定容器镜像或不可变 VM 模板。
- 对供应商闭源包保留来源、许可证、校验和和授权记录。
- 不允许不同信任等级的项目无隔离共享可写缓存。

### 6.5 Toaster 的定位

Toaster 可以作为 Yocto 构建配置和结果查看界面进行 PoC，但不应默认把它设为平台控制中心。

原因：

- 主流程已经由 GitLab 管理。
- 构建配置应以 Git 中的 `kas` 文件为事实源。
- 平台仍需自行补齐制品签名、发布门禁、板卡测试和 ZOTA 关联。

可以借鉴 Toaster 的构建元数据展示，而不是复制第二套流水线状态。

### 6.6 Yocto 输出的发布单元

一次车端发布不应只选择一个镜像文件。推荐生成：

```yaml
release_bundle:
  id: vrb-2026-08-08-001
  platform: vehicle-gateway-a
  hardware_revision:
    - rev-c
    - rev-d
  artifacts:
    rootfs:
      digest: sha256:...
    boot:
      digest: sha256:...
    dtb:
      digest: sha256:...
    ota_delta:
      digest: sha256:...
  sbom:
    digest: sha256:...
  provenance:
    digest: sha256:...
  compatibility_matrix:
    digest: sha256:...
  test_evidence:
    - test-run-qemu-...
    - test-run-board-...
    - scenario-run-...
  signatures:
    - key_id: release-signing-prod
      value: ...
```

ZOTA 发布的是经过门禁的 Release Bundle，而不是临时目录中的散文件。

## 7. Artifact 与软件供应链

### 7.1 制品类型

| 类型 | 示例 | 推荐存储 |
|---|---|---|
| OCI 镜像 | 云服务、边缘服务、构建环境 | Harbor |
| OCI 通用 Artifact | SBOM、签名、provenance、策略包 | Harbor + ORAS |
| 通用软件包 | zip、tar、安装包、SDK | GitLab Generic Package Registry 或 Pulp |
| Yocto 包源 | rpm/deb/ipk feed | Pulp 或对象存储 + 受控索引 |
| 大型镜像 | wic、ext4、swu、raucb | Harbor OCI Artifact 或 TOS |
| 智驾模型 | ONNX、TensorRT engine、权重 | OCI Artifact 或 TOS，元数据入目录 |
| 地图/标定 | 地图切片、参数、标定包 | TOS，摘要和版本入 Release Bundle |
| 测试/仿真结果 | 日志、视频、rosbag/MCAP、报告 | TOS，索引入证据库 |

### 7.2 Harbor 的角色

Harbor 可承担：

- OCI Registry。
- 项目和复制策略。
- 漏洞扫描集成。
- Tag 保留和垃圾回收。
- 制品签名/验签集成。
- OCI Artifact 存储。

Harbor 不是完整的：

- 通用需求和工单系统。
- 测试证据关系库。
- 车辆发布编排系统。
- 大规模日志检索平台。

### 7.3 可信制品门禁

制品进入生产候选区前至少验证：

1. 使用 digest 固定内容。
2. 来源仓库和 commit 可追溯。
3. 构建环境可追溯。
4. 生成 SBOM。
5. 完成漏洞和许可证扫描。
6. 生成 provenance。
7. 通过要求的测试和仿真。
8. 使用受控密钥签名。
9. 通过兼容矩阵。
10. 生成不可变 Release Bundle。

推荐工具组合：

```text
Syft                 -> SBOM
Trivy / Grype        -> 漏洞扫描
Cosign               -> 签名和证明
in-toto              -> 供应链步骤证明
ORAS                 -> OCI Artifact 传输
GUAC                 -> 供应链元数据关系分析，可后续 PoC
OPA / Kyverno        -> 门禁策略
```

### 7.4 制品晋级而不是重新构建

```text
development
  -> candidate
  -> staging
  -> production
```

各阶段必须晋级同一个 digest。不能在测试环境和生产环境分别构建“同版本”制品，否则测试证据无法证明生产内容。

## 8. 自动化测试、板卡农场与仿真

### 8.1 分层测试模型

```text
L0 静态检查和单元测试
L1 组件、API、协议和 UI 测试
L2 镜像、QEMU、容器和升级测试
L3 真实板卡、设备在环和网络故障测试
L4 SIL/HIL/场景仿真和回放
L5 小规模车队或影子流量验证
L6 生产渐进发布和持续验证
```

所有层级都应输出统一测试结果：

```yaml
test_run:
  test_run_id: tr-...
  change_id: ch-...
  build_id: b-...
  artifact_digest: sha256:...
  environment_id: lab-a
  test_suite: ota-power-loss
  result: failed
  started_at: ...
  finished_at: ...
  evidence:
    junit: tos://...
    logs: tos://...
    video: tos://...
    trace: ...
  failure_signature: fs-...
```

### 8.2 通用自动化测试

建议：

- C/C++：CTest、GoogleTest。
- Python：pytest。
- 跨系统验收：Robot Framework。
- Web UI：Playwright。
- API：pytest、Robot Framework、Karate 等按现有技术栈选择。
- 性能：k6、JMeter、Locust。
- 安全：Semgrep、Trivy、Gitleaks、OWASP ZAP。
- 混沌和故障注入：Chaos Mesh、Litmus、Toxiproxy。

GitLab 只保存摘要和短期测试附件，大文件进入对象存储。

### 8.3 QEMU 与 Yocto 测试

Yocto `testimage` 和 `ptest` 可用于：

- 镜像启动。
- 基础命令和服务。
- 软件包自测。
- 网络和存储。
- 安装、升级和回滚。
- 设备配置迁移。

QEMU 无法替代真实硬件：

- Bootloader、闪存、电源中断和 watchdog 行为不同。
- CAN、以太网 PHY、GPU/NPU 和供应商驱动难以完整模拟。
- 时序、温度和硬件故障需要板卡或 HIL。

### 8.4 LAVA 与 labgrid

**LAVA** 更适合：

- 集中式设备实验室。
- 大量设备调度。
- 标准化测试定义。
- 设备健康和队列管理。
- 多团队共享板卡。

**labgrid** 更适合：

- Python 驱动的嵌入式测试。
- 灵活描述电源、串口、网络、USB 和继电器资源。
- 团队自建板卡工装和 pytest 集成。
- 较轻量的实验室自动化。

建议先用 2～5 块代表性硬件进行 PoC，再按以下维度选择：

- 设备数量和地域。
- 工装复杂度。
- 多租户和预约需求。
- 现有测试代码。
- 串口、电源、继电器、CAN 和刷写能力。
- 维护人员能力。

不要同时建设两套生产级板卡调度平台。

### 8.5 HIL 平台

开源项目可以提供调度和测试框架，但完整 HIL 往往依赖：

- 实时机。
- CAN/CAN FD、LIN、车载以太网。
- 电源、故障注入和负载模拟。
- 供应商工具。
- 专用模型和接线矩阵。

因此 HIL 应通过 Adapter 接入统一平台：

```text
Test Orchestrator
  -> HIL Adapter
  -> Vendor/Open HIL Controller
  -> Result Normalizer
  -> Evidence Store
```

平台统一的是作业、资源租约、输入输出和证据，不强行统一每种硬件底层实现。

### 8.6 智驾仿真平台

可采用的开源引擎：

| 项目 | 强项 | 适用方式 |
|---|---|---|
| CARLA | 城市场景、传感器和自动驾驶研究 | 闭环仿真、感知和规划验证 |
| SUMO | 大规模交通流和道路网络 | 交通参与者和拥堵场景 |
| esmini | OpenSCENARIO 播放和轻量仿真 | 场景回归、标准场景执行 |
| Eclipse openPASS | 交通安全和随机仿真 | 风险、事故和统计分析 |

没有一个引擎能覆盖全部验证需求。ZOTA 应二开 `Simulation Orchestrator`：

```text
Scenario Catalog
  -> Scenario Set
  -> Engine Adapter
  -> Simulation Job
  -> Metric Evaluator
  -> Evidence Pack
  -> Release Gate
```

统一场景模型至少包含：

- `scenario_id` 和版本。
- 来源：法规、事故、路测、数据挖掘、人工设计。
- ODD 标签。
- 地图和环境。
- 车辆、模型、标定和配置版本。
- 随机种子。
- 期望指标和通过阈值。
- 仿真引擎和版本。
- 运行日志、视频、轨迹和评价结果。

### 8.7 测试报告和分析

**Allure** 适合：

- 生成可读的测试报告。
- 展示步骤、附件、历史和分类。
- 快速接入现有测试框架。

**ReportPortal** 更适合：

- 大规模测试结果汇总。
- 失败聚类和历史趋势。
- 多团队共享测试分析。
- 机器学习辅助失败分析。

推荐分阶段：

1. 先统一 JUnit/Allure 输出。
2. 测试规模和失败分析成本上升后再评估 ReportPortal。
3. 无论采用哪个 UI，原始证据和主键关系归统一证据模型管理。

## 9. 日志、分析、报告与工单闭环

### 9.1 可观测数据分层

| 数据 | 示例 | 主存储 | 说明 |
|---|---|---|---|
| Metrics | CPU、失败率、升级成功率 | Prometheus/VictoriaMetrics | 聚合数值和告警 |
| Logs | 服务日志、设备日志、审计日志 | Loki/OpenSearch | 检索和调查 |
| Traces | API 和异步调用链 | Tempo/Jaeger | 服务依赖和延迟 |
| Events | 发布、告警、ACK、回滚 | PostgreSQL/Event Bus | 状态机和时间线 |
| Evidence | 测试报告、视频、MCAP、镜像 | TOS/S3 | 大文件和长期保留 |
| Knowledge | Runbook、复盘、FAQ、变更说明 | Git/Docs/Knowledge Base | 人和 AI 复用 |

不要把所有数据都塞进 OpenSearch，也不要让 Loki 或 Prometheus 成为事件工单的事实源。

### 9.2 采集层

推荐：

- 云服务 SDK 和网关：OpenTelemetry。
- Kubernetes/主机日志：Fluent Bit 或 OTel Collector。
- 边缘节点：轻量 Fluent Bit/Vector/OTel Agent。
- 车辆：本地环形缓冲、事件触发采样、断点续传和脱敏。
- 高价值智驾数据：MCAP/对象存储，元数据进入数据目录。

采集标准必须包含：

```text
service.name
service.version
deployment.environment
region
cluster
tenant_id
change_id
build_id
artifact_digest
deployment_id
release_bundle_id
vehicle_id_hash
cohort_id
ecu_id
trace_id
incident_id
```

车辆标识进入通用日志前应脱敏或哈希，原始 VIN 的访问必须单独授权和审计。

### 9.3 云端多服务 OTel APM 接入

OpenTelemetry 负责统一采集协议、上下文、SDK 和 Collector，不负责规定唯一存储后端。ZOTA 应先统一 OTLP 和语义模型，再选择 Tempo、SigNoz、SkyWalking 或其他后端，避免业务代码绑定某个 APM 产品。

推荐拓扑：

```text
Browser / Mobile
  -> ZOTA Telemetry Ingress
       CORS、限流、鉴权、脱敏
       禁止直接暴露内部 Collector
  -> OTel Gateway

Kubernetes Services
  -> OTel SDK / Auto Instrumentation
  -> Node-local OTel Agent DaemonSet
  -> Cluster OTel Gateway

VM / Bare Metal / Edge Service
  -> OTel SDK
  -> Host OTel Agent
  -> Region OTel Gateway

OTel Gateway
  -> resource/k8sattributes
  -> transform/redaction
  -> memory_limiter/batch
  -> trace-id routing
  -> tail sampling
  -> retry + sending queue + WAL
       |
       +-- Traces  -> Tempo
       +-- Metrics -> Prometheus/VictoriaMetrics
       +-- Logs    -> Loki/OpenSearch
       +-- PoC     -> DataBuff/SigNoz，受控双写
```

各层职责：

| 层 | 职责 | 不应承担 |
|---|---|---|
| SDK/自动探针 | 创建 Span、Metric、Log 关联，传播上下文 | 长时间磁盘缓存、复杂路由 |
| Agent Collector | 本机接收、补充主机/Pod 属性、批处理和短期缓冲 | 全局 Tail Sampling、跨集群租户决策 |
| Gateway Collector | 脱敏、路由、采样、限流、租户隔离和后端输出 | 成为业务事件或 Incident 事实源 |
| APM Backend | 存储、查询、拓扑、RED 指标和问题定位 | 保存智驾原始传感器大文件 |

接入顺序：

1. 从 `zota-web/zota-repo-web -> API Gateway -> 2～3 个核心后端 -> PostgreSQL/Redis/Kafka` 建立样板链路。
2. Java 优先使用 OpenTelemetry Java Agent；Node.js、Python、.NET 在框架支持稳定时使用自动埋点。
3. Go、C++ 和业务关键路径使用 SDK 和显式 Span，避免只依赖自动探针。
4. HTTP、gRPC、数据库、Redis 和消息队列先覆盖通用调用，再补充发布、制品、OTA 和车辆领域 Span。
5. 日志统一输出 `trace_id`、`span_id`、`service.name` 和结构化业务 ID。
6. 前端只通过受控 Telemetry Ingress 上报，关闭敏感 Header、Body、Cookie、VIN 和用户输入采集。

#### 9.3.1 Java、Go、TypeScript、Python、C++ 和 ROS 2 接入矩阵

ZOTA 不能使用一种自动探针覆盖所有运行时。推荐按照“成熟自动埋点优先、关键领域显式埋点、实时系统旁路观测”的原则分层接入：

| 技术栈 | 推荐接入方式 | 第一阶段范围 | 约束 |
|---|---|---|---|
| Java/Spring Boot | OpenTelemetry Java Agent + API 手工业务 Span | HTTP、gRPC、JDBC、Redis、Kafka、线程池和异常 | Agent 与手工 Span 使用同一 OTel Context，禁止业务代码再次初始化独立 SDK |
| Go | OTel Go SDK + contrib HTTP/gRPC/数据库中间件 | HTTP、gRPC、SQL、Redis、Kafka/MQTT 和关键业务步骤 | `context.Context` 必须跨 Handler、Service、Repository 和消息处理传播 |
| TypeScript/Node.js | Node.js Auto Instrumentation + 关键业务 Span | Express/NestJS、HTTP、数据库、Redis、消息队列和异常 | 必须在业务模块加载前初始化 Instrumentation，避免漏掉模块 Patch |
| TypeScript/React Web | Browser SDK，第二阶段接入 | 页面加载、API 请求、前端异常和少量关键交互 | 只能上报到受控 Telemetry Ingress；禁止采集 Token、Cookie、表单、VIN 和敏感 URL 参数 |
| Python | `opentelemetry-distro`/自动探针 + 手工 Span | FastAPI/Flask/Django、HTTP、数据库、Celery/任务队列 | 训练、数据处理和长任务使用稳定业务 ID，不创建数小时的单一 Trace |
| C++ | OTel C++ SDK + 显式 Span/Metric | gRPC/HTTP、IPC、任务接收、关键算法阶段、文件切片和上传 | 实时线程禁止同步 Export；高频循环使用本地 Histogram 聚合 |
| ROS 2 | OTel 任务级观测 + `ros2_tracing/LTTng` 实时追踪 | 回放任务、Recorder、上传任务、模块阶段、Executor/DDS/Kernel | 不为每条 Topic Message、每个目标物或每帧传感器数据创建 Span |

建议优先级：

1. Java、Node.js 和 Python 使用成熟自动埋点快速覆盖通用远程调用。
2. Go 使用 SDK 和 contrib 中间件建立明确的 Context 传播基线；自动注入能力只做对照 PoC。
3. C++ 只在远程调用、线程/进程边界、任务边界和关键性能阶段创建 Span。
4. ROS 2 使用双轨观测：OTel 负责车云任务和模块级业务链路，`ros2_tracing/LTTng` 负责 Executor、DDS、线程调度和 Kernel 级诊断。
5. Web Browser 最后接入，先完成采集网关、隐私规则、采样策略和前后端 Trace 关联。

#### 9.3.2 统一运行时配置

所有语言统一使用以下配置模型，具体值由部署系统注入，不写死在镜像和代码仓库中：

```text
OTEL_SERVICE_NAME
OTEL_SERVICE_VERSION
OTEL_EXPORTER_OTLP_ENDPOINT
OTEL_EXPORTER_OTLP_PROTOCOL
OTEL_PROPAGATORS=tracecontext,baggage
OTEL_RESOURCE_ATTRIBUTES=
  service.namespace=zota,
  deployment.environment=...,
  region=...,
  cluster=...,
  zota.release_bundle.id=...
```

统一要求：

- 服务名来自 Service Catalog，禁止同一服务在不同语言或环境使用不同拼写。
- `service.version` 使用可追溯的 Release/Artifact 版本，不使用容器启动时间或可变 Tag。
- HTTP/gRPC 使用 W3C Trace Context，Kafka/Pulsar/MQTT 使用消息 Header 或受控 Envelope。
- 日志输出 `trace_id`、`span_id`、`service.name`、`service.version` 和必要的业务 ID。
- `campaign_id`、`release_bundle_id`、`artifact_digest` 和 `data_capture_id` 进入 Trace/Log/Event。
- `vehicle_id_hash`、`trip_id_hash`、`campaign_id` 和 `trace_id` 不进入常规 Metric Label。
- SDK 默认向本地 Agent Collector 上报，不允许普通业务服务直接绑定 Tempo、DataBuff 或 SigNoz。
- 所有 Exporter 使用异步批处理；安全关键和实时线程不等待云端遥测确认。

#### 9.3.3 多语言样板链路

第一条链路应同时覆盖同步调用、数据库、缓存和异步消息。参考范围：

```text
zota-web
  -> API Gateway
  -> Java API / ZOTA Core
  -> Go Repository Service
  -> PostgreSQL / Redis
  -> Kafka or MQTT
  -> Python Worker
  -> C++/ROS 2 Test or Replay Adapter
```

优先选择创建 Distribution、Release Bundle 或 OTA Campaign 等真实流程，而不是只验证健康检查和列表查询。样板链路至少证明：

- 前端请求进入网关后生成或继承合法 Trace Context。
- Java 到 Go 的 HTTP/gRPC 父子关系完整。
- 数据库和 Redis Span 不记录 SQL 参数、Token、VIN 或敏感 Payload。
- Kafka/MQTT Producer 和 Consumer 能使用 Context 或 Span Link 正确关联。
- Python 长任务使用 `job_id`、`data_capture_id` 等稳定主键，任务重试不会伪造同步父子关系。
- C++/ROS 2 Adapter 只建立任务级边界，不侵入安全关键实时循环。
- 任一错误可以从 Trace 定位到结构化日志、服务版本、制品摘要和最近发布。

#### 9.3.4 分阶段实施计划

**阶段 A：服务盘点和规范，2～3 个工作日**

- 输出 ZOTA Service Catalog：仓库、Owner、语言、框架、协议、数据库、消息队列、部署形态和环境。
- 画出第一条跨语言调用图，标记同步、异步、批处理、车云和实时边界。
- 发布 OTel Resource、Span、Metric、Log 和业务 ID Schema v1。
- 定义敏感字段、高基数、采样、保留和数据出境规则。

交付物：

- `zota-observability-inventory.yaml`。
- `zota-otel-semantic-conventions.md`。
- 样板链路 Sequence Diagram。
- 第一版容量和隐私预算。

**阶段 B：Collector 和云端样板，1～2 周**

- 部署 Agent + Gateway Collector、Tempo、VictoriaMetrics/Prometheus、Loki 和 Grafana。
- 先接入 API Gateway、Java，再依次接入 Go、Node.js 和 Python。
- 打通 HTTP、gRPC、PostgreSQL、Redis 和 Kafka/MQTT。
- 建立 Trace、Metric、Log、Release Bundle 和 Incident 的关联跳转。
- 注入 Collector 重启、Gateway 网络中断和 Tempo 短时不可用故障。

验收基线：

| 指标 | PoC 起始目标 |
|---|---|
| 核心同步链路上下文传播完整率 | `>= 99%` |
| 错误 Trace 保留率 | `100%` |
| 慢请求 Trace 保留率 | `>= 99%` |
| 正常请求初始采样率 | `1%～10%`，按容量调整 |
| Collector 未计量丢失 | `0` |
| 服务 P95 额外延迟 | `< 2%` |
| SDK/Agent CPU 开销 | `< 3%～5%`，按服务等级细化 |

**阶段 C：C++ 和 ROS 2 回放台架，约 2 周**

- C++ 接入任务级 Trace、阶段 Histogram 和上传状态。
- ROS 2 使用 `ros2_tracing/LTTng` Snapshot/Flight Recorder。
- MCAP 保存 Topic 和原始证据，OTel 不承载传感器大数据。
- 用 `release_bundle_id`、`data_capture_id`、`scenario_id` 和 Span Link 关联 OTel、LTTng 和 MCAP。
- 测量对 Executor、实时线程、CPU、内存、磁盘和回放吞吐的影响。

**阶段 D：L2 网关和弱网，约 2～4 周**

- 一台测试车或网关台架接入 OTA、DTC、崩溃、资源和上传任务观测。
- 验证本地 WAL、优先级队列、磁盘配额、过期和断点续传。
- 模拟 24 小时断网、弱网、Collector 重启和服务端不可用。
- 量产默认低采样；远程提升采样必须签名、限时、可审计和自动恢复。

**阶段 E：APM 后端对照和生产决策，约 2 周**

- Tempo 接收生产候选主流量。
- DataBuff/SigNoz 仅接收 `1%～5%` 的受控 Trace 副本。
- 比较查询性能、拓扑、RED 指标、成本、HA、升级、备份、SSO、RBAC 和审计。
- 对 DataBuff 额外验证 AGPL 合规、AI 证据引用、Prompt Injection 和敏感数据边界。
- 输出 Tempo 生产 ADR，以及 DataBuff/SigNoz 的采用、继续观察或淘汰结论。

阶段 A～E 是第 16 章 Phase 4 和第 17 章 PoC F 的语言级执行分解，不建立独立的第二套路线图。

业务 Span 示例：

```text
HTTP POST /api/v1/campaigns
  -> campaign.validate-policy
  -> release-bundle.resolve
  -> vehicle-cohort.resolve
  -> campaign.persist
  -> event.publish
```

不要为每个函数创建 Span。Span 应对应远程调用、消息消费、数据库操作、关键领域步骤和明显的性能边界。

Collector 可靠性要求：

- 所有跨网络 Exporter 启用重试和 `sending_queue`。
- 关键 Gateway 和车端/边缘 Agent 使用 `file_storage` WAL。
- 监控 Collector 自身队列容量、发送失败、丢弃、CPU、内存和磁盘。
- 跨数据中心或强可靠链路可以在 Collector 层之间引入 Kafka，但不应默认给每个小集群增加 Kafka。
- Agent 到 Gateway、Gateway 到 Backend 分别设置独立容量和故障预算。
- Collector 配置进入 Git，使用版本化发布、回滚和配置验证。

### 9.4 Trace 上下文和 ZOTA 语义模型

同步调用默认使用 W3C Trace Context：

```text
traceparent
tracestate
baggage
```

不同协议的传播建议：

| 协议 | 传播方式 |
|---|---|
| HTTP/REST | 标准 `traceparent`/`tracestate` Header |
| gRPC | Metadata |
| Kafka/Pulsar | Message Header |
| MQTT 5 | User Property 或受控消息 Envelope |
| WebSocket | 建连上下文 + 每条业务消息 correlation ID |
| ROS 2/DDS | 应用 Envelope、旁路元数据或 Span Link；不直接修改安全关键消息定义 |
| 离线上传 | 新建上传 Trace，通过 Link 关联采集 Trace 和 `data_capture_id` |

异步消息不能强行伪装成同步父子调用：

- 单消费者处理可继承生产端 Context。
- 批处理、聚合、多输入任务使用 Span Link。
- 长时间离线、跨行程和跨天上传应创建新 Trace，使用稳定业务 ID 关联。
- 不创建持续数小时或数天的“超长车辆 Trace”。

建议资源属性：

```text
service.name
service.namespace
service.version
service.instance.id
deployment.environment
region
cluster
host.arch
zota.change.id
zota.build.id
zota.artifact.digest
zota.release_bundle.id
zota.deployment.id
zota.campaign.id
zota.cohort.id
vehicle.id_hash
vehicle.model
vehicle.hardware_revision
ecu.id
ecu.role
trip.id_hash
data_capture.id
scenario.id
```

高基数字段约束：

- `vehicle.id_hash`、`trip.id_hash`、`trace_id`、`campaign.id` 不进入 Prometheus/VictoriaMetrics 常规 Label。
- 高基数 ID 可以进入 Trace、结构化日志、事件库和对象元数据。
- `baggage` 只放跨服务确实需要的小型非敏感上下文，不放 Token、VIN、用户数据或大对象。
- 自定义字段统一使用 `zota.*`、`vehicle.*`、`ecu.*` 和 `data_capture.*` 命名空间，并维护版本化 Schema。

采样建议：

| 场景 | 起始策略 |
|---|---|
| 云端普通请求 | Head Sampling 控制基础流量，Gateway Tail Sampling 保留错误、慢请求和关键业务 |
| 发布窗口/P1 事件 | 对受影响服务和版本临时提高采样，设置自动过期 |
| 健康检查和高频轮询 | 极低比例或直接丢弃 |
| L2 量产车常规运行 | 低比例软件 Trace + 错误/OTA/诊断事件触发 |
| L4 量产车实时链路 | 不做逐帧 Span；保留阶段聚合指标和事件触发 Flight Recorder |
| 测试车、HIL、SIL | 可提高采样，但仍要测量 CPU、内存、磁盘和时延影响 |

Tail Sampling 前必须确保同一 `trace_id` 的 Span 路由到同一采样 Collector。采样规则、保留率和临时提升策略都需要审计，不能在故障时无限制打开全量 Trace。

### 9.5 APM 后端选型与 DataBuff 判断

| 方案 | 优点 | 主要成本/限制 | ZOTA 定位 |
|---|---|---|---|
| Grafana Tempo + Prometheus/VictoriaMetrics + Loki/OpenSearch | 与现有 Grafana 体系一致；Tempo 使用对象存储；Trace、Metric、Log 可关联；支持服务图和 TraceQL | 需要运营多个后端和统一权限；完整 APM 体验需要配置 | **推荐生产主路线** |
| SigNoz | OTel 原生的一体化 Logs/Metrics/Traces/APM 体验，开箱较完整 | 引入 ClickHouse 和第二套 Dashboard/告警体系；与现有 Grafana 栈重叠 | 一体化 APM 对照 PoC |
| Apache SkyWalking | Java/APM、服务拓扑、Agent 和存量 SkyWalking 生态较成熟 | 有自身 Agent/OAP/协议体系；与纯 OTel 主线存在双模型治理成本 | Java 或已有 SkyWalking 存量时评估 |
| Jaeger | 分布式 Trace 能力清晰，适合调试和中小规模场景 | Metrics、Logs、告警和完整 APM 体验需要外部组件 | 开发测试或专项 Trace |
| DataBuff | 原生 OTLP，支持 Trace、Metrics、Logs、服务拓扑和 AI 问数/诊断；架构较轻 | 项目非常新；HA、升级、规模、租户、审计和 AI 安全需实测；AGPL-3.0；部分 eBPF/AI 应用能力仍在 Roadmap | **隔离 PoC，不作为当前生产主后端** |

DataBuff 当前判断：

- 截至 2026-08-08，`databufflabs/databuff` 创建于 2026-06-18，最新 Release 为 `v0.1.6`，发布于 2026-08-03。
- 当前仓库采用 AGPL-3.0，生产二开、网络服务和分发方式需要法务确认。
- README 描述的核心架构是 `Ingest + Apache Doris + Web`，支持 OTLP `4317/4318`，也兼容 SkyWalking gRPC `11800`。
- Trace、Metric、Log、拓扑和 AI 调查方向与 ZOTA AIOps 有价值。
- eBPF APM 和 AI 应用监控仍被标为 Roadmap，不能按已完成功能进入生产验收。
- `v0.1.6` 的 Kubernetes 安装尚不支持原地升级，需要卸载后重装，生产环境必须先验证数据持久化、备份恢复、滚动升级和回退。
- 项目年龄、Release 历史和生产案例积累不足，当前不能承担 ZOTA 唯一 APM、唯一告警或车辆数据平台。

推荐验证方式：

```text
同一套 OTel SDK/Collector
  -> 主要 Trace 流量 -> Tempo
  -> 受控采样副本 -> DataBuff
  -> 对照采样副本 -> SigNoz，可选
```

PoC 只双写一小部分 Trace，不双写全部日志和指标。比较：

- 端到端 Trace 完整率。
- 服务拓扑准确率。
- RED 指标和错误归因。
- 查询 P95/P99 和高基数属性性能。
- 1000 万、1 亿 Span 级别的存储、压缩和资源成本。
- 多租户、SSO、RBAC、审计、备份、恢复和升级。
- Collector/Backend 故障时的数据丢失和恢复。
- AI 结论的证据引用、准确率、Prompt Injection 和数据出境边界。

最终选择原则：

> 当前 ZOTA 优先使用 `OTel Collector + Tempo + VictoriaMetrics/Prometheus + Loki/OpenSearch + Grafana`。DataBuff 作为 AI 原生 APM 候选做隔离双写 PoC；只有规模、可靠性、安全、合规和迁移能力全部通过后，才讨论扩大范围。

### 9.6 L2/L4 车云双通道可观测与数采

车辆数据必须拆成两个通道：

```text
通道 A：运行可观测
应用/进程/ECU/OTA Agent
  -> OTel SDK / 轻量系统采集
  -> Vehicle OTel Agent
  -> 本地 WAL/优先级队列
  -> T-Box/车载网关
  -> mTLS OTLP
  -> Region OTel Gateway
  -> Tempo + Metrics + Logs

通道 B：智驾原始数据
CAN/CAN FD/ROS 2/DDS/Camera/LiDAR/Radar/GNSS
  -> Vehicle Data Recorder
  -> MCAP/Parquet/专用媒体格式
  -> 本地环形缓冲和事件切片
  -> 校验、压缩、加密、断点续传
  -> TOS/S3
  -> 元数据、摘要和索引进入 Event Bus/Data Catalog
```

OTel 适合：

- OTA Agent、数据上传服务、网关、诊断服务和车云 API 的调用链。
- 进程启动、崩溃、重启、CPU、内存、磁盘、网络和队列指标。
- 感知、定位、预测、规划和控制模块的阶段级延迟与错误摘要。
- 一次数据采集任务从下发、车端执行、上传、解析到入库的业务 Trace。
- 用 `data_capture.id`、`trip.id_hash` 和 `scenario.id` 关联原始文件。

OTel 不适合：

- 每帧摄像头图像、点云、Radar Detection 和高频原始 CAN 全量上报。
- 为每个目标物、每个 Topic Message 或每个算法算子创建 Span。
- 替代 ROS 2/DDS 性能追踪、MCAP、对象存储和数据目录。
- 直接从安全关键实时进程同步发送云端遥测。

L2 建议：

- T-Box/中央网关部署轻量 Vehicle Telemetry Agent。
- CAN 信号经 DBC 解码后按白名单映射到 COVESA VSS 或 ZOTA Vehicle Signal Schema。
- 常规指标在车端聚合后上传，车辆级明细不进入高基数 Metrics Label。
- OTA、DTC、崩溃、性能退化和用户授权事件触发诊断快照。
- 工程车可以提高采样，量产车默认低频、低带宽和可远程限时开启。

L4 建议：

- 智驾域控制器使用专用 Data Recorder 和本地 NVMe，不让 OTel Collector 承担大文件录制。
- ROS 2 内部调度、Executor、DDS 和 Kernel 性能问题使用 `ros2_tracing + LTTng`。
- `ros2_tracing` 使用 Snapshot/Flight Recorder 模式，事件发生时冻结前后时间窗，再转换或关联到证据包。
- MCAP 保存异构时间戳数据、Schema、附件和元数据；按场景、时间窗和触发原因切片。
- 感知到控制的在线观测只保留模块级阶段 Span 和延迟直方图，不做逐帧全链路 Trace。
- 上传调度器根据事件等级、网络、区域合规、车辆状态和成本决定立即上传、Wi-Fi 上传或延迟回传。

弱网和离线要求：

- OTel Collector WAL 只承担有限时间的遥测缓冲，不替代车辆级文件传输管理器。
- 车端队列按安全事件、OTA、诊断、性能和普通运营数据设置优先级及磁盘配额。
- 每个上传对象记录 Digest、分片、重试次数、过期时间和服务端确认状态。
- 长时间离线后按业务 ID 重建上传 Trace，不要求恢复原始长 Trace 的父子关系。
- 所有车端采集策略必须可签名、可审计、可回滚，并有 CPU、内存、磁盘、温度和带宽上限。

### 9.7 Loki 与 OpenSearch 的选择

**Loki** 更适合：

- 已采用 Grafana。
- 主要按标签和时间查询日志。
- 希望控制日志索引成本。
- Kubernetes 服务日志为主。

**OpenSearch** 更适合：

- 需要全文搜索和复杂字段分析。
- 安全日志、审计日志和调查场景较多。
- 希望在同一平台做搜索、分析和部分告警。

可采用双层设计，但应避免全量重复：

```text
常规运行日志 -> Loki，短中期保留
审计/安全/法证日志 -> OpenSearch，独立权限和较长保留
大文件/原始车辆日志 -> TOS，按事件索引
```

### 9.8 从日志到工单

完整闭环：

```text
日志/指标/链路/车辆事件
  -> 确定性检测规则
  -> Alertmanager 路由
  -> Keep 关联、去重、抑制和变更关联
  -> 生成 Incident
  -> GoAlert/OneUptime 通知值班
  -> 自动创建 War Room
  -> 自动创建或关联 Ticket
  -> AI 生成调查摘要和候选原因
  -> 人工批准 Runbook 或低风险自动处置
  -> 验证恢复
  -> 关闭 Incident
  -> 自动生成复盘草稿和改进任务
```

### 9.9 自动报告

每个事件报告至少包含：

- 影响范围和用户/车辆数量。
- 首次发生、发现、ACK、缓解和恢复时间。
- 相关变更、构建、制品和发布。
- 告警时间线和抑制记录。
- 关键日志、指标和链路链接。
- 自动化动作、审批人和执行结果。
- 根因与促成因素。
- 回滚或修复版本。
- 监控和测试缺口。
- 后续任务、负责人和截止时间。

AI 可以生成草稿，但事实字段必须从事件库、GitLab、发布平台和可观测平台读取，不能依赖模型自行回忆。

### 9.10 工单系统选择

| 场景 | 建议 |
|---|---|
| 研发缺陷、代码修复和发布任务 | GitLab Issue |
| 用户支持、服务请求、邮件入口和 SLA | Zammad |
| 项目计划、跨团队改进和治理任务 | OpenProject |
| 资产和传统 ITSM 管理 | GLPI 可评估 |

一个 Incident 可以关联多个 Ticket，但必须只有一个事件事实源。初期可以让 ZOTA Ops Incident 作为事件记录，GitLab Issue 作为修复任务。

## 10. 无人值守告警和值班

### 10.1 能力拆分

“无人值守”至少包含五层：

1. **检测**：规则或模型识别异常。
2. **关联**：去重、抑制、拓扑和变更关联。
3. **通知**：按值班表、升级策略和通信渠道触达。
4. **处置**：执行有边界的 Runbook。
5. **验证**：确认恢复，否则继续升级或回滚。

单独安装一个告警项目不能自动获得无人值守能力。

### 10.2 项目定位

**Prometheus Alertmanager**

- 负责告警分组、抑制、静默和路由。
- 不负责完整 Incident 生命周期。
- 不应承担 AI 调查和工单事实源。

**Keep**

- 适合多来源告警统一、去重、关联和工作流。
- 可作为 Alert Correlation 层评估。
- 不应替代日志存储、指标存储或强可靠 Pager。

**GoAlert**

- 聚焦值班表、升级策略和告警 ACK。
- 架构边界清晰，适合作为自建 Pager。
- 需要自行集成企业 IM、短信、电话和国内通信渠道。

**OneUptime**

- 覆盖监控、状态页、事件和值班等较广能力。
- 适合希望减少组件数量的团队做 PoC。
- 采用前需验证规模、高可用、升级、社区活跃度和与现有 Grafana/Prometheus 的重叠。

**OpsKnight**

- 值得关注的开源 On-call/Incident 项目。
- 相对较新，建议先做功能和可靠性 PoC，不直接承担生产唯一通知链路。

**Grafana OnCall OSS**

- 不建议作为新的自建值班系统。
- Grafana 官方文档显示其 OSS 项目已进入维护并归档；旧方案中如已列出，可保留作历史备选，但新建设应转向 GoAlert、OneUptime 或经验证的其他项目。

### 10.3 通知渠道

至少需要：

- 企业 IM。
- 短信。
- 电话。
- 邮件。
- 移动端 Push，可选。

重大事件不能只发群消息。Pager 必须支持：

- ACK。
- 超时升级。
- 值班替换。
- 多级联系人。
- 通知失败重试。
- 渠道健康检查。
- 完整审计。

### 10.4 自动化等级

| 等级 | 行为 | 示例 |
|---|---|---|
| L0 | 仅观察和记录 | 收集日志、创建事件 |
| L1 | 建议 | AI 给出查询和 Runbook 建议 |
| L2 | 人工批准后执行 | 扩容、重启、暂停发布 |
| L3 | 低风险自动执行 | 重试无副作用任务、切换只读副本 |
| L4 | 受限域闭环自治 | 已验证场景内自动检测、处置和回滚 |

以下动作默认不得无人审批执行：

- 签发或轮换生产发布密钥。
- 大规模车辆升级或回滚。
- 更改安全策略和 ODD。
- 删除生产数据或证据。
- 修改 ECU 安全配置。
- 绕过发布门禁。
- 对外发送事故定责结论。

## 11. War Room 设计

### 11.1 War Room 不是普通群聊

War Room 应由事件系统自动创建，并绑定：

- `incident_id`。
- 严重等级和负责人。
- 影响范围。
- 当前状态。
- 值班人员和专家。
- Dashboard、日志和链路快捷入口。
- 最近变更和发布。
- Runbook。
- 工单和时间线。

### 11.2 推荐实现

**Mattermost**

- 适合自建团队协同。
- Playbooks 可用于标准化事件流程。
- 可通过 Bot 自动创建频道、置顶信息和更新时间线。

**Matrix/Element**

- 开放协议和联邦能力较强。
- 适合需要跨组织、跨网络协同的场景。
- Incident Playbook 和工单集成需要更多二开。

**Zulip**

- 主题化讨论适合长时间事件和多线程协作。
- 可作为协同工具备选。

推荐初始路线：

```text
Incident Service
  -> 创建 Mattermost 事件频道
  -> 邀请值班组和服务 Owner
  -> 发布事件摘要、时间线和快捷操作
  -> 机器人持续同步告警、动作和验证结果
  -> 关闭时归档频道并生成复盘
```

### 11.3 War Room 命令

可以提供受控命令：

```text
/incident status
/incident impact
/incident timeline
/incident owner @user
/incident link-change <change_id>
/runbook suggest
/runbook execute <id>
/release pause <deployment_id>
/release rollback <deployment_id>
/incident resolve
```

命令必须调用统一 API，不能让聊天机器人直接持有 Kubernetes、数据库或车辆生产权限。

## 12. Runbook 与无人值守处置

### 12.1 工具选择

| 工具 | 强项 | 推荐定位 |
|---|---|---|
| AWX | Ansible 作业、Inventory、凭证和审批 | 基础设施和主机处置 |
| Rundeck | Runbook、作业和操作门户 | 运维标准操作 |
| StackStorm | 事件驱动规则和动作 | 告警触发自动化 |
| Temporal | 持久化长流程、重试和补偿 | 发布、事件和跨系统关键流程 |
| Argo Workflows | Kubernetes 批处理工作流 | K8s 内数据/测试任务 |
| n8n | 低代码系统集成 | 非关键通知和办公流程 |

关键业务流程不应只依赖低代码画布。发布、签名、车辆控制和事件状态机应使用可测试、可版本化且支持补偿的工作流。

### 12.2 Runbook 合约

```yaml
runbook:
  id: pause-rollout
  version: 3
  risk_level: medium
  inputs:
    deployment_id:
      type: string
  preconditions:
    - deployment.status in ["progressing", "degraded"]
  approvals:
    required: true
    roles:
      - release-manager
      - service-owner
  action:
    adapter: argo-rollouts
    command: pause
  verification:
    - rollout.paused == true
    - error_rate_not_increasing
  rollback:
    command: resume
  timeout: 5m
  audit:
    retain: 3y
```

### 12.3 自动处置闭环

```text
触发
  -> 校验事件状态
  -> 校验输入和权限
  -> 获取短期凭证
  -> 执行动作
  -> 采集结果
  -> 独立验证
  -> 成功则更新事件
  -> 失败则补偿/回滚
  -> 通知和升级
  -> 写入不可变审计
```

执行器和验证器最好分离，避免同一个脚本既宣布成功又负责证明成功。

## 13. 统一事件、证据和数字主线

### 13.1 必须统一的主键

```text
change_id
pipeline_id
build_id
artifact_digest
release_bundle_id
test_run_id
scenario_set_id
simulation_run_id
deployment_id
campaign_id
vehicle_id_hash
cohort_id
trip_id_hash
data_capture_id
scenario_id
trace_id
incident_id
ticket_id
runbook_execution_id
```

### 13.2 关系示例

```text
GitLab MR !102
  change_id=CH-102
      │
      ├── pipeline_id=PL-8841
      │     ├── build_id=BUILD-1902
      │     ├── test_run_id=TR-901
      │     └── artifact_digest=sha256:abc...
      │
      ├── release_bundle_id=VRB-221
      │     ├── scenario_set_id=SS-45
      │     ├── deployment_id=DEP-81
      │     └── campaign_id=CAMP-301
      │
      └── incident_id=INC-72
            ├── trace_id=7f...
            ├── data_capture_id=CAP-205
            │     ├── trip_id_hash=TRIP-HASH-91
            │     └── scenario_id=SCN-CUTIN-014
            ├── ticket_id=ISSUE-553
            └── runbook_execution_id=RBX-117
```

### 13.3 事实源

| 对象 | 事实源 |
|---|---|
| 代码和评审 | GitLab |
| 流水线执行 | GitLab CI/Jenkins，但统一索引 |
| 制品内容 | Harbor/Package Registry/TOS，以 digest 为准 |
| 云端期望状态 | GitOps 配置仓库 |
| 车辆发布 | ZOTA |
| 测试原始证据 | Evidence Store |
| 运行指标/日志/链路 | Observability Platform |
| 智驾原始数据和回放文件 | TOS/S3 + Data Catalog |
| 行程、采集任务和场景关系 | Vehicle Data Metadata Service |
| Incident 状态 | Incident Service |
| 修复任务 | GitLab/Zammad/OpenProject |
| 人员和组织 | Casdoor/企业 IdP |
| 文档和 Runbook | Git + TechDocs |

每类对象只能有一个权威状态。门户可以汇总展示，但不能偷偷复制并独立修改状态。

## 14. AI 时代的运营层

### 14.1 AI 应解决的问题

- 汇总事件上下文。
- 从日志和链路中提取异常模式。
- 关联最近变更、制品和发布。
- 检索历史相似事件。
- 推荐查询、Runbook 和负责人。
- 生成测试、发布和事件报告草稿。
- 对重复失败做聚类。
- 把确认的修复转为 MR 草稿。
- 发现监控、测试和文档缺口。

### 14.2 AI 不应成为事实源

AI 输出必须分为：

```text
Facts       来自系统 API 的结构化事实
Evidence    可打开的日志、指标、链路和文件
Inference   模型推断，包含置信度
Proposal    建议动作
Decision    人工或策略引擎批准结果
Execution   确定性系统执行结果
```

不能把推断写成事实，也不能让模型声称执行成功而不读取执行器结果。

### 14.3 推荐 AI 架构

```text
ZOTA AI Gateway
  ├── Model Gateway
  │     └── LiteLLM 或企业统一模型网关
  ├── Tool/MCP Gateway
  │     ├── GitLab Read Tool
  │     ├── Observability Query Tool
  │     ├── Artifact/Evidence Tool
  │     ├── ZOTA Release Tool
  │     └── Incident/Runbook Tool
  ├── Retrieval
  │     ├── Runbook/TechDocs
  │     ├── Postmortem
  │     └── Architecture/Service Catalog
  ├── Policy
  │     ├── RBAC/ABAC
  │     ├── Action Risk
  │     └── Approval
  └── Evaluation
        ├── Langfuse/OpenTelemetry traces
        ├── Golden incident set
        └── Accuracy/safety/cost metrics
```

### 14.4 AI 安全

必须防范：

- 日志、Issue 和聊天内容中的 Prompt Injection。
- 模型读取未授权租户或车辆数据。
- 工具返回内容被错误解释为指令。
- AI 绕过审批直接执行高风险操作。
- 敏感日志进入外部模型。
- 自动报告泄露 VIN、密钥、Token 或个人信息。

建议：

- 工具按结构化 Schema 返回数据。
- 所有外部内容都标记为不可信数据。
- 读取权限和执行权限分离。
- 默认只读，按动作申请短期授权。
- 使用脱敏和数据出境策略。
- 保存模型、Prompt、Tool Call 和结果摘要以便审计。

## 15. 智驾领域扩展

### 15.1 智驾发布对象

智驾系统的 Release Bundle 可能包含：

- 感知、预测、规划、定位和控制软件。
- 神经网络模型和推理引擎。
- 地图和地图增量。
- 标定、参数和 Feature Flag。
- 驱动、CUDA/加速库和硬件固件。
- ODD 和车辆配置。
- 场景测试、回放、SIL/HIL 和道路测试证据。

这些对象必须形成兼容矩阵，不能各自独立“最新版”上线。

### 15.2 智驾数字主线

```text
Requirement / Safety Goal
  -> Code / Model / Dataset
  -> Build / Train
  -> Artifact / Model Digest
  -> Scenario Set / Test Evidence
  -> Vehicle Release Bundle
  -> Cohort / Campaign
  -> Fleet Telemetry
  -> Incident / Replay
  -> Fix / New Scenario / Regression
```

### 15.3 数据闭环

```text
车端事件触发
  -> 本地筛选和脱敏
  -> 上传 MCAP/片段和元数据
  -> 场景挖掘
  -> 数据集版本
  -> 标注和 QA
  -> 训练和评估
  -> 模型制品
  -> 场景回归
  -> ZOTA 灰度发布
  -> Shadow Mode/车队验证
```

可借鉴的开源项目：

- ROS 2、Autoware、Apollo：智驾软件架构和研发参考。
- MCAP：高效日志容器。
- CVAT：数据标注。
- FiftyOne：数据集分析和质量。
- MLflow：实验、模型和评估管理。
- DVC/lakeFS：数据版本思路，需结合实际对象存储和规模评估。
- CARLA、SUMO、esmini、openPASS：仿真引擎。

ZOTA 需要重点自研：

- Vehicle Release Bundle。
- Scenario & Evidence Platform。
- OTA Risk Engine。
- Fleet Incident Replay。
- Vehicle/AD MCP Gateway。
- 车型、硬件、模型、地图和标定兼容矩阵。

### 15.4 L2/L4 数据类型、观测方式和存储矩阵

| 数据类型 | 典型频率/规模 | 车端处理 | 传输方式 | 云端主存储 | 与 OTel 的关系 |
|---|---|---|---|---|---|
| OTA Agent、网关和上传服务 Trace | 请求级、低到中频 | Head Sampling、错误优先、本地 WAL | mTLS OTLP | Tempo/DataBuff PoC | 原生 Span，贯通车云服务 |
| CPU、内存、磁盘、温度、网络和队列 | 秒级或分钟级 | 聚合、限频、异常提升采样 | OTLP Metrics/Remote Write | Prometheus/VictoriaMetrics | 原生 Metric，禁止车辆 ID 高基数 Label |
| DTC、崩溃、重启、升级和安全事件 | 事件级 | 本地持久化、优先级队列、去重 | OTLP Log/Event API | Loki/OpenSearch + Event Store | 日志带 `trace_id` 和稳定业务 ID |
| CAN/CAN FD 白名单信号 | 10 Hz～1 kHz，按信号而异 | DBC 解码、VSS 映射、窗口聚合、事件切片 | 批量上传或专用数据协议 | Parquet/时序湖仓/TOS | 只把聚合指标和采集任务状态送 OTel |
| Camera 原始帧/视频 | 高带宽 | 环形缓存、编码、事件前后切片 | 分片、校验、断点续传 | TOS/S3 + Data Catalog | 不进入 OTLP；用 `data_capture_id` 关联 |
| LiDAR/Radar/GNSS/IMU | 高带宽、高频 | 时间同步、压缩、切片和质量检查 | MCAP/专用格式分片上传 | TOS/S3 + Data Catalog | 不逐帧建 Span；只记录阶段延迟和质量摘要 |
| ROS 2/DDS Topic 数据 | 高频、跨进程 | MCAP Recorder、Topic 白名单和配额 | MCAP 上传 | TOS/S3 | OTel 记录 Recorder、上传和处理任务 |
| ROS 2 Executor/DDS/Kernel 调度 | 诊断期开启 | `ros2_tracing + LTTng` Snapshot/Dual Session | 诊断证据包 | Evidence Store | 用 `trace_id`/`data_capture_id` 建 Link，不转成逐事件 Span |
| 感知、预测、规划和控制阶段耗时 | 每周期产生，上传前聚合 | HDR Histogram/直方图、超阈值触发 | OTLP Metrics + 事件快照 | VictoriaMetrics + Evidence Store | 模块级 Metric/Span，不追踪每个目标物 |
| 地图、模型、标定和参数版本 | 变更或启动时 | 版本清单、Digest 和签名校验 | Release/Event API | Release Bundle/Event Store | 作为 Resource/事件属性关联，不作为 Metric Label |
| 仿真、回放和 HIL 结果 | 任务级、大文件 | 结果归一化和证据打包 | 对象上传 + 元数据 API | Evidence Store | 测试任务 Trace 关联 `scenario_id` 和制品摘要 |

统一关联关系：

```text
release_bundle_id
  -> deployment_id / campaign_id
  -> vehicle_id_hash / cohort_id
  -> trip_id_hash
  -> data_capture_id
  -> scenario_id
  -> trace_id
  -> incident_id
  -> replay_run_id / simulation_run_id
```

要求：

- `trace_id` 用于短生命周期技术调用，不能代替行程、采集任务和场景主键。
- `data_capture_id` 是一次车端采集及其文件、上传、解析和回放的稳定主键。
- `trip_id_hash` 只使用不可逆或受控映射值，原始行程和 VIN 进入独立权限域。
- MCAP、视频和点云对象写入 `release_bundle_id`、`data_capture_id`、`scenario_id`、时间范围、Schema 版本和 Digest。
- 云端解析、场景挖掘和回放创建新 Trace，通过 Span Link 关联原采集/上传 Trace。
- 自动生成 Incident 时同时固化 Trace 查询、Metric 时间窗、日志查询和原始证据 URI，避免数据保留期结束后失去证据。

### 15.5 智驾 War Room

智驾重大事件应自动加载：

- 车型、硬件版本和车辆 cohort。
- 软件、模型、地图和标定摘要。
- ODD、道路和天气标签。
- 触发条件和安全影响。
- CAN/以太网/系统日志。
- MCAP、视频和轨迹。
- 最近 OTA 和配置变更。
- 相似场景和历史事件。
- 可复现场景和仿真运行入口。

AI 可以辅助检索和总结，但安全定级、责任判断和车辆控制必须由授权人员和确定性系统完成。

## 16. 推荐落地路线图

### Phase 0：现状盘点与标准，2～4 周

- 清点 GitLab、Jenkins、Runner、制品库、TOS、日志和告警。
- 建立服务、仓库、Owner、环境和车辆平台目录。
- 定义统一 ID、标签和事实源。
- 定义制品保留、日志保留、权限和脱敏策略。
- 选择一个云服务和一个 Yocto 平台作为样板。

交付：

- Current State Map。
- Target Architecture。
- Tool Decision Record。
- Event/Evidence Schema v1。
- 两条样板链路。

### Phase 1：可信构建与制品，1～2 个月

- GitLab Runner 标准化。
- Yocto 使用 `kas` 固化配置。
- 建立 downloads/sstate/hash server。
- Harbor/TOS 制品分层。
- 接入 SBOM、漏洞扫描、签名和 digest。
- 建立 Release Bundle v1。

验收：

- 同一 commit 可复现构建。
- 测试和生产使用同一制品摘要。
- 制品可追溯到源码、构建环境和 SBOM。
- 不允许未签名候选制品进入生产。

### Phase 2：测试与仿真证据，2～4 个月

- 统一 JUnit/Allure。
- 建立 QEMU 镜像测试。
- LAVA 或 labgrid 完成板卡 PoC 并选型。
- 对接现有 HIL。
- 建立 CARLA/SUMO/esmini Adapter PoC。
- 测试证据关联 Release Bundle。

验收：

- 发布页面能看到所有必需测试和原始证据。
- 板卡测试可预约、刷写、执行、复位和回收。
- 仿真任务可复现。
- 失败可聚类到稳定的 failure signature。

### Phase 3：云端与车端发布控制，3～6 个月

- 云端使用 Argo CD 和不可变 digest。
- 使用 Argo Rollouts 做灰度和指标门禁。
- ZOTA 建立 Vehicle Release Bundle 和兼容门禁。
- 发布状态回写 GitLab/Backstage。
- 建立暂停、继续、回滚和恢复 Runbook。

验收：

- 云端和车端职责无重叠。
- 所有生产发布都有审批、证据和审计。
- 失败门禁能自动暂停。
- 车辆离线、断电和升级失败有恢复流程。

### Phase 4：OTel APM、车云观测到 Incident 闭环，4～8 个月

- 为 `zota-web/zota-repo-web -> API Gateway -> 核心服务 -> PostgreSQL/Redis/Kafka` 建立端到端 Trace 样板。
- 使用 OTel SDK/自动探针，统一 W3C Trace Context、Resource 属性、日志关联字段和领域 Span。
- 部署 Agent + Gateway Collector，启用脱敏、队列、重试、WAL、Trace ID 路由和 Tail Sampling。
- 使用 Tempo + VictoriaMetrics/Prometheus + Loki/OpenSearch + Grafana 建立生产主链路。
- 对 DataBuff 和 SigNoz 进行受控 Trace 双写 PoC，不改变业务埋点。
- 为一个 L2 网关建立低带宽运行观测，为一个 L4 回放环境建立 OTel + MCAP + `ros2_tracing` 关联。
- Loki/OpenSearch 分层，原始智驾数据进入 TOS/S3 和 Data Catalog。
- Alertmanager 路由规范。
- Keep 告警关联 PoC。
- GoAlert/OneUptime 二选一完成生产验证。
- 自动创建 Ticket 和 Mattermost War Room。
- 事件时间线和报告自动生成。

验收：

- HTTP、gRPC、数据库和消息链路的上下文传播完整率达到约定 SLO。
- 错误、慢请求、发布和 OTA 关键 Trace 可从 Grafana 关联到日志、指标、版本和 Incident。
- Collector 重启、后端短时不可用和弱网恢复演练不出现未计量的数据丢失。
- 车端 OTel 的 CPU、内存、磁盘、实时性和带宽开销满足量产预算。
- MCAP/诊断证据可通过 `data_capture_id`、`scenario_id` 和 `trace_id` 双向定位。
- P1/P2 告警具备 ACK 和升级。
- 告警关联最近变更和发布。
- War Room、Incident 和 Ticket 状态同步。
- 复盘可以追溯全部证据。

### Phase 5：受控无人值守，6～12 个月

- Runbook 合约和风险分级。
- AWX/Rundeck/Temporal 接入。
- 低风险场景自动执行和独立验证。
- AI Triage、相似事件和报告草稿。
- 建立 AI 黄金数据集和持续评测。
- 扩展车辆和智驾 Incident Replay。

验收：

- 自动化动作有前置条件、审批、验证、补偿和审计。
- AI 建议可追溯到证据。
- 自动处置失败会停止并升级，不会无限重试。
- 高风险动作保持人工批准。

## 17. 第一批 PoC 建议

不要同时验证几十个项目。建议并行开展六个边界清晰的 PoC：

### PoC A：Yocto 可信构建

```text
GitLab CI + kas + dedicated runner
  -> shared downloads/sstate
  -> QEMU testimage
  -> SBOM + Cosign
  -> Harbor/TOS
  -> Release Bundle
```

指标：

- 冷/热构建时长。
- sstate 命中率。
- 复现成功率。
- 构建失败定位时间。
- 制品和证据完整率。

### PoC B：板卡农场

对 LAVA 和 labgrid 进行二选一验证：

- 电源控制。
- 串口采集。
- 自动刷写。
- 设备租约。
- 并发和故障恢复。
- JUnit/Allure 输出。
- 与 GitLab Pipeline 关联。

### PoC C：日志到 War Room

```text
Prometheus/Loki
  -> Alertmanager
  -> Keep
  -> GoAlert
  -> Mattermost
  -> GitLab Issue
```

用三个真实故障演练：

- 云服务错误率突增。
- OTA 活动失败率异常。
- 车辆 cohort 出现同类升级故障。

### PoC D：云车双发布

- 同一变更包含云端服务和车端兼容要求。
- 云端由 Argo CD 发布。
- 车端由 ZOTA 发布。
- 统一变更 ID 和 Release Bundle。
- 验证任一侧失败时的暂停和补偿。

### PoC E：AI Incident Assistant

只读接入：

- GitLab。
- Grafana/Loki/OpenSearch。
- ZOTA 发布记录。
- Runbook 和历史复盘。

评测：

- 事实准确率。
- 引用证据完整率。
- 相似事件召回率。
- 根因候选有效率。
- 敏感信息泄露率。
- Prompt Injection 抵抗能力。

PoC 阶段不开放自动执行生产动作。

### PoC F：云端 APM 与 L2/L4 车云观测

范围：

```text
zota-web/zota-repo-web
  -> API Gateway
  -> 3 个核心服务
  -> PostgreSQL/Redis/Kafka
  -> OTel Agent + Gateway
  -> Tempo 主后端
  -> DataBuff/SigNoz 受控双写

L2 Gateway
  -> OTA/诊断/上传 Trace + 聚合 Metric

L4 Replay Rig
  -> OTel 模块级 Trace/Metric
  -> ros2_tracing Snapshot
  -> MCAP Evidence
```

验证：

- HTTP、gRPC、Kafka/MQTT 的上下文传播完整率和异步 Span Link 正确率。
- 自动探针对 Java/Node.js/Python 的覆盖率，以及 Go/C++ 手工 Span 的必要范围。
- SDK、Collector 和车端 Agent 的 CPU、内存、磁盘、实时性和网络开销。
- Collector 队列溢出、进程重启、Gateway 故障和后端不可用时的数据丢失率。
- Tempo、DataBuff、SigNoz 的查询 P95/P99、服务拓扑、RED 指标、资源成本和操作复杂度。
- DataBuff 的 SSO、RBAC、审计、备份恢复、升级回退、AGPL 合规和 AI 证据准确率。
- L2 弱网 24 小时后优先级队列、WAL 和断点续传恢复。
- L4 事件能否从告警进入 Trace，再定位到 `data_capture_id`、MCAP、`ros2_tracing` 快照和回放任务。
- 不创建逐 CAN 信号、逐 ROS Topic Message、逐传感器帧或逐目标物 Span。

产出：

- OTel Semantic Convention 与 ZOTA/Vehicle 属性 Schema v1。
- Collector Agent/Gateway 基线配置、容量模型和故障预算。
- Tempo 生产 ADR，以及 DataBuff/SigNoz 的采用、观察或淘汰结论。
- L2/L4 车端资源预算、采集白名单、隐私合规和远程调试策略。
- 从 `release_bundle_id` 到 Incident、Trace、MCAP 和 Replay 的可运行演示。

## 18. 不建议事项

### 18.1 不建议追求一个“大一统产品”

大一统容易导致：

- 多种工作负载被迫使用不合适的模型。
- 工具升级和许可证风险集中。
- 团队难以替换局部能力。
- 状态边界不清。

统一应该发生在门户、身份、数据模型、证据链和策略，而不是要求所有能力来自同一个代码仓库。

### 18.2 不建议重复建设流水线中心

GitLab CI 和 Jenkins 可以共存，但必须有明确主次。不要让同一个项目同时维护两套等价流水线和两套环境变量。

### 18.3 不建议用 Argo CD 直接做车辆 OTA

车辆不是 Kubernetes Workload，不能把弱网、离线、整车条件和 ECU 依赖简化成 Git 同步。

### 18.4 不建议让日志平台自动成为工单系统

日志索引生命周期、事件状态生命周期和修复任务生命周期不同。它们应通过 ID 关联，而不是混用一个索引或 Dashboard 代替流程。

### 18.5 不建议未经验证引入新 On-call 项目

值班系统属于关键基础设施。选型必须做：

- HA 和故障演练。
- 通知通道失败演练。
- 升级和回滚。
- 数据备份恢复。
- 值班表边界条件。
- ACK 和超时升级。
- 社区活跃度和版本维护。

### 18.6 不建议 AI 直接拥有生产超级权限

AI 只能通过受控工具调用确定性动作。每次执行都需要：

- 明确输入。
- 权限检查。
- 风险等级。
- 审批策略。
- 执行超时。
- 独立验证。
- 补偿或回滚。
- 审计记录。

## 19. 建议的产品边界

### 19.1 直接采用开源项目

- GitLab Runner。
- Yocto/OpenEmbedded、BitBake、kas。
- Harbor、ORAS、Cosign、Syft、Trivy。
- Argo CD、Argo Rollouts。
- OpenTelemetry Collector、Fluent Bit。
- Prometheus/VictoriaMetrics、Loki/OpenSearch、Tempo/Jaeger、Grafana。
- pytest、Robot Framework、CTest、Playwright。
- Allure，规模需要时引入 ReportPortal。
- LAVA 或 labgrid。
- CARLA、SUMO、esmini、openPASS。
- Alertmanager、Keep。
- GoAlert 或 OneUptime。
- Mattermost 或 Matrix/Element。
- AWX、Rundeck、Temporal。
- OPA/Kyverno、OpenBao/Vault、SOPS。

### 19.2 ZOTA 应重点二开

- Engineering/Ops Portal 插件。
- Release Bundle 和兼容矩阵。
- 云端发布与车辆 OTA 的双控制面关联。
- Scenario/Test/Evidence Adapter。
- Board/HIL/Simulation Job Adapter。
- Vehicle/Fleet Observability Schema。
- Incident Service 和统一时间线。
- War Room Bot。
- Runbook Gateway。
- AI Tool/MCP Gateway。
- OTA Risk Engine。
- Fleet Incident Replay。

### 19.3 不应重复开发

- Git 仓库和代码评审。
- 通用容器 Registry。
- 通用日志索引引擎。
- 通用指标数据库。
- 通用聊天协议。
- 通用值班日历基础能力。
- 通用 CI 执行器。
- 通用仿真物理引擎。

ZOTA 的价值应集中在车云发布、兼容、安全门禁、证据、事件和领域编排。

## 20. 最终建议

建议把目标体系定义为：

> 以 GitLab 变更为起点，以不可变制品和 Release Bundle 为交付载体，以 Argo CD 管理云端期望状态，以 ZOTA 管理车辆和 ECU 发布，以统一遥测和事件模型连接运行反馈，以 Pager、工单和 War Room 完成人机协同，以受控 Runbook 和 AI 辅助逐步实现无人值守运营。

优先建设顺序：

```text
统一 ID 和事实源
  -> Yocto 可复现构建
  -> 可信制品和证据
  -> 分层测试、板卡和仿真
  -> 云端/车端双发布控制面
  -> 统一可观测和 Incident
  -> 值班、工单和 War Room
  -> 受控 Runbook
  -> AI 辅助
  -> 低风险闭环自治
```

判断一个工具是否值得引入，应回答六个问题：

1. 它解决的是哪个单一能力域？
2. 它是否会与现有系统争夺事实源？
3. 它输出的状态和证据如何关联统一 ID？
4. 它的开源、许可、HA 和升级边界是什么？
5. 它故障时是否会阻断构建、发布或告警？
6. 如果两年后替换它，数据和流程能否迁出？

最终目标不是“安装最多的开源项目”，而是形成可追溯、可验证、可恢复、可替换、可审计的研发与运营闭环。

## 21. 开源项目与官方资料

### 21.1 开发、构建与制品

- Backstage Software Catalog：<https://backstage.io/docs/features/software-catalog/>
- Backstage Software Templates：<https://backstage.io/docs/features/software-templates/>
- Backstage TechDocs：<https://backstage.io/docs/features/techdocs/>
- GitLab CI/CD：<https://docs.gitlab.com/ci/>
- GitLab Runner：<https://docs.gitlab.com/runner/>
- GitLab Runner Executors：<https://docs.gitlab.com/runner/executors/>
- GitLab Generic Package Registry：<https://docs.gitlab.com/user/packages/generic_packages/>
- Jenkins：<https://www.jenkins.io/doc/>
- Jenkins Pipeline as Code：<https://www.jenkins.io/doc/book/pipeline/pipeline-as-code/>
- Tekton：<https://tekton.dev/docs/>
- Concourse CI：<https://concourse-ci.org/docs/>
- Zuul：<https://zuul-ci.org/docs/zuul/latest/>
- Woodpecker CI：<https://woodpecker-ci.org/docs/>
- Docker Buildx 多架构构建：<https://docs.docker.com/build/building/multi-platform/>
- Docker Buildx Kubernetes driver：<https://docs.docker.com/build/builders/drivers/kubernetes/>
- BuildKit：<https://github.com/moby/buildkit>
- GitLab Rootless BuildKit：<https://docs.gitlab.com/ci/docker/using_buildkit/>
- Google Kaniko 原归档仓库：<https://github.com/GoogleContainerTools/kaniko>
- Chainguard Kaniko 维护分支：<https://github.com/chainguard-dev/kaniko>
- Buildah：<https://github.com/containers/buildah>
- tonistiigi/xx：<https://github.com/tonistiigi/xx>
- tonistiigi/binfmt：<https://github.com/tonistiigi/binfmt>
- dockcross：<https://github.com/dockcross/dockcross>
- cross-rs：<https://github.com/cross-rs/cross>
- CROPS poky-container：<https://github.com/crops/poky-container>
- CROPS yocto-dockerfiles：<https://github.com/crops/yocto-dockerfiles>
- ZOTA 内部候选 Fork poky-container：<https://github.com/gottaBoy/poky-container>
- ZOTA 内部候选 Fork yocto-dockerfiles：<https://github.com/gottaBoy/yocto-dockerfiles>
- crosstool-NG：<https://crosstool-ng.github.io/docs/>
- Buildroot：<https://buildroot.org/>
- Yocto Project：<https://www.yoctoproject.org/>
- Yocto Documentation：<https://docs.yoctoproject.org/>
- kas Documentation：<https://kas.readthedocs.io/>
- kas-container：<https://kas.readthedocs.io/en/latest/userguide/kas-container.html>
- kas GitHub：<https://github.com/siemens/kas>
- Harbor：<https://goharbor.io/docs/>
- ORAS：<https://oras.land/docs/>
- Sigstore Cosign：<https://docs.sigstore.dev/cosign/>
- in-toto：<https://in-toto.io/>
- Syft：<https://github.com/anchore/syft>
- Trivy：<https://trivy.dev/>
- Pulp：<https://pulpproject.org/>

### 21.2 交付与策略

- Argo CD：<https://argo-cd.readthedocs.io/>
- Argo Rollouts：<https://argoproj.github.io/rollouts/>
- Flux CD：<https://fluxcd.io/>
- Open Policy Agent：<https://www.openpolicyagent.org/docs/>
- Kyverno：<https://kyverno.io/docs/>
- OpenBao：<https://openbao.org/docs/>
- External Secrets Operator：<https://external-secrets.io/>

### 21.3 测试、板卡与仿真

- LAVA：<https://docs.lavasoftware.org/lava/>
- labgrid：<https://labgrid.readthedocs.io/>
- Robot Framework：<https://robotframework.org/>
- Playwright：<https://playwright.dev/>
- Allure Report：<https://allurereport.org/>
- ReportPortal：<https://reportportal.io/>
- CARLA：<https://carla.org/>
- SUMO：<https://eclipse.dev/sumo/>
- esmini：<https://github.com/esmini/esmini>
- Eclipse openPASS：<https://eclipse.dev/openpass/>
- MCAP：<https://mcap.dev/>
- CVAT：<https://www.cvat.ai/>
- FiftyOne：<https://voxel51.com/fiftyone/>
- MLflow：<https://mlflow.org/>

### 21.4 可观测、事件和值班

- OpenTelemetry Collector：<https://opentelemetry.io/docs/collector/>
- OpenTelemetry Collector 部署模式：<https://opentelemetry.io/docs/collector/deployment/>
- OpenTelemetry Collector Agent 模式：<https://opentelemetry.io/docs/collector/deploy/agent/>
- OpenTelemetry Collector Gateway 模式：<https://opentelemetry.io/docs/collector/deploy/gateway/>
- OpenTelemetry Collector 可靠性和 WAL：<https://opentelemetry.io/docs/collector/resiliency/>
- OpenTelemetry Context Propagation：<https://opentelemetry.io/docs/concepts/context-propagation/>
- OpenTelemetry Semantic Conventions：<https://opentelemetry.io/docs/concepts/semantic-conventions/>
- OpenTelemetry Java：<https://opentelemetry.io/docs/languages/java/>
- OpenTelemetry Java Agent：<https://opentelemetry.io/docs/zero-code/java/agent/>
- OpenTelemetry JavaScript/TypeScript：<https://opentelemetry.io/docs/languages/js/>
- OpenTelemetry Browser：<https://opentelemetry.io/docs/languages/js/getting-started/browser/>
- OpenTelemetry Python：<https://opentelemetry.io/docs/languages/python/>
- OpenTelemetry Go：<https://opentelemetry.io/docs/languages/go/>
- OpenTelemetry C++：<https://opentelemetry.io/docs/languages/cpp/>
- OpenTelemetry Operator 自动注入：<https://opentelemetry.io/docs/platforms/kubernetes/operator/automatic/>
- Grafana Tempo：<https://grafana.com/docs/tempo/latest/>
- Grafana Tempo Service Graph：<https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/>
- SigNoz：<https://signoz.io/docs/>
- Apache SkyWalking：<https://skywalking.apache.org/docs/>
- DataBuff：<https://github.com/databufflabs/databuff>
- DataBuff v0.1.6：<https://github.com/databufflabs/databuff/releases/tag/v0.1.6>
- Apache Doris：<https://doris.apache.org/docs/>
- Fluent Bit：<https://docs.fluentbit.io/manual>
- Prometheus Alertmanager：<https://prometheus.io/docs/alerting/latest/alertmanager/>
- Grafana Loki：<https://grafana.com/docs/loki/latest/>
- OpenSearch Observability：<https://docs.opensearch.org/latest/observing-your-data/>
- Keep：<https://github.com/keephq/keep>
- GoAlert：<https://goalert.me/>
- OneUptime：<https://github.com/OneUptime/oneuptime>
- OpsKnight：<https://github.com/opsknight/opsknight>
- Grafana OnCall OSS 维护状态：<https://grafana.com/docs/oncall/latest/>

智驾和车端观测：

- ROS 2 tracing：<https://github.com/ros2/ros2_tracing>
- LTTng：<https://lttng.org/docs/>
- MCAP：<https://mcap.dev/>
- COVESA Vehicle Signal Specification：<https://covesa.global/project/vehicle-signal-specification/>

### 21.5 工单、War Room 和自动化

- Zammad：<https://zammad.com/en/product/features/open-source>
- OpenProject：<https://www.openproject.org/>
- Mattermost Workflow/Playbooks：<https://docs.mattermost.com/end-user-guide/workflow-automation.html>
- Matrix：<https://matrix.org/>
- Element：<https://element.io/>
- AWX：<https://github.com/ansible/awx>
- Rundeck：<https://docs.rundeck.com/>
- StackStorm：<https://docs.stackstorm.com/>
- Temporal：<https://docs.temporal.io/>
- Argo Workflows：<https://argo-workflows.readthedocs.io/>
- Argo Events：<https://argoproj.github.io/argo-events/>

## 22. 维护约定

本方案中的项目状态、许可证、版本、社区活跃度和商业版边界会持续变化。进入 PoC 或生产选型前必须：

1. 复核官方文档和最新 Release。
2. 完成许可证和供应链审查。
3. 验证社区版所需功能。
4. 完成 HA、备份、升级和灾备演练。
5. 记录 Architecture Decision Record。
6. 保留可替换的数据和接口边界。

本文不替代 `ops-automation-toolchain.md`，而是作为 SCM、Yocto、测试/仿真、制品、发布、日志、事件、无人值守和 War Room 这条专项链路的独立深化方案。

## 23. GitHub、Gitee 等代码仓中的平台型 DevOps 调研

### 23.1 调研结论

开源 DevOps 项目大致分为四类：

1. **全栈研发运营平台**：覆盖 SCM、流水线、制品、环境、发布和运维中的多个环节。
2. **云原生持续交付平台**：重点解决 Kubernetes 应用环境、工作流和发布。
3. **内部开发者平台**：聚合现有工具，提供服务目录、自服务模板和统一入口。
4. **原子工具**：只解决 CI、GitOps、制品、测试或工作流中的一个环节。

真正接近用户描述的“SCM 到 War Room”全栈开源平台不多。覆盖面最接近的国内方案是腾讯蓝鲸，但它仍然是多个子平台的组合，而不是一个可以直接替换 ZOTA 全部能力的单体产品。

### 23.2 腾讯蓝鲸 BlueKing

代码仓：

- GitHub：<https://github.com/TencentBlueKing>
- Gitee：<https://gitee.com/Tencent-BlueKing>
- BK-CI：<https://github.com/TencentBlueKing/bk-ci>
- BK-Repo：<https://github.com/TencentBlueKing/bk-repo>
- BK-SOPS：<https://github.com/TencentBlueKing/bk-sops>
- BK-JOB：<https://github.com/TencentBlueKing/bk-job>
- BK-CMDB：<https://github.com/TencentBlueKing/bk-cmdb>
- BK-Monitor：<https://github.com/TencentBlueKing/bk-monitor>
- BK-Turbo：<https://github.com/TencentBlueKing/bk-turbo>

能力覆盖：

```text
BK-CI       流水线、构建机、插件和模板
BK-Repo     通用包、Docker/OCI、Maven、npm、rpm 等制品
BK-Turbo    C/C++ 等构建加速
BK-BCS      Kubernetes 和容器管理
BK-CMDB     配置项和资产关系
BK-Monitor  采集、观测和告警
BK-JOB      脚本和文件分发
BK-SOPS     可视化运维流程编排
BK-PaaS     运维应用和插件开发平台
```

优点：

- 国内大型企业研发运营实践积累较多。
- CI、制品、CMDB、作业和标准运维之间已经形成体系。
- BK-CI 支持分布式构建机、流水线插件和模板。
- BK-Repo 支持多种制品协议、分发、晋级和扫描。
- BK-SOPS/BK-JOB 可借鉴无人值守 Runbook 的执行模型。
- 国内企业 IM、权限、私有化和复杂网络环境适配思路更贴近 ZOTA。

限制：

- 系统较重，部署、升级和二次开发需要专门团队。
- 多个模块依赖蓝鲸自身 PaaS、权限和配置体系。
- 与现有 GitLab、Harbor、Argo CD、Grafana 和 ZOTA 重叠较多。
- 引入完整蓝鲸可能形成第二套研发运营控制平面。
- BK-Turbo 是否能有效加速 BitBake/Yocto，必须针对编译器包装、任务粒度、缓存正确性和供应商工具做实测，不能按 C/C++ 加速宣传直接推断。

ZOTA 建议：

- **重点研究和借鉴，不建议现阶段整套替换。**
- 优先 PoC `BK-Turbo` 对 Yocto 中大型 C/C++ Recipe 的实际收益。
- 对比 `BK-Repo` 与 Harbor + GitLab Package Registry + TOS 的制品能力。
- 借鉴 BK-CI 插件、BK-SOPS 流程节点和 BK-JOB 执行 Agent 模型。
- 借鉴 CMDB 与事件、发布和作业关联方式。

### 23.3 Zadig

代码仓：

- GitHub：<https://github.com/koderover/zadig>
- Gitee：<https://gitee.com/koderover/zadig>
- 官方文档：<https://docs.koderover.com/>
- GitHub Release：<https://github.com/koderover/zadig/releases>
- 仓库许可证：<https://github.com/koderover/zadig/blob/main/LICENSE>

当前状态：

- 截至 2026-08-08，GitHub 主仓未归档，最近代码推送为 2026-08-07。
- 最新正式版本为 `v5.0.0`，发布于 2026-07-31。
- 当前仍是活跃项目，可以进入产品 PoC，不属于只做历史参考的停更项目。

定位：

- 面向开发者的云原生 DevOps 和持续交付平台。
- 以服务、环境、工作流、测试和发布为主要对象。
- 支持 GitLab/GitHub Webhook、Kubernetes、Helm、VM 作业和多种发布策略。
- 新版本加入 AI 代码评审、发布风险、任务编排、环境巡检和效能诊断等方向。
- 它是研发交付体验、环境和流程编排平台，不是交叉编译器、容器镜像 Builder 或通用 Runner。

优点：

- 中文体验和国内系统集成较好。
- 服务环境模型适合微服务联调和测试环境。
- 工作流、测试和发布可视化程度较高。
- 可以非侵入式接入已有测试框架。
- 高并发工作流、服务模板、环境复用和测试管理可以减少研发人员在多个工具间切换。
- 可以把已有 GitLab CI、Jenkins、Argo Workflow、Yocto Job 和自动化测试封装为统一开发者操作入口。
- AI 代码评审和发布风险能力适合做对照 PoC，但必须验证证据引用、误报率、模型成本和数据边界。

限制：

- 核心仍是云原生应用持续交付，不覆盖 Yocto 构建农场、板卡/HIL、车辆 OTA 和 War Room 全链路。
- 与 GitLab CI、Argo CD 和 Backstage 有明显能力重叠。
- 引入后需要明确谁管理环境期望状态、谁管理生产发布。
- Gitee 可能是镜像或同步滞后，版本和活跃度应以项目声明的主仓、官方文档和正式 Release 为准。
- 不应让 Zadig 成为制品摘要、SBOM、测试证据、云端 GitOps 期望状态或车辆发布活动的唯一事实源。

许可证是生产选型阻断项之一：

- 仓库 LICENSE 在 Apache License 2.0 之前增加了附加条件，GitHub API 当前也将 SPDX 标识识别为 `NOASSERTION`。
- 将 Zadig 作为独立商业产品、集成进商业产品或向其他企业分发，需要获得明确许可。
- 使用其源码运行多租户 SaaS 被明确禁止。
- 为绕过企业许可证而修改权限控制或功能启用代码受到限制。
- 维护者保留调整开源协议条件的权利，贡献代码可被用于商业目的。

因此不能在选型表中把它表述为“无附加条件的 Apache-2.0”。内部自用是否满足条件、集团多主体部署是否构成分发、客户现场部署和二次开发边界，都必须由法务和采购书面确认。

建议集成边界：

```text
Zadig
  -> 服务目录、环境、工作流、测试和发布体验
  -> 调用 GitLab CI / GitLab Runner
  -> 调用 Jenkins Yocto/硬件遗留任务
  -> 调用 Argo Workflows 仿真、数据和批处理 DAG
  -> 展示 Harbor/TOS 制品与测试证据链接

GitLab             -> SCM、MR、基础 CI 事实源
Harbor/TOS         -> 制品和大文件事实源
Argo CD            -> Kubernetes 生产期望状态和 GitOps
ZOTA               -> 车辆 OTA、策略、审批、灰度、回滚和证据
Incident/War Room  -> 生产事件、值班、通知和协作
```

ZOTA 建议：

- 作为**开发者体验和环境编排 PoC 首选之一**。
- 用一个非核心微服务项目接入现有 GitLab、测试和 Kubernetes 环境。
- 与 `Backstage + GitLab + Argo` 现有组合以及 Devtron 做同场景对照，不因界面完整就直接增加第二套控制平面。
- 重点评估工作流扩展、API、SSO、RBAC、审计、HA、备份恢复、数据导出、GitOps 共存和版本升级。
- 核查社区版与企业版功能边界，尤其是多租户、权限、审计、审批、效能和 AI 能力。
- 在 PoC 前完成许可证法务评审；许可证和商业使用范围未书面确认前，不进入生产主链路。
- 可以借鉴 UI/UX、服务模板、环境副本和测试结果展示。
- 不直接让 Zadig 接管车辆发布。

### 23.4 KubeSphere DevOps

代码仓：

- KubeSphere：<https://github.com/kubesphere/kubesphere>
- KubeSphere DevOps：<https://github.com/kubesphere/ks-devops>

定位：

- Kubernetes 多租户、应用和基础设施管理平台。
- `ks-devops` 聚焦云原生 DevOps，可结合 Jenkins/Tekton 等能力。

优点：

- Kubernetes 管理、租户、权限和 DevOps 入口较完整。
- 中文社区和私有化部署经验较多。
- 如果基础设施已经采用 KubeSphere，集成成本相对低。

限制：

- 对 Kubernetes 依赖较强。
- 不是 Yocto、板卡、车端和智驾验证平台。
- 若现有平台已经采用原生 Kubernetes + Argo CD + Grafana，引入后可能增加控制面和 UI 重复。

ZOTA 建议：

- 仅在基础设施团队计划统一采用 KubeSphere 时进入正式候选。
- 不为获得一个 DevOps 页面单独引入整个平台。

### 23.5 Devtron

代码仓：

- GitHub：<https://github.com/devtron-labs/devtron>

定位：

- Kubernetes 应用、集群、Helm、CI/CD、GitOps、可观测和安全的统一管理界面。
- 可集成 Argo CD/Flux、Trivy、Grafana 等项目。

优点：

- Kubernetes 应用调试和交付体验完整。
- 与 Argo CD 共存模式较明确。
- 适合多集群应用交付、可视化和平台团队自服务。

限制：

- 主要覆盖 Kubernetes 应用。
- 不解决嵌入式构建、板卡实验室、车辆发布和智驾证据。
- 平台功能较多，需要核对开源版和商业版边界。

ZOTA 建议：

- 可与 Zadig 二选一进行云端应用交付体验 PoC。
- 若主要诉求是 Argo CD 上层的多集群操作体验，Devtron 比重建整套门户更值得先验证。

### 23.6 Rainbond

代码仓：

- GitHub：<https://github.com/goodrain/rainbond>
- Gitee：<https://gitee.com/rainbond/Rainbond>

定位：

- 应用中心化的 Kubernetes/PaaS 平台。
- 强调源码到应用、私有化、离线交付、应用市场和复杂客户环境交付。

优点：

- 对不熟悉 Kubernetes 的开发者更友好。
- 私有化、离线、信创、ARM 和客户现场交付场景有参考价值。
- 应用模板、市场和拓扑适合标准化交付。

限制：

- 不是完整研发治理或 AIOps 平台。
- 许可证基于 Apache 2.0 但包含附加条件，必须完成法务审查。
- 与 ZOTA 云端交付、Argo CD 和应用门户可能重叠。

ZOTA 建议：

- 借鉴离线交付包、应用模板和客户现场交付经验。
- 不作为车辆 OTA 或统一 DevOps 主平台。

### 23.7 Choerodon 猪齿鱼

代码仓：

- GitHub：<https://github.com/choerodon/choerodon>

定位：

- 敏捷协作、DevOps、微服务和多云应用生命周期平台。

优点：

- 需求、迭代、开发、测试、发布和运营的全价值链思路完整。
- 适合作为研发流程和产品模型参考。

限制：

- 系统组成较多、部署较重。
- 部分公开镜像和材料较旧，正式评估前必须核查核心仓近期 Commit、Release、文档和社区支持。
- 现有 GitLab 和项目管理体系迁移成本高。

ZOTA 建议：

- 列为历史架构和流程参考。
- 不进入第一批生产 PoC。

### 23.8 DevStream

代码仓：

- GitHub：<https://github.com/devstream-io/devstream>

原始定位：

- DevOps Toolchain Manager，通过配置安装和管理 GitLab/Jenkins/Argo CD 等工具链。

当前判断：

- 公开仓库内容已经转向自然语言驱动的工作流引擎。
- GitHub 页面显示原工具链管理阶段的最近 Release 为 2023 年。
- 不能依据旧文章继续把它当作活跃的生产级 DevOps 工具链管理器。

ZOTA 建议：

- 保留其声明式工具链和插件架构作为参考。
- 不进入生产选型短名单。

### 23.9 Backstage

代码仓：

- GitHub：<https://github.com/backstage/backstage>

Backstage 不是 CI/CD 或 AIOps 引擎，而是统一开发者门户：

- Software Catalog。
- Software Templates。
- TechDocs。
- 插件和外部系统聚合。

对 ZOTA 的价值：

- 不替换 GitLab、Jenkins、Argo CD、Harbor 和 Grafana。
- 在一个入口中展示服务、Owner、流水线、测试、制品、发布、事件和文档。
- 适合作为可组合架构的上层入口。

因此，Backstage 仍是本文推荐主架构中比“大一统 DevOps 替换”风险更低的方案。

## 24. 平台型 AIOps 和 AI SRE 项目调研

### 24.1 AIOps 项目必须按能力分类

不同项目都可能自称 AIOps，但实际能力差异很大：

| 类型 | 主要能力 | 代表项目 |
|---|---|---|
| 一体化可观测与事件 | Metrics、Logs、Traces、Incident、On-call | OneUptime |
| 告警统一和关联 | 去重、抑制、关联、工作流 | Keep |
| 监控和告警平台 | 采集、规则、通知、Dashboard | Nightingale、HertzBeat |
| eBPF 可观测和 RCA | 无侵入采集、拓扑、根因线索 | Coroot、DeepFlow |
| Kubernetes 事件增强 | 告警上下文、自动处置 | Robusta |
| AI 调查 Agent | 查询多数据源、总结根因 | HolmesGPT |
| Agent 框架 | 构建和运行自定义 Agent | kagent |
| Agent 评测实验室 | 故障注入、基准和安全评测 | Microsoft AIOpsLab |
| 综合 DataOps/AIOps | 运维数据、应用和流程平台 | SREWorks |
| OS 智能运维 | OS 采集、配置、诊断和调优 | openEuler A-Ops/EulerCopilot |

### 24.2 OneUptime

代码仓：

- GitHub：<https://github.com/OneUptime/oneuptime>

覆盖：

- Uptime 和 Synthetic Monitoring。
- Logs、Metrics、Traces 和 APM。
- Incident。
- On-call 和升级策略。
- Status Page。
- Workflow。
- AI 辅助调查和修复建议。

优点：

- 是本次调研中最接近“可观测 + Incident + On-call + 状态页”的单一开源平台。
- Apache 2.0，自建路径清晰。
- 适合快速验证端到端事件响应体验。

限制：

- 不覆盖 SCM、Yocto、板卡、仿真和车辆 OTA。
- 同时替代现有 Prometheus、Loki、Grafana、Pager 和 Incident 系统的迁移风险较高。
- 全功能一体化会带来数据规模、升级、HA 和故障域集中问题。
- AI 自动开 PR 等能力必须用真实场景验证，不能仅依据 README 宣传进入生产。

ZOTA 建议：

- 作为**一体化 AIOps 对照组 PoC**。
- 用同一批故障场景与“Keep + GoAlert + Grafana”组合比较。
- 重点测试 HA、通知可靠性、数据保留、权限、审计和导出能力。

### 24.3 Keep

代码仓：

- GitHub：<https://github.com/keephq/keep>

定位：

- 开源 AIOps 和 Alert Management 平台。
- 重点解决多告警源接入、关联、去重、工作流和事件编排。

优点：

- 适合放在 Alertmanager、Grafana、云监控和 ZOTA 事件之后。
- 连接器和工作流方向与现有可组合架构匹配。
- 可以把最近变更、发布和服务拓扑加入告警上下文。

限制：

- 不是原始日志、指标和链路存储。
- 不是板卡/车辆运维平台。
- Pager、电话、短信和强可靠升级仍需专门系统。

ZOTA 建议：

- 作为**告警关联层优先 PoC**。
- 输入使用标准 Incident Event，不让每个业务直接依赖 Keep 私有模型。
- 输出接 GoAlert/OneUptime、Mattermost 和 Ticket。

### 24.4 Nightingale 夜莺

代码仓：

- GitHub：<https://github.com/ccfos/nightingale>

定位：

- 监控和告警引擎，强调多数据源、规则、事件管道和通知。
- 可配合 Categraf、Prometheus、VictoriaMetrics、Elasticsearch、Loki 和 ClickHouse。
- 当前版本提供内置 MCP/A2A 接口，且写工具默认关闭。

优点：

- 中文社区、国内通知渠道和边缘数据中心场景较友好。
- 支持分布式告警引擎，适合网络不稳定的边缘区域。
- 事件管道、自愈脚本和多数据源对 ZOTA 有参考价值。
- MCP 默认只读的边界符合 AI 运维安全方向。

限制：

- 项目自身明确说明，它不是复杂 On-call、人员排班和升级协作平台。
- 需要外部 TSDB、采集器和值班系统。
- 自愈脚本仍需补齐审批、验证、补偿和审计。

ZOTA 建议：

- 如果重视国内部署、通知和边缘监控，列为**监控告警主选候选**。
- 与 GoAlert、Keep、Mattermost 组合，而不是单独承担无人值守全链路。

### 24.5 Apache HertzBeat

代码仓：

- GitHub：<https://github.com/apache/hertzbeat>
- Gitee 官方镜像：<https://gitee.com/hertzbeat/hertzbeat>

定位：

- Apache 项目的实时可观测系统。
- 支持 Agentless 指标采集、日志接入、告警、通知、状态页、AI 和 MCP。
- 通过 YAML 模板扩展数据库、中间件、主机、网络和应用监控。

优点：

- Apache 2.0 和基金会治理。
- 对数据库、中间件、网络设备和传统基础设施覆盖较广。
- x86/ARM64、分布式 Collector 和云边模式适合边缘节点。
- 国内 IM 通知和中文使用体验较好。

限制：

- “统一监控”不等于完整 AIOps。
- On-call、Incident、War Room、复杂根因和发布关联仍需外部系统。
- Agentless 对部分高频、低延迟或车辆专用数据并不一定合适。

ZOTA 建议：

- 作为**边缘/中间件/网络设备监控 PoC 候选**。
- 与 Nightingale 二选一验证常规基础设施监控，不建议两套同时生产全量部署。

### 24.6 HolmesGPT

代码仓：

- GitHub：<https://github.com/HolmesGPT/holmesgpt>

定位：

- CNCF Sandbox 的开源 SRE 调查 Agent。
- 可连接 Kubernetes、Prometheus、Grafana、日志、数据库、云平台和事件系统。
- 支持后台 Operator Mode、部署验证、定时健康检查和调查结果回写。

优点：

- 面向生产故障调查，而不是通用聊天机器人。
- 支持多种数据源和模型。
- 适合接在 Keep、Alertmanager、Jira 或 War Room 后。
- 对大数据结果提供服务端过滤和上下文预算思路。

限制：

- CNCF Sandbox 不等于生产成熟度认证。
- 自动调查结论仍需证据引用和人工验证。
- 自动 PR 或持续 Operator 需要严格权限和成本控制。
- 对车端、Yocto 和智驾数据需要开发专用 Toolset。

ZOTA 建议：

- 作为**只读 AI Incident Assistant 首选 PoC**。
- 第一阶段只开放 GitLab、Grafana/Loki/OpenSearch 和 ZOTA 发布记录的读取。
- 禁止直接执行生产操作。

### 24.7 Robusta

代码仓：

- GitHub：<https://github.com/robusta-dev/robusta>

定位：

- Kubernetes Prometheus 告警增强。
- 提供智能分组、上下文补充、路由、变更关联和规则化自动处置。
- AI 根因分析已拆分为 HolmesGPT。

优点：

- Kubernetes 告警上下文和 ChatOps 体验较成熟。
- 可以自动附带 Pod 日志、图表和资源变更。
- 支持 Mattermost、Jira、Pager 等多种目标。

限制：

- 高度聚焦 Kubernetes。
- 不能覆盖车端、Yocto 构建、板卡和通用 IT 资产。
- 部分 UI 和平台体验可能依赖其 SaaS，需要确认自建边界。

ZOTA 建议：

- 云端服务 Kubernetes 告警可做 PoC。
- 如果采用 Keep 作为全局关联层，应避免 Robusta 与 Keep 重复维护 Incident 状态。

### 24.8 Coroot

代码仓：

- GitHub：<https://github.com/coroot/coroot>

定位：

- 基于 eBPF 的可观测/APM 和根因线索平台。
- 聚合 Metrics、Logs、Traces、Profiling、SLO、服务拓扑和部署变化。

优点：

- 对云原生服务的无侵入可观测和服务拓扑有价值。
- 预定义检查、部署对比和日志模式可降低初期配置成本。
- Apache 2.0。

限制：

- eBPF 受内核、权限、平台和安全策略限制。
- 不是值班、工单和 War Room 平台。
- 车端 ECU/RTOS、MCU 和受限 Linux 环境不能直接套用。

ZOTA 建议：

- 对 ZOTA 云端微服务做小规模 eBPF RCA PoC。
- 不替代 OTel 语义埋点和车辆领域事件。

### 24.9 DeepFlow

代码仓：

- GitHub：<https://github.com/deepflowio/deepflow>

定位：

- eBPF 网络和应用可观测。
- 提供自动 Metrics、Tracing、Profiling、标签注入和服务关系。

优点：

- 无侵入网络观测和分布式链路增强能力较强。
- 对复杂 Kubernetes、主机和网络问题有价值。
- 可以补充 OTel 手工埋点的盲区。

限制：

- 核心是数据采集和可观测，不是 Incident/On-call/AIOps 全平台。
- 社区版与企业版功能边界需要逐项核查。
- 高流量环境的资源和存储成本需要实测。

ZOTA 建议：

- 在存在明显网络链路盲区时进行专项 PoC。
- 不因为“自动追踪”而同时引入多套 eBPF Agent。

### 24.10 HoloInsight

代码仓：

- GitHub：<https://github.com/HoloInsight/holoinsight>

定位：

- 强调实时日志分析和 AI 集成的云原生可观测平台。

判断：

- 可作为国内可观测和日志分析架构参考。
- 生态、Release、部署文档、规模案例和持续维护需要进一步验证。
- 当前不进入第一优先级生产短名单。

### 24.11 SREWorks

代码仓：

- GitHub：<https://github.com/alibaba/SREWorks>
- Gitee：<https://gitee.com/alibaba/SREWorks>

定位：

- 云原生 DataOps/AIOps 平台。
- 覆盖运维数据、应用、流程和运维中心等概念。

优点：

- AIOps 数据仓库、运维数据平台和操作中心的整体方法有参考价值。
- 国内大型数据平台运维背景。

限制：

- 系统复杂，组件和基础设施依赖较多。
- 正式采用前必须核查近期 Release、Commit、Issue 响应、安装文档和升级路径。
- 与本文可组合架构中的数据、门户、工作流和可观测系统重叠明显。

ZOTA 建议：

- 作为 DataOps/AIOps 方法和数据模型参考。
- 不进入第一批生产部署 PoC。

### 24.12 openEuler A-Ops 与 EulerCopilot

代码仓：

- A-Ops Gitee：<https://gitee.com/openeuler/A-Ops>
- A-Ops AtomGit：<https://atomgit.com/openeuler/A-Ops>
- EulerCopilot：<https://gitee.com/openeuler/EulerCopilot>

当前状态：

- 原 A-Ops 聚合仓已经弃用并拆分为多个子仓。
- 项目迁移到 AtomGit。
- 组件包括 eBPF 观测、配置管理、Agent、服务端和 OS 运维工具。
- EulerCopilot 面向 openEuler 知识问答、命令生成、诊断、调优和工作流。

ZOTA 建议：

- 对 openEuler 车端/边缘系统管理、配置和诊断有专项参考价值。
- 不能把旧聚合仓直接作为完整 AIOps 产品安装。
- 评估时应定位到具体子项目和当前主仓。

### 24.13 kagent

代码仓：

- GitHub：<https://github.com/kagent-dev/kagent>

定位：

- Kubernetes 原生 AI Agent 开发、部署和管理框架。

价值：

- 可用于构建 ZOTA 自有的云原生运维 Agent。
- 提供 Agent 编排和 Kubernetes 部署思路。

限制：

- 它是 Agent 框架，不是完整可观测、Incident 或 On-call 产品。
- 车辆、Yocto、板卡和智驾工具仍需 ZOTA 自行开发。

ZOTA 建议：

- 作为 AI Gateway/Agent Runtime 技术候选。
- 与通用 Agent 框架比较后再决定，不应先有框架后找场景。

### 24.14 Microsoft AIOpsLab

代码仓：

- GitHub：<https://github.com/microsoft/AIOpsLab>

定位：

- 用于设计、开发和评估自治 AIOps Agent 的实验和基准框架。
- 支持部署微服务环境、注入故障、生成负载、导出遥测和评价 Agent。

价值：

- 不适合直接当生产 AIOps 平台。
- 非常适合建立 ZOTA AI 运维 Agent 的测试基线。
- 可借鉴故障场景、交互接口、任务评分和可复现实验。

ZOTA 建议：

- 进入 AI 运维评测工具短名单。
- 扩展 ZOTA 发布失败、队列积压、存储异常、OTA 失败和车辆事件场景。

### 24.15 已归档或不应进入生产主选的项目

**IncidentFox**

- GitHub：<https://github.com/incidentfox/incidentfox>
- 仓库已于 2026-05-31 被所有者归档并转为只读。
- 可以阅读其多 Agent、调查、知识库和沙箱设计，但不应作为新生产系统依赖。

**Grafana OnCall OSS**

- 已进入维护并归档，不应新建生产依赖。

**DevStream 原 DevOps Toolchain Manager**

- 最近公开 Release 停留在 2023 年，且仓库方向已经改变。
- 仅保留架构参考。

项目归档、停更或改变方向不代表代码毫无价值，但意味着 ZOTA 必须承担 Fork、漏洞修复、依赖升级和长期维护成本。

## 25. GitHub、Gitee 和其他代码仓的判断规则

### 25.1 先确定主仓

同一个项目可能同时存在：

- GitHub 主仓。
- Gitee 官方镜像。
- Gitee 自动同步仓。
- 社区 Fork。
- 公司内部二次开发版。
- 已迁移至 AtomGit、GitCode 或其他平台的新仓。

必须确认：

1. README 声明的主仓。
2. Release 实际发布位置。
3. Issue 和 PR 的主要活动位置。
4. 安全公告发布位置。
5. Gitee 是否只做每日同步。

例如：

- 蓝鲸和 HertzBeat 在 Gitee 有官方组织或镜像。
- Zadig 的 Gitee Release 可能落后于 GitHub/官方发布节奏。
- openEuler A-Ops 已从旧聚合仓拆分并迁移。
- 非官方 Gitee Fork 不能用于判断原项目是否活跃。

### 25.2 不以 Star 数做生产选型

Star 只能说明关注度，不能证明：

- 高可用。
- 升级兼容。
- 数据一致性。
- 安全响应。
- 大规模性能。
- 社区版功能完整。
- 值班通知可靠。

生产选型应检查：

```text
最近 12 个月有效 Release
最近 90 天核心代码 Commit
Issue 首次响应和关闭时间
安全策略和 CVE 处理
维护者数量和组织治理
安装、升级、回滚和备份文档
License 和商业版边界
用户迁移和数据导出
HA 与灾备
真实规模案例
```

### 25.3 建议项目状态分级

| 状态 | 定义 | 使用方式 |
|---|---|---|
| A 生产候选 | 活跃、文档完整、边界清晰、完成 PoC | 可进入架构评审 |
| B PoC 候选 | 能力有价值，但成熟度或适配性待验证 | 隔离环境验证 |
| C 设计参考 | 方法和代码有价值，维护或集成风险高 | 不形成生产依赖 |
| D 排除 | 归档、许可证不接受或关键需求不满足 | 不采用 |

## 26. 面向 ZOTA 的候选分级

### 26.1 DevOps 平台

| 项目 | 状态 | 适合 ZOTA 的用途 | 不适合替代 |
|---|---|---|---|
| GitLab + Backstage + Argo CD | A | 推荐主架构 | 车辆 OTA、板卡和仿真 |
| 腾讯蓝鲸 | B | 全栈方法、BK-Turbo/BK-Repo/BK-SOPS PoC | 直接整套替换现有平台 |
| Zadig | B，法务准入前仅限隔离 PoC | 开发者体验、环境和工作流 PoC | 车辆发布、统一事实源和多租户 SaaS |
| Devtron | B | Argo CD 上层应用交付体验 | Yocto、车端和智驾 |
| KubeSphere DevOps | B/C | 已有 KubeSphere 时集成 | 为单一 UI 新建平台 |
| Rainbond | B/C | 离线和客户现场应用交付参考 | 研发治理和车辆 OTA |
| Choerodon | C | 全价值链流程参考 | 新平台主选 |
| DevStream | C | 声明式工具链历史参考 | 生产工具链管理 |

### 26.2 AIOps 平台

| 项目 | 状态 | 适合 ZOTA 的用途 | 关键边界 |
|---|---|---|---|
| Keep | A/B | 告警关联和工作流 PoC | 不存原始遥测，不替代 Pager |
| HolmesGPT | B | 只读 AI 故障调查 | 不直接执行高风险动作 |
| OneUptime | B | 一体化 AIOps 对照 PoC | 验证规模、HA 和迁移 |
| Nightingale | A/B | 国内监控告警、边缘告警 | 需要独立 On-call |
| HertzBeat | A/B | Agentless 基础设施和边缘监控 | 不是完整 Incident 平台 |
| Robusta | B | Kubernetes 告警增强 | 限定云端 K8s |
| Coroot | B | 云端 eBPF RCA | 不覆盖车端和工单 |
| DeepFlow | B | 网络和链路专项可观测 | 不承担事件状态 |
| Microsoft AIOpsLab | B | AI Agent 基准和故障注入 | 不是生产平台 |
| SREWorks | C | AIOps/DataOps 方法参考 | 维护和复杂度需核查 |
| HoloInsight | C | 实时日志和 AI 架构参考 | 生态和成熟度需核查 |
| openEuler A-Ops | C/B | openEuler 专项组件 | 旧聚合仓已拆分迁移 |
| kagent | B | 自研 Agent Runtime 候选 | 不是 AIOps 产品 |
| IncidentFox | D | 仅阅读设计 | 2026-05-31 已归档 |
| Grafana OnCall OSS | D | 历史参考 | 已归档 |

## 27. 推荐新增 PoC 对比

### 27.1 DevOps 平台对比

选择同一个普通云服务，分别验证：

```text
现有基线：
GitLab CI + Argo CD + Backstage

候选 A：
Zadig

候选 B：
Devtron

参考 C：
BlueKing BK-CI/BK-Repo
```

对比指标：

- 一个新服务从模板到测试环境所需时间。
- GitLab 仓库、流水线和权限集成成本。
- 临时环境创建和回收。
- 测试结果和制品追溯。
- GitOps 状态一致性。
- API 和插件扩展难度。
- 系统自身资源和运维成本。
- SSO、RBAC、审计、备份恢复和数据导出完整性。
- 社区版/企业版边界以及许可证对内部部署、客户现场和多主体使用的影响。
- 升级、备份和故障恢复。
- 社区版功能缺口。

### 27.2 Yocto 和制品专项

```text
GitLab Runner + kas + Harbor/TOS
  对比
BK-CI + BK-Turbo + BK-Repo
```

只针对两个代表性镜像测试：

- 全量冷构建。
- sstate 热构建。
- 修改一个大型 C++ Recipe。
- 多分支并发。
- 缓存污染验证。
- SBOM、签名和制品晋级。
- x86/ARM Builder。

如果 BK-Turbo 无法在不破坏 BitBake 任务签名和可复现性的前提下带来明显收益，不应仅为统一界面迁移构建链路。

### 27.3 AIOps 组合对比

**组合 A：可组合主路线**

```text
Prometheus/Loki/OpenSearch
  -> Alertmanager
  -> Keep
  -> GoAlert
  -> Mattermost
  -> GitLab Issue
  -> HolmesGPT 只读调查
```

**组合 B：一体化对照**

```text
OneUptime
  -> Monitoring
  -> Incident
  -> On-call
  -> Status Page
  -> AI
```

**组合 C：国内监控对照**

```text
Nightingale 或 HertzBeat
  -> Keep
  -> GoAlert
  -> Mattermost
  -> HolmesGPT
```

必须用相同故障集测试：

1. 云服务错误率上升。
2. PostgreSQL 连接池耗尽。
3. Kafka 消费积压。
4. 对象存储延迟。
5. Argo Rollout 新版本回归。
6. OTA 活动失败率异常。
7. 某车辆 cohort 重复下载或安装失败。
8. 车端日志突然停止上报。

比较：

- 检测时间。
- 告警压缩率。
- 正确关联变更率。
- 通知到达和 ACK 时间。
- 调查摘要准确率。
- 人工查询次数。
- 自动化成功和误执行率。
- 事件关闭后证据完整率。
- 总资源和维护成本。

### 27.4 AI Agent 评测

使用 Microsoft AIOpsLab 的方法，加上 ZOTA 自有场景：

```text
通用 Kubernetes 故障集
  + ZOTA 云端故障集
  + GitLab/Yocto 构建故障集
  + OTA 发布故障集
  + 车辆/智驾日志调查集
```

对 HolmesGPT、自研 Agent 或其他候选统一评价：

- 故障检测准确率。
- 根因 Top-1/Top-3 命中率。
- 证据引用准确率。
- 工具调用次数。
- 平均调查时长。
- Token 和模型成本。
- 越权动作率。
- Prompt Injection 成功率。
- 无答案时正确拒绝率。
- 同一故障重复运行稳定性。

## 28. 调研后的最终选型建议

### 28.1 不整体更换现有主链路

ZOTA 已经有 GitLab、Jenkins、Argo CD、制品和可观测方向，当前最合理的做法不是再安装一个“大而全 DevOps/AIOps”并迁移全部状态，而是：

```text
保留：
GitLab + GitLab Runner/Jenkins + Harbor/TOS + Argo CD + ZOTA

增强：
Backstage/ZOTA Portal
Argo Workflows 仿真/数据工作流
Rootless BuildKit + tonistiigi/xx 多架构容器构建
Kaniko 遗留任务迁移
Yocto/kas 构建农场
统一 Evidence Model
Keep 告警关联
GoAlert/OneUptime 值班
Mattermost War Room
HolmesGPT 只读调查
AIOpsLab 评测
```

### 28.2 第一优先级借鉴项目

**DevOps 体验和流程**

- Zadig：服务、环境、工作流、测试和 AI 发布风险。
- BlueKing：CI 插件、制品、构建加速、CMDB、JOB 和 SOPS。
- Devtron：Argo CD 上层的 Kubernetes 操作和交付体验。
- Backstage：统一入口和服务目录。

**AIOps 和无人值守**

- Keep：告警关联。
- Nightingale/HertzBeat：国内监控和边缘采集候选。
- GoAlert/OneUptime：值班和升级。
- HolmesGPT：AI 调查。
- Robusta/Coroot/DeepFlow：云端专项可观测。
- AIOpsLab：Agent 安全和效果评测。

### 28.3 第一批实际验证项目

建议优先启动以下六项：

1. `Zadig vs Devtron vs 现有 Backstage/Argo` 的开发者交付体验对比。
2. `GitLab Instance Runner vs 现有 Jenkins Agent` 的 Yocto 构建专项对比。
3. `Argo Workflows vs GitLab Kubernetes Runner` 的仿真和数据 DAG 专项对比。
4. `Rootless BuildKit + tonistiigi/xx vs Kaniko` 的多架构容器构建对比。
5. `Keep + GoAlert + HolmesGPT` 的日志到 War Room 闭环。
6. `OneUptime` 作为一体化 AIOps 对照组。

CI/CD 的最终主次关系固定为：

```text
GitLab CI             默认 CI 控制面
GitLab Runner         默认通用和容器执行器，PoC 后决定新建 Yocto 任务
Jenkins               成熟 Yocto、遗留插件、固定硬件和迁移期执行后端
Argo Workflows        Kubernetes 仿真、数据、ML 和批处理后端
Argo CD/Rollouts      云端 GitOps 和渐进式交付
ZOTA                  车辆、ECU 和边缘 OTA
```

### 28.4 生产采用原则

一个候选项目只有同时满足以下条件，才能进入生产架构：

- 主仓和许可证清晰。
- 最近版本仍在维护。
- 完成 HA、备份、升级和回滚演练。
- 可接入 Casdoor/企业 IdP 和审计。
- 所有关键状态可以导出。
- 不与现有系统争夺事实源。
- 可以传播统一 `change_id`、`artifact_digest`、`deployment_id` 和 `incident_id`。
- 故障时不会同时打断发布和告警。
- AI 功能可关闭，基础确定性流程仍可工作。
- 完成至少一次真实故障演练和一次灾备演练。

仓库调研的最终结论仍然是：

> 开源世界已经具备完整蓝图所需的大部分零件，也存在蓝鲸、Zadig、OneUptime 这类覆盖较广的平台，但没有一个项目能直接、安全地覆盖 ZOTA 的云端 DevOps、Yocto、板卡/HIL、智驾仿真、车辆 OTA、可观测、值班和 War Room。最优路线是以现有主链路为骨架，选择少量项目补齐能力，并把统一事件、证据、策略和 AI 安全层掌握在 ZOTA 自己手中。
