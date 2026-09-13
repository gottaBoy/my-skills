# IB_Robot 在 DGX Spark 上的 Docker Compose 与研发体系方案

评估日期：2026-09-13，Asia/Shanghai。

评估对象：`gottaBoy/IB_Robot`，本次获取的默认分支 HEAD 为
`3c0cd3586576d79127135247288ded1ee9cd5d47`，提交时间为
`2026-09-12T17:37:41+08:00`。这不是对未来提交的兼容承诺。

交付状态：**设计方案与平台预检配置，不是已经部署的 IB_Robot 系统**。
本次只进行源码审阅、主机只读检查、官方资料与镜像/软件包索引查询。
没有安装宿主机依赖、运行项目 setup/build、下载模型、拉取业务镜像、启动业务容器或控制机器人。
检索覆盖项目源码和 NVIDIA、ROS、Docker、PyTorch、OpenClaw、DORA 等一手资料，不代表穷尽全网。

## 1. 决策摘要

1. **有条件适合在 Spark 上推进，不能原样一键跑通，也尚未实测跑通。**
   优先目标是 SO-101 的受控技能闭环或一个 ACT 推理闭环，不能把所有模型、导航、抓取和基准一次作为 POC。
2. **所有应用依赖使用 Docker Compose 管理。**
   保留 Spark 的系统、驱动和 Docker 环境；ROS Humble 使用 ARM64 Ubuntu 22.04 容器。
3. **OpenClaw 不应成为前置依赖。**
   当前源码默认入口已经是 Hermes + `robot-skill` + Capability Gateway；
   README 把 RosClaw 标注为可选旧社交桥接。研发自动化与机器人控制应分别治理。
4. **先建立可重复构建、测试门禁、版本追溯与回滚，再增加 Agent 自动化。**
   项目已经有 Skills、契约、模型 manifest、安全网关和测试，不需要另造一套机器人执行框架。

源码依据见第 3 节；硬件与容器依据见文末 S1-S8。

## 2. 当前主机事实与能力边界

以下是本次只读命令输出，不是远程网页推测：

| 项目 | 实际观察 |
| --- | --- |
| CPU 架构 | `aarch64` |
| GPU | `NVIDIA GB10` |
| 驱动 | `580.173.02`，来自 `nvidia-smi` |
| 操作系统 | Ubuntu 24.04.3 LTS |
| 内存 | `/proc/meminfo` 的 MemTotal 为 `125483392 kB`，约 119.7 GiB 的 OS 可见容量 |
| 已有 CUDA 工具包元数据 | `/usr/local/cuda/version.json` 声明 CUDA SDK `13.0.3` |
| Docker | Engine 29.2.1，服务端 `linux/arm64` |
| Compose | v5.0.2 |
| 宿主机 ROS | 未发现 `/opt/ros`，无需为本方案补装 |
| GPU 容器接入 | 已有 `/var/run/cdi/nvidia.yaml`，包含 `nvidia.com/gpu` 和 `all` 设备 |

Docker runtime 列表未出现 `nvidia`，不能直接假定传统 `driver: nvidia` 路径可用。
本模板选择现有 CDI 的 `devices: ["nvidia.com/gpu=all"]`；**CDI 文件存在不等于
GPU 容器实测通过**，仍需运行预检。不得为绕过失败自动修改 daemon.json、驱动或 CDI 文件。
Docker 官方支持 Compose CDI 设备声明；NVIDIA 文档说明了 CDI 注入方式及与旧 hook 的冲突边界。[S5-S6]

NVIDIA 官方规格为 128 GB 统一内存、ARM CPU 与 Blackwell GPU；GB10 的 CUDA
compute capability 为 12.1。[S1-S2] 统一内存不应理解成“128 GB 独立显存外加系统内存”。
模型权重、KV cache、图像、训练激活、仿真和系统需要共同规划容量。
厂商的低精度峰值算力也不能直接换算成策略控制频率或多 Agent 并发能力。

**本次没有测得推理速度、训练时间、控制周期或仿真帧率，不承诺具体性能。**

## 3. 源码审阅：真正需要处理的问题

下表路径均相对上述固定 commit，可在本次只读副本
`/tmp/ib-robot-audit-20260913` 中检查。

| 风险 | 直接证据 | 影响与处理 |
| --- | --- | --- |
| 宿主机发行版不匹配 | `scripts/setup/detect.sh:152` 只识别 Ubuntu 22.04，`:192` 拒绝未知平台 | 不在 24.04 主机强行传 `--platform ubuntu-22.04`；放入真实 Jammy ARM64 容器 |
| 旧 PointNet2 制品不兼容 | `scripts/setup/install_graspgen_pip.sh:37` 固定 `cp310...x86_64.whl`；`:47` 检查 Torch 2.7.1+cu126 | 该 wheel 不能直接用于 ARM64；有 nvcc 时虽有源码路径，仍需适配验证 |
| CUDA 扩展目标不匹配 | 同文件 `:125` 默认 `TORCH_CUDA_ARCH_LIST=8.6` | GB10 为 12.1；需要对应工具链与算子测试，不能只改一个环境变量就宣布支持 |
| Full 安装依赖面过大 | `scripts/setup/python_venv.sh:460` 附近默认安装 GraspGen；`requirements/manipulation.txt` 含 `spconv-cu120`、`torch-scatter` | POC 先使用已有 `--profile inference`；后续增加可组合 core/sim/grasp profile，避免删除依赖冒充通过 |
| LIBERO 当前入口限制平台 | `scripts/setup/benchmark_profile.sh:42` 检查 Jammy；`:47` 明确检查 x86_64 | 单独适配或留在 x86_64 GPU runner；这不是对 MuJoCo 或 Spark 的普遍否定 |
| 默认 Agent 已变化 | `README.md:569` 将 RosClaw 标为可选旧桥接；`src/embodied_agent/README.md:3` 为 Hermes-only | 新接入复用高层 Gateway，不按首页宣传重建 OpenClaw 控制面 |
| 现有 scheduler 有组合约束 | `src/inference_service/README.md:250` 明确拒绝 scheduler + distributed 组合 | 分容器分布式推理先使用既有 distributed 路径并保持 scheduler 关闭 |
| CI 文件不等于完整质量门禁 | `src/workflows/jenkinsfile_gate` 可见流程主要执行 commit message 检查与回写 | 需核查实际外部 Jenkins 配置并补 build/test/GPU/SIL；不能据此断言项目外部完全没有 CI |

此外：

- LeRobot、RosClaw、MoveIt 接口、雷达等采用跨 GitCode/AtomGit 的子模块，
  需要固定 gitlink、补丁序列、下载来源和哈希；不能只锁主仓 SHA。
- 本次没有递归下载全部子模块或权重，因此不能确认所有依赖在当前网络可获取。
- 仓库有大量契约、模拟、执行、取消、安全与推理测试；**存在测试文件不等于这些测试本轮通过**。
- `third_party/vendor/` 已区分厂商制品身份与再分发授权。产品交付前应建立完整授权清单；
  根目录本次未发现 LICENSE 文件，不能仅凭 README 的 Apache 2.0 描述完成发布审核。
  这是需要补证据的交付门禁，不是对整个项目授权性质的法律结论。

## 4. 建议的容器内兼容基线

### 4.1 ROS 与策略推理

建议优先验证：

```text
Host: existing DGX OS / NVIDIA driver / Docker / CDI
  |
  +-- Container: Ubuntu 22.04 ARM64
        ROS 2 Humble + Python 3.10
        IB_Robot pinned commit + managed LeRobot patches
        Torch 2.10.0+cu130
        TorchVision 0.25.0+cu130
        TorchAudio 2.10.0+cu130, only if needed
```

本次在 PyTorch 官方索引中确实找到以下制品，不是猜测存在：[S7]

| 制品 | SHA256 |
| --- | --- |
| `torch-2.10.0+cu130-cp310-cp310-manylinux_2_28_aarch64.whl` | `adfb2bca94f12a5baca6ccf9aa40d6c5b1259748ebb38938be670b07a24d4e15` |
| `torchvision-0.25.0+cu130-cp310-cp310-manylinux_2_28_aarch64.whl` | `a82d06af6e538c2a860ed9bfdce696cfe0a130a27dc495d32cda099d8d68c85a` |
| `torchaudio-2.10.0+cu130-cp310-cp310-manylinux_2_28_aarch64.whl` | `132a50937cd4f4d4570c3dbc31a74410efe7d058619c9475fcdda1a9b7be0b27` |

**制品存在只解决了部分可安装性，不是完整依赖解析、GPU 算子或 LeRobot 验证结果。**
后续在 image build 中固定约束与哈希，检查 `pip check`、CUDA 计算、torchvision 算子、
policy 加载和 golden input/output；禁止安装流程静默换成 CPU Torch。
NumPy/OpenCV、Empy、LeRobot Python 兼容补丁沿用项目现有 ROS ABI 约束。
编译 CUDA 扩展所需工具链只装入 builder image，不复用或挂载宿主机 `/usr/local/cuda`。

Docker 官方镜像清单明确列出 `humble-ros-core-jammy` 和 `humble-ros-base-jammy`
支持 `arm64v8`。[S8] 本次查询 Docker Hub 实时 manifest 超时，
所以尚未取得 ROS image digest；不能将这个网络失败解释成架构不支持。

### 4.2 为什么不能直接把 NGC 镜像当完整 ROS 镜像

平台预检使用的 NVIDIA PyTorch 25.09 镜像包含 Ubuntu 24.04、Python 3.12 和 CUDA 13.0，
是选择的历史验证基线，不是声称它为当前最新版本。[S3]
本次已查询其 `linux/arm64` manifest digest：

```text
nvcr.io/nvidia/pytorch:25.09-py3
sha256:89172d8ef9c4641aacdcddf02c085bf7a736501b443ce2c4e0a660754f67106b
```

该镜像只用于证明 GPU 容器底座，**不能把 Jammy/Python 3.10 的 rclpy/venv 直接复制进去**。
初期业务路径优先保持两个 ROS 容器同为 Humble/Python 3.10。
若后续采用 NGC 独立模型服务，必须实现并测试明确的 RPC adapter；
IB_Robot 当前 distributed 协议并不是任意 HTTP/OpenAI-compatible server 的即插即用客户端。
对话 LLM 服务与机器人 policy 服务也不是同一种接口。

## 5. Docker Compose 总体设计

将应用分成三个独立 Compose project，以下服务是**目标设计，尚未实现部署文件或镜像**：

| Project | 服务 | 职责 |
| --- | --- | --- |
| `ibrobot-runtime` | `ros-control` | Humble、Gateway、技能、安全、动作执行；初期不接真机 |
| `ibrobot-runtime` | `policy-cuda` | 同 ABI 的 ROS 推理镜像，按 manifest 加载单个策略，使用既有 distributed 协议 |
| `ibrobot-runtime` | `sim`，可选 profile | 先 mock 验证接口，再 Gazebo/MuJoCo 验证物理与相机；mock 不代表物理仿真 |
| `ibrobot-runtime` | `robot-agent`，可选 profile | 采用项目现有 Hermes/robot-skill 集成，构建兼容的客户端镜像 |
| `ibrobot-dev` | `dev-worker` / `test-worker` | 隔离工作树、lint、单测、镜像构建和受信 CI job；不连接机器人网络 |
| `ibrobot-dev` | `openclaw`，可选 profile | 消息入口、日报、只读查询、受控工作项提交，不直接获得 ROS 或部署权限 |
| `ibrobot-ops` | 实验追踪、制品与可观测服务 | 按需部署 MLflow/数据库/OTel/Prometheus/Grafana；已有服务可复用 |

```text
Product / Issue / Acceptance Criteria
              |
      Trusted Work Queue <----- OpenClaw (optional message interface)
              |
       Coding Worker --> PR --> CI --> Human Release Approval
                                           |
                                Immutable Release Manifest
                                           |
                                   Deployment Executor

Hermes / robot-skill --> Capability Gateway --> Safety --> Controller
                                 |
                        Policy / Perception Service --> GPU
                                 |
                      Telemetry / Evidence / Dataset Feedback
```

OpenClaw 到工作队列的权限 adapter 是待实现项，不是本项目已经提供的研发集成。
真机高层控制入口与研发 Agent 不能共用任意 shell、凭证、网络权限或 Docker socket。

### 5.1 不污染宿主机的准确含义

- 不在主机执行 `apt install`、`pip install`、`npm install -g`、项目 `setup.sh`。
- 不修改主机 ROS、Python、Node、驱动、systemd、udev、sysctl、Docker daemon 配置。
- 不使用 `privileged: true`，不映射整个 `/dev`，不挂载 `/`、用户 home 或 Docker socket。
- 默认 bridge 网络；管理 UI 只发布到 `127.0.0.1`，不公开 rosbridge 9090 或 DDS 端口。
- runtime 非 root、最小 capabilities、只读 rootfs、临时目录 tmpfs；
  builder 安装依赖时的 root 仅存在于构建容器内。
- 代码与配置只读挂载；模型 runtime 只读；实验产物、日志、状态进入项目专用 volumes。
- 停止/重建不自动删除数据卷；备份必须有恢复演练，清理只针对本 project。

Docker 镜像、缓存、数据卷和日志仍占用主机磁盘；GPU 透传仍依赖现有主机驱动与 CDI。
所以这是“应用依赖不进入主机环境”，不是“零磁盘占用”或“独立内核的强租户隔离”。
GPU 接入不满足条件时停在预检并报告，不暗中修复主机。

### 5.2 网络与安全边界

ROS 容器位于专用 robot network，使用一致的 Domain ID、RMW 和消息版本。
同宿主机先验证 DDS 发现与 UDP 通信；跨机器接真机需要额外明确路由、发现方式、
QoS、时间同步、图像帧龄和断线行为，不能假设 bridge 自动覆盖局域网。
`ROS_DOMAIN_ID` 是发现隔离参数，不是认证或授权机制。

不要因为容器互通就让 OpenClaw/编码 Agent 加入 robot network。
进程 hook、SKILL.md 的“禁止裸 ROS”提示不是操作系统安全边界；
应在受控 Gateway、凭证、网络和必要的 DDS 安全策略上落实权限。
软件 safety_guard 不替代物理急停、看门狗和经过风险评估的真机保护。

Compose secrets 也不是自动加密的密钥保险库；应用必须真正支持读取相应文件，
密钥源、备份和访问权限另行管理。不能把真实 token 写入 YAML、镜像或测试报告。

### 5.3 Spark 资源调度

起步只允许一个重 GPU job：策略推理、训练、GPU CI 三者排队。
真实机器人关键时段暂停后台训练和不受控本地 LLM 请求，优先保证控制 deadline。
CPU/内存/PID/日志限制写入 Compose；共享内存使用独立 `shm_size`，不默认 `ipc: host`。

**`mem_limit` 和 GPU 设备授权不能证明 GPU 内存被硬隔离。**
统一内存使用必须结合实际模型测量、准入控制与故障测试。
先用 20%-30% 容量余量作为规划起点，实际余量以峰值和目标并发验证为准，
不把它当硬件保证或安全阈值。

## 6. OpenClaw 是否有必要本地部署

| 诉求 | 建议 |
| --- | --- |
| 先让 IB_Robot 仿真、技能或 ACT 跑通 | 不需要，优先当前 Hermes/Gateway 或确定性测试入口 |
| AI 编码、生成测试、PR review | 不需要换入口；复用现有编码 Agent + Skills + CI |
| 飞书/QQ 等远程交互、日报、事件通知 | 可部署独立 OpenClaw Compose profile，先只读 |
| 敏感代码和数据不出网 | 需要同时评估模型端点、工具、遥测与消息渠道；仅本地 Gateway 不足够 |
| 多个互不信任团队共同使用 | 不共用一个高权限 Gateway；按信任边界分实例与凭证 |
| 自动改生产、部署、控制机械臂 | 不授予通用 shell 或直通权限，进入受控执行器与审批门禁 |

OpenClaw 官方区分 Docker 中运行 Gateway 与工具 sandbox，
并明确其主要信任模型是 personal assistant，而不是任意敌对多租户隔离。[S9-S10]
网关本地部署与大模型本地推理是两个决策，不能混为一谈。

建议权限递进为：查询状态 -> 创建草稿工作项 -> 提交受限 PR -> 申请发布。
发布审批绑定具体 commit、镜像/model digest、环境、动作和有效期，不接受笼统“同意自动化”。
机器人运动另设人工授权和现场保护；Agent 内部 `confirm-plan` 不应被当成人类审批证据。

## 7. 项目到运维的统一研发体系

建议先选一个小产品切片，例如“在固定工位完成一个经批准的 SO-101 技能任务”。
先定义物体、场景、权限、失败退出与验收方法，不同时承诺导航、开放世界抓取和通用助手。

| 环节 | 必须产物 | 可自动化工作 | 必须门禁 |
| --- | --- | --- | --- |
| 项目 | 里程碑、负责人、依赖、风险、WIP 上限 | 状态汇总、风险提醒 | 每个里程碑绑定运行证据，不以文档数量记完成 |
| 产品 | PRD、用例、非目标、异常路径、验收场景 | 需求结构化、场景草稿 | 人确认业务价值、边界与可验收性 |
| 设计 | ADR、接口契约、机器人/模型/数据版本 | 影响分析、契约检查 | 控制与安全变更经过领域审查 |
| 研发 | 小 PR、明确 scope、关联 Issue | 编码、补测试、局部重构 | 有限重试；不自批、自合并或修改验收标准 |
| 测试 | 单元/契约/mock/GPU/SIL/HIL 证据 | 回归、重放、差异报告 | 验证目标 SHA；不可用与跳过不能算通过 |
| CI | 可重复镜像、测试、扫描、制品摘要 | 每个 PR 的确定性检查 | 必需检查失败即阻断；不只检查 commit message |
| CD | 版本清单、审批、预发、回滚点 | 拉取指定 digest、健康检查 | 不自动开启机器人运动，不由部署成功推断任务成功 |
| 运维 | 仪表盘、告警、runbook、复盘 | 只读诊断、证据归档、工单草稿 | 恢复/回滚分级授权，危险故障需要现场处置 |
| 数据/模型 | 数据集版本、标定、训练记录、评测和模型包 | 数据筛选、评测、受控候选训练 | 独立测试集、泄漏检查、模型发布审批 |

### 7.1 复用当前两个仓库

- `my-skills` 的 `spec-generator`、`execution-governor`、`code-review`、
  `verify-feedback`、`devops-engineer`、`ops-playbook` 可作为工作流规范源。
- IB_Robot 自带的环境、构建、推理验证、契约、patch、Git/PR Skills 作为项目专属执行说明。
- Hooks/Skills/Agent 角色不能替代必需 CI checks、分支保护或受控发布权限。
- 明确一个 Issue/PR 主系统；IB_Robot 已有 AtomGit/openEuler 协作约定，
  不因个人 GitHub fork 再建立第二套互相冲突的任务状态和审批记录。
- 遵守现有 DCO、AI 辅助贡献披露和人工审查要求；Agent 不能批量替代人提交未经审查的输出。

### 7.2 测试金字塔与 runner 分工

1. **PR 快检查**：Ruff、配置/schema、纯逻辑单测、patch fixture、敏感信息检查。
2. **ARM64 ROS 集成**：容器 clean build，`rclpy`/消息 ABI，mock launch、取消、幂等和失败关闭。
3. **GPU 合约检查**：GB10 算子、模型包加载、固定输入输出、精度差异、warm/cold latency 和峰值内存。
4. **SIL**：固定 seed/场景、图像与状态对齐、reset 后重复、任务成功与失败恢复。
5. **HIL**：有授权的设备映射、标定、限位、失联、重启、陈旧动作、急停与看门狗。
6. **发布候选 soak**：长时间运行、负载变化、资源泄漏、故障注入、升级和回滚后重新验收。

纯 CPU 与通用 x86_64 检查放普通 runner；Spark 承担受信 ARM64/GPU 验证。
不能把 QEMU 跨架构构建当成 GB10 执行验证；Docker 官方也提示其编译等任务可能显著更慢。[S11]
外部 PR 不应直接运行在持有机器人权限、生产凭证或长期挂载 Docker socket 的 Spark runner；
GitHub 官方明确提示 self-hosted runner 执行不受信代码的风险。[S12]

### 7.3 发布的是完整机器人系统

每份 release manifest 至少关联：

```text
requirement / issue
code commit + submodule commits + patch hashes
container image digests + platform + runtime dependencies
model artifact hashes + inference manifest + dataset version
robot config digest + calibration + skill catalog identity
test reports + deployment environment + approval + rollback target
```

不能只回滚容器却保留不兼容模型、技能清单或标定。
新版本启动后默认保持运动未授权，完成健康和兼容性验收后再由人授权。
数据库或状态格式变化要有迁移与恢复策略。

### 7.4 运维与数据闭环

优先监控：任务成功/失败及原因、p95/p99 端到端延迟、deadline miss、
观测帧龄、取消结果、安全拒绝、推理耗时、内存、队列等待、容器重启和数据写入失败。
“节点进程存在”不能代替“机器人任务可用”。

沿 Issue -> PR -> CI run -> release -> robot task -> model run 建立关联 ID。
指标用于告警，结构化日志/trace 用于定位；录制数据、图像和高频消息独立保存，
不把全部原始视频灌入监控系统。实验工具登记运行、参数、指标和制品，
继续以 IB_Robot 的 inference manifest 作为机器人执行接口的权威定义。

失败任务经过脱敏、人工确认和数据版本登记后进入回归集或训练候选集，
不能让 Agent 自动用失败现场数据训练后直接替换线上模型。

## 8. 如何真正提高效率

优先级从高到低：

1. **可重复环境**：固定基础 image digest、依赖约束、wheel 哈希、子模块和模型。
   Dockerfile 中缓存构建依赖；按架构/ROS/Python/CUDA 维度隔离 cache，避免错误复用。
2. **小任务与快反馈**：每个任务一个交付目标、独立 worktree、一个写入 Agent，
   可配一个独立审查者；先确定性测试，再申请昂贵 GPU/SIL/HIL。
3. **减少无效上下文**：项目规范、接口、相关源码与当前证据按需读取，不把所有历史对话反复发给模型。
4. **模型按任务分配**：敏感检索/摘要可试本地小模型；复杂架构、CUDA 排障、跨模块审查按数据政策选模型，
   用真实任务评测决定，不能因为可装入内存就选择最大模型。
5. **有界自动化**：设置重试次数、wall time、token/费用、工具权限和停止条件。
   无测试改进的重复修复应转人工，而不是循环“再试一次”。
6. **复用现有服务**：起步无需 Kubernetes、多个消息中间件或完整自建研发平台。
   单机 Compose 足以做开发验证，但不能据此宣称高可用；关键协作与备份不要只放在实验用 Spark 上。

DORA 2025 的公开结论强调 AI 会放大组织既有优势与问题，应同时改善底层研发系统，
不能仅靠工具投资获得收益。[S13] 这支持上述优先级，但不是本项目效率提升的实测证明。

先记录两周基线，再对比：从就绪需求到合入/发布的时间、CI 排队与首轮通过率、
人工审查耗时、返工、逃逸缺陷、故障恢复、任务成功率及每个验收交付的总成本。
不以 Agent 数量、生成代码行数或 token 消耗评价效率，也不承诺“提升十倍”。

## 9. 建议实施顺序与验收

以下是小团队的初步排期假设，不是已完成工作或交付承诺。

| 阶段 | 建议范围 | 退出条件 |
| --- | --- | --- |
| P0，先做 | 固定源码与镜像，运行本目录平台预检 | ARM64 ROS 与 GB10 CUDA 容器分别通过；记录证据和网络障碍 |
| P1，约第 1 周 | Jammy/Humble ARM64 builder + 最小 inference 依赖；纯逻辑与 ROS mock | 可从干净环境重建，核心契约/取消/失效保护通过 |
| P2，约第 2 周 | 单一 ACT 或单一确定性技能；一个仿真场景 | 模型真实加载与执行，重复场景、延迟和资源基线可复现 |
| P3，约第 3-4 周 | PR/CI、制品、审批、预发、监控、回滚，受控 HIL | 一份需求贯通发布与真实任务证据，故障和回滚演练通过 |
| P4，之后 | GraspGen、LIBERO ARM64、导航、多模型、本地 LLM、OpenClaw | 每个扩展独立 compatibility matrix，不破坏前述闭环 |

GraspGen 自定义算子、传感器驱动和真机条件可能成为关键路径，应单独估时。
先明确是否有 SO-101、相机、急停与授权操作人员；没有硬件时只能验收软件/SIL 层。

建议前五个工作项：

1. `spark-preflight`：CDI、ROS image digest、GPU 算子与日志归档。
2. `spark-inference-image`：上述候选 wheel、LeRobot 补丁与 ROS ABI 的容器内验证。
3. `core-sim-profile`：将现有 full/inference 安装范围扩成可验证的 core/sim/grasp 组合。
4. `arm64-ci-gates`：将现有测试真正连到受信 runner 和必需 PR 检查。
5. `vertical-slice-release`：一个场景、一份 release manifest、一次故障恢复与回滚。

## 10. 已提供的 Compose 预检模板

文件：[compose.preflight.yaml](compose.preflight.yaml)。

仅提供两个一次性容器：`ros-probe` 和 `gpu-probe`。
均显式 ARM64、非 root、只读 rootfs、无容器网络、无主机目录挂载、无端口、
无数据卷、无特权、无 Docker socket；GPU probe 仅额外获准访问 GPU。
执行 matrix kernel 不会控制机器人，但会短暂使用 GPU。

从本目录执行配置校验，不下载镜像、不启动容器：

```bash
docker compose -f compose.preflight.yaml --profile "*" config --quiet
```

以下命令是**后续执行步骤，本次未执行**。首次运行可能拉取较大镜像并写入 Docker image store：

```bash
docker compose -f compose.preflight.yaml --profile ros-check run --rm ros-probe
docker compose -f compose.preflight.yaml --profile gpu-check run --rm gpu-probe
```

ROS 标签目前作为预检默认值保留。仓库可达后，通过
`docker buildx imagetools inspect ros:humble-ros-core-jammy`
取得 digest，并使用 `ROS_PROBE_IMAGE=ros:humble-ros-core-jammy@sha256:...` 固定真实值。
不要原样使用带省略号的占位值。业务 release 禁止未锁定标签。

如 CDI/驱动、镜像网络、容器权限或 kernel 验证失败，保留原始错误作为 P0 证据，
不要自动降级 CPU、切换 amd64、增加 privileged 或修改宿主机来掩盖失败。
两个 probe 即使都通过，也仍未验证 IB_Robot 编译、业务模型、ROS 跨容器通信、物理仿真或 HIL。

本轮配置校验结果：待静态校验后记录；运行验证未执行。

## 11. 一手资料索引

外部网页为 2026-09-13 检索时的动态内容；源码判断以上述固定 SHA 为准。
软件包和镜像索引的“存在”与下载、加载、性能验证严格区分。

| 编号 | 来源与用途 | 地址 |
| --- | --- | --- |
| S1 | NVIDIA Spark 硬件与统一内存 | `https://docs.nvidia.com/dgx/dgx-spark/hardware.html` |
| S2 | NVIDIA CUDA GPU compute capability | `https://developer.nvidia.com/cuda-gpus` |
| S3 | NVIDIA PyTorch 25.09 容器 OS/Python/CUDA 基线 | `https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/rel-25-09.html` |
| S4 | NVIDIA Spark 软件栈 | `https://docs.nvidia.com/dgx/dgx-spark/software.html` |
| S5 | Docker Compose services，devices/CDI 与隔离参数 | `https://docs.docker.com/reference/compose-file/services/` |
| S6 | NVIDIA Container Toolkit CDI | `https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html` |
| S7 | PyTorch 官方 CUDA 13.0 wheel 索引 | `https://download.pytorch.org/whl/cu130/torch/`；`https://download.pytorch.org/whl/cu130/torchvision/`；`https://download.pytorch.org/whl/cu130/torchaudio/` |
| S8 | Docker 官方 ROS 镜像声明与支持架构 | `https://raw.githubusercontent.com/docker-library/official-images/master/library/ros` |
| S9 | OpenClaw Docker 部署与 sandbox 边界 | `https://docs.openclaw.ai/install/docker` |
| S10 | OpenClaw 安全与信任边界 | `https://docs.openclaw.ai/gateway/security` |
| S11 | Docker 多架构构建与 QEMU 限制 | `https://docs.docker.com/build/building/multi-platform/` |
| S12 | GitHub Actions 安全与 self-hosted runner | `https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions` |
| S13 | DORA 2025 AI 辅助研发报告公开摘要 | `https://dora.dev/research/2025/dora-report/` |
| R1 | 被评估的源码快照 | `https://github.com/gottaBoy/IB_Robot/tree/3c0cd3586576d79127135247288ded1ee9cd5d47` |

未验证或本次受限：完整子模块/模型可获取性、ROS Docker Hub manifest 查询超时、
业务依赖解析和构建、容器实际启动、GPU 扩展、SIL、HIL、外部 Jenkins 门禁实际配置。
