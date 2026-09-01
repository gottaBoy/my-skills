# 05 DSH 进度与验收

更新时间：`2026-08-29`

## 状态定义

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>状态</th><th>含义</th><th>不能表达的含义</th></tr></thead>
  <tbody>
    <tr><td><code>approved</code></td><td>设计已评审，可进入实现</td><td>不是代码已完成或已部署</td></tr>
    <tr><td><code>implemented</code></td><td>代码或文档已完成</td><td>不是现场已验证</td></tr>
    <tr><td><code>verified</code></td><td>已有构建、测试或现场证据验证</td><td>不是全车型、全车队已放量</td></tr>
    <tr><td><code>blocked</code></td><td>连续三次相同外部阻塞且无合理推进路径</td><td>不能用于表示“还没做”或“需要更多测试”</td></tr>
  </tbody>
</table>

## 当前进度

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>工作项</th><th>状态</th><th>现状</th><th>下一步</th></tr></thead>
  <tbody>
    <tr><td>前端本地结构化埋点</td><td><code>verified</code></td><td>500 条环形缓存、sequence、performance.now、过滤订阅、异常隔离；Vite build 通过</td><td>补单元测试和真实现场回归</td></tr>
    <tr><td>黑屏恢复误重载防护</td><td><code>implemented</code></td><td>internalCode 锁定、旧响应隔离、共享租约、stats 门禁、render eligibility</td><td>Playwright、隐藏 Tab、换车、HMR 和真实黑屏</td></tr>
    <tr><td>后端 JVM 单调耗时</td><td><code>verified</code></td><td>EventBus/queue/send 同 JVM duration 字段已消费，Maven compile 通过</td><td>部署后确认字段非负并接入指标</td></tr>
    <tr><td>车端 RTSP 本地诊断埋点</td><td><code>implemented/unverified</code></td><td><code>ztd_rtsp</code> 的 ROS callback、appsrc demand/push、GStreamer flow、pipeline 生命周期、encoder、RTP 和 bus 诊断已落到 <code>RtspStream</code>；实车当前未继续出现前端“重拉”，但新代码尚未完成编译和部署二进制核对</td><td>编译部署后确认完整 <code>rtsp_diag</code>/<code>rtsp_timing</code>/<code>gst_bus</code> 字段，并完成至少 30 分钟回归</td></tr>
    <tr><td>云端进入到车端的 <code>remotejoystick</code> 分段埋点</td><td><code>implemented/unverified</code></td><td>暂不依赖驾驶仓；ziot latest-only 在途/完成、TCP write/连接生命周期，以及车端 body receive/decrypt/parse/dispatch、handler/publish/MRC 日志已落地</td><td>执行一条真实云端下发指令，确认云端指标/日志增长、同一 <code>messageId/seq/correlationId</code> 在车端出现，并验证 DeepFlow/Collector/DataBuff；ROS 下游消费和底盘执行暂不纳入</td></tr>
    <tr><td>车端业务事件与 monotonic ledger</td><td><code>approved</code></td><td>已定义控制和视频统一事件模型、字段、队列和资源预算；不等同于 RTSP 本地诊断代码已接入统一出口</td><td>实现 <code>ztd_observability</code>、完整事件出口、统一 trace context 和两个服务接入</td></tr>
    <tr><td>车端 eBPF/DeepFlow 节点监控</td><td><code>approved</code></td><td>已定义 V0 能力检查、首期 tracepoint 和四组性能对照</td><td>目标车验证 BTF、权限、Agent 兼容性</td></tr>
    <tr><td>三链路 Trace Context</td><td><code>approved</code></td><td>已定义 command/video/status 的 Trace/Span 和旧版本降级</td><td>实现控制 headers、视频预绑定和云端传播</td></tr>
    <tr><td>OTel/Gateway/Collector/DeepFlow</td><td><code>implemented/verified-poc</code></td><td>DeepFlow 7.1.002 已在 K8s <code>deepflow</code> Namespace 完成单节点 POC；Server 健康、Agent 注册、Kubernetes/eBPF 平台同步、内部受控 HTTP 流量写入 ClickHouse 和 Grafana API 均已验证</td><td>验证真实云端到车端指令流量关联、采样脱敏、性能、断网恢复，并接入 ECS/外部 Docker Agent；DeepFlow flow 到 DataBuff 的自动导出仍需单独验收</td></tr>
    <tr><td>GreptimeDB Edge/Arrow 车端数据平面</td><td><code>approved</code></td><td>已记录 Edge/Edge Manager 边界、Arrow 内存/批量交换、Parquet 归档、Trace Context 和 WAL/DataBuff 断点续传边界；Flow batching 与向量能力纳入版本校验</td><td>完成目标车版本矩阵、单车 Edge POC、Arrow/IPC 生命周期、断网恢复、Flow/向量能力验证和四组性能对照</td></tr>
    <tr><td>DSH Integration Pack 与进度治理</td><td><code>implemented</code></td><td>Profile、6 个 Schema、工具注册表、正负例夹具、依赖无关校验脚本、专题文档、完整基线和 <code>loop/STATE.md</code> 已同步；本地契约校验通过</td><td>部署 DSH/Cordis runtime 和适配器后，按能力矩阵逐项留存运行证据</td></tr>
  </tbody>
</table>

## 验收顺序

1. `V0`：车载镜像能力和资源基线。
2. `V1`：本地业务事件有界队列，不阻塞实时线程。
3. `V2`：控制和视频阶段 monotonic duration 非负且可聚合。
4. `V3`：控制 Trace Context、视频 `VideoTraceBinding` 和旧版本降级。
5. `V4`：eBPF 网络/调度/资源事实与业务事件按 PID、cgroup、socket cookie 和时间窗关联。
6. `V5`：OTel/WAL 异步批量、断网缓存、恢复补传和 drop 计数。
7. `V6`：单车单路的视频、指令、状态上报闭环。
8. `V7`：注入帧、显示屏相机或 GPIO/LED 物理校准后放量。

GreptimeDB Edge/Arrow 专项还必须提供以下证据后，才能把该工作项从
`approved` 更新为 `implemented` 或 `verified`：

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>证据</th><th>必须记录</th><th>放行条件</th></tr></thead>
  <tbody>
    <tr><td>目标车版本矩阵</td><td>车型、SoC、BSP/内核、Edge、Arrow、Collector、OTAP/上传协议和配置版本</td><td>所有使用的能力均有兼容性结论，未验证接口不作为生产前提</td></tr>
    <tr><td>资源对照</td><td>全关闭、本地事件、Edge 写入、全链路上传四组的 CPU、RSS、磁盘写入、网络流量、控制 P95 和视频 FPS/首帧</td><td>没有不可接受的控制或视频回退，队列和批次有硬上限</td></tr>
    <tr><td>断网与恢复</td><td>WAL/DataBuff 积压、checksum、重试、断点续传、重复上传和磁盘水位淘汰</td><td>恢复后可幂等补传；观测故障不阻塞实时链路</td></tr>
    <tr><td>格式与诊断能力</td><td>Arrow/IPC 生命周期、Parquet 文件完整性、Trace 字段、Flow batching 和向量能力</td><td>Trace 仍由上下文承担；Flow/向量仅用于诊断，不触发控制或视频 reload</td></tr>
  </tbody>
</table>

## 测试必须证明

<table border="1" cellpadding="6" cellspacing="0">
  <thead><tr><th>场景</th><th>必须看到的证据</th><th>通过条件</th></tr></thead>
  <tbody>
    <tr><td>正常控制</td><td>receive、parse、handler、ROS publish、messageId 一致</td><td>阶段 duration 非负，业务结果不改变</td></tr>
    <tr><td>控制网络重传</td><td>message timeout/ping RTT、eBPF retrans/RTO/queue</td><td>能区分网络异常和 handler 慢</td></tr>
    <tr><td>正常视频</td><td>ROS frame、encoder、first RTP、ZLM、ICE、inbound RTP、decode、render</td><td>可串起一路视频生命周期</td></tr>
    <tr><td>车端编码停滞</td><td>ROS/appsrc 继续，encoder output age 增长，RTP 停止</td><td>分类为编码或资源问题，不归因浏览器黑屏</td></tr>
    <tr><td>浏览器渲染冻结</td><td>inbound RTP 增长，framesDecoded/render 停止，页面资格字段齐全</td><td>分类为解码/渲染，不触发无依据全路重载</td></tr>
    <tr><td>观测系统故障</td><td>drop、exporter error、Agent/Collector 不可达</td><td>控制、视频和状态主链路继续运行</td></tr>
  </tbody>
</table>

DSH 只能基于查询到的事件、Trace、Metric、Log、ZLMediaKit、Broker 和发布记录输出根因
候选、支持证据、反证、缺失证据和下一步查询。生产自动修复必须经过人工审批、范围限制、
成功条件、退出条件、审计和回滚。

## 文档同步规则

每次实现或验证完成时同步：

1. 本专题文档的状态、证据、日期和下一步。
2. [完整设计基线](../full-link-observability.md) 的对应章节或工作项。
3. [`../loop/STATE.md`](../loop/STATE.md) 的一条追加记录。

本轮完成 GreptimeDB Edge/Arrow 专题设计、公开资料边界校正和 DSH 进度同步；另有
车端 `ztd_rtsp` 本地诊断代码修改，但尚未部署统一 `ztd_observability`、OTel、Collector、
DeepFlow、DataBuff，也没有完成当前代码的编译和目标车辆长时间验证。公开案例的吞吐、
CPU、内存和压缩数字仍只作为 POC 压测输入。

## 2026-08-26 关机检查点

当前状态冻结为：

- POC 工具已落盘到 `aura/tools/observability_poc/`。
- 尚未运行本机单元测试、能力矩阵、WAL 恢复、Arrow/IPC 或四组性能 smoke test。
- 尚未安装 `pyarrow`，也未部署 GreptimeDB Edge、OTel、DeepFlow 或 OTAP。
- 本轮已修改 `ztd_rtsp` 车端 `RtspStream` 运行逻辑，范围包含 push 并发/生命周期保护和本地诊断；
  尚未修改 operator、takeover/Redis 或统一 OTel/DeepFlow 生产链路。
- 所有 GreptimeDB Edge/Arrow 工作项继续保持 `approved`，不得标记为实车
  `implemented` 或 `verified`。

下次开机按以下顺序恢复：

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr><th>顺序</th><th>工作项</th><th>输出证据</th><th>通过条件</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>目标车型版本矩阵</td><td>车型、SoC、BSP、内核、BTF/eBPF、ROS 2、GStreamer、容器、Edge、Arrow、Collector 和上传协议版本</td><td>每项能力有 supported/unsupported/unverified 结论，不用开发机结果代替目标车结果</td></tr>
    <tr><td>2</td><td>单车 Edge POC</td><td>一台目标车、一路 <code>cam_f_12</code>、一条 <code>remotejoystick</code> 的写入、查询、资源和故障隔离报告</td><td>Edge 停止、写入失败或查询变慢均不影响控制、编码、RTP 和视频恢复逻辑</td></tr>
    <tr><td>3</td><td>Arrow/IPC 生命周期</td><td>Schema metadata、monotonic 时间、原子发布、读回、checksum、进程重启和损坏文件隔离报告</td><td>无半文件可见、Schema 可演进、内存与批次有硬上限、Trace Context 不被格式层替代</td></tr>
    <tr><td>4</td><td>断网补传</td><td>断网 5 分钟、积压、磁盘水位、重试、checksum、重复 batch、进程重启和恢复补传报告</td><td>幂等补传；损坏数据隔离；观测队列满时丢弃并计数，不阻塞实时业务</td></tr>
    <tr><td>5</td><td>A/B/C/D 性能对照</td><td>全关闭、本地事件、Edge 写入、全链路上传四组 CPU、RSS、磁盘、网络、控制 P95/P99、视频 FPS、首帧和黑屏次数</td><td>资源增量在目标车型预算内，控制和视频无不可接受回退</td></tr>
  </tbody>
</table>

恢复后先执行开发机工具自检，结果只能作为工具验证：

```bash
cd /Users/minyi/workspace/autodrive/aura
python3 -m unittest discover -s tools/observability_poc/tests -v
python3 tools/observability_poc/pocctl.py matrix \
  --vehicle-model development-host \
  --environment local-poc \
  --output poc-results/version-matrix-local.json
python3 tools/observability_poc/pocctl.py wal-recovery \
  --batches 8 \
  --output poc-results/wal-recovery-local.json
python3 tools/observability_poc/pocctl.py arrow-ipc \
  --rows 1000 \
  --output poc-results/arrow-ipc-local.json
```

开发机 `arrow-ipc` 在 `pyarrow` 未安装时预期返回
`unavailable / pyarrow_not_installed`。是否安装依赖应在恢复后单独决定，不能通过跳过测试把
该项记为通过。

## DSH 能力契约与真实落地状态

本专题文档中的 DSH 内容当前是**可执行设计契约和验收标准**，不是 DSH
生产部署完成声明。截至 `2026-08-27`，仓库已落盘
[DSH Integration Pack](../dsh/README.md)：

- 已落地：Profile、6 个 JSON Schema、工具注册表、正负例夹具、依赖无关校验脚本，以及 DSH 的职责边界、
  只读优先原则、Multi-Agent 分工、证据格式、风险分级、审批/执行/验证/回滚流程
  和文档状态治理。
- 尚未落地：DSH/Cordis runtime 安装和固定版本、Cordis 插件、六类查询适配器、
  Session 存储/回放服务、
  Scheduler、Evidence Reviewer 运行组件、审批 UI、受控执行器和 OTel Session Telemetry
  导出。
- 已有但不等同于 DSH：车端/云端/前端的局部结构化事件、云端指标、ZLMediaKit exporter
  和观测 POC。它们是 DSH 的潜在数据源，不代表 DSH 已经可以查询、关联或执行闭环。
- 未验证：目标车上的 eBPF/DeepFlow 能力、生产数据源权限和新鲜度、跨系统时间关联、
  证据查询性能、Session 可复现性、审批执行链路以及安全测试结果。

因此 profile 的 `design_status` 为 `implemented`，但 `runtime_status` 必须保持
`unverified`；能力矩阵中的生产运行项仍保持 `approved`，不能标记为 `verified`。
`implemented` 仅可用于明确写明“契约、文档或某个独立代码组件已完成”的范围，不能
推导为整套 DSH 已上线。

## Capability Acceptance Matrix

每项能力必须分别记录 `design_status`、`runtime_status` 和 `evidence_refs`。
没有运行证据时，运行状态使用 `unverified`，不能用文档存在替代验证。

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>能力</th>
      <th>契约范围</th>
      <th>当前真实状态</th>
      <th>验收证据</th>
      <th>放行门</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Query adapters</td>
      <td>command、media、broker、ZLM、eBPF、vehicle health 六类受控只读查询</td>
      <td><code>approved</code>；接口设计完成，生产插件未部署</td>
      <td>固定参数 Schema、权限矩阵、查询结果和数据源健康报告</td>
      <td>禁止任意 Shell/SQL/PromQL/LogQL；时间窗、车辆范围和返回大小有硬限制</td>
    </tr>
    <tr>
      <td>Evidence correlation</td>
      <td>按 <code>incident_id</code>、<code>trace_id</code>、<code>message_id</code>、<code>video_session_id</code>、车辆和时间窗关联</td>
      <td><code>approved</code>；关联键已定义，跨系统闭环未验证</td>
      <td>同一故障的控制和媒体样本可形成有序时间线，冲突和缺口可见</td>
      <td>不同时间域不得直接相减；跨时钟域只标记为 correlated evidence</td>
    </tr>
    <tr>
      <td>Hypothesis validation</td>
      <td>每个根因候选必须列支持证据、反证、缺失证据和下一步查询</td>
      <td><code>approved</code>；规则已定义，Reviewer 运行组件未部署</td>
      <td>历史故障回放中能降低无证据结论和错误归因</td>
      <td>缺少关键数据时最高只能输出 <code>low</code>/<code>medium</code> 置信度</td>
    </tr>
    <tr>
      <td>Multi-Agent</td>
      <td>Coordinator、Vehicle、Network、Command、Video、Cloud/Change 和 Reviewer</td>
      <td><code>approved</code>；先采用受限 Subagent/外部编排，未依赖实验性 Agent Teams</td>
      <td>固定输入输出 Schema、并发上限、失败隔离和合并结果审计</td>
      <td>专项 Agent 只读，不得直接调用生产写工具</td>
    </tr>
    <tr>
      <td>Session storage/replay/fork</td>
      <td>保存 Incident、工具调用、证据引用、版本、审批和执行结果</td>
      <td><code>approved</code>；追加式格式已定义，存储和回放服务未部署</td>
      <td>固定数据、版本和工具结果可恢复、回放、分叉并得到可解释结果</td>
      <td>原始敏感正文默认不出域；Session 不得成为生产状态唯一事实源</td>
    </tr>
    <tr>
      <td>Scheduler</td>
      <td>告警分析、发布后观察、周期巡检和人工触发</td>
      <td><code>approved</code>；策略已定义，生产调度任务未创建</td>
      <td>并发、超时、预算、去重、熔断和错峰行为的测试记录</td>
      <td>不能进入车端实时控制路径；DSH 不可用时原有告警继续工作</td>
    </tr>
    <tr>
      <td>UI review/approval</td>
      <td>War Room、证据审核、审批、拒绝、过期和接管</td>
      <td><code>approved</code>；RBAC/SSO/审计接口未接入</td>
      <td>审批人、范围、参数摘要、原因、时间和决定可追溯</td>
      <td>P0/P1、车辆相关和 L4 动作必须人工决策</td>
    </tr>
    <tr>
      <td>Controlled execution</td>
      <td>独立执行器接收已审批任务，使用短期凭证执行幂等 Runbook</td>
      <td><code>approved</code>；无生产写权限和执行器部署</td>
      <td>任务签名、前置检查、执行日志、结果和权限审计</td>
      <td>DSH 只能提交任务，不能直接 SSH、MQTT、TCP、CAN 或写车辆配置</td>
    </tr>
    <tr>
      <td>Verification/rollback</td>
      <td>动作前基线、动作后 SLO、退出条件、自动回滚和人工接管</td>
      <td><code>approved</code>；未进行真实变更演练</td>
      <td>成功、失败、超时和回滚四类结果均可复现并留痕</td>
      <td>不满足成功条件或触发风险门禁时停止并回滚</td>
    </tr>
    <tr>
      <td>OTel Session Telemetry</td>
      <td>Session、工具调用、耗时、状态和 evidence reference 的 OTLP Logs</td>
      <td><code>approved</code>；Collector/Exporter 未部署</td>
      <td>脱敏、采样、断网缓存、恢复补传、丢弃计数和资源对照</td>
      <td>默认不发送 Prompt、模型回复、工具正文和敏感参数</td>
    </tr>
    <tr>
      <td>Sandbox/security</td>
      <td>插件、Skill、模型上下文和工具执行隔离</td>
      <td><code>approved</code>；目标环境和红队测试未验证</td>
      <td>越权、注入、泄露、恶意插件、重放篡改和故障隔离测试</td>
      <td>任何 DSH/模型/插件故障都不能阻塞业务链路或绕过人工流程</td>
    </tr>
  </tbody>
</table>

## 只读工具契约

所有工具都使用结构化请求，不接受模型拼接的命令或查询语言。工具适配器必须在
服务端执行鉴权、参数校验、脱敏、限流和审计。以下接口名是逻辑契约，具体实现可映射
到 Tempo、Prometheus、Loki、Broker、ZLMediaKit、车云诊断网关或 eBPF/DeepFlow
查询服务。

### 公共请求与响应

公共请求至少包含：

```json
{
  "request_id": "req-20260825-001",
  "schema_version": "1",
  "incident_id": "inc-20260825-001",
  "tool": "query_command_path",
  "caller": {
    "subject": "dsh-coordinator",
    "tenant_id": "tenant-001",
    "roles": ["incident-reader"],
    "purpose": "diagnose command timeout",
    "authorization_ref": "auth://incident/inc-20260825-001"
  },
  "time_window": {
    "start": "2026-08-25T10:00:00Z",
    "end": "2026-08-25T10:10:00Z"
  },
  "parameters": {
    "vehicle_id": "vehicle_hash_001",
    "message_id": "message_hash_001",
    "include_raw_body": false
  },
  "limit": 500,
  "cursor": null
}
```

实际工具按需增加业务键，但必须遵守：

- 时间窗默认不超过 10 分钟，最大不超过 1 小时；跨天或全量查询需要人工授权。
- `vehicle_id`、会话 ID、消息 ID 和流 ID 必须经过调用者权限校验；不得只依赖模型提供的范围。
- 返回结果必须包含查询实际使用的时间窗、数据源、查询版本、执行耗时和分页信息。
- 工具失败、数据源不可达、权限不足和无数据必须使用不同的结果状态，不能统一返回空数组。
- 返回记录数量、字段大小和并发数必须有上限；原始 payload、Token、密钥、手机号和 VIN
  默认不返回。

统一响应结构如下：

```json
{
  "source": "adapter-name",
  "query": {
    "tool": "query_command_path",
    "schema_version": "1",
    "parameters_hash": "sha256:...",
    "time_window": {
      "start": "2026-08-25T10:00:00Z",
      "end": "2026-08-25T10:10:00Z"
    }
  },
  "status": "ok",
  "freshness": {
    "observed_at": "2026-08-25T10:10:05Z",
    "data_end": "2026-08-25T10:09:58Z",
    "age_ms": 7000
  },
  "clock_domains": ["vehicle_monotonic", "cloud_monotonic", "wall_clock"],
  "gaps": [],
  "evidence_ref": [
    {
      "ref": "evidence://...",
      "record_count": 12,
      "content_hash": "sha256:..."
    }
  ],
  "records": []
}
```

`status` 至少支持 `ok`、`partial`、`no_data`、`stale`、`forbidden`、
`source_unavailable` 和 `invalid_request`。`no_data` 不表示组件正常；
`gaps` 必须说明缺少哪个来源、时间段或关联键。

### 业务工具

| 工具 | 必填业务参数 | 必须返回的阶段/事实 | 禁止的推断 |
|---|---|---|---|
| `query_command_path` | `vehicle_id`、`message_id` 或 `seq`/`correlation_id`、时间窗 | cockpit send、云端接收/入队、latest-only pending/inflight、TCP write completion、车端 receive/decrypt/parse/dispatch、handler、ROS publish、ACK/MRC；每项带 monotonic 时间、来源和状态 | handler 未收到不能直接推断 TCP 丢包；应用 RTT 不能直接命名为纯 TCP RTT |
| `query_media_path` | `vehicle_id`、`video_session_id`、`stream`、时间窗 | ROS frame、appsrc、encoder、RTP、RTSP/ZLM、WebRTC/ICE、inbound RTP、decode、render、首帧/末帧/恢复和错误事件 | 浏览器黑屏不能直接归因车端编码；无业务事件不能由模型补造首帧 |
| `query_broker_session` | `vehicle_id` 或脱敏 client/session 标识、时间窗 | connect/disconnect、reason、keepalive、订阅、publish/ack、重连和 broker 节点 | 仅凭连接在线不能证明消息已被业务消费 |
| `query_zlm_stream` | `app`、`stream_name`、时间窗 | media online/offline、reader/session、输入输出码率、包计数/年龄、RTSP/WebRTC API 错误、ZLM 进程/容器状态 | ZLM online 不能证明浏览器已解码或渲染 |
| `query_ebpf_network` | `vehicle_id`/服务、PID 或 cgroup、socket/四元组、时间窗 | TCP RTT、retrans、RTO、connect/close、send/receive queue、丢包/拥塞、调度延迟和采样限制 | eBPF 旁证不能替代业务阶段事件；采样缺失不能当作没有异常 |
| `query_vehicle_health` | `vehicle_id`、时间窗 | 镜像/内核/BTF/BPF 权限、进程、CPU/RSS/FD、网络接口、Agent/Collector/WAL/DataBuff 状态、磁盘水位和配置版本 | 诊断网关不可达不能直接推断车辆故障；观测 Agent 正常不能证明控制链路正常 |

`query_command_path` 和 `query_media_path` 是业务优先工具；eBPF 查询只用于补充
内核和资源事实。DSH 不得因为 eBPF 没有记录就覆盖车端业务日志，也不得因为 ZLM
有流就跳过浏览器和车端阶段查询。

## Evidence Envelope 与 Evidence Reviewer Gate

### 统一 Evidence Envelope

Incident、工具结果、Agent 判断和人工审批都引用同一种 evidence envelope。Envelope
本身只保存索引、摘要和不可变引用；大体量日志、原始包和敏感正文保留在原数据源。

```json
{
  "envelope_version": "1",
  "evidence_id": "ev-20260825-001",
  "incident_id": "inc-20260825-001",
  "kind": "command_path",
  "scope": {
    "vehicle_id": "vehicle_hash_001",
    "remote_session_id": "session_hash_001",
    "message_id": "msg_hash_001",
    "video_session_id": null
  },
  "time_window": {
    "start": "2026-08-25T10:00:00Z",
    "end": "2026-08-25T10:10:00Z",
    "clock_domains": ["vehicle_monotonic", "cloud_monotonic", "wall_clock"]
  },
  "source": {
    "system": "vehicle|cloud|broker|zlm|browser|ebpf",
    "service": "service-name",
    "instance": "instance-id",
    "agent_version": "version",
    "query_ref": "query://..."
  },
  "observation": {
    "event_type": "remotejoystick_received",
    "observed_at": "2026-08-25T10:00:01.123Z",
    "monotonic_ns": 1234567890,
    "attributes": {}
  },
  "freshness": {
    "data_end": "2026-08-25T10:00:01.123Z",
    "age_ms": 7000,
    "completeness": "complete|partial|unknown"
  },
  "relation": {
    "trace_id": "trace_hash_001",
    "span_id": "span_hash_001",
    "parent_ref": null,
    "correlation_keys": ["message_id", "seq", "correlation_id"]
  },
  "assessment": {
    "role": "supports|contradicts|missing|context",
    "claim_id": "claim-001",
    "confidence": "high|medium|low"
  },
  "integrity": {
    "content_hash": "sha256:...",
    "created_at": "2026-08-25T10:10:05Z",
    "retention_class": "incident-30d"
  }
}
```

必须满足以下不变量：

- `evidence_id`、`incident_id`、查询引用和内容摘要可审计；引用内容变化时哈希必须变化。
- 每条证据标注来源、实例/版本、实际数据结束时间、完整性和时钟域。
- `supports`、`contradicts`、`missing`、`context` 必须与具体 `claim_id` 关联；
  没有关联 Claim 的记录只能作为背景。
- 同一字段来自不同时间域时不得生成伪造的 parent-child Trace；只能建立
  `correlated evidence` 关系。
- 敏感数据使用哈希或受控映射；Envelope 不直接保存 Token、私钥、MQTT 密码、
  原始控制 payload 或浏览器用户隐私内容。

### Evidence Reviewer Gate

Coordinator 只有在 Reviewer 返回 `pass` 或 `pass_with_gaps` 后，才能提交诊断结论；
没有 Reviewer 结果时不得输出 `high` 置信度或生成 L2/L3 任务。Reviewer 至少执行：

1. **来源检查**：查询是否来自允许的数据源，调用者是否有权限，版本和实例是否可追溯。
2. **时间检查**：实际返回时间窗是否覆盖事故，事件排序是否使用同一时钟域；
   跨域数据是否只做有明确限制的关联。
3. **新鲜度检查**：数据是否陈旧、是否存在采集延迟、窗口尾部是否缺失。
4. **完整性检查**：是否有 command/media/broker/ZLM/eBPF/vehicle health 的关键缺口，
   空结果是否被错误解释为正常。
5. **一致性检查**：message/seq/correlation、video session、实例和版本是否冲突；
   识别重复、重放或哈希不一致。
6. **结论检查**：每个结论是否至少有支持证据；是否列出反证、未验证假设和下一步查询。
7. **隐私检查**：是否发生高基数标签、原始 payload、凭证或个人数据泄露。

Reviewer 输出至少包含：

```json
{
  "review_status": "pass|pass_with_gaps|reject",
  "claim_reviews": [
    {
      "claim_id": "claim-001",
      "support_refs": ["ev-001"],
      "contradict_refs": [],
      "missing": ["tcp_receive"],
      "confidence_ceiling": "medium"
    }
  ],
  "blocking_reasons": [],
  "reviewed_at": "2026-08-25T10:11:00Z"
}
```

`reject` 用于来源、权限、完整性或严重时间错误；`pass_with_gaps` 允许输出有限结论，
但必须带缺口和置信度上限。任何“没有日志所以没有故障”的结论都应被 Reviewer 拒绝。

## Session Replay 与 Fork 验收

DSH Session 必须是追加式、可寻址和可校验的分析记录，至少包含：

- DSH、模型、Profile、插件、Skill 和工具 Schema 版本。
- 初始 Incident Envelope、用户范围、时间窗、权限主体和脱敏策略。
- 每次工具调用的参数摘要、授权结果、返回状态、耗时、evidence reference 和内容哈希。
- Coordinator/专项 Agent/Reviewer 的输入输出引用、决策顺序和失败原因。
- 审批、执行、验证和回滚任务的引用；不得只保存模型最终文字。

验收要求：

1. **Replay**：冻结同一数据快照、工具返回、版本和配置后，Session 可以从任意检查点恢复，
   不重新访问生产写接口。
2. **Fork**：从检查点创建分支时，原 Session 不可变；分支必须记录父 Session、
   分支点和改变的输入/策略。
3. **Determinism**：工具返回和排序固定时，关键证据集合、结论依据和 Reviewer 门状态
   应稳定；允许模型文字存在非关键差异，但不能改变证据引用和风险等级而无记录。
4. **Failure replay**：模拟工具超时、部分数据、权限拒绝、陈旧数据和插件失败，
   回放必须保留失败状态，不能把失败重写为空结果。
5. **Tamper detection**：修改 Session 记录、证据引用或版本元数据时，完整性校验必须失败，
   原 Session 不得继续用于审批。

当前未部署 Session 存储、回放或分叉运行组件，因此上述内容仍为 `approved` 验收标准。

## Scheduler 契约

Scheduler 只负责触发和编排，不直接执行车辆或生产写操作。首期允许的触发器：

| 触发器 | 默认动作 | 禁止事项 |
|---|---|---|
| P0/P1 告警 | 创建 Incident，启动一次只读证据收集 | 自动改配置、重启、关闭告警 |
| 发布完成 | 发布后 15～30 分钟 SLO 对照和报告 | 未经审批自动回滚生产 |
| 周期巡检 | 容量、ZLM 流、Broker、Agent/WAL 和数据质量检查 | 以巡检结果直接改变车辆状态 |
| 人工触发 | 按授权范围启动诊断或回放 | 扩大到未授权车辆、时间窗或租户 |

每个调度任务必须声明：

```json
{
  "schedule_id": "sched-001",
  "trigger": "alert|post_deploy|periodic|manual",
  "scope": {
    "vehicles": ["vehicle_hash_001"],
    "services": ["parallel-driving-manager"],
    "time_window": {}
  },
  "limits": {
    "max_concurrency": 2,
    "timeout_ms": 120000,
    "max_tool_calls": 30,
    "max_cost": "bounded",
    "cooldown_ms": 600000
  },
  "dedupe_key": "incident_id+release_id",
  "fallback": "human_queue",
  "write_permission": false
}
```

验收必须覆盖并发、超时、重复告警、队列积压、数据源不可达、预算耗尽、插件崩溃、
Scheduler 重启和恢复。失败时任务进入 `human_queue` 或 `failed`，不能 fail-open。

## L2/L3 审批任务契约

L2 只能生成待审批计划；L3 才能在人工审批后提交给独立执行器。两者都不能直接进入
车端实时控制线程。

任务至少包含：

```json
{
  "task_version": "1",
  "task_id": "task-001",
  "incident_id": "inc-20260825-001",
  "risk_level": "L2|L3",
  "action": "single_media_session_reconnect",
  "scope": {
    "environment": "staging",
    "tenant_id": "tenant-001",
    "vehicle_id": "vehicle_hash_001",
    "video_session_id": "session_hash_001",
    "max_targets": 1
  },
  "preconditions": [
    "review_status=pass_with_gaps",
    "vehicle_mode_is_safe",
    "no_active_safety_incident"
  ],
  "success_criteria": [
    "first_frame_age_ms<5000",
    "no_new_session_error_for_60s"
  ],
  "exit_criteria": [
    "timeout_ms=30000",
    "second_failure"
  ],
  "rollback_plan": {
    "action": "restore_previous_session_binding",
    "owner": "independent-executor",
    "runbook_id": "runbook-media-reconnect-rollback"
  },
  "approval": {
    "required": true,
    "status": "pending",
    "approver_id": null,
    "approver_role": "oncall-owner",
    "scope_hash": "sha256:...",
    "decision_ref": null,
    "approved_at": null,
    "expires_at": "2026-08-25T10:20:00Z",
    "token_ref": null
  },
  "audit": {
    "parameters_hash": "sha256:...",
    "runbook_version": "runbook@1",
    "executor_ref": "service://controlled-observability-executor"
  },
  "idempotency_key": "inc-20260825-001:session_hash_001:reconnect:1",
  "created_at": "2026-08-25T10:10:00Z",
  "expires_at": "2026-08-25T10:20:00Z",
  "nonce": "nonce-20260825-001",
  "task_hash": "sha256:..."
}
```

L2 验收：

- 只生成参数、影响范围、前置条件、成功/退出条件和回滚计划。
- 没有审批令牌时无法提交执行。
- 任务过期、范围变化、证据被拒绝或版本不匹配时自动失效。

L3 验收：

- 只允许经过白名单的幂等动作，例如单路媒体会话重连、单个观测 Agent 重启或
  单车单路短时采样提升；动作参数由执行器重新校验。
- 执行器使用短期凭证并二次校验 scope、preconditions 和当前车辆状态。
- 执行后自动查询 success/exit criteria；失败、超时或风险升高时执行 rollback，
  并把结果交给人工接管。
- 记录审批人、审批时间、任务哈希、执行器、实际目标、开始/结束时间、结果和回滚状态。

车辆控制参数、MQTT/TCP/CAN 指令、批量重启/升级、密钥、权限和安全策略始终属于
L4 人工决策，不能通过 L3 绕过。

## DSH 安全测试

DSH 进入任何生产只读或受控执行环境前，必须通过以下测试并保留原始结果、版本和
修复记录：

| 测试类别 | 注入/故障样例 | 必须证明 |
|---|---|---|
| Prompt injection | 日志、ZLM 元数据、工单或网页内容伪造“忽略审批/执行命令” | 内容被当作不可信数据；工具策略和权限优先级不变 |
| 越权查询 | Agent 请求未授权车辆、租户、时间窗或原始 payload | 服务端拒绝，且不通过改写参数、分页或缓存绕过 |
| 工具注入 | 恶意字符串、Shell/SQL/PromQL/LogQL 特殊字符 | 只使用结构化参数；无任意命令、查询或 SSRF |
| 敏感数据泄漏 | Token、私钥、MQTT 密码、VIN、手机号和控制 payload 进入 Prompt/Log/OTLP | 脱敏或拒绝；审计中不出现原文 |
| 恶意插件/Skill | 签名缺失、版本漂移、读取宿主机或生产密钥 | 插件不加载或在沙箱失败，不能获得生产写权限 |
| Session 篡改/重放 | 修改 evidence hash、审批令牌、scope 或旧任务重放 | 完整性校验失败；过期/重复任务不可执行 |
| 资源耗尽 | 超大时间窗、海量标签、并发告警、无限 Agent 循环 | 受限、超时、熔断，业务观测和控制链路不被拖垮 |
| 组件故障 | 模型、DSH、插件、Collector、Prometheus、ZLM 或 Broker 查询不可用 | 降级人工流程；原有告警、控制、视频和状态链路继续 |
| 失败安全 | 执行器超时、部分成功、目标状态变化、回滚失败 | 停止扩散、保留审计、人工接管，不自动扩大范围 |

安全验收还必须检查：查询身份与执行身份分离、最小权限、短期凭证、插件签名和
版本锁定、Session 加密/保留/删除策略、审计日志不可由 DSH 删除，以及 DSH 沙箱
不能挂载生产密钥、宿主机写目录或车端控制接口。

## 当前 DSH 未验证项清单

以下项目在获得实际运行证据前保持未验证，不得在进度表中改为 `verified`：

1. DSH/Cordis Profile、插件和 Skill 的固定版本安装、启动、升级和回滚。
2. 六类工具对真实数据源的权限、参数限制、查询结果、新鲜度和错误语义。
3. command/media/broker/ZLM/eBPF/vehicle health 在同一 Incident 中的关联闭环。
4. Evidence Reviewer 对时间域、缺口、冲突、陈旧数据和无日志误判的拦截效果。
5. Session 的追加写、恢复、回放、分叉、哈希校验和结果稳定性。
6. Scheduler 的去重、预算、并发、熔断、重启恢复和人工队列降级。
7. L2/L3 审批、短期凭证、独立执行器、成功检查、退出条件和回滚演练。
8. Prompt injection、越权查询、敏感数据泄漏、恶意插件、资源耗尽和故障隔离测试。
9. OTel Session Telemetry 的脱敏、采样、断网恢复、丢弃计数和资源开销。
10. 目标车 eBPF/DeepFlow 权限、BTF、CO-RE、内核探针和容器安全策略。

完成任一项后，必须追加日期、环境、版本、原始证据引用、结论和遗留风险；仅更新
文字描述或运行开发机 POC 不足以将生产能力标记为 `verified`。
