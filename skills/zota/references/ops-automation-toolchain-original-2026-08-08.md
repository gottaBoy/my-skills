# ZOTA 运维自动化工具链 — 方案分析

> 状态：提案 | 日期：2026-08-08 | 作者：AI Copilot

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
