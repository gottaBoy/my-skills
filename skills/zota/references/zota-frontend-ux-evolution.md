# ZOTA 前端用户体验演进方案

> 分析日期：2026-08-03
> 状态：方案记录，尚未修改业务代码。
> 关联文档：`zota-unified-identity-ui-analysis.md`、`ziot-casdoor-web-analysis.md`。

## 1. 结论：从哪个项目开始

### 1.1 实际代码首选 `hawkbit-updater-ui`

如果目标是提升整个 ZOTA/ZIOT 平台的用户体验，建议把 **zota-web（`hawkbit-updater-ui`）作为第一个 UX 业务试点**。

原因：

- 它承载 Target、Distribution、Action、Rollout、配置等核心 OTA 运维流程，能真实验证信息架构和交互是否有效。
- React 19、Ant Design 6、TanStack Query、Zustand、Vitest 基础较新，适合建立第一版设计令牌和 React 组件模式。
- 与 `zota-repo-web` 技术栈高度接近，试点成功后可以低成本复用到第二个 React 前端。
- 当前应用可以独立部署，适合通过 feature flag 和 standalone 模式灰度，不需要先改变整个 ziot 门户。
- 当前 Basic 登录、两级角色和 `isAdmin` 判断是明确问题，修正后可以建立正确的登录、权限和错误体验基线。

### 1.2 实施前置是 `hawkbit`，但它不是 UX 试点

`hawkbit-updater-ui` 要正确显示菜单、按钮和无权限状态，必须依赖 zota-server 返回真实用户和 permissions。因此首个业务 UI PR 之前，需要先在 `hawkbit` 完成最小认证前置：

- provider-neutral OIDC Resource Server。
- issuer/audience 校验。
- group/role 到 `SpPermission` 的映射。
- `/rest/v1/userinfo` 稳定返回 username、tenant、permissions，必要时增加 subject 和 display name。

顺序是“`hawkbit` 做认证底座 -> `hawkbit-updater-ui` 做首个 UX 试点”，而不是在后端项目里做 UI。

## 2. 为什么不先从其他前端开始

| 项目 | 优势 | 不作为首个试点的原因 | 推荐顺序 |
|---|---|---|---|
| `hawkbit-updater-ui` | OTA 核心流程、React 19、Ant Design 6、已有测试和模式组件 | 需要先修正认证和 permission | 第 1 个 |
| `zota-repo-web` | 发布、审批、版本和合规流程完整，与 zota-web 技术栈接近 | 当前 Casdoor 实现和 token 安全需要先收口；业务面较广 | 第 2 个 |
| `zeron-cloud-web` | 用户、菜单、按钮、微前端和门户能力完整 | 与 JetLinks token、菜单、WebSocket 强耦合，改动影响所有 ziot 用户 | 第 3 个，作为门户壳 |
| `jetlinks-community` 管理 UI 模块 | 权限和设备管理完整 | 页面量大、模块多，不适合用来探索第一版设计系统 | 门户稳定后分模块迁移 |

不建议先对 `zeron-cloud-web` 做大规模换肤。子应用尚未提供 embedded 模式、统一认证和统一 token 安全边界时，先改壳只会得到双导航、风格拼接和跨应用会话问题。

## 3. UX 目标不是“换皮”

平台面向 OTA 发布、车队运维和故障处置，体验目标应围绕任务完成效率：

1. 用户无需理解功能属于哪个后端系统。
2. 用户能从车辆、软件、发布或失败事件进入同一上下文。
3. 危险操作前能看到影响范围、风险、审批和回滚条件。
4. 长任务有进度、阶段、失败原因、重试和审计入口。
5. 权限不足、网络错误、服务降级和数据过期不会被混为一种错误。

视觉采用安静、紧凑、工作导向的运营平台风格。减少装饰渐变、大圆角卡片、玻璃背景和纯展示型 Dashboard，把空间留给表格、状态、筛选、批量操作和异常信息。

## 4. 首个试点范围

不要第一批重构全部页面。建议在 `hawkbit-updater-ui` 选择两个端到端工作流。

### 4.1 工作流 A：Rollout 创建与监控

目标流程：

```text
选择发布内容
  -> 选择目标范围
  -> 兼容性与影响检查
  -> 设置灰度/失败阈值/维护窗口
  -> 审核摘要
  -> 提交执行
  -> 阶段进度与失败处置
  -> 暂停/继续/回滚/审计
```

重点改进：

- 把分散字段组织成有状态的步骤流程，支持草稿恢复。
- 提交前显示车辆数量、车型、版本变化、在线率、风险项和回滚能力。
- 默认值来自组织策略，危险选项必须显式确认。
- 执行页使用阶段时间线、状态分组和失败原因聚合，不只展示百分比。
- 暂停、取消、强制和回滚按钮按真实 permissions 和 rollout 状态显示。

### 4.2 工作流 B：单车升级失败处置

目标流程：

```text
搜索 VIN/设备
  -> 当前版本与期望版本
  -> 最近 Action/Rollout
  -> 失败阶段与原始反馈
  -> 关联日志/诊断
  -> 重试、重新分配或回滚
  -> 记录处理结果
```

重点改进：

- 全局搜索直接进入车辆详情，不要求用户先找到正确菜单。
- 页面固定显示环境、VIN、车型、当前版本、目标版本和连接状态。
- 错误信息包含原因、影响、建议动作和技术详情展开区。
- 所有跳转保留车辆上下文和返回位置。
- 将 WebSocket 实时状态与 polling 降级状态明确展示。

这两个流程分别覆盖“计划性发布”和“异常处置”，足以验证设计系统是否适合真实操作。

## 5. 第一版 UX 基础设施

### 5.1 设计令牌

先在 `hawkbit-updater-ui` 建立可导出的 token schema，不立刻抽象大型公共组件库：

```text
src/design-system/
  tokens.ts
  css-variables.css
  antd-theme.ts
  status-semantics.ts
```

稳定后再抽取为独立 `@zeron/design-tokens`。这样可以先通过真实页面验证密度、间距和状态语义，避免过早固定错误抽象。

第一版至少统一：

- 4/6/8px radius。
- 紧凑和舒适两种 density。
- 字号、行高、间距、层级和内容最大宽度。
- success、warning、danger、info、offline、stale、running、paused、rollback 状态。
- 表格、表单、工具栏、页头、弹窗、抽屉和通知的 token 映射。

### 5.2 基础体验组件

优先实现或收敛：

- `PageHeader`：标题、上下文、状态和页面主操作。
- `FilterBar`：搜索、条件、保存视图、清空和结果计数。
- `DataTable`：稳定列宽、批量选择、密度、空态和错误态。
- `PermissionAction`：权限、禁用原因、危险级别和审计提示。
- `StatusTag`：统一状态文案、颜色和图标。
- `AsyncState`：loading、empty、error、offline、stale 和 retry。
- `TaskProgress`：长任务阶段、进度、日志、重试和取消。

React 组件在 `zota-repo-web` 出现第二个真实消费者后，再抽取 `@zeron/react-ui`，避免公共包只服务一个项目。

### 5.3 页面壳模式

`hawkbit-updater-ui` 从第一阶段就支持：

- `standalone`：完整 header、导航和用户菜单，便于独立部署与回滚。
- `embedded`：隐藏内部 header/footer，由统一门户提供导航和主题。

embedded 模式只接收 locale、theme、density、display user 和 navigation context，不接收长期 access token。

## 6. 分阶段实施

### Phase U0：研究与基线

- 定义三类核心用户：发布管理员、车队运维、审计/只读用户。
- 记录 Rollout 创建和故障处置的当前步骤、页面跳转、耗时和常见失败。
- 定义统一信息架构、状态词典、permission 展示规则和设计 token。
- 保存关键页面桌面/小屏基线截图，建立可对比的验收样本。

### Phase U1：认证与全局状态

- 完成 HawkBit OIDC 和 `/userinfo.permissions`。
- 前端删除 Basic credential 持久化和用户名推断角色。
- 统一登录、回调、会话恢复、401、403、网络错误和服务降级页面。
- 增加 `can/canAll/canAny` 并逐步替换 `isAdmin`。

### Phase U2：zota-web UX 试点

- 落地 token、基础体验组件和 embedded 模式。
- 重构 Rollout 创建与监控。
- 重构单车失败处置。
- 保留旧页面 feature flag，允许按用户或环境灰度。

### Phase U3：复用到 zota-repo-web

- 抽取稳定的 design tokens 和 React 组件。
- 统一发布、审批、兼容性、下发和审计页面。
- 串联“版本准备 -> 审批 -> 下发 -> Rollout -> 结果”的跨系统深链接。

### Phase U4：统一门户

- `zeron-cloud-web` 演进为 portal shell，统一导航、主题、语言、用户菜单和全局任务中心。
- 接入两个 React embedded 子应用。
- 清理微前端 token 传递，使用同源 BFF cookie 或子应用独立 session 恢复。
- 再将设计 token 映射到 Ant Design Vue，逐步替换 ziot 模块页面。

### Phase U5：平台级体验

- 全局 VIN、设备、版本、发布和 Rollout 搜索。
- 跨应用任务中心、通知中心和审计时间线。
- 保存视图、批量操作、快捷命令和个人密度偏好。
- 无障碍、键盘操作、小屏应急查看和性能治理。

## 7. 首批分支与 PR

当前工作区已有用户修改，不立即切换分支。确认改动归属后建议：

| 仓库 | 分支 | 首批内容 |
|---|---|---|
| `.github` | `docs/zota-frontend-ux-evolution` | UX 基线、状态词典、流程和验收 |
| `hawkbit` | `feat/zota-oidc-resource-server` | OIDC、permission mapping、userinfo |
| `hawkbit-updater-ui` | `feat/zota-ux-foundation` | auth session、tokens、基础组件、embedded mode |
| `hawkbit-updater-ui` | `feat/zota-rollout-ux-pilot` | Rollout 与故障处置试点 |
| `zota-repo-web` | `feat/zota-shared-ux` | 第二消费者和 React 组件抽取 |
| `zeron-cloud-web` | `feat/zeron-portal-experience` | 门户聚合与 Vue token adapter |

不要把认证改造、两个完整工作流、门户接入和全量换肤放进一个 PR。

## 8. 验收指标

视觉一致只是验收的一部分，至少记录：

- 创建一次标准 Rollout 的完成时间、步骤数和返回修改次数。
- 从失败告警定位到具体原因和可执行动作的时间。
- 全局搜索成功率和进入正确详情页的点击数。
- 401/403、网络错误和服务降级造成的无效重试次数。
- 批量任务成功率、取消率、重试率和回滚耗时。
- permission 导致的死路、隐藏操作和误报管理员数量。
- 页面加载、表格交互、WebSocket 降级和错误恢复时间。
- 键盘可操作性、焦点顺序、颜色对比度和 200% 缩放可用性。

## 9. 最终建议

方案从文档和状态契约开始，但首个可见 UX 成果应落在 `hawkbit-updater-ui`。它既代表 ZOTA 最核心的运营工作流，又能为 `zota-repo-web` 提供可复用的 React 基线。`zeron-cloud-web` 应在子应用具备安全 session、embedded 模式和稳定设计 token 后再升级为统一门户壳，而不是成为第一轮全量重构现场。
