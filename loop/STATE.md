# Loop State

> 模型会遗忘，但仓库不会。所有状态存在磁盘上，不在上下文里。

## 2026-07-04

### ✅ 已完成
- [x] Skills 体系搭建 (15+ skills)
- [x] Sub-agents 角色定义 (architect, test-strategist, ui-designer)
- [x] Loop Engineering 基础设施初始化

### 🔄 进行中
- [ ] MCP Connectors 配置
- [ ] Automation 定时任务
- [ ] Worktree 隔离规范

### 📋 待处理
- [ ] CI 自动修复 Loop
- [ ] 代码审查自动化
- [ ] 数据库迁移安全检查

---

## 循环日志

| 日期 | 循环 | 发现 | 操作 | 结果 |
|------|------|------|------|------|
| 2026-07-04 | 初始化 | 项目已有 Harness 层，缺 Loop 层 | 创建 loop/ 目录和配套文件 | ✅ |
| 2026-08-26 | 车端全链路可观测性 | 不能从公开资料确认小米、小鹏、理想的具体量产技术组合；当前车端需要业务语义、单调耗时、跨进程关联和系统事实分层实现 | 更新 `.github/full-link-observability.md` 的行业对标、车端最佳取舍、实施顺序和 DSH 进度项 | ✅ 设计已记录；车端 C++ 运行逻辑、OTel/DeepFlow/DataBuff 部署仍未实施 |
| 2026-08-26 | 文档分域治理 | 单一完整文档同时承载行业对标、车端节点、三条链路、前端黑屏和 DSH 验收，维护成本较高 | 新增 `.github/observability/` 文档组和导航，保留 `full-link-observability.md` 作为完整设计基线 | ✅ 已拆分；专题状态和实施证据仍需随里程碑同步 |
| 2026-08-26 | GreptimeDB Edge 与 Arrow 数据平面 | 车云一体方案需要同时覆盖车端高频时序、实时批量交换、断网缓存和云端归档；Arrow 与 Parquet 的职责不能混用 | 新增 `.github/observability/06-greptime-edge-and-arrow.md`，同步完整设计基线、导航和 DSH 进度；明确 Edge/Arrow/Parquet/WAL 与 Trace、eBPF、DSH 的边界 | ✅ 设计状态为 `approved`；尚未部署或现场验证，下一步完成目标车版本矩阵、单车 POC、断网补传和四组性能对照 |
| 2026-08-26 | GreptimeDB/Arrow 方案校正 | 完整基线需要明确 Edge Manager 控制面、Arrow/Parquet/Trace 三者边界，以及 Flow 和向量能力的版本风险；公开案例指标不能直接作为当前车型承诺 | 在 `full-link-observability.md`、`observability/05-dsh-progress-and-acceptance.md` 和专题 06 中同步控制面边界、版本矩阵要求、Flow batching 优先、向量后置和公开指标校正 | ✅ 文档已同步；状态仍为 `approved`，尚未部署 Edge/OTAP/Parquet/DeepFlow，下一步执行目标车能力矩阵和单车 POC |
| 2026-08-26 | GreptimeDB Edge/Arrow POC 关机检查点 | 下一步需要执行目标车型版本矩阵、单车 Edge POC、Arrow/IPC 生命周期、断网补传和 A/B/C/D 四组性能对照；当前开发机缺少 `pyarrow`，且未执行工具测试 | 将 POC 工具位置、执行顺序、输入输出、通过条件、故障隔离边界和恢复命令写入完整基线、专题 05/06 和 Loop 状态 | ⏸ 已安全落盘；状态保持 `approved`，未标记为实车验证；下次开机先做开发机工具自检，再补适配器并进入 AD1/Jetson/x86 实车测试 |
| 2026-08-27 | DSH Integration Pack 契约落盘 | DSH 能力清单已覆盖模型、只读查询、Skills、Multi-Agent、Session replay/fork、Scheduler、审批、受控执行、OTel Session Telemetry 和 Sandbox；原 Incident Schema 引用了不存在的共享 `$defs` | 新增/校正 `.github/dsh/` profile、5 个 Schema 和校验脚本，补齐共享 `time_window` 定义，并同步专题文档与完整基线 | ✅ 契约文件已完成，待执行校验；DSH/Cordis runtime、插件、适配器、OTel/eBPF/DeepFlow 仍未部署验证，运行状态保持 `unverified` |
| 2026-08-27 | DSH 能力契约闭环 | 工具别名、查询参数、Evidence、Action、Session、Scheduler、审批绑定和 Telemetry 约束此前存在跨文件不一致，Query Response 也没有独立 Schema | 增加 Profile canonical tool registry、6 个 Schema、7 个正例和 2 个拒绝负例；加入结构化查询/响应、claim+hash Evidence、L2/L3 任务签名元数据、Session hash chain、Scheduler 预算/RBAC/OTLP/WAL/Sandbox 约束，并同步 DSH 文档 | ✅ `python3 .github/dsh/validate_contract.py` 通过；仅证明契约和本地校验通过，DSH/Cordis runtime、适配器、Collector、eBPF/DeepFlow 和目标车现场仍为 `unverified` |
