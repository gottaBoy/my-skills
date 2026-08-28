# 车云端可观测性文档导航

更新时间：`2026-08-26`

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
      <td><code>approved</code>：业务事件和上下文待实现</td>
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
  </tbody>
</table>

## 使用规则

1. 设计原则和跨专题决策写入 `01` 或完整设计基线。
2. 车端代码、内核、Agent 和资源预算写入 `02`。
3. Trace Context、消息关联和三条链路字段写入 `03`。
4. 浏览器、WebRTC、黑屏状态机和前端埋点写入 `04`。
5. 状态、证据、验收、阻塞和发布结论写入 `05`，并同步 `../loop/STATE.md`。
6. GreptimeDB、Arrow、Parquet、WAL/DataBuff 和数据上传策略写入 `06`，并同步完整设计基线。
7. 运行逻辑、阈值或协议发生变化时，专题文档和完整设计基线必须在同一变更中更新。
8. 专题文档不得把设计状态写成已部署；必须区分 `implemented`、`verified`、`approved`
   和 `blocked`。

## 快速入口

- [完整设计基线](../full-link-observability.md)
- [车端控制与视频现状](../full-link-observability.md#914-车端控制视频与-ebpf-实施设计)
- [前端现状与本地埋点](../full-link-observability.md#912-前端-otelrum-与-deepflow-接入设计)
- [当前工作项进度](../full-link-observability.md#913-当前工作项进度)
- [GreptimeDB Edge 与 Arrow 车云数据平面](06-greptime-edge-and-arrow.md)
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
