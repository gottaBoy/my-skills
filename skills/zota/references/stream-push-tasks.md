# Tasks: ztd_rtsp 多路推流

## 依赖图

```
Task 1 (配置) ──→ Task 2 (数据结构) ──→ Task 3 (Pipeline tee) ──→ Task 4 (构建验证)
```

## 任务列表

- [ ] **Task 1**: 新增 `sink_profiles` YAML 配置
  - 文件: `config/package_config/ztd_rtsp/stream_settings.yml`
  - 内容: 新增 `sink_profiles` 数组，默认空（不影响现有行为）
  - 验证: YAML 语法正确，`ros2 launch ztd_rtsp ztd_rtsp_vehicle.launch.py` 不报错
  - 估时: 0.5h

- [ ] **Task 2**: 新增 `SinkProfile` 数据结构
  - 文件: `include/ztd_rtsp/rtsp_stream.hpp`
  - 变更: 新增 `SinkProfile` struct + `std::vector<SinkProfile> sink_profiles_` 成员 + setter
  - 依赖: Task 1
  - 估时: 0.5h

- [ ] **Task 3**: `factory_gst_video_pipeline()` 插入 tee + 动态 sink
  - 文件: `src/vehicle/rtsp_stream.cpp`
  - 变更: h264parse 后 tee → RTSP 分支保留 + 按 `sink_profiles_` 追加 rtmpsink/srtsink 分支
  - 依赖: Task 2
  - 验证: `ros2 launch ztd_rtsp ztd_rtsp_vehicle.launch.py`，RTSP 播放正常，`GST_DEBUG=3` 日志无 tee 相关 error
  - 估时: 2h

- [ ] **Task 4**: `RtspServer` 加载 sink_profiles 并传递给 RtspStream
  - 文件: `src/vehicle/rtsp_server.cpp`
  - 变更: 加载 `stream_settings.yml` 中 `sink_profiles`，逐 camera 传递
  - 依赖: Task 3
  - 估时: 1h

- [ ] **Task 5**: 构建 + 车端验证
  - 命令: `colcon build --packages-select ztd_rtsp`
  - 验证:
    1. 默认配置（sink_profiles 空）→ RTSP 正常
    2. 开启 ZLM push → RTSP + RTMP 并行工作
    3. 断开 RTMP 目标 → RTSP 不受影响
  - 估时: 1h
