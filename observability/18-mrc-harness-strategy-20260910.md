# DeepSeek Harness 侧远控退出/MRC1 验证策略

分析日期：`2026-09-10`

约束：不得修改 e2e 状态机，不得修改 watchdog 判定策略

架构图：[remote-session-exit.architecture.html](/Users/minyi/workspace/autodrive/.github/observability/diagrams/remote-session-exit.architecture.html)

## 0. 实施状态与协议证据

已实施：

- `.github/dsh/replay_remote_session.py`
- `.github/dsh/fixtures/replay/remote-session-scenarios.json`
- `.github/dsh/verify_exit_timeline.py`
- `validate_contract.py` 已校验回放只读约束、场景唯一性和时间单调性

验证结果：

```text
$ python3 .github/dsh/validate_contract.py
validated DSH contract: 6 schemas, 11 capability groups, 10 read-only tools, 7 valid fixtures, 2 rejected fixtures, 7 replay scenarios

$ PYTHONPYCACHEPREFIX=/tmp/autodrive-pycache python3 .github/dsh/replay_remote_session.py --all
PASSED normal-onrelease: mrc1=0 brake_frames=1 stale_messages=0
PASSED bt-others-exit: mrc1=0 brake_frames=0 stale_messages=0
PASSED release-vs-timeout: mrc1=1 brake_frames=1 stale_messages=0
PASSED repeated-release: mrc1=0 brake_frames=1 stale_messages=0
PASSED real-joystick-loss: mrc1=1 brake_frames=0 stale_messages=0
RISK   delayed-old-session-message: mrc1=1 brake_frames=1 stale_messages=1
RISK   late-release-clears-new-session: mrc1=0 brake_frames=1 stale_messages=0
```

对 `2026-09-09` 和 `2026-09-10` 的现有车端日志核对后确认：

- `onTakeover/onRelease` 当前没有稳定 `session_id`
- 同一生命周期事件会到达两次，两次 `inputs.id` 相同
- 两次事件中的 `omsno/vin` 会分别呈现驾驶仓/车辆两个方向
- `parallelDrivingControl/driveMode` 也不携带会话归属字段

因此本轮不增加 `session_id/session_generation` 拦截，不增加 release
后的时间窗口丢弃。Harness 将跨会话延迟消息标为 `known-risk`，等待
协议补充稳定的会话字段后再实施 cloud 层门控。

## 1. 当前改动概览

文件：[cloud_driving_vehicle.cpp](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp)

### 1.1 两条退出路径的语义区分

前端页面结束远控（`onRelease`）和手柄 `bt_others=1` 正常退出是两个不同的操作：

- **页面结束（`onRelease`）**：全部退出，清除所有缓存，发布 `DRIVE_R + PD_EXIT + BRAKE` 帧保持 R 模式安全制动
- **手柄退出（`bt_others=1`）**：手柄暂时不发消息，远控会话保持活跃，抑制 watchdog 检测

### 1.2 `release_remote_session` / `clear_remote_command_cache_locked`

```cpp
void release_remote_session(const char* source, const std::string& correlation_id)
```

职责：
- 清除 `cached_drive_mode_` 和全部灯光/EPB 缓存
- 重置 `mrc_cloud_`、`pd_steer_angle_`、`pd_js_status_`
- 调用 `reset_joystick_monitor()`（清零时间戳、重置 `joy_sm_`、`joystick_rx_seen_=false`）
- 若释放前处于 R 模式，发送一帧 `DRIVE_R + PD_EXIT + PD_STOP_FLAG_BRAKE`
  - e2e 保持 R 模式，进入 `joystick_status != PD_DRIVING` 分支：刹车 + 双闪 + 空挡
  - 车辆保持安全静止状态，alarm 保持亮，等待下一次接管
  - 不切换到 M 模式，避免 `SetDefaultValueForPDCtrl()` 清零所有安全指示
- 打印 `[remote-session] release source=...` 日志

入口：`handle_onRelease` -> `release_remote_session("onRelease", correlation_id)`
- 使用 `inputs.id` 作为 correlation_id（跨两次到达稳定）

### 1.3 `bt_others=1` 处理路径（不调用 `release_remote_session`）

```cpp
// bt_others=1 handler in handle_remotejoystick
if (bt_others_raw == 1) {
    mrc_cloud_.store(0, std::memory_order_relaxed);
    control_msg.joystick_status = PD_EXIT;
    control_msg.stop_flag = PD_STOP_FLAG_BRAKE;
    // 然后正常发布该帧（不走 release_remote_session）
}
```

职责：
- 清除 `mrc_cloud_`（joystick 侧）
- 在当前帧设置 `joystick_status=PD_EXIT` + `stop_flag=PD_STOP_FLAG_BRAKE`
- 调用 `joy_sm_.on_packet(1)` -> 进入 SUPPRESSED 状态
- **不**清除 `cached_drive_mode_`
- **不**清除 page-commanded 功能缓存
- **不**调用 `release_remote_session`
- 远控会话保持活跃，后续 `bt_others=0` 可恢复

### 1.4 `bt_others` 字段解析策略（已实施）

```cpp
// joystickdata 嵌套优先，外层回退
const bool nested_bt_others = jd.contains("bt_others") && !jd["bt_others"].is_null();
const bool top_level_bt_others = inputs.contains("bt_others") && !inputs["bt_others"].is_null();
const json* bt_others_source = &jd;
if (!nested_bt_others && &jd != &inputs && top_level_bt_others) {
    bt_others_source = &inputs;
}
const uint8_t bt_others_raw = static_cast<uint8_t>(
    json_int64_field(*bt_others_source, "bt_others").value_or(0));
```

### 1.5 watchdog 保护点（未改动）

- `ping_joystick()` 中：`if (!joystick_rx_seen_ || last_ms <= 0) return;`
- 进入 R 但尚未收到首帧时不会触发超时

## 2. 可落地 Harness 验证方案

当前 `ztd_cloud_driving` 包没有任何测试目标（CMakeLists.txt 仅 library + example）。新增的改动不需要完整的 ROS2 环境即可进行结构化验证。以下方案分为三个层级：

### 2.1 层级一：JoyMrcStateMachine 纯逻辑单元测试

`JoyMrcStateMachine` 是一个独立的组合体，只有三个公共方法（`on_tick`, `on_packet`, `reset`, `mrc_level`, `state`），无 ROS/外部依赖。

建议创建 `test/test_joy_mrc_state_machine.cpp`：

```cpp
// 测试场景矩阵
//
// ┌──────────────────────────────┬──────────────────────────────────────┐
// │ 场景                          │ 预期状态序列                        │
// ├──────────────────────────────┼──────────────────────────────────────┤
// │ NORMAL 下发 bt_others=1       │ SUPPRESSED, mrc_level=0             │
// │ NORMAL 下发 bt_others=2       │ MRC1, mrc_level=2                  │
// │ DETECTING 中连续 gap 恢复     │ DETECTING→NORMAL                    │
// │ DETECTING 达到 consec_thresh  │ DETECTING→MRC1                     │
// │ MRC1 保持期内 gap 恢复        │ 保持 MRC1（hold_ticks 不耗尽）       │
// │ MRC1 保持期后 gap 恢复        │ MRC1→NORMAL                        │
// │ SUPPRESSED 持续大 gap         │ 保持 SUPPRESSED, 不触发 DETECTING   │
// │ SUPPRESSED→on_packet(0)      │ SUPPRESSED→NORMAL (恢复检测)        │
// │ MRC1 中收到 bt_others=1       │ MRC1→SUPPRESSED, mrc_level=0       │
// │ reset 后任意状态              │ NORMAL, mrc_level=0, lost_count=0  │
// └──────────────────────────────┴──────────────────────────────────────┘
```

CMakeLists.txt 补充（在 `ztd_cloud_driving/CMakeLists.txt` 中）：

```cmake
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_joy_mrc_sm test/test_joy_mrc_state_machine.cpp)
  target_link_libraries(test_joy_mrc_sm ${PROJECT_NAME})
  ament_target_dependencies(test_joy_mrc_sm rclcpp)
endif()
```

新增的命令行验收日志关键字：

```text
[----------] 10 tests from JoyMrcStateMachineTest
[ RUN      ] JoyMrcStateMachineTest.bt_others_1_enters_suppressed
[       OK ] JoyMrcStateMachineTest.bt_others_1_enters_suppressed
[ RUN      ] JoyMrcStateMachineTest.bt_others_2_enters_mrc1
[       OK ] JoyMrcStateMachineTest.bt_others_2_enters_mrc1
[ RUN      ] JoyMrcStateMachineTest.suppressed_ignores_large_gap
[       OK ] JoyMrcStateMachineTest.suppressed_ignores_large_gap
[ RUN      ] JoyMrcStateMachineTest.mrc1_hold_prevents_premature_recovery
[       OK ] JoyMrcStateMachineTest.mrc1_hold_prevents_premature_recovery
[ RUN      ] JoyMrcStateMachineTest.reset_clears_all_state
[       OK ] JoyMrcStateMachineTest.reset_clears_all_state
[ RUN      ] JoyMrcStateMachineTest.release_in_mrc1_clears_mrc
[       OK ] JoyMrcStateMachineTest.release_in_mrc1_clears_mrc
[----------] 10 tests (X ms total)
```

### 2.2 层级二：`release_remote_session` 行为验证

该函数依赖 `vehicle_cmd_mutex_`、`mrc_cloud_`、`joy_sm_`、`pd_control_pub_`、`reset_joystick_monitor`。需要一个 minimal `ParallelDrivingVehicleNode` 实例化或重构为可独立测试的 helper。

**推荐方案**：将 `release_remote_session` 和 `clear_remote_command_cache_locked` 提取到自由函数或静态帮助类中，接受一个 `ReleaseContext` 参数（包含需要修改的原子变量和 publisher 的引用/回调）。这样可以在不启动 ROS2 的情况下验证：

```text
测试 1: release_remote_session 在 R 模式下应发送制动帧
  - 预置 cached_drive_mode_=2
  - 调用 release_remote_session("test", "msg-1")
  - 验证: cached_drive_mode_==0, mrc_cloud_==0, pd_js_status_==0
  - 验证: pd_control_pub_ 收到 (DRIVE_R, PD_EXIT, PD_STOP_FLAG_BRAKE)

测试 2: release_remote_session 在 M/A 模式下不应发送制动帧
  - 预置 cached_drive_mode_=0
  - 调用 release_remote_session("test", "msg-2")
  - 验证: 无 pd_control_pub_ 调用

测试 3: 连续两次 release_remote_session 应幂等
  - 调用两次，验证第二次不产生额外制动帧
```

验收日志关键字：

```text
[remote-session] release source=test message_id=msg-1
  previous_drive_mode=2 cached_drive_mode=0 cloud_mrc=0
  joystick_monitor=reset e2e_brake_frame=published

[remote-session] release source=test message_id=msg-2
  previous_drive_mode=0 ... e2e_brake_frame=not_needed
```

### 2.3 层级三：场景回放验证（已落地，DSH 纯离线）

这是**最高业务价值**的方案。CloudDrivingClient 已具备 `register_function_handler` + `invoke_function` 的接口，车端 handler 的入口是 JSON inputs。可以编写一个 Python 驱动脚本，直接构造函数调用的 JSON 输入，按指定时间序列注入 handler，然后监测输出状态变量。

#### 2.3.1 回放架构

```text
                  ┌─────────────────────────┐
                  │ replay_remote_session.py│
                  │   (Python 3 + rclpy)    │
                  ├─────────────────────────┤
                  │ 1. 启动 vehicle node    │
                  │ 2. 按场景时间线注入消息  │
                  │ 3. 监听 topic / 日志    │
                  │ 4. 断言结果 / 输出报告  │
                  └─────────┬───────────────┘
                            │ invoke_function 模拟云端
                            ▼
                 ┌─────────────────────┐
                 │ cloud_driving_vehicle│
                 │ function handlers   │
                 │ handle_driveMode    │
                 │ handle_onTakeover   │
                 │ handle_onRelease    │
                 │ handle_remotejoy..  │
                 └─────────────────────┘
                            │ publish pd_control_pub_
                            ▼
                 ┌─────────────────────┐
                 │ /zeron/parallel_    │
                 │ driving/control_info │
                 │ topic subscriber    │
                 └─────────────────────┘
```

#### 2.3.2 所需辅助改动（最小化，不修改核心状态机）

在 `ParallelDrivingVehicleNode` 中增加：

```cpp
// 暴露 pd_control_pub_ 的最后发布消息（用于断言，无锁读取）
std::optional<parallel_driving_msgs::msg::ParallelDrivingControl>
get_last_pd_control_msg() const;
```

这是为可测试性增加的**观测接口**，不改变任何业务逻辑。回放脚本订阅该独立 topic 或轮询状态变化。

#### 2.3.3 场景定义

**场景 A：正常 `onRelease` 退出**

注入序列：

| step | 时间偏移 | 消息 | 关键字段 |
|------|---------|------|---------|
| 1 | 0s | `onTakeover` | `{session_id: "s1", cabin_id: "GQ004"}` |
| 2 | +0.1s | `driveMode` | `drive_mode=2` |
| 3 | +0.2s | `remotejoystick` | `bt_others=0, up=50, left=0` |
| 4~20 | +0.3s~+2.0s | `remotejoystick` | 持续控制帧，100ms间隔 |
| 21 | +2.1s | `onRelease` | `{session_id: "s1"}` |
| 22 | +3.0s | 结束 | 检查最后2秒内无 MRC1 |

预期：
- `release_remote_session` 被调用，日志打印 `[remote-session] release source=onRelease`
- `joystick_rx_seen_` 重置为 false
- watchdog 后续 tick 因 `!joystick_rx_seen_` 跳过，不触发 DETECTING/MRC1
- pd_control_pub_ 收到 `DRIVE_R + PD_EXIT + PD_STOP_FLAG_BRAKE`

验收日志关键字：

```text
[处理] onRelease 收到请求
[remote-session] release source=onRelease ... e2e_brake_frame=published
[JOYSTICK] MRC1 triggered  # 不能出现
[JOYSTICK] detecting loss  # 不能出现
```

**场景 B：`bt_others=1` 手柄源退出**

注入序列：

| step | 时间偏移 | 消息 | 关键字段 |
|------|---------|------|---------|
| 1 | 0s | `onTakeover` | `session_id: "s1"` |
| 2 | +0.1s | `driveMode` | `drive_mode=2` |
| 3 | +0.2s | `remotejoystick` | 持续控制帧 |
| 4~20 | 持续 | `remotejoystick` | 持续控制帧 |
| 21 | +2.0s | `remotejoystick` | `bt_others=1, joystickdata.bt_others=1` |
| 22 | +3.0s | 结束 | 检查无 MRC1 |

预期：
- `bt_others=1` 清除 `mrc_cloud_`，设置 `PD_EXIT + BRAKE` 到当前帧
- `joy_sm_.on_packet(1)` -> SUPPRESSED，抑制 watchdog
- **不**调用 `release_remote_session`，`cached_drive_mode_` 保持不变
- 远控会话保持活跃
- 后续 `bt_others=0` 恢复正常控制

验收日志关键字：

```text
[joystick] driver exit, suppress joystick source, hold brake; remote session remains active
```

**场景 C：`onRelease` 和 MRC timeout 竞态**

注入序列：

| step | 时间偏移 | 消息 | 关键字段 |
|------|---------|------|---------|
| 1 | 0s | `onTakeover` | |
| 2 | +0.1s | `driveMode` | `drive_mode=2` |
| 3 | +0.2s | `remotejoystick` | 首帧 |
| 4~5 | 持续 | `remotejoystick` | 2帧（建立 `joystick_rx_seen_`） |
| 6 | +0.8s | 停止发送 joystick | 模拟断流 |
| 7 | +1.5s | `onRelease` | 此时 watchdog 可能正在 DETECTING 或已到 MRC1 |
| 8 | +3.0s | 结束 | 检查结果 |

预期：
- 若 `onRelease` 在 MRC1 触发前到达 → 无 MRC1，正常退出
- 若 `onRelease` 在 MRC1 触发后到达 → 清除 MRC，退出
- 无论哪种时序，退出后不应因旧 session 的 timeout tick 回退到 MRC1

验收日志关键字：

```text
# onRelease 先于 MRC1
[remote-session] release source=onRelease
[JOYSTICK] MRC1 triggered  # 不能出现

# onRelease 晚于 MRC1
[JOYSTICK] MRC1 triggered gap=... last_message_id=...
[remote-session] release source=onRelease
[JOYSTICK] MRC1 cleared — joystick recovered  # 期望
```

**场景 D：连续 `onRelease` 幂等**

注入序列：

| step | 时间偏移 | 消息 | 关键字段 |
|------|---------|------|---------|
| 1~3 | 同场景A | 建立远控 | |
| 4 | +2.0s | `onRelease` #1 | |
| 5 | +2.1s | `onRelease` #2 | 重复 release |
| 6 | +2.2s | `onRelease` #3 | 重复 release |
| 7 | +3.0s | 结束 | 检查状态 |

预期：
- 第一个 `onRelease` 正常执行退出
- 后续 `onRelease` 幂等：`cached_drive_mode_` 已为 0，不触发额外退出逻辑
- 无异常、无 MRC1

验收日志关键字：

```text
[remote-session] release source=onRelease ... e2e_brake_frame=published
[remote-session] release source=onRelease ... e2e_brake_frame=not_needed
```

**场景 E：旧 session generation 的延迟 timeout tick**

注入序列：

| step | 时间偏移 | 消息 | 关键字段 |
|------|---------|------|---------|
| 1~3 | 0s~+0.3s | 建立 session s1 | |
| 4 | +1.0s | `onRelease` | 结束 s1 |
| 5 | +1.1s | `onTakeover` | 新 session s2 |
| 6 | +1.2s | `driveMode` | `drive_mode=2` |
| 7 | +1.3s | `remotejoystick` | 首帧 |
| 8 | +1.5s~+3.0s | `remotejoystick` | 持续控制 |
| 9 | +3.0s | 结束 | 检查 s1 旧 tick 不影响 s2 |

此场景当前代码**没有 session generation 保护**，需要在 harness 中暴露问题。

验收日志关键字：

```text
# 当前代码：可能看到旧 tick 触发 DETECTING，但 joystick_rx_seen_ 已被新帧置 true
# 改进后：应完全隔离旧 session 的 tick
```

### 2.4 离线日志回放验证（已落地）

已有历史日志文件（如 `ztd_cloud_driving_20260909185341.log`）可离线解析，提取关键事件时间线，与实车行为对照。

推荐工具命令：

```bash
# 提取所有 joystick/handler/MRC 事件
grep -E '\[remotejoystick-observation\]|\[joystick\]|\[MRC\]|\[remote-session\]|onRelease|onTakeover' \
  ztd_cloud_driving_20260909185341.log

# 提取 e2e MRC 判定
grep -E 'MRC active|MRC1 is triggering|effective_mrc' e2e_control_20260909185341.log

# 提取 bt_others
grep -E 'bt_others|driver exit' ztd_cloud_driving_20260909185341.log
```

已落地 `.github/dsh/verify_exit_timeline.py` 自动分析：

```python
#!/usr/bin/env python3
"""
离线日志回放检查：验证退出流程是否符合预期。

用法:
  python3 .github/dsh/verify_exit_timeline.py \
    --cloud-driving ztd_cloud_driving_20260909.log \
    --e2e e2e_control_20260909.log \
    --scenario cabin-switch-exit

输出:
  - 事件时间线（Exit Timeline）
  - bt_others 存在性检查
  - watchdog / MRC1 触发判定
  - 根因推断
"""
```

## 3. 当前代码可改进的小问题

以下问题通过代码审查发现，不修改核心状态机或 watchdog，可安全地补充。

### 3.1 `bt_others` 嵌套字段取数策略

[cloud_driving_vehicle.cpp:965](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:965)

```cpp
const uint8_t bt_others_raw = static_cast<uint8_t>(jd.value("bt_others", 0));
```

`jd` 优先取自 `joystickdata` 嵌套对象。但 GQ004 日志中可能将 `bt_others` 放在外层。建议：

```cpp
// 优先从 joystickdata 读取，若不存在或为 0 则回退到 inputs 顶层
uint8_t bt_others_raw = static_cast<uint8_t>(jd.value("bt_others", 0));
if (bt_others_raw == 0 && &jd != &inputs) {
    bt_others_raw = static_cast<uint8_t>(inputs.value("bt_others", 0));
}
```

同时打印读取来源日志，便于排查：

```cpp
RCLCPP_DEBUG(get_logger(),
    "[joystick] bt_others resolved: raw=%u source=%s message_id=%s",
    bt_others_raw,
    (&jd == &inputs) ? "top_level" : "joystickdata_nested",
    message_id.c_str());
```

### 3.2 `onRelease` 缺少 session 校验

当前 `handle_onRelease` 直接执行 `release_remote_session`，不校验消息中的 session_id 是否匹配当前活动 session。若旧驾驶仓延迟到达的 `onRelease` 在新 session 后被处理，会清空新 session 的状态。

建议增加可选校验（不改变核心状态机的前提下）：

```cpp
// 读取 release 请求中的 session_id/cabin_id
std::string req_session = json_scalar_string(inputs, "session_id", "");
std::string req_cabin  = json_scalar_string(inputs, "cabin_id", "");

// 只在配置了校验时才校验；默认跳过以保持向后兼容
if (!req_session.empty() && !active_session_id_.empty()
    && req_session != active_session_id_) {
    RCLCPP_WARN(get_logger(),
        "[处理] onRelease session mismatch: request=%s active=%s, ignored",
        req_session.c_str(), active_session_id_.c_str());
    return {{"success", true}, {"messageId", message_id}, {"ack", "ok"}};
}
```

### 3.3 `release_remote_session` 中 `mrc_cloud_` 无条件清零

[cloud_driving_vehicle.cpp:607](/Users/minyi/workspace/autodrive/aura/src/ztd/ztd_network/ztd_cloud_driving/examples/cloud_driving_vehicle.cpp:607)

```cpp
mrc_cloud_.store(0, std::memory_order_relaxed);
```

若 MRC 由其他来源（health/arbitrator/emergencystop）设置，退出远控会话不应清零。建议：

```cpp
// 只清除来源于当前远控会话的 MRC
if (mrc_source_ == "remote_session") {
    mrc_cloud_.store(0, std::memory_order_relaxed);
}
```

当前代码没有追踪 `mrc_source_`，若要实现需增加一个原子变量记录最近一次 MRC 设置的来源。这是一个增量改进，不改变核心状态机。

### 3.4 `pd_keepalive_timer_` 在 release 后仍会运行

`release_remote_session` 将 `cached_drive_mode_` 置为 0，因此 `publish_pd_keepalive()` 会在 `cached_drive_mode_ != 2` 时直接 return。这已经是安全的退路。

但定时器仍然在 tick（约 0.15s 间隔），只是空转。建议在 release 后取消定时器，下次 `onTakeover + drive_mode=2` 时再创建：

```cpp
if (pd_keepalive_timer_) {
    pd_keepalive_timer_->cancel();
}
```

这个改动很小，且不涉及状态机的逻辑变化。

## 4. 验收用例与日志关键字汇总

| 场景 | 是否覆盖 | 验收日志关键字 |
|---|---|---|
| `bt_others=1` 手柄源退出 | 层级二/三 | `[joystick] driver exit, suppress joystick source, hold brake` |
| `onRelease` 正常退出 | 层级二/三 | `[remote-session] release source=onRelease` |
| 连续退出幂等 | 层级三 | `e2e_brake_frame=not_needed`（第二次起） |
| release 后无 MRC1 | 层级三 | `[JOYSTICK] MRC1 triggered` 不应出现 |
| release 在断流后到达 | 层级三 | 先 MRC1 后 release → `MRC1 cleared` |
| 旧 session tick 不影响新 session | 层级三 | 需 session_generation 保护（当前无） |
| `bt_others` 嵌套/顶层兼容 | 层级一/三 | `bt_others resolved: raw=1 source=joystickdata_nested` |
| 首帧前 watchdog 抑制 | 层级三 | 进入 R 后 0.9s 内不断流不应触发 MRC1 |
| `onRelease` session 校验 | 层级三 | `session mismatch: request=x active=y, ignored` |

## 5. 推荐实施顺序

```
优先度 1: 层级三回放场景 A+B（最高业务价值，可直接验证当前代码行为）
  └─ 编写 replay_driver.py + 对应的 pytest 用例
  └─ 预期产出：两个场景自动通过

优先度 2: 层级一 JoyMrcStateMachine 单元测试（低风险、高覆盖）
  └─ 创建 test/test_joy_mrc_state_machine.cpp
  └─ 预期产出：10 个测试全部通过

优先度 3: 3.1 bt_others 嵌套回退 + 日志改进
  └─ 修改 cloud_driving_vehicle.cpp 第 965 行附近
  └─ 预期产出：bt_others 来源可观测

优先度 4: 层级三场景 C（竞态）和场景 D（幂等）
  └─ 需要先确认 fix 3.3 和 3.2 是否合入

优先度 5: 3.2 onRelease session 校验 + 3.3 mrc_cloud 来源感知
  └─ 这两个改动涉及增量状态，需要实车验证
```

## 6. Harness 脚本入口与命令

### 6.1 回放驱动脚本结构

实际位置：`.github/dsh/replay_remote_session.py`

```python
#!/usr/bin/env python3
"""
远控会话生命周期回放验证脚本。

用法:
  # 场景 A: onRelease 正常退出
  ros2 run ztd_cloud_driving replay_remote_session.py \
    --scenario normal-onrelease

  # 场景 B: bt_others=1 退出
  ros2 run ztd_cloud_driving replay_remote_session.py \
    --scenario bt_others-exit

  # 场景 C: onRelease 与 MRC 竞态
  ros2 run ztd_cloud_driving replay_remote_session.py \
    --scenario release-vs-timeout

  # 所有场景
  ros2 run ztd_cloud_driving replay_remote_session.py --all
```

### 6.2 离线验证脚本

实际位置：`.github/dsh/verify_exit_timeline.py`

```bash
# 提取 GQ004 最终退出的完整时间线
python3 verify_exit_timeline.py \
  --cloud-driving /Users/minyi/Downloads/ztd_cloud_driving_20260909185341.log \
  --e2e /Users/minyi/Downloads/e2e_control_20260909185341.log \
  --since 1788954809 \
  --until 1788954860

# 输出：
# Exit Timeline:
#   1788954809.678  last_joystick_frame  transport_seq=10501
#   1788954810.013  watchdog_detecting   gap=335ms
#   1788954810.562  mrc1_triggered       gap=884ms
#   1788954854.305  onRelease_received
#
# Root cause: bt_others=1 not found in timeline.
#             joystick stream stopped but no exit signal processed.
```

## 7. 风险与未覆盖事项

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| 回放场景使用 mock 函数签名，不经过真实 TCP 收发 | 无法验证传输层延迟、乱序、重连 | 建议独立做网络模拟测试（超出本 scope） |
| 当前无 session generation 保护 | 旧 session 的延迟 timeout tick 可能影响新 session | 已在场景 E 暴露，建议作为下一步 fix |
| `pd_keepalive_timer_` 空转 | 无功能影响，但有轻微性能浪费 | 优先级低，release 后可取消定时器 |
| 日志回放依赖时间戳精度 | 日志中 `wall clock` 可能被 NTP 调整或跨设备偏移 | 只在单一设备日志内做时序分析 |
| 无法覆盖 `health_arbitrator` 触发的 MRC 与远控退出竞争 | 这是另一独立模块的生命周期 | 需端到端集成测试，超出本 harness 范围 |

## 8. 结论

当前改动正确回答了 GQ004/GQ002 暴露的问题：`onRelease` 清理全部远控缓存并发布 `DRIVE_R + PD_EXIT + BRAKE` 帧保持 R 模式安全制动；`bt_others=1` 只抑制手柄源 watchdog 不结束远控会话。Harness 验证方案可覆盖全部六种场景，核心价值为：

1. **回放场景 A+B**：验证正常退出路径，这是当前故障的直接反面
2. **JoyMrcStateMachine 单元测试**：10 个矩阵覆盖全部可能的状态转换
3. **bt_others 嵌套回退**：消除报文格式兼容性隐患
4. **退出时间线离线分析**：无需实车即可对历史日志做结构化原因判定

不做的事项：
- e2e 内部状态机：不修改
- watchdog 判定策略：不修改
- session_id/session_generation：标记为风险区域，由本次 harness 暴露问题但不修复
- 旧 `drive_mode=2` 跨会话拒绝：需 cloud 层增加消息序列校验，不在本 scope
