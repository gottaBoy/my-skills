# 车云端可观测性文档导航

更新时间：`2026-09-16`

本文档组按实际职责拆分，便于设计评审、开发跟踪、测试验收和 DSH 进度治理。
完整的字段、代码挂点、历史问题和详细决策仍集中保留在
[完整设计基线](../full-link-observability.md)。

## 文档分工

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>文档</th>
      <th>负责内容</th>
      <th>主要读者</th>
      <th>当前状态</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="01-strategy-and-industry.md">01-strategy-and-industry.md</a></td>
      <td>总体原则、小米/理想/小鹏公开方案、当前项目取舍</td>
      <td>架构、可观测性、DSH、评审人</td>
      <td><code>implemented</code>：设计已记录</td>
    </tr>
    <tr>
      <td><a href="02-vehicle-node-monitoring.md">02-vehicle-node-monitoring.md</a></td>
      <td>车端节点性能、eBPF、业务事件、单调时钟、资源预算</td>
      <td>车端平台、C++、测试、运维</td>
      <td><code>approved</code>：待目标车验证</td>
    </tr>
    <tr>
      <td><a href="03-three-links-tracing.md">03-three-links-tracing.md</a></td>
      <td>指令、视频、状态上报三条车-云-端链路的 Trace/Span 设计</td>
      <td>车端、云端、前端、ZLMediaKit</td>
      <td><code>implemented/unverified</code>：云端到车端控制分段已落地，统一上下文和运行闭环待验证</td>
    </tr>
    <tr>
      <td><a href="04-frontend-black-screen.md">04-frontend-black-screen.md</a></td>
      <td>前端黑屏归因、误重载防护、本地埋点和后续 OTel/DeepFlow</td>
      <td>前端、测试、ZLMediaKit、现场支持</td>
      <td><code>implemented/verified</code>：基础埋点已落地</td>
    </tr>
    <tr>
      <td><a href="05-dsh-progress-and-acceptance.md">05-dsh-progress-and-acceptance.md</a></td>
      <td>DSH 规范、里程碑、证据、测试矩阵、上线门禁和未完成项</td>
      <td>项目管理、测试、DSH、发布负责人</td>
      <td><code>implemented</code>：进度治理已建立</td>
    </tr>
    <tr>
      <td><a href="06-greptime-edge-and-arrow.md">06-greptime-edge-and-arrow.md</a></td>
      <td>GreptimeDB Edge、Arrow、Parquet、OTel/OTAP、WAL/DataBuff 车云数据平面</td>
      <td>车端平台、数据平台、可观测性、测试</td>
      <td><code>approved</code>：设计已记录，待目标车 POC</td>
    </tr>
    <tr>
      <td><a href="07-vehicle-rtsp-reconnect-analysis.md">07-vehicle-rtsp-reconnect-analysis.md</a></td>
      <td>车端 RTSP 频繁重拉、OTel 行为变化、push 竞态、编码队列和验收标准</td>
      <td>车端 RTSP、GStreamer、云端拉流、测试、现场支持</td>
      <td><code>implemented/unverified</code>：代码已修改，待编译和实车验证</td>
    </tr>
    <tr>
      <td><a href="08-zlmediakit-ebpf-deepflow-databuff.md">08-zlmediakit-ebpf-deepflow-databuff.md</a></td>
      <td>ZLMediaKit Docker、宿主机 eBPF/DeepFlow、exporter/API、OTLP 与 DataBuff 上传</td>
      <td>流媒体、网络、可观测性、数据平台、现场支持</td>
      <td><code>approved/unverified</code>：方案已记录，待目标主机和后端联调</td>
    </tr>
    <tr>
      <td><a href="09-rtsp-timestamp-and-deepflow-correlation.md">09-rtsp-timestamp-and-deepflow-correlation.md</a></td>
      <td>车端 RTSP 时间戳、RTP 时间、ZLMediaKit 收包和 DeepFlow 网络事实的关联边界</td>
      <td>车端 RTSP、流媒体、网络、可观测性、测试</td>
      <td><code>approved/unverified</code>：关联方案已记录，待两端收包事件和目标环境验证</td>
    </tr>
    <tr>
      <td><a href="10-ziot-prometheus-control-plane.md">10-ziot-prometheus-control-plane.md</a></td>
      <td>ziot Actuator/Prometheus、并行驾驶控制面阶段指标、ZLM/DeepFlow 关联</td>
      <td>云端、流媒体、可观测性、测试、现场支持</td>
      <td><code>implemented/unverified</code>：代码和配置已落地，待启动端点与目标环境采集验证</td>
    </tr>
    <tr>
      <td><a href="11-k8s-deepflow-databuff-deployment-plan.md">11-k8s-deepflow-databuff-deployment-plan.md</a></td>
      <td>K8s 部署 DeepFlow、OTel Collector、DataBuff 的阶段方案、边界和验收</td>
      <td>平台、可观测性、网络、数据平台、现场支持</td>
      <td><code>implemented/verified-poc</code>：DeepFlow 单节点 POC 已部署，内部受控流量已写入 ClickHouse 且 Grafana API 已验证；外部 Docker/ECS Agent、真实指令关联和生产 HA 待后续</td>
    </tr>
    <tr>
      <td><a href="12-mrc-command-to-e2e.md">12-mrc-command-to-e2e.md</a></td>
      <td>MRC 从页面指令、ziot 后端、车端远控节点到 e2e 安全输出的调用链、状态机、协议边界和验收</td>
      <td>前端、云端、车端远控、e2e、测试、可观测性</td>
      <td><code>implemented/unverified</code>：代码链路已梳理，自恢复消费者已在专用车端分支实现；真实端到端执行、MRC 主状态恢复和 emergency-stop 协议待验证或修复</td>
    </tr>
    <tr>
      <td><a href="19-ipm-fps-fluctuation-analysis-20260911.md">19-ipm-fps-fluctuation-analysis-20260911.md</a></td>
      <td>上一批 IPM FPS 波动、历史帧积压、RTSP stale_drop 放大路径和修改边界</td>
      <td>车端图像、RTSP、GStreamer、测试、现场支持</td>
      <td><code>analysis/unverified</code>：适用于 0729 分支对应日志，不与 0818 本批结论混用</td>
    </tr>
    <tr>
      <td><a href="20-ipm-fps-fluctuation-analysis-20260911-0818-pd-test.md">20-ipm-fps-fluctuation-analysis-20260911-0818-pd-test.md</a></td>
      <td>0818 PD Test 分支 IPM 低 FPS、三路 compressed 同步链路、RTSP 边界和 camera_merge 修改范围</td>
      <td>车端图像、camera_merge、RTSP、测试、现场支持</td>
      <td><code>analysis/unverified</code>：本批日志显示 IPM 约 5.22 FPS，优先只改 camera_merge；待实现后的实车回归</td>
    </tr>
    <tr>
      <td><a href="21-ipm-fps-fluctuation-analysis-20260912-pd-test.md">21-ipm-fps-fluctuation-analysis-20260912-pd-test.md</a></td>
      <td>feature/pd_test_0818 分支 IPM 10 Hz 运行、cam_f_12 SIGINT 断流、三路同步停摆和 RTSP 故障边界</td>
      <td>车端图像、camera_merge、相机进程管理、RTSP、测试、现场支持</td>
      <td><code>analysis/unverified</code>：本批正常约 10 Hz，主要波动由 cam_f_12 被中断造成；待确认信号来源和自动恢复策略</td>
    </tr>
    <tr>
      <td><a href="22-vehicle-online-state-stabilizer-20260912.md">22-vehicle-online-state-stabilizer-20260912.md</a></td>
      <td>远控页面在线/离线周期抖动、仅展示状态稳定、原始业务状态保持不变</td>
      <td>前端、云端设备状态、测试、现场支持、可观测性</td>
      <td><code>implemented/unverified</code>：仅展示状态稳定器和诊断已落地，控制与连接生命周期保持原逻辑，待目标环境回归</td>
    </tr>
    <tr>
      <td><a href="23-vehicle-data-platform-selection-20260912.md">23-vehicle-data-platform-selection-20260912.md</a></td>
      <td>四家乘用车公开证据、TXT/SQLite/DuckDB/GreptimeDB 选型、MCAP/Parquet、OTel/eBPF 分阶段方案</td>
      <td>架构、车端平台、数据平台、可观测性、测试</td>
      <td><code>design/recorded</code>：方案已记录；代码级保密附录仅本地保存，不纳入 Git；未部署或实车验收</td>
    </tr>
    <tr>
      <td><a href="25-zota-agent-first-boot-target-token-20260915.md">25-zota-agent-first-boot-target-token-20260915.md</a></td>
      <td>zota-agent 首次启动获取 Target securityToken 的可行性、安全边界和建议流程</td>
      <td>云端 ZOTA、车端 agent、安全、测试</td>
      <td><code>analysis/unverified</code>：代码级分析已完成，未修改业务代码，待方案评审和端到端验证</td>
    </tr>
    <tr>
      <td><a href="26-zota-enrollment-token-design-20260915.md">26-zota-enrollment-token-design-20260915.md</a></td>
      <td>enrollment token 的两阶段 exchange/confirm 设计、数据模型、崩溃恢复和并发语义</td>
      <td>云端 ZOTA、车端 agent、安全、测试</td>
      <td><code>implemented/unverified</code>：已有代码，审查发现上线阻塞，详见 27</td>
    </tr>
    <tr>
      <td><a href="27-zota-enrollment-review-20260915.md">27-zota-enrollment-review-20260915.md</a></td>
      <td>enrollment 全链路审查、真实迁移/租户事务复现、安装恢复边界及 archify 图</td>
      <td>云端 ZOTA、车端 agent、安全、测试、发布负责人</td>
      <td><code>reviewed/blockers-found</code>：本地复现及图验证完成，业务修复和生产验收未完成</td>
    </tr>
    <tr>
      <td><a href="28-zota-enrollment-compatibility-hardening-20260915.md">28-zota-enrollment-compatibility-hardening-20260915.md</a></td>
      <td>enrollment 兼容修复、默认禁用、真实集成回归与旧事件测试对照</td>
      <td>云端 ZOTA、车端 agent、安全、测试、发布负责人</td>
      <td><code>implemented/local-verified</code>：新模块核心测试通过，旧事件断言存在历史问题，未生产或实车验收</td>
    </tr>
    <tr>
      <td><a href="29-zota-enrollment-single-config-20260915.md">29-zota-enrollment-single-config-20260915.md</a></td>
      <td>仅使用 config.yaml、安装/正式凭证互斥替换、确认重试与旧布局兼容</td>
      <td>车端 agent、安装平台、安全、测试</td>
      <td><code>implemented/local-verified</code>：Agent 全量、race、vet 和 ARM64 构建通过，未部署或实车验收</td>
    </tr>
    <tr>
      <td><a href="30-zota-enrollment-web-20260916.md">30-zota-enrollment-web-20260916.md</a></td>
      <td>登记令牌前端、admin 最小权限、永久/限时规则及分页 VIN 使用记录</td>
      <td>前端、云端 ZOTA、安全、安装平台、测试</td>
      <td><code>implemented/local-verified</code>：前端回归与浏览器模拟、后端真实集成通过，未部署或实车验收</td>
    </tr>
  </tbody>
</table>

## 使用规则

1. 设计原则和跨专题决策写入 `01` 或完整设计基线。
2. 车端代码、内核、Agent 和资源预算写入 `02`。
3. Trace Context、消息关联和三条链路字段写入 `03`。
4. 浏览器、WebRTC、黑屏状态机和前端埋点写入 `04`。
5. 状态、证据、验收、阻塞和发布结论写入 `05`，并同步 `../loop/STATE.md`。
6. GreptimeDB、Arrow、Parquet、WAL/DataBuff 和数据上传策略写入 `06`，并同步完整设计基线。
7. 车端 RTSP 重拉、GStreamer pipeline、appsrc push 协议和编码队列写入 `07`。
8. ZLMediaKit Docker、DeepFlow/eBPF、exporter/API、OTLP 和 DataBuff 接入写入 `08`。
9. RTSP 时间戳、RTP 收发关联和 DeepFlow 网络耗时边界写入 `09`。
10. ziot Prometheus 暴露、控制面阶段指标和云端采集验证写入 `10`。
11. K8s 部署、Collector 路由、DeepFlow Agent 覆盖和 DataBuff 联调写入 `11`，
    可部署模板统一放在工作区根目录 `my-otel`。
12. MRC 页面指令、ziot 转发、车端远控节点、e2e 仲裁和安全输出写入 `12`；
    Sequence/Lifecycle 图源和 HTML 放在 `diagrams/`。
13. 上一批 IPM 图像实时性、camera_merge 积压和 RTSP stale frame 分析写入 `19`；
    该文档只适用于对应的 0729 分支日志。
14. 0818 PD Test 分支的 IPM 低 FPS、三路 compressed 同步、10 FPS/20 FPS 目标
    边界和“优先只改 camera_merge”的结论写入 `20`。
15. feature/pd_test_0818 分支的 20 Hz 原图输入、10 Hz IPM 正常表现、
    cam_f_12 断流传播和进程恢复建议写入 `21`。
16. 远控页面车辆在线状态、周期探测、确认窗口、状态 WebSocket 实时证据和前端
    防抖验收写入 `22`。
17. 运行逻辑、阈值或协议发生变化时，专题文档和完整设计基线必须在同一变更中更新。
18. 专题文档不得把设计状态写成已部署；必须区分 `implemented`、`verified`、`approved`
    和 `blocked`。
19. 截至 `2026-08-30`，ziot Prometheus 端点和自定义指标注册已经由现场输出验证；
    业务操作后指标增长以及
    ZLMediaKit 与 zlmexporter 容器正在运行。DeepFlow 单节点 POC 已完成基础部署、
    健康、Agent 注册、平台同步和 Kubernetes 内部受控流量写入 ClickHouse 验证；
    Collector/DataBuff 持续闭环、真实指令关联以及 ECS/外部 Docker Agent 仍需按
    目标流量继续验收。
20. 数据库横向选型和公开行业证据写入 `23`；代码级保密评估放入
    `private/` 并保持 Git 忽略，不复制凭证、内部地址或原始敏感数据。
21. L4 Harness 目标、需求映射、场景矩阵、证据包和量产门禁写入 `24`；
    `design_only` 不得解释为已实现或已通过实车验证。
22. zota-agent 首次启动 Target 安全令牌、enrollment 凭证、exchange API 和
    持久化边界写入 `25`；本文只记录分析结论，不代表功能已实现。
23. enrollment token 的详细设计、状态机、API、数据模型、崩溃恢复和测试边界
    写入 `26`；实际实现缺口、复现证据和当前/建议图写入 `27`，
    不得将单测或编译通过等同于生产可用。

## 快速入口

- [完整设计基线](../full-link-observability.md)
- [完整选型：SQLite、DuckDB、GreptimeDB 与车云数据平台](23-vehicle-data-platform-selection-20260912.md)
- [L4 数据与可观测性 Harness 方案](24-l4-data-observability-harness-plan-20260912.md)
- [zota-agent 首次启动 Target 安全令牌分析](25-zota-agent-first-boot-target-token-20260915.md)
- [zota-agent enrollment token 设计](26-zota-enrollment-token-design-20260915.md)
- [enrollment 全链路审查](27-zota-enrollment-review-20260915.md)
- [enrollment 兼容性修复与验证](28-zota-enrollment-compatibility-hardening-20260915.md)
- [enrollment 单配置文件与凭证互斥](29-zota-enrollment-single-config-20260915.md)
- [enrollment 前端管理与永久令牌](30-zota-enrollment-web-20260916.md)
- [enrollment 当前架构图](diagrams/zota-enrollment-20260915/current.architecture.html)
- [enrollment 建议修正时序](diagrams/zota-enrollment-20260915/proposed.sequence.html)
- [车端控制与视频现状](../full-link-observability.md#914-车端控制视频与-ebpf-实施设计)
- [前端现状与本地埋点](../full-link-observability.md#912-前端-otelrum-与-deepflow-接入设计)
- [当前工作项进度](../full-link-observability.md#913-当前工作项进度)
- [GreptimeDB Edge 与 Arrow 车云数据平面](06-greptime-edge-and-arrow.md)
- [车端 RTSP 重拉分析与修复记录](07-vehicle-rtsp-reconnect-analysis.md)
- [ZLMediaKit eBPF/DeepFlow 与 DataBuff 方案](08-zlmediakit-ebpf-deepflow-databuff.md)
- [RTSP 时间戳与 DeepFlow 关联方案](09-rtsp-timestamp-and-deepflow-correlation.md)
- [ziot Prometheus 与控制面指标](10-ziot-prometheus-control-plane.md)
- [MRC 指令到 e2e 安全输出](12-mrc-command-to-e2e.md)
- [IPM FPS 波动与车端实时性分析](19-ipm-fps-fluctuation-analysis-20260911.md)
- [0818 PD Test 分支 IPM 分析](20-ipm-fps-fluctuation-analysis-20260911-0818-pd-test.md)
- [feature/pd_test_0818 IPM 断流分析](21-ipm-fps-fluctuation-analysis-20260912-pd-test.md)
- [远控页面车辆在线状态稳定器](22-vehicle-online-state-stabilizer-20260912.md)
- [车辆在线状态稳定器架构图](diagrams/vehicle-online-state-stabilizer.architecture.html)
- [IPM 数据流与断流传播图](diagrams/ipm-pd-test-20260912.dataflow.html)
- [MRC 指令 Sequence 图](diagrams/mrc-command-to-e2e.sequence.html)
- [MRC 状态 Lifecycle 图](diagrams/mrc-command-lifecycle.lifecycle.html)
- [DSH Integration Pack](../dsh/README.md)
- [现场验证步骤](../full-link-observability.md#92-第一阶段现场验证步骤)

## DSH Integration Pack

仓库已提供一个 runtime-neutral 的 DSH 契约包：
[`.github/dsh/README.md`](../dsh/README.md)。
它把模型、结构化只读查询、Skills、Multi-Agent、Session replay/fork、
Scheduler、审批 UI、受控执行、OTel Session Telemetry 和 Sandbox 的边界
固化为 profile 与 JSON Schema。

当前状态要分开看：

- `design_status=implemented`：profile、Schema 和依赖无关校验脚本已落盘。
- `runtime_status=unverified`：DSH/Cordis、插件、适配器、Session 服务、
  Scheduler、审批 UI、执行器和 OTel Collector 尚未在目标环境部署验证。
- 所有写操作仍为空；车辆控制、MQTT/TCP/CAN、ZLMediaKit 全局修改和主机
  SSH 不属于 DSH 直接能力。

校验命令：

```bash
cd /Users/minyi/workspace/autodrive
python3 .github/dsh/validate_contract.py
python3 -m json.tool .github/dsh/vehicle-cloud-observability.profile.json >/dev/null
```
