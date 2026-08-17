# ZOTA 运维自动化工具链 — 方案分析

> 状态：提案 | 日期：2026-08-08 | 作者：AI Copilot
>
> **阅读说明**：第 1～7 章保留初版方案及当时的候选工具判断，不删除、不回退；第 8 章以后是在全仓配置核查和开源项目复核基础上的生产化增补。若两部分结论冲突，以后面的“生产化修订建议”为当前决策依据，旧方案继续作为候选池和演进记录。

## 导航

本文按“历史方案保留、生产运维修订、全生命周期蓝图、智驾领域扩展”四个层次组织：

| 范围 | 内容 | 阅读建议 |
|---|---|---|
| 第 1～7 章 | 初版运维自动化候选和三阶段方案 | 作为历史方案、候选池和演进依据保留 |
| 第 8～22 章 | ZOTA 生产运维、可观测性、值班、Runbook 和受控自治 | 作为当前生产运维决策基线 |
| 第 23～38 章 | 开发、测试、供应链、GitOps、AI 工程和平台化路线 | 作为研发到线上运营的总蓝图 |
| 第 39～54 章 | 智驾系统工程、车端、数据、模型、仿真、安全、车云和车队运营 | 作为智驾领域扩展蓝图 |

建议按角色阅读：

- 管理者和架构负责人：第 8、11、12、18、23、24、33、37、39、40、53、54 章。
- 平台、DevOps 和 SRE：第 9～22、24～33 章。
- 开发、测试和安全团队：第 23～31、34～36 章。
- 智驾系统、算法、数据和验证团队：第 39～54 章。

## 1. 背景

ZOTA 平台（zota-repo + zota-server + zeol + JetLinks）上线后，运维工作将涵盖：
- 发布巡检（漂移检测、rollout 进度、合规状态）
- 事故响应（升级失败排查、EOL 报告回溯）
- 定时报告（每日/每周车队状态汇总）
- 跨系统编排（zota-repo API → Jira → Slack → 审批）

目前这些操作依赖人工在不同页面/API 间切换，效率低且容易遗漏。本文分析可配合 autodrive 平台的运维自动化工具链。

## 2. 候选工具总览

| 工具 | 定位 | Stars | 协议 | 适合场景 |
|------|------|-------|------|---------|
| **OpenWorker** | 桌面 AI 同事 | 13.6k | MIT | Slack 交互式运维、定时巡检、跨工具编排 |
| **n8n** | 可视化工作流引擎 | 55k+ | Sustainable Use | API 编排、定时任务、条件分支、审批流 |
| **Dify** | AI 应用构建平台 | 70k+ | Apache 2.0 | 知识库问答、内部 Runbook 助手、ChatOps |
| **DataBuff** | AI 原生 APM | 新 | Apache 2.0 | 全链路追踪、AI 根因分析、自然语言问系统、多智能体巡检 |
| **OpenTelemetry** | 可观测性标准 | 7k+ | Apache 2.0 | SDK 埋点标准、OTel Collector、厂商中立 |
| **Playwright MCP** | 浏览器自动化 | — | Apache 2.0 | 前端回归验证、截图监控、UI 巡检 |
| **Grafana OnCall** | 值班轮转 | 4k+ | AGPL 3.0 | 告警路由、排班、升级策略、电话/短信通知 |
| **Temporal** | 持久化执行引擎 | 13k+ | MIT | 长时间部署流程、Saga 事务、重试/补偿 |

## 3. 工具详解

### 3.1 OpenWorker（吴恩达团队）

```
┌────────────────────────────────────────────┐
│           OpenWorker 桌面 App              │
│  ┌──────────────────────────────────────┐  │
│  │  对话界面  │  Slack @OpenWorker 触发  │  │
│  ├──────────────────────────────────────┤  │
│  │  Python Agent 引擎 (aisuite)          │  │
│  │  ├─ 文件读写    ├─ 终端命令           │  │
│  │  ├─ 25+ 连接器 ├─ MCP 客户端         │  │
│  │  └─ 定时任务   └─ 审批门控           │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

**在 autodrive 中的应用：**

| 场景 | 具体流程 |
|------|---------|
| 发布巡检 | 定时查 zota-repo 漂移 API → 异常则发 Slack |
| 事故响应 | `@OpenWorker VIN=xxx 升级失败原因` → 查 target 状态 + deploy history + EOL 报告 |
| 发布前检查 | 给定 release_bundle_id → 查兼容矩阵 + 法规合规 + 门禁 → go/no-go |
| 日常周报 | 每周汇总：新模块数、漂移趋势、升级成功率 → 生成 MD 报告 |

**优点**：本地运行、BYO 模型（支持 DeepSeek/Ollama）、审批门控（写操作需确认）
**局限**：Beta 阶段（v0.1.7），Slack 集成需 OAuth，不适合服务端无人值守长期运行

### 3.2 n8n — 可视化工作流引擎

```
┌─────────────────────────────────────────────┐
│                n8n (自部署)                   │
│  ┌───────────────────────────────────────┐   │
│  │  拖拽式工作流编辑器 (Web UI)           │   │
│  ├───────────────────────────────────────┤   │
│  │  400+ 集成节点：                       │   │
│  │  HTTP Request · Slack · Jira · Email   │   │
│  │  PostgreSQL · Webhook · Cron · AI     │   │
│  │  Code (JS/Python) · Switch · Loop      │   │
│  └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**在 autodrive 中的应用：**

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Cron    │───→│ HTTP    │───→│ Switch  │───→│ Slack   │
│ 每30分钟│    │ GET     │    │ 漂移>0? │    │ #ops    │
│         │    │ /drift  │    └────┬────┘    └─────────┘
└─────────┘    └─────────┘         │ 否 → 静默
                                   │ 是 → 继续
                              ┌────▼────┐    ┌─────────┐
                              │ HTTP    │───→│ Jira    │
                              │ POST    │    │ 创建工单 │
                              │ /deploy │    └─────────┘
                              └─────────┘
```

**优点**：自部署、可视化编排、400+ 集成、Code 节点可写自定义逻辑
**局限**：复杂状态机不如 Temporal，AI 能力需外挂（可调用 LLM API 节点）

### 3.3 Dify — AI 应用 + 知识库

```
┌─────────────────────────────────────────────┐
│              Dify (自部署)                    │
│  ┌───────────────────────────────────────┐   │
│  │  知识库 ← 导入 Runbook / 架构文档      │   │
│  ├───────────────────────────────────────┤   │
│  │  ChatBot → "MCU 刷写失败怎么办？"      │   │
│  │          → 检索知识库 → 给出操作步骤    │   │
│  ├───────────────────────────────────────┤   │
│  │  Workflow → 多步推理 + API 调用        │   │
│  └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**在 autodrive 中的应用：**

- **内部 Runbook 助手**：导入 `zota-user-guide.md`、`mcu-updater-design.md`、`ops-playbook` → 新人/值班人员直接问
- **故障诊断**：输入错误日志 → Dify 检索相似历史问题 → 给出排查步骤
- **API Agent**：自然语言 → Dify Workflow 调用 zota-repo API → 返回结构化结果

**优点**：知识库 RAG、可视化 Workflow、支持多模型、可嵌入现有前端
**局限**：复杂状态编排不如 n8n/Temporal，更多是"问答+轻量编排"

### 3.4 Playwright MCP — 浏览器自动化

**在 autodrive 中的应用：**

- **前端冒烟测试**：每次部署后自动打开 zota-repo-web → 截图关键页面 → 对比基线
- **UI 巡检**：定期检查 Dashboard/漂移页面渲染是否正常
- **E2E 验证**：下发 → 等待 → 截图 rollout 进度页 → 确认状态

**优点**：真实浏览器环境、支持截图对比、可作为 MCP Server 被 OpenWorker/Dify 调用
**局限**：仅前端层面，需要配合 API 层面的验证

### 3.5 OpenTelemetry — 可观测性标准

```
┌─────────────────────────────────────────────────────────┐
│                  OpenTelemetry 三支柱                     │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   Traces    │  │   Metrics   │  │     Logs        │  │
│  │ 全链路追踪   │  │  指标采集    │  │  结构化日志      │  │
│  │ ─────────── │  │ ─────────── │  │  ────────────── │  │
│  │ zota-repo   │  │ HTTP 延迟   │  │ 请求日志        │  │
│  │ → HawkBit   │  │ DB 查询耗时  │  │ 错误堆栈        │  │
│  │ → TOS       │  │ 下发成功率   │  │ 审计事件        │  │
│  │ → RabbitMQ  │  │ 队列积压     │  │ 部署记录        │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          │                               │
│                 ┌────────▼────────┐                      │
│                 │  OTel Collector │  (sidecar / daemon)  │
│                 └────────┬────────┘                      │
│                          │                               │
│            ┌─────────────┼─────────────┐                 │
│            ▼             ▼             ▼                 │
│      ┌─────────┐  ┌──────────┐  ┌──────────┐            │
│      │ Grafana │  │  Tempo   │  │  Loki    │            │
│      │ 仪表盘   │  │ 链路存储  │  │ 日志存储  │            │
│      └─────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
```

**在 autodrive 中的应用：**

| 场景 | 具体收益 |
|------|---------|
| **下发链路追踪** | `deploy → GetOrCreateSM → UploadArtifact → CreateDS → CreateRollout` 每一步耗时可视化 |
| **DDI 轮询监控** | 车端 `GET /DDI/.../controller/v1/{VIN}` 的延迟、成功率、错误分布 |
| **跨服务关联** | 一个 VIN 的升级请求 → zota-repo 日志 + HawkBit 日志 + TOS 日志 → 同一 TraceID 串联 |
| **性能瓶颈定位** | 发现 "下发耗时 P99 突然从 3s 涨到 30s" → 点开 Trace → 定位到 TOS UploadArtifact 超时 |
| **告警规则** | `deploy 成功率 < 95%`、`DDI 轮询 P99 > 5s`、`RabbitMQ 队列积压 > 1000` |

**Go 服务接入示例（zota-repo）：**

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// 自动注入 HTTP 服务端 trace
router.Use(func(next http.Handler) http.Handler {
    return otelhttp.NewHandler(next, "zota-repo")
})

// 关键业务 Span
func (h *Handler) Deploy(w http.ResponseWriter, r *http.Request) {
    ctx, span := otel.Tracer("zota-repo").Start(r.Context(), "deploy")
    defer span.End()
    // ... 业务逻辑
}
```

**优点**：厂商中立（CNCF 标准）、Go/Java/Python SDK 成熟、与 Grafana LGTM 栈无缝集成
**局限**：需要部署 OTel Collector + 存储后端，初期有一定运维成本

### 3.6 Temporal — 持久化执行引擎

**在 autodrive 中的应用：**

- **多阶段部署**：SM 创建 → Artifact 上传 → DS 创建 → Rollout → 等待完成 → 验证 → 通知（每步有重试/补偿）
- **Saga 事务**：灰度升级出问题 → 自动回滚 Rollout → 通知相关人
- **长时等待**：下发后等待 30 分钟 → 检查升级成功率 → 决定继续或暂停

**优点**：SDK 强类型、自动重试、持久化状态、Saga 支持
**局限**：需要独立部署 Temporal Server + Worker，Go SDK 学习成本

### 3.7 DataBuff — AI 原生 OpenTelemetry APM

```
┌──────────────────────────────────────────────────────────────┐
│                    DataBuff APM                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    AI 大脑                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │  │
│  │  │ 智能问数  │ │ 智能巡检  │ │ 运维专家  │ │ 答疑专家   │  │  │
│  │  │ NL→SQL   │ │ 自动巡检  │ │ SSH 修复  │ │ 文档问答   │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Traces   │  │ Metrics  │  │ 拓扑     │  │ 告警       │  │
│  │ OTLP/SW  │  │ RED/QPS  │  │ 服务依赖  │  │ 阈值+突变  │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
│                                                              │
│  三组件: Ingest → Doris → Web | Docker/K8s 一条命令部署      │
└──────────────────────────────────────────────────────────────┘
```

**核心能力（7 级 AIOps）：**

| 级别 | 能力 | 示例 |
|------|------|------|
| ① 看得见 | 自然语言问系统 | "最近 1 小时哪个服务最慢" → AI 查 20 个服务给出排行 |
| ② 军团协同 | 多 Agent 并发派发 | 丢任务给大脑 → 并行派给问数+巡检 → 汇总故障报告 |
| ③ 会巡检 | 服务巡检 + HTML 报告 | 81 秒生成完整巡检报告：健康分、异常日志、瓶颈分析 |
| ④ 会诊断 | 根因分析带证据链 | "service-a 瓶颈在哪" → 拓扑归因 → 下游占 73.2% |
| ⑤ 会修 | 运维专家 SSH 上机 | 容器 OOM → SSH 登机器 → 删旧容器重建 → 恢复 |
| ⑥ 会预测 | 容量健康度分析 | 分析 Redis 容量 → 98 QPS 远低于瓶颈 → 大 Key 问题 |
| ⑦ 会答疑 | 产品自带客服 | "OTel SDK 怎么接入？" → 翻文档给出端口和代码 |

**在 autodrive 中的应用：**

- **零改造接入**：zota-repo (Go otelhttp) + zota-server (Java Agent) 的 OTLP 数据直接进 DataBuff
- **AI 巡检**：定时自动巡检 zota-repo 服务 → HTML 报告推 Slack，异常自动告警
- **故障诊断**："zota-repo deploy 接口为什么慢" → AI 自动拉 Trace + 拓扑 → 定位 TOS UploadArtifact 超时
- **自然语言运维**：不用写 PromQL/SQL，"昨天下午有多少台车升级失败了？"
- **MCP 互通**：DataBuff 暴露 MCP Server → OpenWorker/Dify 可直接调用 Trace 查询

**优点**：CNCF Landscape + OTEL Vendors 双收录、OTLP + SkyWalking 双协议、AI 原生而非外挂、Docker 一条命令部署
**局限**：项目较新，社区尚小；重度依赖 Doris 存储

### 3.8 Grafana OnCall — 值班轮转 + 告警路由

```
┌──────────────────────────────────────────────────────┐
│                Grafana OnCall 告警流                   │
│                                                      │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐          │
│  │ Grafana │──→│ OnCall   │──→│ 排班表   │          │
│  │ Alert   │   │ 路由引擎  │   │ 周一: 张三│          │
│  │ /n8n    │   └────┬─────┘   │ 周二: 李四│          │
│  └─────────┘        │         └──────────┘          │
│                     │                                │
│          ┌──────────┼──────────┐                     │
│          ▼          ▼          ▼                     │
│      ┌──────┐  ┌──────┐  ┌──────────┐               │
│      │电话  │  │短信  │  │Slack/钉钉│               │
│      │通知  │  │通知  │  │/飞书     │               │
│      └──────┘  └──────┘  └──────────┘               │
│                                                      │
│  升级策略: 5min 未确认 → 升级到主管 → 15min → 经理   │
└──────────────────────────────────────────────────────┘
```

**在 autodrive 中的应用：**

- **值班轮转**：运维团队 3 人轮班，每周自动切换，假期自动调整
- **告警路由**：`deploy 失败` → 发布负责人；`DDI 异常` → 车辆通讯组
- **升级策略**：P0 告警 5 分钟未确认 → 电话通知主管 → 15 分钟 → 通知经理
- **静默窗口**：计划内维护期间自动静默，避免误报告警
- **事后复盘**：每次事故自动记录响应时间线，导出复盘报告

**优点**：与 Grafana 原生集成、支持电话/短信/Slack/钉钉/飞书、开源自部署
**局限**：需要独立部署 OnCall Engine + RabbitMQ + Redis

## 4. 推荐组合方案

### 三阶段路线

```
Phase 1 ──── 快速见效（1-2 周）────────────
│
├─ OpenWorker 本地使用
│   └─ 工程师桌面装 OpenWorker，接入 zota-repo API
│      做发布巡检、事故排查（人工触发 + Slack 交互）
│
├─ DataBuff 部署
│   └─ Docker 一条命令部署, zota-repo + zota-server OTLP 数据接入
│      开箱即得全链路追踪 + AI 自然语言查询
│
├─ Playwright MCP
│   └─ 写几个关键页面的截图脚本
│      每次部署后自动跑，作为冒烟验证
│
Phase 2 ──── 自动化编排（2-4 周）──────────
│
├─ n8n 自部署（K8s 一个 Pod）
│   ├─ 定时巡检工作流（漂移/合规/门禁）
│   ├─ 告警推 Slack/Jira
│   └─ 部署后自动验证（API + Playwright）
│
├─ Dify 自部署
│   ├─ 导入所有参考文档 → 知识库
│   └─ 嵌入 zota-repo-web（右下角 AI 助手）
│
├─ Grafana OnCall 部署
│   ├─ 排班表 + 告警路由规则
│   ├─ deploy 失败 / DDI 异常 / RabbitMQ 积压 → 自动通知值班人
│   └─ 升级策略：未确认 → 电话通知上级
│
Phase 3 ──── 深度整合（按需）──────────────
│
├─ DataBuff × OpenWorker MCP 互通
│   └─ DataBuff 暴露 MCP → OpenWorker 直接查 Trace 做根因分析
├─ Temporal（如有复杂多步骤部署需求）
├─ 自建 MCP Server
│   └─ 把 zota-repo / zota-server / zeol API
│      封装为 MCP Tools，供 OpenWorker/Dify 调用
└─ 车端 OTel
    └─ 接入 aura-ota-agent 的 DDI 轮询 + 更新流程 Trace
```

### 最终架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        运维层 (Ops Layer)                             │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │OpenWorker│ │   n8n    │ │   Dify   │ │ DataBuff │ │OnCall     │ │
│  │ AI 同事  │ │ 工作流   │ │ 知识库   │ │ AI APM   │ │值班轮转   │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘ │
│       │             │             │            │             │       │
│       └─────────────┼─────────────┼────────────┼─────────────┘       │
│                     │             │            │                      │
│            ┌────────▼─────┐ ┌─────▼────────┐ ┌─▼───────────────┐    │
│            │  MCP Server  │ │  HTTP APIs   │ │ OTLP gRPC 4317  │    │
│            │  (自建)      │ │  (已有)       │ │ (OpenTelemetry) │    │
│            └──────┬───────┘ └──────┬────────┘ └──────┬──────────┘    │
│                   │               │                   │              │
├───────────────────┼───────────────┼───────────────────┼──────────────┤
│              平台层 (Platform Layer)                    │              │
│                   │               │                   │              │
│  ┌────────────────▼───────────────▼───────────────────▼────────────┐ │
│  │  zota-repo     │  zota-server    │  zeol    │  JetLinks         │ │
│  │  (otelhttp)    │  (Java Agent)   │          │                   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  zota-repo-web (内嵌 Dify AI 助手)                             │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## 5. 投入产出分析

| 阶段 | 投入 | 产出 |
|------|------|------|
| Phase 1 | 个人装 OpenWorker + OTel 接入（3-5 行代码改动）+ Playwright 脚本（3-5 天） | 日常巡检效率提升 50%+，全链路 Trace 可视化，冒烟测试自动化 |
| Phase 2 | 部署 n8n + Dify（1-2 天）+ 写工作流 + Grafana 告警规则（3-5 天） | 巡检全自动、告警自动推、新人可自助查 Runbook、异常秒级发现 |
| Phase 3 | 写 MCP Server（3-5 天）+ Temporal 接入 + 车端 OTel（按需） | 工具间深度互通、复杂部署流程可靠执行、端到端全链路可观测 |

## 6. 建议

1. **立即开始**：工程师本地装 OpenWorker，把日常巡检命令模板化
2. **短期目标**：n8n 部署到 K8s（与 zota-repo 同集群），第一个工作流：`定时漂移巡检 → Slack 告警`
3. **按需深入**：Dify 知识库等文档积累够 10+ 篇再上；Temporal 等出现第一个复杂 Saga 需求再引入
4. **自建 MCP Server**：用 Go 写一个轻量 MCP Server，暴露 zota-repo 的核心读 API（查模块/查漂移/查下发历史），这是所有 AI 工具的统一入口

## 7. 参考

- [OpenWorker](https://github.com/andrewyng/openworker) — v0.1.7, MIT
- [n8n](https://github.com/n8n-io/n8n) — v1.x, Sustainable Use License
- [Dify](https://github.com/langgenius/dify) — v1.x, Apache 2.0
- [DataBuff](https://github.com/databufflabs/databuff) — AI-native OTEL APM, Apache 2.0, 入选 CNCF Landscape + OTEL Vendors
- [OpenTelemetry Go SDK](https://github.com/open-telemetry/opentelemetry-go) — Apache 2.0
- [otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) — HTTP 自动插桩
- [Playwright MCP](https://github.com/microsoft/playwright-mcp) — Apache 2.0
- [Grafana OnCall](https://github.com/grafana/oncall) — AGPL 3.0
- [Temporal](https://github.com/temporalio/temporal) — MIT

---

## 8. 生产化修订建议

### 8.1 当前结论

初版方案中的工具和思路继续保留，但 ZOTA 上线后的主线不应是“先部署 AI Agent，再让 Agent 直接操作线上”，而应调整为：

1. 先建立可靠的指标、日志、Trace、事件和审计数据底座。
2. 用确定性规则完成告警、抑制、去重、值班升级和标准恢复。
3. 把 Runbook 做成可测试、幂等、限权、可回滚的执行单元。
4. AI 首先承担只读调查、证据汇总、历史检索和建议生成。
5. 只有经过长期验证的低风险动作，才逐步进入自动执行。
6. 车辆批量控制、证书吊销、数据库修复等高风险动作长期保留人工决策。

当前推荐主线：

```text
应用 / 车辆 / 基础设施
        |
        v
OpenTelemetry Collector
        |
        +--> Prometheus --> Alertmanager -------------------+
        |                                                   |
        +--> Loki                                            v
        |                                             GoAlert 值班升级
        +--> Tempo                                           |
        |                                                    v
        +--> Grafana                                   飞书/Slack/电话
                                                             |
                                                             v
                                              HolmesGPT 只读调查与证据汇总
                                                             |
                                                             v
                                              受控 Runbook / 审批 / Argo CD
```

Keep 可在告警规模和来源明显增加后插入 Alertmanager 与 GoAlert 之间，负责跨源聚合、去重、富化和相关性分析。它不是第一阶段硬依赖。

### 8.2 范围

本文覆盖：

- ZOTA 服务端、管理端、OTA 控制面、制品链路和车辆侧的可观测性。
- 上线巡检、告警路由、值班升级、事故协同和复盘。
- 确定性自动恢复、受控 Runbook 和 AI 辅助调查。
- 私有 ChatOps/IM 的选型边界。
- 发布验证、容量治理、安全审计和持续运营指标。

本文暂不直接实施：

- 修改现有 Prometheus、Alertmanager、Kubernetes 或应用代码。
- 一次性引入本文列出的全部组件。
- 让大模型持有生产集群管理员、数据库写入或车辆控制权限。
- 用 AI 判断替代 OTA 发布门禁、安全门禁或法规审批。

## 9. 现状核查与上线阻塞项

以下问题来自当前仓库配置核查，应在生产上线前进入 Phase 0 整改清单。

### 9.1 ZOTA 告警规则未被加载

- `monitoring/prometheus.yml:5` 只加载 `alert-rules.yml`。
- `monitoring/docker-compose-monitoring.yml:8` 只挂载 `alert-rules.yml`。
- `monitoring/prometheus/zota-alerts.yml` 在当前 Compose 监控栈中实际不会生效。

风险：文件存在容易造成“已经配置告警”的错觉，但真实故障不会触发通知。

建议：

- 明确 Compose 和 Kubernetes 两套监控入口，避免同一套规则散落在多个目录。
- 用 `promtool check rules` 进行 CI 校验。
- 启动后通过 Prometheus Rules API 验证规则已加载，而不是只检查文件存在。

### 9.2 Compose Prometheus 未抓取 ZOTA 核心服务

当前 `monitoring/prometheus.yml` 包含 JetLinks、Redis、Postgres、nginx 和 hawkBit，但没有：

- `zota-repo`
- `zota-server`
- `zeol`
- 车辆遥测聚合服务

风险：即使规则加载成功，也可能因为没有时序数据而永远不触发。

建议：

- Compose 环境补齐静态抓取目标。
- Kubernetes 环境统一采用 Prometheus Operator，并确认 `serviceMonitorSelector`、namespace selector 和标签匹配。
- 为每个服务建立 `up`、HTTP RED、依赖健康、业务关键指标四类最小仪表盘。

### 9.3 漂移告警指标名不一致

- 告警使用 `zota_repo_drift_vehicles`。
- 实际指标定义为 `zota_repo_drift_vehicles_total`，见 `zota-repo/internal/metrics/metrics.go:44`。

建议：

- 修正规则并增加规则单元测试。
- Gauge 不建议使用 `_total` 后缀，后续可规划兼容迁移，但不要在上线前无兼容地直接改名。

### 9.4 告警严重级别与路由不一致

- ZOTA 告警规则使用 `page` 和 `warning`。
- Alertmanager 仅对 `severity=critical` 配置专用路由。
- `monitoring/alertmanager/alertmanager.yml:16` 的接收器没有启用真实 webhook、邮件或电话渠道。

建议统一为：

| 严重级别 | 含义 | 默认动作 |
|---|---|---|
| `critical` | 用户或车队正在受到重大影响，需要立即处理 | 电话/短信/IM，进入值班升级 |
| `warning` | 有风险或局部退化，需要工作时间内处理 | IM + 工单 |
| `info` | 状态变化或趋势提示 | 事件流/日报，不打扰值班 |

`page` 可以保留为兼容标签，但应在进入 Alertmanager 时规范化为 `critical`。

### 9.5 指标高基数风险

`zota-repo/internal/metrics/metrics.go` 当前存在：

- 直接使用 `r.URL.Path` 作为 HTTP 指标标签。
- 使用 VIN 作为 `zota_repo_reconciliation_sync_total` 标签。

风险：

- VIN 数量随车队线性增长。
- 原始 URL 可能包含资源 ID、VIN、版本号等动态片段。
- Prometheus 时序数量和内存、磁盘成本可能快速失控。

建议：

- HTTP `path` 改为路由模板，例如 `/api/v1/vehicles/:vin`。
- Prometheus 指标只保留车型、区域、渠道、结果等有限枚举维度。
- VIN、制品 ID、rollout ID 放入日志、Trace attributes 或事件存储，不进入常规指标标签。
- 建立每个 metric 的 series 数量和 label value 数量监控。

### 9.6 车辆指标没有车队聚合路径

`aura-ota-agent/internal/metrics/exporter.go:96` 只在单车本地暴露 `/metrics`。生产环境通常无法由中心 Prometheus 直接抓取每台车。

建议优先级：

1. 通过现有车云消息链路上报聚合事件。
2. 服务端把车辆事件转换为低基数车队指标。
3. 需要逐车调查时，把 VIN 保存在结构化日志/事件库中。
4. 只有网络、安全和成本模型都经过论证后，才考虑受控 remote-write。

不建议直接让中心 Prometheus 穿透网络逐车抓取。

### 9.7 ServiceMonitor 所属关系不统一

- `zota-repo/k8s/base/servicemonitor.yaml` 位于 `zota` namespace。
- `monitoring/prometheus/servicemonitors.yaml` 中同名对象位于 `monitoring` namespace。

建议确定唯一所有者：

- 应用仓库负责 Service 和指标端点。
- 平台监控仓库负责 ServiceMonitor/PodMonitor、规则和告警路由。
- 或者全部随应用部署，但必须建立统一标签和 namespace selector 约定。

同一对象不应由两套清单重复管理。

### 9.8 健康探针没有区分语义

当前 `zota-repo` 的 liveness 和 readiness 都访问 `/health`，且没有 `startupProbe`。

建议拆分：

- `/livez`：进程是否存活，不依赖外部数据库。
- `/readyz`：是否具备接收真实流量的条件，可检查必要依赖。
- `/startupz`：初始化、迁移、缓存预热是否完成。

数据库短暂不可用不应立即触发无限重启；readiness 负责摘流，liveness 只处理进程失活或不可恢复死锁。

### 9.9 上线前最低完成标准

在引入 AI 或告警聚合平台前，必须先满足：

- 所有核心服务都能被稳定抓取。
- ZOTA 告警规则真实加载并有测试告警。
- 至少一个真实通知渠道和一个兜底渠道可达。
- 告警有 owner、severity、runbook、dashboard 和 source link。
- 关键日志具备 `trace_id`、`request_id`、`release_id`、`rollout_id`。
- 不再把 VIN 和原始动态 URL 放进 Prometheus 高基数标签。
- 备份恢复、发布回滚和证书轮换至少完成一次演练。

## 10. SLI、SLO 与错误预算

“无人值守”不能以告警数量为中心，应以服务目标和用户影响为中心。

### 10.1 服务级 SLI

| 范畴 | 建议 SLI | 初始目标建议 |
|---|---|---|
| 控制面可用性 | 关键读写 API 成功请求比例 | 月度 99.9%，上线后按基线校准 |
| 控制面延迟 | 发布、查询、审批 API 的 P95/P99 | 按接口分类，不用全局平均值 |
| 发布可靠性 | 合法发布请求成功创建 rollout 的比例 | 99.9% |
| 车辆触达 | 在约定窗口内收到任务的在线目标比例 | 按网络环境和车型分层 |
| OTA 成功率 | 在发布窗口内完成且校验成功的车辆比例 | 按 release/channel/model 分层 |
| OTA 停滞率 | 超过阶段时限未前进的车辆比例 | 趋近 0，按阶段定义阈值 |
| 制品完整性 | 签名、哈希、下载校验成功比例 | 100%，失败即阻断 |
| 审计完整性 | 高风险操作存在操作者、审批、前后状态和结果 | 100% |
| 恢复能力 | 备份恢复、回滚演练成功率 | 每季度 100% 完成演练 |

以上数字是初始目标，不应脱离真实车队网络、发布频率和业务风险直接固化。

### 10.2 OTA 发布应采用分层 SLO

不能只看全局成功率。至少按以下维度切分：

- 环境：测试、预生产、生产。
- 发布渠道：内测、灰度、正式。
- 车型/硬件批次。
- ECU/MCU/软件模块。
- 网络类型和区域。
- release、distribution set、rollout。

对单个 VIN 的调查使用事件和日志；对 SLO 和告警使用聚合维度。

### 10.3 错误预算策略

建议把错误预算直接连接到发布策略：

| 错误预算状态 | 发布策略 |
|---|---|
| 充足 | 正常发布，允许扩大灰度 |
| 消耗过快 | 降低并发，延长观察窗口 |
| 接近耗尽 | 只允许缺陷修复和安全更新 |
| 已耗尽 | 暂停非必要发布，优先修复可靠性 |

AI 可以解释预算消耗原因，但不得单独决定绕过门禁。

## 11. 目标架构

### 11.1 分层结构

```text
┌────────────────────────────────────────────────────────────────────┐
│ 业务与边缘层                                                       │
│ zota-repo / zota-server / zeol / hawkBit / JetLinks / OTA Agent   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ metrics / logs / traces / events
┌──────────────────────────────▼─────────────────────────────────────┐
│ 采集与标准化层                                                     │
│ OpenTelemetry Collector / Prometheus exporters / event gateway     │
└───────────────┬──────────────────────┬─────────────────────────────┘
                │                      │
┌───────────────▼──────────────┐  ┌────▼─────────────────────────────┐
│ 可观测性与证据层             │  │ 发布与审计事件层                 │
│ Prometheus / Loki / Tempo     │  │ PostgreSQL/事件存储/对象存储     │
│ Grafana / recording rules     │  │ rollout、车辆、审批、变更事件   │
└───────────────┬──────────────┘  └────┬─────────────────────────────┘
                │ alerts               │ context
┌───────────────▼───────────────────────▼─────────────────────────────┐
│ 告警与事故层                                                       │
│ Alertmanager -> [Keep 可选] -> GoAlert -> IM/电话/邮件/工单         │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ incident context
┌──────────────────────────────▼─────────────────────────────────────┐
│ 调查与知识层                                                       │
│ HolmesGPT（只读）/ Dify Runbook RAG / 历史事故与变更检索           │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ approved action request
┌──────────────────────────────▼─────────────────────────────────────┐
│ 执行与治理层                                                       │
│ Argo CD / Argo Rollouts / Robusta / 受控 K8s API / Temporal（可选）│
│ RBAC / 审批 / 幂等 / 限流 / 验证 / 回滚 / 审计                     │
└────────────────────────────────────────────────────────────────────┘
```

### 11.2 每层只保留一个事实源

| 信息 | 事实源 |
|---|---|
| 实时指标与告警状态 | Prometheus/Alertmanager |
| 日志 | Loki 或确定的日志平台 |
| Trace | Tempo 或确定的 Trace 平台 |
| 值班表与升级状态 | GoAlert |
| 发布期望状态 | Git/Argo CD |
| rollout 业务状态 | ZOTA/hawkBit 业务库和事件 |
| 事故记录 | 工单/事故系统 |
| Runbook 定义 | Git |
| AI 调查报告 | 事故附件，不作为事实源 |

避免 Keep、GoAlert、n8n、IM 和工单系统各自维护一套互相冲突的事故状态。

### 11.3 统一事故事件信封

所有告警、变更、调查和动作应使用可关联的数据结构：

```json
{
  "event_id": "uuid",
  "event_type": "alert.firing",
  "occurred_at": "RFC3339",
  "environment": "production",
  "service": "zota-repo",
  "severity": "critical",
  "fingerprint": "stable-dedup-key",
  "release_id": "optional",
  "rollout_id": "optional",
  "vehicle_scope": {
    "model": "optional",
    "region": "optional",
    "count": 0
  },
  "trace_id": "optional",
  "dashboard_url": "optional",
  "runbook_id": "optional",
  "actor": {
    "type": "system|human|ai",
    "id": "subject"
  },
  "evidence": [],
  "correlation_id": "incident-or-change-id"
}
```

默认不在通知正文中暴露完整 VIN、证书、Token 或敏感车辆数据。

## 12. 自动化自治等级

### 12.1 L0：平台自动恢复

适用动作：

- Kubernetes restart、HPA、PDB、节点迁移。
- 客户端和服务端有限次数重试。
- 熔断、超时、隔离和限流。
- Argo Rollouts 基于明确指标的自动暂停或自动回滚。

要求：动作由确定性策略触发，不依赖大模型判断。

### 12.2 L1：确定性 Runbook 自动执行

适用动作：

- 重启单个无状态 Pod。
- 暂停单个异常 rollout。
- 清理明确可重建的临时缓存。
- 对指定 consumer 执行受限扩容。
- 重新执行幂等的只读同步或索引刷新。

要求：

- 白名单动作。
- 作用域上限。
- 幂等。
- 执行前检查。
- 执行后验证。
- 失败回滚或停止。
- 冷却时间。
- 全量审计。

### 12.3 L2：AI 只读调查

AI 可以：

- 查询指标、日志、Trace、Kubernetes events。
- 关联 Git commit、部署事件、rollout 和历史事故。
- 生成时间线、候选根因和验证步骤。
- 推荐已审核 Runbook。
- 生成交接摘要和复盘草稿。

AI 不可以：

- 使用通用 shell 任意执行生产命令。
- 持有 unrestricted kubeconfig。
- 写数据库或直接控制车辆。
- 在没有证据的情况下关闭事故或宣告恢复。

### 12.4 L3：审批后执行

适用动作：

- 暂停或恢复 rollout。
- 回滚一个明确 release。
- 临时扩容。
- 切换受控流量。
- 执行影响有限目标集合的补偿任务。

要求：

- 双人或职责分离审批。
- 展示动作影响范围、预期变化和回滚方式。
- 审批有时效，参数变更后必须重新审批。
- 执行身份是 Runbook 服务账号，不是 AI 身份。

### 12.5 L4：仅人工决策

长期禁止无人自动执行：

- 批量车辆升级、回滚或控制命令。
- 大规模证书吊销、密钥轮换或信任根变更。
- 数据库手工修复、批量删除和不可逆迁移。
- 绕过签名、兼容性、法规或安全门禁。
- 全车队紧急策略变更。
- 修改审计记录或证据。

AI 可提供证据和方案，但最终动作必须由授权人员发起和确认。

## 13. 工具分层与选型结论

### 13.1 可观测性底座

| 工具 | 当前建议 | 可借鉴能力 | 边界 |
|---|---|---|---|
| OpenTelemetry | 采用 | 统一采集、上下文传播、厂商中立 | 不是存储和告警产品 |
| Prometheus | 采用 | 指标、规则、recording rules、SLO | 不存逐车明细 |
| Loki | 采用或对接现有日志平台 | 结构化日志和 Trace 关联 | 控制高基数字段和保留周期 |
| Tempo | 采用或对接现有 Trace 平台 | 跨服务调用链 | 采样策略需按错误和关键链路设计 |
| Grafana | 采用 | 仪表盘、探索和统一入口 | 不作为值班排班事实源 |
| Coroot | 备选替代方案 | 服务拓扑、eBPF、SLO、RCA | 与完整 LGTM 同时部署会重复建设 |
| DataBuff | 实验 | 自然语言问数、AI 巡检和诊断交互 | 项目较新，不进入生产写路径 |

决策：首期优先完善现有 Prometheus/Grafana，并补齐 Loki、Tempo 和 OTel Collector。Coroot/DataBuff 用隔离环境做对比验证，不在首期叠加两个 APM 主栈。

### 13.2 告警、值班与事故

| 工具 | 当前建议 | 可借鉴能力 | 边界 |
|---|---|---|---|
| Alertmanager | 采用 | 抑制、分组、静默、基础去重和路由 | 不负责完整排班和事故协同 |
| GoAlert | 推荐 | 排班、升级链、确认、通知 | 需要与国内电话/IM 渠道做集成验证 |
| KeepHQ Keep | Phase 2 评估 | 多源告警聚合、富化、相关性、工作流 | Elastic License 2.0，需法务和部署评估 |
| OneUptime | 替代型评估 | 监控、状态页、事故和值班一体化 | 应作为整套替代方案评估，不与所有组件叠加 |
| Grafana OnCall OSS | 不再新引入 | Slack 集成、排班和升级 UX | 到 2026-08-08 上游仓库已归档 |
| OpenDuty | 仅参考 | 简单排班和升级模型 | 上游已归档，不能作为生产基础 |

推荐演进：

```text
首期：Alertmanager -> GoAlert -> 飞书/Slack/电话
中期：Alertmanager -> Keep -> GoAlert -> 多渠道
```

Keep 负责事件相关性，GoAlert 负责“现在应该叫醒谁”。两者不要重复维护排班。

### 13.3 确定性自动化与发布控制

| 工具 | 当前建议 | 适用场景 |
|---|---|---|
| Argo CD | 推荐 | GitOps、期望状态、变更审计、受控同步 |
| Argo Rollouts | 推荐 | 灰度、Canary、自动暂停和指标驱动回滚 |
| Robusta | 推荐评估 | Kubernetes 告警富化、事件响应和受控 playbook |
| Temporal | 按需 | 长时间 OTA 工作流、重试、补偿、Saga |
| StackStorm | 备选 | 事件驱动自动化、大量成熟 action/integration |
| Rundeck | 备选 | 人工触发的受控作业、自助运维和权限治理 |
| n8n | 集成层采用 | Jira、飞书、Slack、邮件、报表和业务 API 编排 |

n8n 不承担以下职责：

- 核心 OTA 状态机。
- 数据库事务补偿。
- 集群管理员操作。
- 高风险车辆控制。
- 唯一审计事实源。

Temporal 只有在现有业务状态机无法可靠处理数小时/数天等待、重试和补偿时再引入，避免过早增加平台复杂度。

### 13.4 AI 调查与知识

| 工具 | 当前建议 | 可借鉴能力 | 边界 |
|---|---|---|---|
| HolmesGPT | 推荐试点 | Kubernetes/SRE 调查、证据汇总、工具调用 | 默认只读，输出必须附证据 |
| Dify | 采用或评估 | Runbook RAG、文档问答、内部助手 | 不作为事故控制面 |
| OpenWorker | 工程师侧实验 | 本地助手、MCP、交互式调查 | 不适合生产常驻无人值守 |
| DataBuff AI | 隔离实验 | 自然语言观测查询、多 Agent 调查 | 不授予 SSH 或生产写权限 |
| 自建 MCP Server | 推荐逐步建设 | 封装 ZOTA 只读查询，形成稳定工具契约 | 第一阶段只暴露 read-only tools |

AI 输出必须区分：

- 已观察事实。
- 基于事实的推断。
- 待验证假设。
- 推荐动作。
- 实际已执行动作。

禁止把模型生成文本直接当成故障根因或恢复证明。

### 13.5 发布验证

| 工具/方式 | 用途 |
|---|---|
| Playwright / Playwright MCP | 管理端关键路径、截图和可访问性冒烟 |
| API contract tests | zota-repo、zota-server、hawkBit 接口兼容 |
| Synthetic probes | 登录、查询、创建发布、只读 rollout 查询 |
| promtool | 告警规则语法与测试 |
| k6 或同类工具 | API 容量和回归压测 |
| Argo Rollouts AnalysisTemplate | 基于 SLI 的发布门禁 |

UI 验证只是发布验证的一部分，不能替代 API、消息、制品和车辆侧验证。

## 14. IM 与 ChatOps 候选项目

### 14.1 先明确 IM 能解决什么

IM 项目可以提供：

- 消息投递。
- 离线消息和已读回执。
- 群组会话和事故房间。
- Bot 交互。
- 事故时间线展示。
- 私有化部署和数据主权。

IM 项目不能替代：

- SLI/SLO 和告警计算。
- 告警分组、抑制和降噪。
- 值班排班与升级策略。
- 事故状态机。
- Runbook 安全执行。
- OTA 发布门禁。

因此，IM 是通知和协作渠道，不是无人运维控制面。

### 14.2 用户提供仓库与上游映射

截至 2026-08-08，以下 `gottaBoy/*` 仓库均为 fork，应同时跟踪其上游：

| 内部跟踪仓库 | 上游仓库 | 结论 |
|---|---|---|
| `gottaBoy/keep` | `keephq/keep` | Keep 内部 fork，不是独立产品 |
| `gottaBoy/open-im-server` | `openimsdk/open-im-server` | OpenIM 上游 |
| `gottaBoy/TangSengDaoDaoServer` | `TangSengDaoDao/TangSengDaoDaoServer` | 唐僧叨叨服务端上游 |
| `gottaBoy/gim` | `alberliu/gim` | GIM 上游 |
| `gottaBoy/WuKongIM` | `WuKongIM/WuKongIM` | 悟空 IM 上游 |

内部 fork 的用途应限定为：

- 固定评估版本。
- 保存内部适配补丁。
- 进行安全扫描和 PoC。
- 跟踪 upstream commit 和许可证变化。

不要长期静默分叉；需要配置定期 upstream sync 和差异审计。

### 14.3 crossoverJie/cim

定位：Java/Netty 轻量 IM 项目。

可以借鉴：

- 客户端心跳和连接保活。
- 断线重连。
- 消息路由。
- 长连接网关。
- 服务发现和基础集群思路。

不适合：

- 直接承担 ZOTA 值班、告警聚合和事故管理。
- 作为生产 ChatOps 的首选基础设施。

结论：保留为协议、Netty 和长连接实现参考，不纳入主线部署。

### 14.4 OpenIM

定位：Go 实现的完整 IM 服务端和 SDK 生态。

可以借鉴：

- 多端 SDK。
- 离线消息、回执和会话同步。
- 微服务拆分。
- 私有 Bot/ChatOps 通道。
- 内部事故群和消息归档。

风险：

- 组件较多，部署、升级、存储和容量治理成本高。
- 仅为发送告警而引入整套 IM 不划算。
- 仍需要 Alertmanager、GoAlert 和事故管理层。

结论：如果公司后续明确要求私有通信平台，可与 WuKongIM 进入正式 PoC；否则先使用现有飞书、Slack、钉钉、邮件和电话渠道。

### 14.5 TangSengDaoDaoServer

定位：构建在 WuKongIM 之上的完整应用/业务层。

可以借鉴：

- 组织与会话模型。
- 事故群、机器人、消息时间线的产品交互。
- 通讯录、群组和后台管理能力。
- 基于 WuKongIM 构建上层产品的方式。

风险：

- 产品能力远超单纯告警通知需求。
- 与公司已有 IM/组织体系可能重复。

结论：主要借鉴产品层和 ChatOps UX，不作为第一阶段运维基础设施。

### 14.6 GIM

定位：较轻量的 Go IM 组件。

可以借鉴：

- 网关与业务服务分离。
- 长连接消息转发。
- 较小规模的 Go IM 工程结构。

风险：

- 更接近学习和参考项目。
- 值班、事故、审计和安全治理能力需要自行建设。

结论：保留为技术实现参考，不作为生产无人运维平台。

### 14.7 WuKongIM

定位：分布式 Go 消息基础设施。

可以借鉴：

- 私有部署。
- 消息路由和集群。
- 多端 SDK。
- 高并发长连接。
- 频道、离线消息和回执。

风险：

- 版本稳定性必须按具体 release 核验，不直接追随 beta 主线。
- 自建 IM 会新增存储、消息可靠性、推送、合规和客户端运维成本。
- 它只解决传输和会话，不解决告警和执行治理。

结论：在用户列出的 IM 项目中，它是私有消息基础设施的重点候选之一；正式选择前与 OpenIM 做同场景 PoC。

### 14.8 IM 选型顺序

1. 首期复用现有企业 IM webhook、邮件和电话。
2. 统一告警卡片、确认、静默、升级和事故链接的消息格式。
3. 只有合规、数据主权或内部产品需求明确时才建设私有 IM。
4. 私有 IM PoC 优先比较 WuKongIM 和 OpenIM。
5. TangSengDaoDao 借鉴应用层体验。
6. CIM/GIM 借鉴长连接与工程实现。

PoC 指标至少包括：

- 端到端消息时延。
- 丢失、重复和乱序率。
- 离线消息与回执。
- 多租户和组织隔离。
- Bot/Webhook/MCP 接入成本。
- 集群升级和故障恢复。
- 审计与数据保留。
- 移动推送和国产环境适配。

## 15. ZOTA 告警矩阵

以下为建议模板，具体阈值必须用预生产和生产基线校准。

| 范畴 | 信号 | 严重级别 | 初始响应 | 可自动动作 |
|---|---|---|---|---|
| API | 关键 API 5xx/SLO burn rate | critical | 值班 + 变更关联 | 暂停发布、受控回滚 |
| API | P99 延迟异常 | warning/critical | 查 Trace 和依赖 | 限流或扩容需策略 |
| rollout | 成功率快速下降 | critical | 暂停扩大灰度 | 自动暂停单个 rollout |
| rollout | 阶段长时间无进展 | warning | 查在线率、任务状态 | 只读重查，重试需审批 |
| 制品 | 签名/哈希校验失败 | critical | 立即阻断发布 | 自动阻断，不自动绕过 |
| 存储 | Artifact 下载失败率升高 | critical | 查 TOS/CDN/网络 | 降并发、切换需审批 |
| hawkBit | DDI/Management API 错误率 | critical | 查实例与 DB | 摘除故障实例 |
| 数据库 | 连接耗尽、复制延迟、磁盘不足 | critical | DBA/平台响应 | 扩容只在已审核规则内 |
| Redis/MQ | backlog、延迟、失败率 | warning/critical | 查 consumer 和热点 | 受限扩容 consumer |
| 车辆 | 在线率按车型/区域突降 | critical | 关联网络与版本 | 禁止自动批量下发 |
| 车辆 | OTA preflight 失败激增 | warning | 按 check 分组 | 自动暂停新批次 |
| 证书 | 过期窗口进入阈值 | warning/critical | 创建轮换任务 | 不自动大规模吊销 |
| EOL | 证据链生成或查询失败 | warning | 检查存储和任务 | 重试幂等生成任务 |
| 审计 | 高风险操作无审计事件 | critical | 安全响应 | 阻断后续写操作 |
| 监控 | Prometheus/Alertmanager 无数据 | critical | 平台响应 | 启用兜底探针 |

### 15.1 防止告警风暴

- 使用 multi-window burn-rate 告警，而不是只用单阈值瞬时告警。
- 同一 rollout 的车辆失败先聚合，再按影响范围升级。
- 依赖故障时抑制下游派生告警。
- 发布窗口内把变更信息附加到告警，不直接静默所有告警。
- 每条 critical 告警必须能映射到一个 owner 和 Runbook。
- 连续误报两次的告警必须进入治理清单。

## 16. Runbook 执行契约

所有自动或审批执行的 Runbook 应存放在 Git，并包含以下字段：

```yaml
id: pause-rollout-on-error-budget
version: 1
owner: ota-platform
risk: medium
autonomy_level: L1

trigger:
  alertname: OTARolloutErrorBudgetBurn

preconditions:
  - rollout_status == running
  - affected_rollout_count == 1
  - metrics_freshness < 120s

scope:
  max_rollouts: 1
  max_vehicles: 500

action:
  type: zota.pause_rollout
  timeout: 30s
  idempotency_key: incident_id

verification:
  - rollout_status == paused
  - no_new_assignments_for >= 2m

rollback:
  type: zota.resume_rollout
  requires_approval: true

cooldown: 30m
audit:
  retain_for: 365d
```

### 16.1 必须满足的属性

| 属性 | 要求 |
|---|---|
| 前置条件 | 数据新鲜、对象存在、状态符合预期 |
| 幂等性 | 重复调用不会扩大影响 |
| 作用域 | 明确最大 Pod、rollout、车辆或租户数量 |
| 超时 | 超时停止，不无限等待 |
| 验证 | 用独立信号确认结果 |
| 回滚 | 明确是否可回滚、由谁批准 |
| 冷却 | 防止重复触发和震荡 |
| 审计 | 保存输入、审批、执行人、输出和前后状态 |
| Dry-run | 上线前支持只计算影响范围 |
| Kill switch | 平台和安全团队可全局禁用自动执行 |

### 16.2 AI 与 Runbook 的连接方式

正确流程：

```text
AI 提出候选 Runbook
    -> 策略引擎校验 alert / scope / freshness / permission
    -> 如需要则人工审批
    -> 固定参数化执行器运行
    -> 独立验证器确认
    -> 写入审计和事故时间线
```

错误流程：

```text
AI 生成 shell
    -> 使用管理员 kubeconfig 执行
```

## 17. 安全、权限与审计

### 17.1 身份分离

至少分离以下身份：

- 可观测性只读身份。
- AI 调查身份。
- Runbook 执行身份。
- 发布系统身份。
- 车辆控制身份。
- 安全/证书管理身份。

AI 调查身份不应继承 Runbook 执行权限。

### 17.2 最小权限

- Kubernetes 使用 namespace、resource、verb 级 RBAC。
- 数据库默认只读副本或只读账号。
- ZOTA API 使用按 tool 划分的 scope。
- 每个 Runbook 使用独立 service account 或细粒度授权。
- Secret 从 Vault/KMS 获取，不写入 prompt、日志和事故消息。
- MCP Tool 使用固定 schema，拒绝任意命令和任意 URL。

### 17.3 Prompt Injection 防护

日志、工单、IM 消息、车辆上报内容都属于不可信输入。

要求：

- 模型读取的文本不能改变系统权限。
- Tool 参数由结构化 schema 校验。
- 外部内容不能要求模型读取 Secret 或扩大权限。
- AI 生成的 URL、命令和查询必须经过 allowlist。
- 高风险动作必须由非模型策略引擎判断。

### 17.4 审计要求

每次自动化动作保存：

- 原始告警和 fingerprint。
- 证据快照和数据时间范围。
- 模型、prompt 模板和工具版本。
- 模型建议与置信度。
- 策略判断结果。
- 审批人、审批时间和审批参数。
- 执行动作、返回值和耗时。
- 验证结果。
- 回滚结果。

生产自动化的未授权操作目标必须为 `0`。

## 18. 分阶段路线

### Phase 0：上线前基线，建议 2～4 周

目标：先保证“看得见、叫得到人、能够回滚”。

交付：

- 修复告警规则加载、抓取目标、指标名和 severity 路由。
- 配置至少两个真实通知渠道。
- 建立 zota-repo、zota-server、hawkBit、DB、Redis/MQ 基础仪表盘。
- 清理高基数指标。
- 建立结构化日志和关联 ID。
- 区分 startup/liveness/readiness。
- 建立发布、回滚、备份恢复、证书轮换 Runbook。
- 接入 Playwright/API 发布后冒烟。
- 完成一次故障和回滚演练。

此阶段不部署生产写权限 AI。

### Phase 1：稳定运营，建议上线后 1～2 个月

目标：建立确定性告警和值班闭环。

交付：

- Alertmanager 分组、抑制、静默和 burn-rate 告警。
- GoAlert 排班、升级和确认。
- 飞书/Slack/电话/邮件通知统一模板。
- 自动创建事故工单和时间线。
- OTel Collector、Loki、Tempo 补齐。
- Argo CD/Argo Rollouts 纳入生产发布。
- 第一批 L0/L1 Runbook 只覆盖低风险动作。
- 每周告警质量评审。

### Phase 2：AI 辅助调查与告警治理

目标：降低 MTTR 和人工检索成本，不扩大生产风险。

交付：

- HolmesGPT 只读接入 metrics/logs/traces/K8s/Git/deployment events。
- Dify 接入 Runbook、架构、历史事故知识库。
- 自建 ZOTA read-only MCP Server。
- Keep 做多源告警聚合 PoC，达到阈值后再上线。
- AI 自动生成事故摘要、交接和复盘草稿。
- AI 建议命中率、证据完整率和人工采纳率纳入评估。

### Phase 3：受控自治

目标：把已验证的重复动作升级为审批或自动执行。

交付：

- Runbook 策略引擎。
- Dry-run、作用域限制、Kill switch 和独立验证器。
- 中风险动作进入 L3 审批执行。
- 达到成熟条件后，少量动作从 L3 降为 L1。
- 复杂长时 OTA 流程确有需求时评估 Temporal。
- 合规需要时评估 WuKongIM/OpenIM 私有 ChatOps。

### Phase 4：持续优化

目标：按数据改善可靠性，而不是追求“自动化数量”。

交付：

- SLO 和错误预算进入发布决策。
- 自动化动作按成功率和副作用定期降级或下线。
- Chaos/故障演练覆盖关键依赖。
- 容量预测、异常检测和成本治理。
- 供应链安全、镜像签名、SBOM 和依赖漏洞闭环。

## 19. 验收指标

### 19.1 事故运营

- MTTD：重大故障发现时间。
- MTTA：值班确认时间。
- MTTR：恢复时间。
- P0/P1 未确认告警数量。
- 告警通知渠道送达率。
- 事故时间线完整率。

### 19.2 告警质量

- False-page rate。
- 重复告警压缩率。
- 无 owner 告警数量。
- 无 Runbook 的 critical 告警数量。
- 告警数据过期或 no-data 漏报数量。
- 每周新增、修改和删除规则数量。

### 19.3 自动化质量

- Runbook 成功率。
- 自动化后验证成功率。
- 回滚率。
- 因自动化造成的事故数量。
- 超出作用域动作数量。
- 未授权生产动作数量，目标为 `0`。
- Kill switch 演练成功率。

### 19.4 AI 质量

- 调查报告附带有效证据的比例。
- 候选根因被人工确认的比例。
- 推荐 Runbook 的采纳率。
- 错误建议率。
- 工具调用失败率。
- 敏感信息泄露事件，目标为 `0`。

AI 指标不能只统计回答次数或 Token 消耗。

## 20. 当前不建议做的事情

- 不要一次部署 OpenTelemetry、LGTM、DataBuff、Coroot、Keep、OneUptime、Dify、n8n、Temporal 和私有 IM 全家桶。
- 不要因为引入 Keep 就删除 Alertmanager。
- 不要让 GoAlert、Keep、IM 和工单系统重复维护值班状态。
- 不要继续新引入已归档的 Grafana OnCall OSS 或 OpenDuty。
- 不要把 n8n 当 OTA 核心状态机。
- 不要让 Dify/OpenWorker/DataBuff 通过 SSH 任意修复生产。
- 不要把 VIN、证书序列号和动态 URL 直接作为 Prometheus 标签。
- 不要用单一全局 OTA 成功率掩盖车型、区域或版本问题。
- 不要在没有验证器和回滚机制时自动执行修复。
- 不要为发送告警而单独建设整套私有 IM。
- 不要把大模型输出写回事实源并覆盖原始证据。

## 21. 开源候选清单

以下项目即使当前不适合主线，也全部保留，便于后续借鉴或重新评估。

### 21.1 可观测性

- [OpenTelemetry](https://github.com/open-telemetry)
- [Prometheus](https://github.com/prometheus/prometheus)
- [Alertmanager](https://github.com/prometheus/alertmanager)
- [Grafana](https://github.com/grafana/grafana)
- [Loki](https://github.com/grafana/loki)
- [Tempo](https://github.com/grafana/tempo)
- [Coroot](https://github.com/coroot/coroot)
- [DataBuff](https://github.com/databufflabs/databuff)

### 21.2 告警、值班与事故

- [GoAlert](https://github.com/target/goalert)
- [KeepHQ Keep](https://github.com/keephq/keep)
- [gottaBoy/keep](https://github.com/gottaBoy/keep)
- [OneUptime](https://github.com/OneUptime/oneuptime)
- [Grafana OnCall archived repository](https://github.com/grafana-cold-storage/oncall)
- [OpenDuty](https://github.com/openduty/openduty)

### 21.3 自动化、发布与工作流

- [Argo CD](https://github.com/argoproj/argo-cd)
- [Argo Rollouts](https://github.com/argoproj/argo-rollouts)
- [Robusta](https://github.com/robusta-dev/robusta)
- [Temporal](https://github.com/temporalio/temporal)
- [StackStorm](https://github.com/StackStorm/st2)
- [Rundeck](https://github.com/rundeck/rundeck)
- [n8n](https://github.com/n8n-io/n8n)

### 21.4 AI 调查、知识与验证

- [HolmesGPT](https://github.com/HolmesGPT/holmesgpt)
- [Dify](https://github.com/langgenius/dify)
- [OpenWorker](https://github.com/andrewyng/openworker)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)

### 21.5 IM 与 ChatOps

- [crossoverJie/cim](https://github.com/crossoverJie/cim)
- [gottaBoy/open-im-server](https://github.com/gottaBoy/open-im-server)
- [OpenIM upstream](https://github.com/openimsdk/open-im-server)
- [gottaBoy/TangSengDaoDaoServer](https://github.com/gottaBoy/TangSengDaoDaoServer)
- [TangSengDaoDaoServer upstream](https://github.com/TangSengDaoDao/TangSengDaoDaoServer)
- [gottaBoy/gim](https://github.com/gottaBoy/gim)
- [GIM upstream](https://github.com/alberliu/gim)
- [gottaBoy/WuKongIM](https://github.com/gottaBoy/WuKongIM)
- [WuKongIM upstream](https://github.com/WuKongIM/WuKongIM)

## 22. 最终推荐

生产首期建议采用：

```text
OpenTelemetry + Prometheus + Loki + Tempo + Grafana
    -> Alertmanager
    -> GoAlert
    -> 现有企业 IM / 电话 / 邮件
    -> Argo CD / Argo Rollouts / 受控 Runbook
```

第二阶段增加：

```text
HolmesGPT 只读调查
Dify Runbook RAG
ZOTA read-only MCP
Keep 告警聚合 PoC
```

按需求再评估：

```text
Temporal：复杂长时 OTA 工作流
Robusta/StackStorm/Rundeck：确定性运维执行
WuKongIM/OpenIM：合规驱动的私有 ChatOps
Coroot/DataBuff/OneUptime：替代型或实验型平台
```

核心原则不是完全取消人工，而是：

> 让机器负责持续观察、确定性恢复和证据整理；让 AI 负责调查和建议；让人保留高风险、不可逆和涉及车辆安全的最终决策权。

---

## 23. AI 原生研发运营总蓝图

### 23.1 蓝图目标

第 8～22 章重点解决生产运维。本章将范围扩展为完整的软件与 OTA 生命周期：

```text
需求 -> 设计 -> 编码 -> 构建 -> 测试 -> 安全 -> 制品
     -> 发布 -> 部署 -> OTA 灰度 -> 线上运营 -> 事故
     -> 复盘 -> 知识沉淀 -> 下一轮改进
```

目标不是建设一个“万能 AI 运维机器人”，而是建设一套可组合的平台能力：

- 每个阶段都有清晰事实源、质量门禁和责任人。
- 代码、配置、制品、发布、运行状态和事故证据可以关联。
- 高频工作通过黄金路径标准化。
- 确定性工具完成执行，AI 完成理解、检索、生成和建议。
- 所有生产动作受策略、权限、审批、验证和审计约束。
- 平台能力可替换，不被单个开源项目或供应商锁定。

### 23.2 闭环模型

```text
┌────────────── Plan / Design ──────────────┐
│ 需求、ADR、威胁建模、SLO、验收条件         │
└────────────────────┬──────────────────────┘
                     v
┌────────────── Code / Review ──────────────┐
│ 模板、AI 编码、静态检查、评审、依赖治理     │
└────────────────────┬──────────────────────┘
                     v
┌──────────── Build / Verify / Secure ──────┐
│ 可复现构建、单测、契约、E2E、安全、SBOM     │
└────────────────────┬──────────────────────┘
                     v
┌──────────── Artifact / Release ───────────┐
│ Harbor、签名、证明、发布清单、风险门禁       │
└────────────────────┬──────────────────────┘
                     v
┌──────────── Deploy / OTA Rollout ─────────┐
│ GitOps、灰度、车辆分群、自动暂停、回滚       │
└────────────────────┬──────────────────────┘
                     v
┌──────────── Operate / Observe ────────────┐
│ SLO、告警、值班、Runbook、容量、成本、安全   │
└────────────────────┬──────────────────────┘
                     v
┌──────────── Learn / Improve ──────────────┐
│ 事故复盘、DORA、质量趋势、知识库、规则优化   │
└────────────────────┴───────────> 回到 Plan
```

### 23.3 八个逻辑平面

#### A. 产品与架构平面

负责：

- 需求、验收条件、风险等级和业务 owner。
- ADR、架构图、API 契约和数据契约。
- SLO、威胁模型、合规要求和发布策略。

候选工具：

- Git + Markdown/Docs as Code。
- OpenProject、Plane、Taiga：需求和项目协同备选。
- Backstage TechDocs：统一服务和文档入口。
- Structurizr、PlantUML、Mermaid：架构即代码。

#### B. 开发者体验平面

负责：

- 服务目录。
- 项目脚手架。
- 本地开发环境。
- 黄金路径。
- API、事件、依赖、owner 和 Runbook 发现。

核心候选：

- Backstage：开发者门户和软件目录。
- Dev Containers：一致的开发环境。
- Taskfile/Make：统一命令入口。
- Renovate：依赖自动更新。
- OpenRewrite：Java 大规模自动重构。

#### C. 持续集成与测试平面

负责：

- 构建、单元测试、集成测试、契约测试、E2E、性能和安全测试。
- 临时环境。
- 测试数据、模拟器和数字孪生。
- 质量门禁和结果回传。

核心候选：

- 现有 GitHub Actions/GitLab CI 优先。
- 自建可选 Woodpecker CI、Tekton Pipelines。
- Kubernetes 批任务可使用 Argo Workflows。
- Testcontainers、Pact、Schemathesis、k6、Playwright、OWASP ZAP。
- vCluster 用于高隔离临时测试环境。

#### D. 软件供应链平面

负责：

- 制品仓库。
- SBOM。
- 漏洞、许可证、Secret 和恶意依赖检查。
- 制品签名、来源证明和准入。

核心候选：

- Harbor：镜像和 OCI 制品中心。
- ORAS：使用 OCI 分发非容器制品。
- Syft：生成 SBOM。
- Grype/Trivy：漏洞和配置扫描。
- Dependency-Track：持续跟踪组件风险。
- Gitleaks：Secret 扫描。
- Cosign/Sigstore：签名和验证。
- in-toto/SLSA：供应链证明模型。

#### E. 配置、基础设施与发布平面

负责：

- 基础设施即代码。
- 集群、配置、Secret 和策略。
- GitOps 发布。
- 灰度、回滚和环境晋级。

核心候选：

- OpenTofu：云和基础设施声明。
- Crossplane：Kubernetes 控制平面方式管理基础设施。
- Helm/Kustomize：应用配置。
- Argo CD：GitOps。
- Argo Rollouts 或 Flagger：灰度。
- OpenBao + External Secrets Operator + SOPS：Secret 管理。
- Kyverno 或 OPA Gatekeeper：Policy as Code。

#### F. 运行与安全平面

负责：

- 指标、日志、Trace、Profile、事件。
- 运行时安全、网络和成本。
- 备份恢复和混沌演练。

核心候选：

- OpenTelemetry + Prometheus + Loki + Tempo + Grafana。
- Cilium/Hubble：网络可观测和策略。
- Falco 或 Tetragon：运行时安全。
- Kubescape：集群和工作负载安全检查。
- Velero：Kubernetes 资源和卷备份。
- CloudNativePG/pgBackRest：PostgreSQL 高可用与恢复。
- LitmusChaos 或 Chaos Mesh：故障演练。
- OpenCost：Kubernetes 成本。

#### G. 事故与自动化平面

负责：

- 告警、值班、升级和事故协同。
- Runbook、审批和自动恢复。
- 状态页、工单和复盘。

核心候选：

- Alertmanager、GoAlert、Keep。
- Robusta、StackStorm、Rundeck。
- Temporal：长流程和补偿。
- n8n：通知、工单和外围集成。
- OneUptime：一体化替代方案评估。

#### H. AI 与知识平面

负责：

- 编码和评审助手。
- 测试生成和失败分析。
- 只读 SRE 调查。
- Runbook/架构/事故 RAG。
- 模型网关、评估、观测和安全。

核心候选：

- OpenHands、SWE-agent、Aider：研发 Agent/助手候选。
- HolmesGPT：SRE 调查。
- Dify：知识和内部工作流助手。
- LiteLLM：统一模型网关。
- vLLM/Ollama：私有模型服务。
- Langfuse 或 Arize Phoenix：LLM Trace、反馈和评估。
- Promptfoo、Ragas：Prompt/RAG 回归测试。
- pgvector 或 Qdrant：知识向量检索。
- OPA/Kyverno + 自建执行网关：AI 工具权限决策。

## 24. 推荐的平台产品

不要按开源项目建立团队边界，应按内部平台产品建立。

### 24.1 Developer Portal

面向开发、测试、SRE 和安全团队的统一入口。

应提供：

- 服务目录、owner、依赖、API、事件和数据存储。
- Dashboard、SLO、告警、Runbook 和事故入口。
- 项目模板和新服务脚手架。
- 环境、发布、制品和变更记录。
- 安全、质量和成本状态。

推荐以 Backstage 为框架二开，而不是自研完整门户。

ZOTA 需要开发的插件：

- 车型、ECU、软件模块和车辆分群视图。
- release/distribution/rollout 关联。
- 制品签名和兼容矩阵状态。
- OTA 质量门禁。
- 事故、告警和车辆影响范围。

### 24.2 CI/Test Platform

应对不同仓库提供统一黄金路径：

```text
lint
  -> unit
  -> component
  -> contract
  -> integration
  -> security
  -> build
  -> SBOM/sign
  -> ephemeral environment
  -> E2E/performance
  -> release candidate
```

平台输出统一的 Test Evidence：

- commit SHA。
- 构建环境和依赖锁。
- 测试套件版本。
- 测试结果、覆盖率和性能基线。
- SBOM、漏洞和许可证结果。
- 制品 digest 和签名。
- 可追溯到需求、缺陷和 release。

### 24.3 Software Supply Chain Platform

制品晋级应以 digest 为中心，不允许在环境间重新构建：

```text
同一 digest：
dev -> test -> preprod -> production
```

每个 release bundle 至少包含：

- 制品 digest。
- SBOM。
- 签名。
- provenance。
- 兼容矩阵。
- 测试证据。
- 已知风险。
- 回滚制品。
- 变更说明。

ZOTA OTA 制品可采用 OCI Artifact/ORAS 统一分发元数据，但是否替代现有 TOS 存储需要单独验证，不应强行迁移。

### 24.4 Release Control Plane

这是 ZOTA 最值得二开的核心领域平台，而不是 fork Argo CD 或 Keep。

应负责：

- release bundle 和 distribution set 的统一发布模型。
- 车型、硬件、ECU、区域、渠道和 VIN cohort 规则。
- 兼容性、安全、法规、测试和错误预算门禁。
- 灰度波次和观察窗口。
- 暂停、继续、回滚和终止。
- 影响范围预估。
- 全链路审计和证据。

Argo CD/Argo Rollouts 负责服务端部署；ZOTA Release Control Plane 负责车辆 OTA 领域发布。两者通过事件和 API 协同，不要混为一个状态机。

### 24.5 Reliability Platform

应提供：

- SLO 和错误预算。
- 统一观测查询。
- 告警和事故。
- Runbook。
- 容量和成本。
- 备份恢复。
- 演练。

其目标是减少认知负担，不是仅增加仪表盘数量。

### 24.6 AI Engineering Platform

统一提供：

- 模型路由、配额、降级和成本。
- Prompt/Agent 版本。
- Tool/MCP 注册。
- 知识源注册和权限。
- LLM Trace 和评估。
- 敏感信息过滤。
- 审批和执行策略。

业务团队不应在每个服务中分别保存模型密钥、重复实现 RAG 和直接连接生产工具。

## 25. ZOTA 领域控制面的二开边界

### 25.1 建议自研或二开的能力

#### Release Graph

建立可查询关系：

```text
requirement
  -> commit
  -> build
  -> artifact digest
  -> software module
  -> distribution set
  -> rollout
  -> vehicle cohort
  -> vehicle result
  -> EOL evidence
  -> incident
```

这是研发、测试、发布和事故分析共用的主索引。

#### Risk and Gate Engine

输入：

- 代码和依赖风险。
- 测试证据。
- 制品签名。
- 车型兼容性。
- 当前 SLO 和错误预算。
- 历史同类发布表现。
- 车辆在线率和网络状况。
- 安全/法规审批。

输出：

- `allow`
- `allow_with_approval`
- `pause`
- `deny`

规则由确定性策略实现，AI 只解释和推荐。

#### OTA Digital Twin / Simulator

至少模拟：

- 不同 ECU/MCU 组合。
- 弱网、断网、重连和限速。
- 下载中断、磁盘不足和校验失败。
- 电量、温度、点火和驾驶状态。
- 安装失败、重启失败和回滚。
- 旧版本跨级升级。
- 批量并发和长尾车辆。

这比单纯增加 UI E2E 测试更能降低 OTA 线上风险。

#### Incident Context Builder

收到事故后自动聚合：

- 最近部署和配置变更。
- 相关 release/rollout。
- 影响车型、区域和数量。
- 指标、日志和 Trace。
- 依赖健康。
- 同类历史事故。
- 可用 Runbook 和 owner。

输出标准化事故包，供值班人员和 HolmesGPT 使用。

#### Runbook Registry and Execution Gateway

自建薄层，不自建完整工作流引擎：

- Runbook 元数据和版本。
- 参数 schema。
- 风险等级和审批策略。
- service account 映射。
- Dry-run、限流、Kill switch。
- 调用 Argo、Robusta、Rundeck、Temporal 或 ZOTA API。
- 统一审计。

#### ZOTA MCP Gateway

第一阶段只提供只读工具：

- 查 release。
- 查 distribution/rollout。
- 查车辆聚合状态。
- 查制品和测试证据。
- 查 SLO、告警、日志和 Trace 链接。
- 查历史事故和 Runbook。

第二阶段才允许受控 action request，并且实际执行仍由 Execution Gateway 完成。

### 25.2 不建议 fork 的核心项目

除非上游无法扩展且存在明确长期维护团队，不建议深度 fork：

- Kubernetes。
- Prometheus/Grafana/Loki/Tempo。
- Argo CD/Argo Rollouts。
- Harbor。
- Backstage。
- OpenTelemetry。
- GoAlert/Keep。
- OpenBao/Kyverno。
- WuKongIM/OpenIM。

优先方式：

1. 插件。
2. Operator/Controller。
3. Adapter。
4. Webhook。
5. MCP Tool。
6. 独立领域服务。
7. 最后才是长期 fork。

### 25.3 二开项目治理

每个内部 fork 必须有：

- 明确 owner。
- fork 原因。
- 与 upstream 的同步周期。
- 本地 patch 清单。
- 升级和冲突策略。
- 安全响应责任。
- 退出或回归 upstream 的计划。

## 26. 开发与代码质量体系

### 26.1 仓库标准

每个服务至少包含：

- `README`：用途、依赖、运行和调试。
- `CODEOWNERS`。
- `SECURITY.md`。
- `Makefile` 或 `Taskfile.yml`。
- 本地开发容器配置。
- 架构/ADR 目录。
- API/事件 schema。
- 单元、集成和契约测试。
- Dockerfile 和部署清单。
- Dashboard、SLO、告警和 Runbook 引用。
- SBOM、签名和发布元数据生成流程。

### 26.2 黄金路径模板

为 Go、Java、React 和车端 C/C++ 分别提供模板。

模板内置：

- 日志、metrics、Trace 和 correlation ID。
- 健康探针。
- 配置和 Secret 接入。
- 重试、超时、熔断和优雅退出。
- CI workflow。
- 安全扫描。
- Helm/Kustomize。
- Dashboard/SLO/Alert skeleton。
- Runbook skeleton。

项目创建时自动注册到 Backstage。

### 26.3 AI 编码治理

AI 可以：

- 生成样板和测试。
- 分析静态检查结果。
- 解释失败日志。
- 提交小范围 PR。
- 建议重构和依赖升级。

AI 生成代码必须：

- 走普通 PR。
- 通过相同测试和安全门禁。
- 标注使用的 Agent、模型和任务。
- 由 CODEOWNER 评审高风险模块。
- 不得直接 push 受保护分支。
- 不得自动降低测试、安全或覆盖率阈值。

OpenHands/SWE-agent/Aider 应运行在隔离 workspace，凭证仅允许读取必要仓库和创建分支/PR。

## 27. 测试工程体系

### 27.1 测试分层

| 层级 | 目标 | 典型工具 |
|---|---|---|
| 静态 | 编译、lint、类型、规则 | golangci-lint、ESLint、SpotBugs、Semgrep |
| 单元 | 纯业务逻辑 | Go test、JUnit、Vitest |
| 组件 | DB、MQ、缓存和协议适配 | Testcontainers |
| 契约 | 服务/API/事件兼容 | Pact、Schemathesis、AsyncAPI tests |
| 集成 | zota-repo/hawkBit/JetLinks/TOS | 临时环境 + 固定数据集 |
| E2E | 用户关键流程 | Playwright |
| OTA 仿真 | 车端状态和故障 | 自建数字孪生/仿真器 |
| 性能 | 容量、长尾和稳定性 | k6 |
| 安全 | SAST/DAST/依赖/镜像 | Semgrep、ZAP、Trivy |
| 韧性 | 依赖和网络故障 | LitmusChaos/Chaos Mesh |

### 27.2 测试结果不能只显示 Pass/Fail

需要保留：

- 失败分类。
- 环境和数据版本。
- flaky 标记。
- 重试次数。
- 性能基线差异。
- 影响模块和需求。
- 相关日志和 Trace。

AI Test Analyst 可自动归类失败、识别重复问题和生成候选测试，但不能把失败测试自动标记为通过。

### 27.3 临时环境策略

推荐顺序：

1. 单测和 Testcontainers 解决大部分依赖。
2. PR 级共享集成环境。
3. 高风险变更使用 namespace 或 vCluster 临时环境。
4. 夜间运行全链路和长稳测试。

不要为每个 PR 无差别复制整套 ZOTA、hawkBit、JetLinks 和所有存储，成本和维护复杂度会很高。

## 28. 安全供应链与合规

### 28.1 CI 安全门禁

建议顺序：

```text
secret scan
  -> SAST
  -> dependency/OS vulnerability
  -> license policy
  -> build
  -> SBOM
  -> image/config scan
  -> sign/provenance
  -> admission policy
```

### 28.2 准入策略

生产环境只允许：

- 来自受信 Harbor project 的制品。
- digest 固定。
- 签名有效。
- provenance 满足要求。
- 不存在策略禁止级别漏洞。
- 存在 SBOM。
- release bundle 已批准。

可使用 Kyverno 或 Gatekeeper 校验，Cosign 验证签名。

### 28.3 OTA 特殊要求

- ECU/MCU 制品签名与容器镜像签名分开管理。
- 密钥使用 HSM/KMS 或受控签名服务。
- 签名服务与发布审批职责分离。
- 每次车辆安装结果关联制品 digest 和签名身份。
- EOL 证据不可由普通运维账号修改。

## 29. AI 能力架构

### 29.1 AI Control Plane

```text
Developer / Tester / SRE / Security / Product
                         |
                         v
                 AI Portal / ChatOps
                         |
                         v
                 Agent Orchestrator
          +--------------+--------------+
          |              |              |
          v              v              v
     Knowledge       Read Tools     Action Request
     Retrieval       / MCP          (not execution)
          |              |              |
          v              v              v
      pgvector       Observability   Policy Engine
      / Qdrant       Git/Test/ZOTA        |
                                           v
                                  Execution Gateway
                                           |
                                           v
                                     Approved Tools
```

横向治理：

- LiteLLM 统一模型路由、配额、审计和降级。
- vLLM/Ollama 承载可私有化模型。
- Langfuse/Phoenix 记录 LLM Trace 和反馈。
- Promptfoo/Ragas 做离线和回归评估。
- OpenBao 管理模型和工具凭证。
- OPA/Kyverno/自建策略引擎判断工具权限。

### 29.2 建议的 AI 角色

| Agent | 输入 | 输出 | 初始权限 |
|---|---|---|---|
| Architecture Assistant | ADR、代码、依赖、SLO | 影响分析、ADR 草稿 | 只读 |
| Coding Agent | Issue、代码、测试 | 分支/PR | 非保护分支写 |
| Review Assistant | Diff、规则、历史缺陷 | 评审建议 | 只读 |
| Test Analyst | 测试结果、日志、Trace | 失败分类和新增测试建议 | 只读 |
| Release Guardian | release evidence、SLO、风险 | go/no-go 建议 | 只读 |
| SRE Investigator | 指标、日志、Trace、变更 | 根因候选和证据包 | 只读 |
| Incident Scribe | 事件和聊天记录 | 时间线、交接、复盘草稿 | 写事故文档 |
| Security Analyst | SBOM、漏洞、策略 | 风险解释和修复建议 | 只读 |
| Capacity Planner | 趋势、成本、发布计划 | 容量建议 | 只读 |

只有 Release Guardian 和 SRE Investigator 经过验证后，才可以提出结构化 action request；它们仍不直接执行。

### 29.3 AI 评估数据集

建立内部金标集：

- 历史构建失败。
- 历史测试失败。
- 历史 OTA 故障。
- 历史告警和事故。
- 安全漏洞与真实处置。
- 正确和错误 Runbook 选择。
- Prompt Injection 和敏感信息样本。

每次模型、Prompt、Tool 或知识库升级都跑回归。

### 29.4 AI 上线门禁

至少评估：

- 事实正确率。
- 证据引用率。
- 工具参数正确率。
- 拒绝越权率。
- 敏感信息泄露率。
- 延迟、成本和可用性。
- 人工采纳率。
- 对 MTTR 或交付周期的真实改善。

## 30. 数据与事件骨干

### 30.1 统一 ID

全链路统一并传播：

- `requirement_id`
- `commit_sha`
- `build_id`
- `artifact_digest`
- `release_id`
- `rollout_id`
- `incident_id`
- `trace_id`

VIN 只在授权业务数据层出现，不在通用指标和广域通知中传播。

### 30.2 事件总线

优先复用现有 RabbitMQ/JetLinks 事件能力，先定义 schema，再决定是否引入新中间件。

当出现以下需求时再评估 NATS JetStream、Kafka 或 Redpanda：

- 需要长时间事件重放。
- 多团队独立消费。
- 大规模车辆事件流。
- 需要严格顺序、分区和流处理。
- 当前 MQ 的吞吐、保留和治理能力不足。

不要仅为“AI 平台”再造一条重复消息总线。

### 30.3 工程效能数据

Apache DevLake 可聚合代码、CI、Issue 和发布数据，用于 DORA 和研发效能分析。

注意：

- 指标用于发现系统问题，不用于简单排名个人。
- Lead Time 要拆分等待、开发、评审、测试和发布。
- Change Failure Rate 要关联真实事故和回滚。
- AI 生成代码比例不应作为生产力核心指标。

## 31. 能力到开源项目的映射

### 31.1 研发平台与协作

| 能力 | 首选/优先复用 | 备选 | 建议 |
|---|---|---|---|
| Git/代码托管 | 现有 GitHub/GitLab | Gitea/Forgejo | 没有合规要求不要迁移 |
| Developer Portal | Backstage | 自建轻门户 | 基于插件二开 |
| 项目管理 | 现有 Jira | OpenProject/Plane/Taiga | 统一 Issue ID |
| 工程效能 | Apache DevLake | 自建数仓 | 先做 DORA 基线 |
| 依赖更新 | Renovate | Dependabot | 自动 PR，不自动合并高风险更新 |

### 31.2 CI、工作流和测试

| 能力 | 首选/优先复用 | 备选 | 建议 |
|---|---|---|---|
| CI | 现有 GitHub Actions/GitLab CI | Woodpecker/Tekton | 不因“开源”重复迁移 |
| K8s 工作流 | Argo Workflows | Tekton | 与 Argo CD 生态协同 |
| 集成测试 | Testcontainers | Docker Compose | 测试数据版本化 |
| 契约测试 | Pact/Schemathesis | 自建 schema tests | API 与事件都覆盖 |
| E2E | Playwright | Cypress | 关键路径少而稳定 |
| 性能 | k6 | JMeter/Gatling | 建立版本化基线 |
| DAST | OWASP ZAP | Nuclei | 只对授权环境扫描 |
| 临时集群 | vCluster | namespace | 高风险变更再使用 |

### 31.3 供应链与安全

| 能力 | 首选 | 备选/补充 |
|---|---|---|
| Registry | Harbor | 现有云 Registry |
| SBOM | Syft | Trivy |
| 漏洞 | Trivy/Grype | Dependency-Track 持续治理 |
| Secret scan | Gitleaks | TruffleHog |
| 签名 | Cosign | 企业签名服务 |
| Policy | Kyverno | Gatekeeper/Conftest |
| Secret | OpenBao + ESO | 云 KMS/Secret Manager + ESO |
| K8s posture | Kubescape | kube-bench |
| Runtime | Falco/Tetragon | KubeArmor |

### 31.4 发布、运行与运营

| 能力 | 首选 | 备选/补充 |
|---|---|---|
| IaC | OpenTofu | Crossplane |
| GitOps | Argo CD | Flux |
| Progressive delivery | Argo Rollouts | Flagger |
| Observability | OTel + LGTM | Coroot/OneUptime 替代评估 |
| On-call | GoAlert | OneUptime |
| Alert correlation | Keep | 自建轻量事件富化 |
| K8s automation | Robusta | StackStorm/Rundeck |
| Durable workflow | Temporal | 现有业务状态机 |
| Backup | Velero + 数据库原生备份 | 云备份服务 |
| Chaos | LitmusChaos/Chaos Mesh | 自建故障注入 |
| FinOps | OpenCost | 云成本平台 |

### 31.5 AI 平台

| 能力 | 首选/候选 | 建议 |
|---|---|---|
| Coding Agent | OpenHands/SWE-agent/Aider | 隔离执行，只创建 PR |
| SRE Agent | HolmesGPT | 只读先行 |
| RAG/Assistant | Dify | 不作为控制面 |
| Model Gateway | LiteLLM | 统一密钥、配额和降级 |
| Private Inference | vLLM/Ollama | 按模型和吞吐选 |
| LLM Observability | Langfuse/Phoenix | 记录 prompt/tool/version |
| Evaluation | Promptfoo/Ragas | 建立内部金标集 |
| Vector Store | PostgreSQL + pgvector | 规模或隔离要求高时 Qdrant |
| Policy | OPA + Execution Gateway | 模型不直接做授权判断 |

## 32. 推荐参考栈

### 32.1 最小可行平台

先复用现有 Git 和 CI，新增最少组件：

```text
Backstage
Harbor
Trivy + Syft + Cosign
Argo CD + Argo Rollouts
OpenTelemetry + Prometheus + Loki + Tempo + Grafana
Alertmanager + GoAlert
OpenBao/现有 Secret Manager + External Secrets Operator
Kyverno
Playwright + k6 + Testcontainers
```

### 32.2 AI 辅助层

基础平台稳定后增加：

```text
LiteLLM
HolmesGPT
Dify
Langfuse or Phoenix
Promptfoo
PostgreSQL + pgvector
ZOTA read-only MCP Gateway
```

### 32.3 受控自动化层

成熟后增加：

```text
Runbook Registry
Policy Engine
Execution Gateway
Robusta/Rundeck/StackStorm adapters
Temporal（有明确长流程需求时）
Keep（多源告警规模足够时）
```

### 32.4 可选私有通信层

只有存在明确需求时：

```text
WuKongIM or OpenIM
    + incident bot
    + private notification gateway
    + audit/archive integration
```

## 33. 实施路线图

### Stage 0：治理和基线，0～30 天

目标：知道系统由谁负责、如何发布、如何发现和恢复故障。

主要工作：

- 建立服务清单、owner、环境和依赖清单。
- 定义统一 ID、事件信封、severity 和 SLO 模板。
- 盘点 Git、CI、Registry、K8s、Secret 和监控现状。
- 修复第 9 章的监控阻塞项。
- 确定开源许可证和内部 fork 政策。
- 定义 AI 权限红线和数据分级。

交付物：

- Current-state architecture。
- 服务目录 v0。
- 上线检查表。
- 事故响应流程。
- 平台 ADR。

### Stage 1：交付黄金路径，1～3 个月

目标：每个服务都能用一致方式构建、测试、扫描、签名和发布。

主要工作：

- 建立 Backstage 服务目录和项目模板。
- CI 模板覆盖 Go、Java、React、C/C++。
- Harbor、SBOM、漏洞扫描、Cosign。
- Testcontainers、契约测试和 Playwright 基线。
- Argo CD 管理服务端环境。
- OpenBao/ESO 和 Kyverno 基线。
- 建立 release evidence。

验收：

- 新服务通过模板创建。
- 生产制品 100% 有 digest、SBOM 和签名。
- 受保护分支不能绕过质量门禁。
- 环境间不重新构建制品。

### Stage 2：测试与 OTA 发布控制，3～6 个月

目标：把测试证据和车辆风险纳入发布决策。

主要工作：

- 建设 OTA Simulator/Digital Twin v1。
- 建立 release graph。
- 实现车辆 cohort 和灰度波次。
- 建立兼容矩阵和门禁引擎。
- Argo Rollouts 管理服务端灰度。
- ZOTA 控制面管理车辆灰度。
- 引入性能、韧性和长稳测试。

验收：

- 每次 OTA release 可追溯到 commit、制品和测试。
- 支持自动暂停单个异常 rollout。
- 回滚流程经过演练。
- 高风险 release 必须有人工审批。

### Stage 3：可靠性与事故闭环，4～8 个月

目标：完成监测、告警、值班、恢复和复盘闭环。

主要工作：

- 完成 OTel/LGTM。
- SLO、错误预算和 burn-rate 告警。
- Alertmanager + GoAlert。
- Incident Context Builder。
- Runbook Registry 和前几项 L0/L1 动作。
- 备份恢复、混沌和容量演练。
- Apache DevLake/DORA 基线。

验收：

- critical 告警全部有 owner 和 Runbook。
- P0/P1 通知有确认和升级。
- 事故时间线自动生成。
- MTTD、MTTA、MTTR 可量化。

### Stage 4：AI Copilot，6～10 个月

目标：AI 提升研发和调查效率，但不直接控制生产。

主要工作：

- LiteLLM 模型网关。
- Langfuse/Phoenix + Promptfoo。
- Dify Runbook/ADR/事故知识库。
- HolmesGPT 只读调查。
- Coding/Review/Test Agent 小范围试点。
- ZOTA read-only MCP。
- 建立内部 AI 金标数据集。

验收：

- AI 输出可以追溯到模型、Prompt、Tool 和证据。
- 越权测试全部拒绝。
- 敏感信息泄露为 0。
- 至少一个场景对 Lead Time 或 MTTR 有统计改善。

### Stage 5：受控自治，9～15 个月

目标：把经过验证的重复动作自动化。

主要工作：

- Execution Gateway。
- Policy Engine。
- 审批和 Kill switch。
- Runbook Dry-run、验证和回滚。
- Keep 告警相关性评估。
- 部分 L3 动作进入审批执行。
- 成熟动作逐项降级为 L1。

验收：

- 每个自动动作有作用域和独立验证。
- 自动化成功率达到内部目标后才扩大范围。
- 未授权生产动作始终为 0。
- 因自动化导致的事故可立即全局熔断。

### Stage 6：规模化运营，12～24 个月

目标：按车队、区域、车型和组织规模持续优化。

主要工作：

- 容量和成本预测。
- 多集群/多区域灾备。
- 安全运营自动化。
- 发布风险模型持续训练和校准。
- 私有 IM 的需求决策。
- 供应商替代和退出演练。
- 平台产品满意度和采用率治理。

## 34. 组织与职责

建议设立虚拟平台团队，而不是把全部工作压给运维：

| 角色/团队 | 主要职责 |
|---|---|
| Platform Engineering | Developer Portal、CI 模板、GitOps、平台 API |
| SRE | SLO、告警、事故、容量、Runbook、演练 |
| Quality Engineering | 测试策略、数字孪生、性能和 flaky 治理 |
| Product Security | 供应链、密钥、策略、漏洞和运行时安全 |
| OTA Domain Team | release graph、兼容矩阵、车辆分群和门禁 |
| Data/AI Platform | 模型网关、RAG、评估、AI 观测和工具治理 |
| Service Teams | 服务 owner、测试、Dashboard、Runbook 和值班 |

平台团队提供自助能力，服务团队仍对自己的生产结果负责。

## 35. 全局度量

### 35.1 研发交付

- Deployment Frequency。
- Lead Time for Changes。
- Change Failure Rate。
- Time to Restore Service。
- PR 等待和评审时间。
- 构建成功率和平均时长。

### 35.2 测试质量

- 缺陷逃逸率。
- flaky test rate。
- 测试反馈时间。
- 契约破坏次数。
- 性能回归次数。
- OTA 仿真覆盖的故障模式。

### 35.3 安全供应链

- 签名制品覆盖率。
- SBOM 覆盖率。
- 高危漏洞修复时间。
- Secret 泄露事件。
- 不符合准入策略的部署次数。
- 密钥轮换和恢复演练完成率。

### 35.4 生产可靠性

- SLO 达成率。
- 错误预算消耗。
- MTTD/MTTA/MTTR。
- 告警误报和重复率。
- 发布自动暂停/回滚次数。
- 备份恢复成功率。

### 35.5 OTA 业务

- 按车型/区域/release 的升级成功率。
- 任务触达时间。
- 各阶段停滞率。
- 回滚率。
- 制品校验失败率。
- EOL 证据完整率。

### 35.6 平台与 AI

- 黄金路径采用率。
- 开发者门户活跃服务比例。
- 自助操作成功率。
- AI 建议采纳率和错误率。
- AI 节省时间的可验证样本。
- AI 越权和泄露事件。

## 36. 优先级建议

### 必须先做

1. 服务目录、owner、环境和发布清单。
2. CI/Test/Security/Artifact 的统一黄金路径。
3. Harbor、SBOM、签名和准入策略。
4. GitOps、灰度、回滚和 release evidence。
5. 可观测性、SLO、告警和值班。
6. OTA release graph、兼容矩阵和车辆灰度门禁。
7. 备份恢复、故障演练和审计。

### 然后做

1. Backstage 深度集成。
2. OTA Digital Twin。
3. Incident Context Builder。
4. DevLake/DORA。
5. HolmesGPT、Dify 和只读 MCP。
6. Runbook Registry 和 Execution Gateway。

### 有明确需求再做

1. Temporal。
2. Keep。
3. Crossplane。
4. vCluster 大规模临时环境。
5. 私有 WuKongIM/OpenIM。
6. 多 Agent 自动编排。
7. 自建事件流平台。

## 37. 结论

完整方案应被视为一个持续演进的内部平台，而不是一次性工具采购：

```text
标准和治理
  + 开发者黄金路径
  + 可追溯的软件供应链
  + 自动化测试与 OTA 仿真
  + GitOps 和领域发布控制
  + SLO/事故/Runbook
  + AI 只读理解层
  + 策略约束的执行层
```

最有价值的二开应集中在 ZOTA 的领域差异：

- 车辆和 ECU 软件关系。
- release graph。
- 兼容矩阵。
- 车辆 cohort 和风险门禁。
- OTA Digital Twin。
- 事故上下文。
- 受控 Runbook。
- ZOTA MCP。

其他通用能力尽量采用成熟开源项目，通过插件、Adapter、Operator、Webhook 和标准协议组合。这样既能形成覆盖开发、测试、上线和运营的完整体系，也能控制长期维护成本。

## 38. 总蓝图新增参考

### 38.1 平台与工程效能

- [Backstage](https://github.com/backstage/backstage)
- [Apache DevLake](https://github.com/apache/devlake)
- [Woodpecker CI](https://github.com/woodpecker-ci/woodpecker)
- [Tekton Pipelines](https://github.com/tektoncd/pipeline)
- [Argo Workflows](https://github.com/argoproj/argo-workflows)
- [OpenTofu](https://github.com/opentofu/opentofu)
- [Crossplane](https://github.com/crossplane/crossplane)
- [vCluster](https://github.com/loft-sh/vcluster)


### 38.2 供应链与安全

- [Harbor](https://github.com/goharbor/harbor)
- [ORAS](https://github.com/oras-project/oras)
- [Cosign](https://github.com/sigstore/cosign)
- [Syft](https://github.com/anchore/syft)
- [Grype](https://github.com/anchore/grype)
- [Trivy](https://github.com/aquasecurity/trivy)
- [Dependency-Track](https://github.com/DependencyTrack/dependency-track)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
- [Renovate](https://github.com/renovatebot/renovate)
- [OpenBao](https://github.com/openbao/openbao)
- [External Secrets Operator](https://github.com/external-secrets/external-secrets)
- [SOPS](https://github.com/getsops/sops)
- [Kyverno](https://github.com/kyverno/kyverno)
- [OPA Gatekeeper](https://github.com/open-policy-agent/gatekeeper)
- [Kubescape](https://github.com/kubescape/kubescape)
- [Falco](https://github.com/falcosecurity/falco)
- [Tetragon](https://github.com/cilium/tetragon)

### 38.3 测试、韧性、成本与灾备

- [Testcontainers](https://github.com/testcontainers)
- [Pact](https://github.com/pact-foundation)
- [Schemathesis](https://github.com/schemathesis/schemathesis)
- [k6](https://github.com/grafana/k6)
- [OWASP ZAP](https://github.com/zaproxy/zaproxy)
- [LitmusChaos](https://github.com/litmuschaos/litmus)
- [Chaos Mesh](https://github.com/chaos-mesh/chaos-mesh)
- [OpenCost](https://github.com/opencost/opencost)
- [Velero](https://github.com/velero-io/velero)

### 38.4 AI 工程

- [OpenHands](https://github.com/OpenHands/OpenHands)
- [SWE-agent](https://github.com/SWE-agent/SWE-agent)
- [Aider](https://github.com/Aider-AI/aider)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [vLLM](https://github.com/vllm-project/vllm)
- [Ollama](https://github.com/ollama/ollama)
- [Langfuse](https://github.com/langfuse/langfuse)
- [Arize Phoenix](https://github.com/Arize-ai/phoenix)
- [Promptfoo](https://github.com/promptfoo/promptfoo)
- [Ragas](https://github.com/explodinggradients/ragas)
- [pgvector](https://github.com/pgvector/pgvector)
- [Qdrant](https://github.com/qdrant/qdrant)

所有候选项目在正式采用前都必须重新核对：

- 当前维护状态。
- 许可证和附加条款。
- 安全响应机制。
- 升级和数据迁移能力。
- 中国区网络、镜像和通知渠道适配。
- 团队实际可维护性。

---

## 39. 智驾研发运营体系范围

智驾平台不能只覆盖云端服务和 OTA，还需要覆盖从车辆需求、安全目标、数据、算法、模型、仿真、车端软件到量产运营的完整闭环。

### 39.1 主要领域

| 领域 | 核心资产 | 关键结果 |
|---|---|---|
| 系统工程 | ODD、功能定义、需求、接口、安全目标 | 可追溯的系统基线 |
| E/E 与车端平台 | ECU、SoC、MCU、OS、中间件、驱动 | 可复现的软件运行环境 |
| 传感器与标定 | Camera、LiDAR、Radar、IMU、GNSS、时间同步 | 可验证的标定和传感器健康 |
| 感知与融合 | 检测、分割、跟踪、占用、融合 | 场景分层的性能和鲁棒性 |
| 定位与地图 | GNSS/INS、SLAM、HD Map、Lane Model | 可用性、精度和地图一致性 |
| 预测 | 行为预测、轨迹预测、交互建模 | 分布和长尾场景性能 |
| 规划与决策 | 路径、行为、速度、博弈、最小风险策略 | 安全、舒适和可解释决策 |
| 控制与执行 | 横纵向控制、底盘接口、执行器 | 稳定性、跟踪误差和故障降级 |
| 数据闭环 | 采集、筛选、上传、治理、标注、挖掘 | 可复用、可审计的数据资产 |
| 模型工程 | 训练、评估、压缩、部署、监控 | 可追溯的模型制品 |
| 仿真与验证 | 场景库、SIL、MIL、HIL、VIL、道路测试 | 可量化的场景和风险覆盖 |
| 车云协同 | 车辆信号、事件、诊断、影子模式、远程协助 | 安全可靠的端云数据流 |
| OTA 与配置 | 软件、模型、地图、标定、策略发布 | 可控灰度、回滚和证据 |
| 功能安全/SOTIF | HARA、Safety Case、触发条件、残余风险 | 可审计的安全论证 |
| 网络安全 | TARA、CSMS、密钥、入侵检测、漏洞响应 | 生命周期安全闭环 |
| 车队运营 | 在线、健康、任务、事故、维修、召回 | 车辆可用性和运营效率 |

### 39.2 统一管理的软件定义车辆资产

智驾发布不应只有一个应用版本号。应把以下内容都作为独立、不可变、可签名、可追溯的制品：

- ECU/MCU 固件。
- 操作系统和 BSP。
- 智驾应用和共享库。
- 感知、预测、规划等模型。
- 地图和道路语义数据。
- 传感器标定参数。
- 车辆配置、Feature Flag 和策略参数。
- 诊断规则和安全降级策略。
- 数据采集触发规则。
- 仿真场景集和测试基线。

一个车辆 Release Bundle 应引用这些制品的 digest，而不是复制可变文件。

### 39.3 智驾数字主线

```text
ODD / 安全目标 / 需求
        |
        v
系统设计 / 软件架构 / 接口契约
        |
        +-------------------------------+
        |                               |
        v                               v
代码 / 配置 / 地图 / 标定           数据集 / 标签 / 场景
        |                               |
        v                               v
构建与静态验证                     训练 / 评估 / 仿真
        |                               |
        +---------------+---------------+
                        v
                Vehicle Release Bundle
                        |
                        v
             台架 -> 封闭场 -> 道路 -> 车队
                        |
                        v
          车辆事件 / Shadow / 接管 / 故障 / EOL
                        |
                        v
             场景挖掘 / 缺陷 / 数据闭环
                        |
                        +-----------> 下一轮需求与训练
```

任何线上异常都应能反向追溯到：

- 车辆硬件和传感器配置。
- 软件、模型、地图和标定版本。
- 构建和签名证据。
- 训练数据和模型评估。
- 仿真场景和道路测试。
- 发布审批和 rollout。

## 40. 智驾端云总体架构

```text
┌──────────────────────────── Vehicle Plane ────────────────────────────┐
│ Sensors -> Drivers -> Middleware -> Localization/Perception/Fusion    │
│        -> Prediction -> Planning -> Control -> Vehicle Interface      │
│                                                                      │
│ Health / Recorder / Diagnostics / Security / OTA Agent / Safe State  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ selected telemetry / events / artifacts
┌───────────────────────────────▼──────────────────────────────────────┐
│ Edge & Connectivity Plane                                            │
│ Vehicle Gateway / VSS / MQTT-DDS-Zenoh / Upload Policy / Cache       │
│ Identity / Certificate / Encryption / Bandwidth / Privacy            │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│ Vehicle Cloud & Fleet Plane                                          │
│ ZOTA / JetLinks / hawkBit / Vehicle Twin / Fleet Health / Commands   │
│ Release / Rollout / EOL / Incident / Remote Diagnostics              │
└───────────────────────┬───────────────────────┬──────────────────────┘
                        │                       │
┌───────────────────────▼────────────┐  ┌──────▼───────────────────────┐
│ Data Closed-loop Plane            │  │ Reliability & Security Plane │
│ Ingest/Lakehouse/Catalog/Label    │  │ OTel/SLO/SOC/CSMS/Runbook    │
│ Mine/Curate/Train/Evaluate        │  │ Audit/Backup/Incident        │
└───────────────────────┬────────────┘  └──────┬───────────────────────┘
                        │                      │
┌───────────────────────▼──────────────────────▼───────────────────────┐
│ Validation & Release Plane                                           │
│ Scenario DB / SIL / HIL / VIL / Track / Road / Safety Case          │
│ Gate Engine / Release Graph / Signed Vehicle Release Bundle          │
└──────────────────────────────────────────────────────────────────────┘
```

AI 平台横跨各层，但不成为车辆实时控制链路的一部分。

## 41. 系统工程与安全需求

### 41.1 ODD 是顶层配置

每个智驾功能必须有机器可读的 ODD 描述，至少包括：

- 道路类型。
- 地理范围。
- 速度范围。
- 天气、光照和能见度。
- 交通参与者。
- 道路设施和地图要求。
- 传感器和车辆健康条件。
- 驾驶员/远程协助要求。
- 退出、接管和最小风险状态。

ODD 变化必须触发影响分析、场景增补和重新验证，不能只是修改产品文档。

### 41.2 需求到验证双向追溯

```text
Safety Goal
  -> Functional Safety Requirement
  -> Technical Safety Requirement
  -> Software/Hardware Requirement
  -> Implementation
  -> Unit/Integration/Scenario Test
  -> Vehicle Evidence
```

可评估：

- Eclipse Capra：跨工件追溯。
- ReqIF 作为需求交换格式。
- Git/Docs as Code 保存 ADR、接口和验证计划。
- Backstage 汇总 owner、需求、测试和事故链接。

AI 可以帮助检查缺失链接和生成影响分析草稿，但不能签署安全需求或 Safety Case。

### 41.3 适用标准与法规

至少纳入：

- ISO 26262 功能安全。
- ISO 21448 SOTIF。
- ISO/SAE 21434 道路车辆网络安全工程。
- UNECE R155 网络安全和 CSMS。
- UNECE R156 软件更新和 SUMS。
- 适用的国家标准、行业标准、型式认证和 OEM 要求。

标准版本和适用范围会变化，必须由功能安全、网络安全和法规团队在项目立项、SOP 和重大变更时确认，本文不替代合规判断。

## 42. 车端软件工程

### 42.1 车端分层

```text
Hardware/BSP
  -> OS/Hypervisor
  -> Drivers/Time Sync
  -> Communication Middleware
  -> Vehicle Signal & Service Layer
  -> AD Runtime
  -> Perception/Localization/Prediction/Planning/Control
  -> Diagnostics/Recorder/OTA/Security/Safety Supervisor
```

每层分别管理：

- API/ABI。
- CPU/GPU/NPU/内存预算。
- 启动顺序和健康。
- 实时性和 deadline。
- 降级和故障隔离。
- 兼容矩阵。

### 42.2 中间件候选

| 项目 | 可借鉴能力 | 建议 |
|---|---|---|
| ROS 2 | 节点、Topic、Service、Action、工具生态 | 研发和原型优先，量产需裁剪和安全评估 |
| Eclipse Cyclone DDS | DDS 实现 | 与 ROS 2/车端通信 PoC |
| eProsima Fast DDS | DDS 实现和工具 | 与 Cyclone DDS 做时延、资源和稳定性对比 |
| Eclipse Zenoh | Pub/Sub、Query、端云和弱网 | 适合边缘/端云研究，不直接替换现有链路 |
| Apollo Cyber RT | Apollo 运行时和通信 | 参考高性能智驾模块化架构 |
| COVESA VSS | 车辆信号语义标准 | 建立统一车辆信号模型 |
| Eclipse KUKSA Databroker | VSS 车内数据代理 | 车云和应用信号层 PoC |

注意：旧的 `kuksa.val` 已归档，应评估当前 `kuksa-databroker`，不要按历史教程引入 EOL 组件。

### 42.3 记录与回放

建议统一记录格式和元数据：

- rosbag2 或 MCAP。
- 时间同步状态。
- Topic/schema 版本。
- 车辆、硬件和软件基线。
- 触发原因。
- 数据权限和保留期限。
- 文件校验和加密信息。

MCAP 适合作为序列化无关的机器人数据容器候选；需要对现有日志、带宽、索引、分片和回放工具做 PoC。

### 42.4 车端可观测性

车端重点不是把全部原始指标上传云端，而是分层：

| 层级 | 数据 | 处理 |
|---|---|---|
| 实时安全 | deadline、进程、传感器、控制器健康 | 本地确定性监督和降级 |
| 车队健康 | 在线、版本、资源、错误码、阶段状态 | 聚合上云 |
| 调试证据 | 关键 Topic、Trace、core、日志 | 事件触发采集 |
| 数据闭环 | 场景片段、模型不确定性、接管 | 按策略脱敏上传 |

实时安全监督不能依赖云端 AI。

## 43. 传感器、标定与时间同步

### 43.1 资产化

传感器和标定需要版本化管理：

- 传感器型号、序列号和固件。
- 内参、外参和时间偏移。
- 标定方法、数据集和工具版本。
- 标定质量指标。
- 适用车辆和硬件批次。
- 生效时间和审批。

### 43.2 自动检查

可自动化：

- 传感器遮挡、污损、失焦和曝光异常检测。
- LiDAR 点云密度和时间戳异常。
- Radar object/track 健康。
- IMU/GNSS 跳变和漂移。
- 多传感器时间同步偏差。
- 标定参数漂移。

AI/视觉模型可以做候选异常检测，但安全降级应由确定性阈值和安全策略触发。

### 43.3 工具候选

- Kalibr：Camera/IMU 标定参考。
- ROS 2 calibration 生态。
- OpenCV：相机标定和视觉基础工具。
- PCL/Open3D：点云处理和质量分析。
- chrony/PTP/linuxptp：时间同步基础能力。

量产标定工具通常需要结合自有硬件、工位和质量体系二开。

## 44. 数据闭环平台

### 44.1 数据闭环流程

```text
Trigger Definition
  -> Vehicle-side Selection
  -> Local Buffer/Redaction
  -> Secure Upload
  -> Raw Data Landing
  -> Catalog/Quality/Lineage
  -> Scenario Mining
  -> Dedup/Curate
  -> Annotation/QA
  -> Dataset Version
  -> Train/Evaluate/Simulate
  -> Release
  -> Shadow/Production Feedback
```

### 44.2 数据分层

| 层 | 内容 |
|---|---|
| Raw | 原始传感器和车辆信号，只追加 |
| Standardized | 时间同步、schema 统一、脱敏 |
| Scenario | 切片、标签、道路和参与者语义 |
| Curated | 去重、平衡、难例、训练/验证/测试集 |
| Feature/Embedding | 特征、向量和场景索引 |
| Evidence | 训练、评估、仿真和发布引用的数据快照 |

训练集、验证集和测试集必须防止车辆、路线、时间或场景泄漏。

### 44.3 数据平台候选

| 能力 | 候选 |
|---|---|
| 对象存储 | MinIO、Ceph 或现有云对象存储 |
| Lakehouse 表格式 | Apache Iceberg |
| 批处理 | Apache Spark、Ray |
| 流处理 | Apache Flink |
| SQL 查询 | Trino |
| 数据版本 | lakeFS、DVC |
| 数据目录/血缘 | DataHub、OpenMetadata |
| 标注 | CVAT、Label Studio |
| 数据集探索/质量 | FiftyOne |
| 向量检索 | pgvector、Qdrant、Milvus |

不建议同时部署多个 Lakehouse、目录和向量数据库。首期围绕现有对象存储和 PostgreSQL 做最小闭环。

### 44.4 场景挖掘

重点触发：

- 接管和最小风险状态。
- 碰撞/近碰。
- 规划急变、舒适性异常。
- 感知不确定性和模块分歧。
- 新颖场景和 ODD 边界。
- 传感器异常。
- 地图不一致。
- Shadow 与生产决策差异。

AI 可以生成场景摘要和候选标签；最终训练标签需经过自动规则、交叉模型和人工抽检的质量闭环。

### 44.5 数据治理

必须记录：

- 数据来源和合法用途。
- 脱敏策略。
- 访问控制。
- 保留和删除策略。
- 训练/评估使用记录。
- 跨境和地域限制。
- 标注供应链和质量。

数据一旦被删除或撤回，需要能定位受影响的模型和发布。

## 45. 模型与算法 MLOps

### 45.1 模型不是普通文件

模型版本应包含：

- 模型结构和权重 digest。
- 训练代码 commit。
- 数据集版本和采样规则。
- 超参数和随机种子。
- 框架、CUDA、驱动和算子版本。
- 指标和分场景评估。
- 压缩、量化和编译结果。
- 目标芯片和性能。
- 已知限制和 ODD。
- 签名和审批。

### 45.2 模型生命周期

```text
Experiment
  -> Candidate
  -> Offline Qualified
  -> Simulation Qualified
  -> Vehicle Bench Qualified
  -> Shadow Qualified
  -> Release Candidate
  -> Production
  -> Deprecated/Revoked
```

晋级必须复制不可变模型版本或 digest 引用，不在原对象上修改。

### 45.3 MLOps 候选

| 能力 | 候选 | 建议 |
|---|---|---|
| Experiment/Registry | MLflow | 记录训练、评估和模型别名 |
| Pipeline | Kubeflow Pipelines、Flyte、Argo Workflows | 根据现有 K8s 和团队能力选一个 |
| 分布式计算 | Ray | 训练、评估和数据处理 PoC |
| Serving | KServe、BentoML | 主要用于云端/离线服务 |
| Inference runtime | ONNX Runtime、OpenVINO、Triton | 车端需结合芯片工具链 |
| Dataset quality | FiftyOne | 视觉/多模态数据分析 |
| Feature store | Feast | 有跨模型共享特征需求时再引入 |
| Drift/quality | Evidently、whylogs | 云端和 Shadow 监控参考 |

车端模型发布仍由 ZOTA Release Control Plane 管理，不由 MLflow 直接部署车辆。

### 45.4 模型评估维度

不能只看一个总 mAP/accuracy：

- 类别、距离、遮挡、尺寸。
- 天气、光照、道路和区域。
- 硬件/传感器批次。
- ODD 内外。
- 安全关键场景。
- 延迟、抖动、内存、功耗和温度。
- 模块联调和闭环驾驶表现。
- 与上一生产版本的回归。

### 45.5 Shadow Mode

新模型可在不控制车辆的情况下运行：

- 记录候选输出。
- 与生产模型比较。
- 统计场景差异和性能。
- 触发难例采集。

Shadow 结果进入数据闭环，但不得直接在线学习并自动替换生产模型。

## 46. 感知、融合、定位、预测、规划与控制

### 46.1 统一模块契约

每个模块必须定义：

- 输入输出 schema。
- 坐标系和时间语义。
- 频率、deadline 和超时。
- 质量/置信度。
- 无效值和降级语义。
- 资源预算。
- 兼容版本。

契约进入 CI 和回放测试，避免只在整车联调阶段发现接口问题。

### 46.2 感知与融合

重点工程能力：

- 数据和标签版本。
- 分场景评估。
- Sensor dropout 和故障注入。
- 模型/规则融合的可解释证据。
- 在线健康和不确定性。
- 量化/编译前后精度一致性。

可借鉴：

- OpenMMLab/MMDetection3D。
- OpenPCDet。
- Open3D/PCL。
- FiftyOne。

这些是研发工具和算法参考，不等于量产感知方案。

### 46.3 定位与地图

需要管理：

- 地图格式和版本。
- 地图区域、瓦片和生效时间。
- 采集、生产、审核和发布流程。
- GNSS/INS/SLAM 质量。
- 地图与实时道路的偏差。
- 无图/轻图/高精地图策略。

可借鉴：

- Lanelet2。
- ASAM OpenDRIVE 生态。
- Autoware map tools。
- OpenStreetMap/SUMO 转换工具。

地图是安全相关制品，不能由普通内容发布流程直接覆盖。

### 46.4 预测、规划与控制

验证重点：

- 确定性和可重复性。
- 约束满足。
- 舒适性和稳定性。
- 稀有交互场景。
- 最小风险策略。
- 传感器和定位退化。
- 执行器饱和、迟滞和故障。

AI 可以辅助生成场景和解释行为，不能在没有验证的情况下在线修改规划/控制参数。

## 47. 仿真与验证体系

### 47.1 验证阶梯

```text
Unit/Component
  -> MIL
  -> SIL
  -> Scenario Simulation
  -> Replay
  -> HIL
  -> VIL
  -> Closed Track
  -> Public Road
  -> Shadow/Fleet Monitoring
```

上一级结果不能完全替代下一级，但应尽量把问题提前。

### 47.2 场景库

场景应包含：

- 逻辑场景：参数范围和约束。
- 具体场景：确定参数和环境。
- 来源：法规、事故、路测、仿真生成、专家设计。
- ODD、风险和需求映射。
- 可重复随机种子。
- 预期行为和通过条件。
- 覆盖和执行历史。

### 47.3 开源仿真候选

| 项目 | 用途 | 注意 |
|---|---|---|
| CARLA | 传感器、环境、闭环智驾仿真 | 版本、Unreal、资产和 GPU 成本需评估 |
| ScenarioRunner | CARLA 场景执行 | 适合构建回归场景 |
| SUMO | 交通流和微观交通仿真 | 可与 CARLA 联合仿真 |
| esmini | OpenSCENARIO/OpenDRIVE 轻量执行 | 适合标准场景快速回归 |
| Eclipse openPASS | 交通/安全影响仿真 | 官方源码位于 Eclipse GitLab，评估场景和模型适配 |
| Gazebo | 机器人和传感器仿真 | 适合部分组件/原型 |
| Scenic | 场景编程和生成 | 适合约束随机场景 |
| VerifAI | 场景搜索和 falsification | 适合发现边界反例 |
| OSI | 仿真器与自动驾驶功能接口 | 作为联合仿真接口候选 |

Autoware 和 Apollo 可用于架构、工具链和基准对照，但不能未经产品化、安全化和硬件适配直接视为量产方案。

### 47.4 HIL/VIL 平台

需要统一：

- 台架硬件和固件版本。
- I/O 和总线配置。
- 植入故障。
- 仿真时间和同步。
- 测试脚本。
- 数据记录。
- 通过条件。

可借鉴：

- QEMU/Renode：部分 ECU/MCU 和软件虚拟化。
- SocketCAN、can-utils、python-can：CAN 测试。
- ROS 2/MCAP 回放。
- 自建硬件适配层。

商用 HIL 通常不可完全被开源工具替代，但其作业、数据和证据应接入统一测试平台。

### 47.5 场景覆盖

建议同时衡量：

- 需求覆盖。
- ODD 参数覆盖。
- 行为/交互覆盖。
- 代码和状态机覆盖。
- 风险和安全目标覆盖。
- 历史事故回归覆盖。
- 新版本差异覆盖。

累计仿真里程不是单独充分指标。

## 48. 车云协同与车队运营

### 48.1 Vehicle Digital Twin

云端车辆孪生应包含：

- 硬件、传感器和 ECU 清单。
- 软件、模型、地图、标定和配置版本。
- 在线、网络、电源和资源状态。
- 诊断故障码。
- OTA 状态和历史。
- 证书和身份状态。
- 车辆能力和 ODD。
- 当前任务和运营状态。

孪生是状态视图，不是直接下发任意命令的后门。

### 48.2 远程诊断与协助

操作分级：

| 类型 | 示例 | 控制 |
|---|---|---|
| 只读诊断 | 查询状态、日志、版本 | 常规授权 |
| 低风险维护 | 刷新诊断、重新拉取非关键配置 | Runbook + 审计 |
| 运营指令 | 暂停任务、进入维护状态 | 审批和范围限制 |
| 车辆控制 | 远程驾驶、制动、转向 | 独立安全系统和法规流程 |

AI 不应直接发起车辆控制。

### 48.3 车队运营 SLI

- 可运营车辆比例。
- 车辆在线率。
- 任务完成率。
- 每千公里接管/故障/最小风险事件。
- 传感器和计算平台健康。
- 远程协助率和处理时长。
- OTA 对运营可用性的影响。
- 按车型/区域/版本的事故和维修趋势。

## 49. 智驾安全与网络安全运营

### 49.1 Safety Operations

量产后持续收集：

- ODD 越界。
- 接管和最小风险状态。
- 安全监控触发。
- 近碰和异常行为。
- 传感器退化。
- 地图和道路不一致。
- 模型/规则的未知场景。

这些事件应进入 SOTIF 和 Safety Case 的持续更新，不只进入普通故障工单。

### 49.2 Cybersecurity Operations

覆盖：

- 车辆身份和证书。
- Secure Boot、固件和模型验证。
- CAN/Ethernet/诊断接口。
- 车云 API 和消息。
- 供应链漏洞。
- 入侵检测和事件响应。
- 漏洞披露、补丁和召回。

云端 SOC 和车辆安全事件需要统一事件 ID，但权限和处置流程分离。

### 49.3 安全发布门禁

以下情况应阻断发布：

- 签名或 digest 不匹配。
- 兼容矩阵不通过。
- 安全目标对应测试缺失。
- 高风险场景回归失败。
- 标定或地图适用范围不明确。
- 关键漏洞未按策略处置。
- 回滚或最小风险策略不可用。
- EOL/审计链不完整。

AI 只能解释阻断原因，不能自行豁免。

## 50. 智驾 AI Agent 设计

### 50.1 可采用的 Agent

| Agent | 主要能力 | 初始权限 |
|---|---|---|
| Requirement Trace Agent | 查缺失追溯、生成影响分析 | 只读 |
| Data Curator Agent | 去重、聚类、难例和采样建议 | 写候选数据集 |
| Annotation QA Agent | 发现漏标、错标和不一致 | 标记问题，不直接覆盖金标 |
| Scenario Mining Agent | 从路测/事故提取场景参数 | 创建候选场景 |
| Model Evaluation Agent | 汇总分场景回归和资源变化 | 只读 |
| Simulation Triage Agent | 归类失败、定位首次异常帧 | 只读 |
| Vehicle Log Investigator | 关联 MCAP、日志、DTC、版本 | 只读 |
| Calibration Assistant | 分析标定质量和漂移 | 建议复检 |
| Release Guardian | 汇总安全、测试、SLO 和车队风险 | go/no-go 建议 |
| Safety Case Assistant | 整理证据和变更影响 | 草稿，不签署 |
| Fleet Risk Agent | 识别车型/区域/版本风险 | 只读 |

### 50.2 禁止交给 Agent 的事项

- 自动批准安全需求或 Safety Case。
- 自动修改生产 Ground Truth 并用于训练。
- 自动把实验模型提升为量产模型。
- 在线学习后直接替换生产模型。
- 自动修改规划、控制或安全监控参数。
- 绕过台架、仿真、封闭场或道路测试。
- 直接发送车辆控制命令。
- 自动吊销大批车辆证书。
- 删除事故、路测和 EOL 证据。

## 51. 智驾重点二开项目

### 51.1 AD Digital Thread

统一索引：

```text
ODD / Requirement / Safety Goal
  -> Code / Data / Label / Model / Map / Calibration
  -> Scenario / Test / Evidence
  -> Vehicle Release Bundle
  -> Vehicle / Fleet Result
  -> Incident / Safety Event
```

建议以独立元数据服务实现，底层引用现有 Git、MLflow、对象存储、ZOTA、测试平台和事故系统，不复制所有原始数据。

### 51.2 Scenario & Evidence Platform

应提供：

- 场景目录和版本。
- OpenSCENARIO/OpenDRIVE 等格式适配。
- 仿真器 Adapter。
- 执行调度。
- 覆盖度和结果。
- 失败聚类。
- 需求和安全目标关联。
- 不可变证据包。

### 51.3 Vehicle Release Bundle

建议扩展当前 ZOTA 发布模型：

```json
{
  "release_id": "vrb-...",
  "vehicle_platform": "platform-a",
  "hardware_compatibility": [],
  "software_artifacts": [],
  "model_artifacts": [],
  "map_artifacts": [],
  "calibration_artifacts": [],
  "config_artifacts": [],
  "safety_constraints": [],
  "test_evidence": [],
  "rollback_bundle": "vrb-previous",
  "signature": "..."
}
```

### 51.4 OTA Risk Engine

除通用发布风险外增加：

- 车型和硬件批次。
- ECU/MCU 依赖。
- 车辆电量、网络和存储。
- 当前运营任务。
- 地图区域。
- ODD 和环境。
- 历史升级长尾。
- 安全事件和召回状态。

### 51.5 Fleet Incident Replay

将一个车辆事件关联为可回放包：

- 事件前后窗口。
- MCAP/日志/Trace。
- 软件和模型版本。
- 地图、标定和配置。
- DTC 和系统资源。
- 云端命令和 rollout。
- 仿真复现场景。

这是 AI 调查和事故复盘最有价值的数据产品之一。

## 52. 智驾开源候选清单

### 52.1 智驾栈与中间件

- [ROS 2](https://github.com/ros2)
- [Autoware](https://github.com/autowarefoundation/autoware)
- [Autoware Core](https://github.com/autowarefoundation/autoware_core)
- [Autoware Universe](https://github.com/autowarefoundation/autoware_universe)
- [Apollo](https://github.com/ApolloAuto/apollo)
- [Eclipse Cyclone DDS](https://github.com/eclipse-cyclonedds/cyclonedds)
- [Fast DDS](https://github.com/eProsima/Fast-DDS)
- [Eclipse Zenoh](https://github.com/eclipse-zenoh/zenoh)
- [COVESA Vehicle Signal Specification](https://github.com/COVESA/vehicle_signal_specification)
- [Eclipse KUKSA Databroker](https://github.com/eclipse-kuksa/kuksa-databroker)
- [MCAP](https://github.com/foxglove/mcap)
- [Rerun](https://github.com/rerun-io/rerun)

### 52.2 数据、标注与模型

- [Apache Iceberg](https://github.com/apache/iceberg)
- [Apache Spark](https://github.com/apache/spark)
- [Apache Flink](https://github.com/apache/flink)
- [Trino](https://github.com/trinodb/trino)
- [lakeFS](https://github.com/treeverse/lakeFS)
- [DVC](https://github.com/iterative/dvc)
- [DataHub](https://github.com/datahub-project/datahub)
- [OpenMetadata](https://github.com/open-metadata/OpenMetadata)
- [CVAT](https://github.com/cvat-ai/cvat)
- [Label Studio](https://github.com/HumanSignal/label-studio)
- [FiftyOne](https://github.com/voxel51/fiftyone)
- [MLflow](https://github.com/mlflow/mlflow)
- [Kubeflow Pipelines](https://github.com/kubeflow/pipelines)
- [Flyte](https://github.com/flyteorg/flyte)
- [Ray](https://github.com/ray-project/ray)
- [KServe](https://github.com/kserve/kserve)
- [BentoML](https://github.com/bentoml/BentoML)
- [ONNX Runtime](https://github.com/microsoft/onnxruntime)
- [OpenVINO](https://github.com/openvinotoolkit/openvino)

Flyte 需要结合选定版本、部署复杂度、现有 K8s 基础和团队维护能力单独评估；不要仅依据项目热度替换已经稳定运行的流水线。

### 52.3 感知、点云与地图

- [MMDetection3D](https://github.com/open-mmlab/mmdetection3d)
- [OpenPCDet](https://github.com/open-mmlab/OpenPCDet)
- [Open3D](https://github.com/isl-org/Open3D)
- [PCL](https://github.com/PointCloudLibrary/pcl)
- [Lanelet2](https://github.com/fzi-forschungszentrum-informatik/Lanelet2)
- [Kalibr](https://github.com/ethz-asl/kalibr)

### 52.4 仿真与验证

- [CARLA](https://github.com/carla-simulator/carla)
- [CARLA ScenarioRunner](https://github.com/carla-simulator/scenario_runner)
- [SUMO](https://github.com/eclipse-sumo/sumo)
- [esmini](https://github.com/esmini/esmini)
- [Eclipse openPASS](https://gitlab.eclipse.org/eclipse/openpass/opSimulation)
- [Gazebo](https://github.com/gazebosim/gz-sim)
- [Scenic](https://github.com/BerkeleyLearnVerify/Scenic)
- [VerifAI](https://github.com/BerkeleyLearnVerify/VerifAI)
- [Open Simulation Interface](https://github.com/OpenSimulationInterface/open-simulation-interface)
- [Renode](https://github.com/renode/renode)
- [can-utils](https://github.com/linux-can/can-utils)
- [python-can](https://github.com/hardbyte/python-can)

### 52.5 OTA、安全和车辆生命周期

- [The Update Framework](https://github.com/theupdateframework/python-tuf)
- [Uptane](https://github.com/uptane)
- [Aktualizr](https://github.com/advancedtelematic/aktualizr)
- [Eclipse hawkBit](https://github.com/eclipse-hawkbit/hawkbit)
- [RAUC](https://github.com/rauc/rauc)
- [SWUpdate](https://github.com/sbabic/swupdate)
- [OSTree](https://github.com/ostreedev/ostree)
- [Eclipse Capra](https://github.com/eclipse-capra/capra)
- [Eclipse Ditto](https://github.com/eclipse-ditto/ditto)

以上项目用于能力借鉴和 PoC，不意味着可以直接满足量产、功能安全、SOTIF、网络安全或型式认证要求。

## 53. 智驾路线图并入总计划

### AD Stage 0：资产和追溯基线，0～3 个月

- 定义车辆软件资产模型和 Release Bundle。
- 统一车辆、硬件、软件、模型、地图、标定 ID。
- 建立 ODD、需求、安全目标到测试的追溯。
- 统一车端记录元数据和事件格式。
- 建立最小车辆孪生。

### AD Stage 1：数据与模型闭环，2～6 个月

- 对象存储、数据目录和数据集版本。
- 场景触发、上传、脱敏和质量。
- 标注和 QA。
- MLflow/训练流水线。
- 模型制品签名和 ZOTA 发布关联。
- Shadow Mode。

### AD Stage 2：场景与仿真验证，4～9 个月

- 场景目录。
- CARLA/SUMO/esmini 等 Adapter PoC。
- 回放、SIL 和场景回归。
- HIL 作业和证据接入。
- OTA Digital Twin 与车辆仿真。
- 场景覆盖 Dashboard。

### AD Stage 3：智驾发布门禁，6～12 个月

- 兼容矩阵。
- 模型、地图、标定和配置门禁。
- 车辆 cohort 风险引擎。
- 测试和 Safety Evidence。
- 自动暂停、人工继续和受控回滚。
- Fleet Incident Replay。

### AD Stage 4：AI 辅助研发与调查，9～15 个月

- Data Curator/Annotation QA/Scenario Mining Agent。
- Model Evaluation/Simulation Triage Agent。
- Vehicle Log Investigator。
- Safety Case Assistant。
- 智驾 MCP 只读工具。
- 内部事故和场景金标集。

### AD Stage 5：规模化安全运营，12～24 个月

- 多车型、多硬件平台和多区域治理。
- 车队风险和 SOTIF 持续监控。
- CSMS/SUMS 证据自动汇总。
- 大规模仿真和成本治理。
- 受控 Runbook 和跨域事故联动。
- 发布风险模型持续校准。

## 54. 智驾部分最终建议

智驾体系的优先级应是：

```text
安全目标和 ODD
  -> 数字主线和资产追溯
  -> 数据与模型闭环
  -> 场景仿真和分层验证
  -> Vehicle Release Bundle 和 OTA 门禁
  -> 车队健康、安全和事故闭环
  -> AI 辅助理解
  -> 最后才是受控自治
```

优先二开：

- AD Digital Thread。
- Vehicle Release Bundle。
- Scenario & Evidence Platform。
- OTA Risk Engine。
- Fleet Incident Replay。
- Vehicle/AD MCP Gateway。

优先采用或集成成熟开源能力：

- ROS 2/Autoware/Apollo 作为架构与研发参考。
- MCAP 和回放工具。
- CVAT/FiftyOne/MLflow 等数据与模型工具。
- CARLA/SUMO/esmini/openPASS 等仿真工具。
- TUF/Uptane/hawkBit/RAUC/SWUpdate 等 OTA 安全机制。

最终边界：

> AI 可以扩大测试、调查、数据治理和知识复用能力，但实时控制、安全监控、发布门禁、车辆控制和安全签署必须保持确定性、可验证和可审计。
