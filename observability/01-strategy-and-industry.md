# 01 总体策略与行业方案

更新时间：`2026-08-26`

## 结论

当前没有足够公开证据证明小米、理想、小鹏的量产车端都使用固定组合
`eBPF + OpenTelemetry + DeepFlow + DataBuff`。公开资料只能用于提炼工程方向，
不能替代厂商内部架构、版本、权限和性能数据。

本项目的最佳取舍是分层建设：

```text
车端业务事件 + 进程内 monotonic ledger
  -> ROS/GStreamer 稳定 hook
  -> eBPF/DeepFlow 系统事实
  -> OTel/Collector/DataBuff 异步传输与留存
  -> 云端 ZLMediaKit + 浏览器事件
  -> DSH 只读证据关联和治理
```

## 三家公开方向

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>厂商</th>
      <th>公开资料可支持的方向</th>
      <th>本项目借鉴</th>
      <th>不能推断</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>小米</td>
      <td>公开 DeepFlow 落地材料显示，在既有监控体系上补充 eBPF/cBPF、网络、socket、五元组、进程和高基数适配。</td>
      <td>保留现有日志/指标，用 eBPF 补充 TCP/UDP、重传、队列、调度和资源；先做能力探测和限流。</td>
      <td>不能证明小米汽车车端使用本文同样的 Agent、OTel、DataBuff 或字段。</td>
    </tr>
    <tr>
      <td>小鹏</td>
      <td>公开远程驾驶资料强调传感器、云端、控制传输、执行器、驾驶舱和显示链路的分段时延，以及时间戳注入和物理测量。</td>
      <td>建立控制/视频分段时间账本；线上用 monotonic，实验室用注入帧、显示屏相机或 GPIO/LED 校准。</td>
      <td>专利不是量产代码证明，不能证明其使用某个 Trace SDK 或 eBPF 组合。</td>
    </tr>
    <tr>
      <td>理想</td>
      <td>公开车端数据案例强调车端采集、解码、结构化、压缩、本地缓存或文件上传，避免实时链路被大数据处理阻塞。</td>
      <td>业务事件进入有界队列/WAL，异步批量上传；观测失败只丢低优先级数据，不阻塞控制和视频。</td>
      <td>不能把公开数据架构案例等同于 DeepFlow、OTel 或本项目的具体实现。</td>
    </tr>
  </tbody>
</table>

## 当前系统的硬边界

<table border="1" cellpadding="6" cellspacing="0">
  <thead>
    <tr>
      <th>组件/层</th>
      <th>负责</th>
      <th>不负责</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>业务事件与 OTel</td><td>messageId、functionId、session、video、首帧、业务结果和 Trace Context</td><td>不能证明内核网络或浏览器最终渲染</td></tr>
    <tr><td>monotonic ledger</td><td>同一进程/时钟域阶段耗时</td><td>不能把跨设备墙钟差当真实延迟</td></tr>
    <tr><td>eBPF/DeepFlow</td><td>网络、socket、RTT、重传、调度、CPU、RSS、进程生命周期</td><td>不能理解 remotejoystick、IDR 或视频渲染语义</td></tr>
    <tr><td>WAL/DataBuff</td><td>批量、断网缓存、重试、限额和丢弃计数</td><td>不是 Trace 生成器，不能进入实时同步路径</td></tr>
    <tr><td>DSH</td><td>只读查询、证据关联、RCA、治理和审批建议</td><td>不进入手柄/CAN、视频重连或车辆安全路径</td></tr>
  </tbody>
</table>

## 实施决策

1. 先做车端业务事件和单调耗时，不先部署全量 eBPF 或生产 DataBuff。
2. 再做控制协议 Trace Context 和视频短 TTL 预绑定。
3. 然后以独立 Agent 方式接入 eBPF/DeepFlow，首期只采集低风险系统事实。
4. 最后接 OTel Gateway、Collector、WAL/DataBuff 和 DSH 只读分析。
5. 先完成单车单路闭环，再扩展多路、车型和车队。

详细代码挂点和公开资料引用见[完整设计基线第 9.1.5 至 9.1.9 节](../full-link-observability.md#915-公开行业参考与本项目最佳取舍)。

