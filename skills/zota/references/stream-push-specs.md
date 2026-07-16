# Specs: ztd_rtsp 多路推流

## 功能需求

### REQ-001: GStreamer tee 多路分发（P0）
**描述**: `factory_gst_video_pipeline()` SHALL 在 h264parse 后插入 `tee` 元素，将 H264 流分发到多个独立 sink 分支。

**场景**:
- **Given** 配置了 1 个 RTSP + 1 个 RTMP sink
- **When** pipeline 启动
- **Then** RTSP Server 正常服务，RTMP 推流到 ZLM，两端独立工作

- **Given** RTMP sink 目标不可达
- **When** pipeline 运行中
- **Then** RTSP Server 不受影响，RTMP sink 仅输出 GStreamer warning 日志

### REQ-002: Sink Profile 配置驱动（P0）
**描述**: 系统 SHALL 从 `stream_settings.yml` 的 `sink_profiles` 数组读取 sink 配置，默认空数组（行为不变）。

**场景**:
- **Given** `sink_profiles: []` 或未配置
- **When** pipeline 启动
- **Then** 行为与当前完全一致，仅 RTSP Server

- **Given** `sink_profiles` 包含 `{type: rtmp, url: "rtmp://zlm...", enabled: true}`
- **When** pipeline 启动
- **Then** 自动构建 rtmpsink 分支并推流

### REQ-003: 故障隔离（P1）
**描述**: 每个 sink 分支 MUST 有独立 `queue` 元素，单 sink 失败 MUST NOT 影响其他 sink。

**场景**:
- **Given** RTMP 推流目标重启
- **When** RTMP 连接中断
- **Then** RTSP Server 正常服务，RTMP 自动重连（GStreamer rtmpsink 内置），无 pipeline 崩溃

### REQ-004: 零额外编码开销（P0）
**描述**: 多路分发 MUST 复用已有 H264 编码输出，MUST NOT 增加第二路编码。

**验证**: `nvidia-smi` 编码器负载与单路 RTSP 一致（±5%）

## 非功能需求

### NFR-001: 兼容性
- MUST NOT 改变现有 RTSP URL、端口、mount point
- MUST 兼容 `use_compressed_image` 参数
- MUST 兼容 NVIDIA `nvh264enc` 和 CPU `x264enc` 两种编码路径

### NFR-002: 可观测性
- 每个 sink 状态 SHALL 输出到 ROS2 log（INFO: 连接成功, WARN: 重连, ERROR: 持续失败）
- RTMP 推流 URL SHALL 包含 `${camera_name}` 变量替换
