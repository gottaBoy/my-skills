# Proposal: ztd_rtsp 多路推流（GStreamer tee）

## 动机 (Motivation)
- **当前痛点**: 车端仅支持 RTSP Server 被动拉流（ZLM pull），无法主动推流到多个云媒体服务（腾讯 TRRO、百度等）
- **预期收益**: 一次编码 → 多路分发，零额外 CPU，兼容任意 GStreamer sink 协议

## 影响范围 (Impact)
- **涉及服务**: 仅车端 `ztd_rtsp`（`aura/src/ztd/ztd_network/ztd_rtsp/`）
- **涉及模块**:
  - `src/vehicle/rtsp_stream.cpp` — 修改 GStreamer pipeline 构建逻辑
  - `src/vehicle/rtsp_server.cpp` — 新增 sink profile 加载
  - `include/ztd_rtsp/rtsp_stream.hpp` — 新增 sink profile 数据结构
  - `config/package_config/ztd_rtsp/stream_settings.yml` — 新增 sink_profiles 配置
- **是否涉及数据库变更**: 否
- **是否涉及 API 变更**: 否（RTSP Server 接口不变）

## 约束 (Constraints)
- [x] 不改变现有 RTSP Server 行为
- [x] 不引入新的外部依赖（GStreamer rtmp2/flvmux 插件为系统已有）
- [x] 编码 pipeline 不改（一次编码，tee 分流）
- [x] 配置驱动，默认全部 sink 关闭，显式开启
- [x] 单 sink 故障不影响其他 sink（queue 隔离）
- [x] 不影响现有 RTSP 延迟和稳定性

## Non-Goals
- TRRO SDK 集成（Phase 2）
- 百度云推流（Phase 3）
- 运行时动态增减 sink（Phase 2）
- WVP/HTTP API 集成（后续）
