# GStreamer rtspsrc Keyframe 请求限制

## 现状

GStreamer 1.16（JetPack 4.x 自带）的 `rtspsrc` 不支持以下 keyframe 请求机制：

- ❌ `request-keyframe` action signal（GStreamer 1.18+）
- ❌ `GstForceKeyUnit` upstream event 处理（GStreamer 1.18+）
- ❌ RTCP PLI/FIR 发送（无公开 API）

## 当前方案（2026-07-16）

### 常规 IDR：NVENC 固定 GOP
- `rtsp_stream.cpp`：`gop-size=keyIntMax` → NVENC 编码器按固定间隔自产 IDR
- 不依赖外部 PLI，自主产生 IDR

### 按需 Keyframe：IDR 缓存 + 重发
- `push_node.cpp`：`TrroStreamCtx::last_idr` 缓存最近一个 IDR（SPS/PPS + slice）
- TRRO SDK 请求 keyframe 时重发缓存 IDR，远程客户端初始化解码器
- 代价：缓存 IDR 可能来自旧 GOP → 花屏 ≤1 GOP 周期（gop-size=10 时 ~333ms）→ 下个 live IDR 自动修复

## 升级路径

目标：GStreamer ≥ 1.18

版本对照：
| GStreamer | JetPack | rtspsrc request-keyframe |
|-----------|---------|:--:|
| 1.16 | 4.x | ❌ |
| 1.20+ | 5.x | ✅ |

升级后可简化为：

```cpp
// 当前：60+ 行 IDR 缓存逻辑
// 升级后：
g_signal_emit_by_name(rtspsrc, "request-keyframe");
```

数据流（升级后）：
```
TRRO SDK 请求 keyframe
  → rtspsrc::request-keyframe
  → RTCP PLI → gst-rtsp-server → nvh264enc 即时产新 IDR
  → 精确无误，零花屏窗口 ✅
```

## 涉及文件

| 文件 | 当前逻辑 | 升级后可简化 |
|------|---------|------------|
| `aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/rtsp_stream.cpp` | `gop-size` probe（可保留做 defence-in-depth） | 不变 |
| `aura/src/ztd/ztd_network/ztd_rtsp/src/vehicle/push_node.cpp` | `TrroStreamCtx`, IDR 缓存, `request_keyframe` 重发 | 删 IDR 缓存，改为 signal emit |
