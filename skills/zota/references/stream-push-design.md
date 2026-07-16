# Design: ztd_rtsp 多路推流

## 架构决策

**方案**: 在现有 GStreamer pipeline 的 `h264parse` 后插入 `tee`，每个 sink profile 生成独立分支。

**备选方案**: 独立 ffmpeg 进程推流（`camera_stream` 方案）— 否决原因：额外编码开销 + 独立进程管理复杂度。

## 数据流

```
Camera → ROS2 CompressedImage → cv_bridge decode → appsrc
  → videoconvert → videocrop → videoscale
  → nvh264enc (硬件编码，一次)
  → h264parse
  → tee name=t
      ├─ queue → rtph264pay → RTSP Server :8554   (现有，不变)
      ├─ queue → flvmux → rtmpsink → ZLM          (新增，按配置)
      └─ queue → appsink → (TRRO SDK, Phase 2)
```

## Pipeline 字符串改造

### 现有（rtsp_stream.cpp L98-120）

```cpp
"( appsrc ... nvh264enc ... ! h264parse ... ! rtph264pay name=pay0 ... )"
```

### 改造后

```cpp
"( appsrc ... nvh264enc ... ! h264parse ... ! tee name=t "
"  t. ! queue ! rtph264pay name=pay0 pt=96 ... "    // RTSP（保留）
// 按 sink_profiles 动态追加:
"  t. ! queue ! flvmux ! rtmpsink name=push_zlm location=rtmp://... "
")"
```

## 模块变更

### 修改文件

| 文件 | 变更 | 行数 |
|------|------|:--:|
| `src/vehicle/rtsp_stream.cpp` | `factory_gst_video_pipeline()` 插入 tee，追加动态 sink 分支 | ~30 |
| `src/vehicle/rtsp_server.cpp` | 加载 `sink_profiles` 配置，传递给 RtspStream | ~20 |
| `include/ztd_rtsp/rtsp_stream.hpp` | 新增 `SinkProfile` struct + `sink_profiles_` 成员 | ~15 |
| `config/package_config/ztd_rtsp/stream_settings.yml` | 新增 `sink_profiles` 配置段 | ~10 |

### 不修改的文件（明确排除）

- `src/vehicle/rtsp_server_node.cpp` — 入口不动
- `src/operator/` — 操作端不动
- `launch/` — launch 文件不动
- 所有 `include/` 公共头文件 — 接口不动

## 配置格式

```yaml
# stream_settings.yml 新增
sink_profiles:
  - name: zlm_push
    type: rtmp                    # rtmp | srt | appsink
    url: "rtmp://10.8.201.14/live/${camera_name}"
    enabled: true
```

- `url` 支持 `${camera_name}` 替换为相机名（如 `cam_f_7`）
- `enabled: false` 的 sink 不构建

## 风险 & 回滚

- **最大风险**: `tee` 引入内存拷贝，单个 queue 满可能导致 pipeline 全局卡顿
  - **缓解**: 每个分支 queue 设 `max-size-buffers=4 leaky=downstream`（与现有 leaky_q 一致）
- **回滚方式**: `sink_profiles: []` 或删除配置段 → 行为完全回退
- **监控指标**: `nvh264enc` 帧率、RTMP sink 连接状态、内存增长
