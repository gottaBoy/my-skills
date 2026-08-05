# ziot / ziot-web 接入 Casdoor 分析

> 分析日期：2026-08-03
> 状态：仅记录方案，未修改 `jetlinks-community` 或 `zeron-cloud-web` 业务代码。
> 项目映射：`ziot = jetlinks-community`，`ziot-web = zeron-cloud-web`。

## 1. 直接结论

### 1.1 能否无缝接入

可以，但“无缝”只适用于**身份认证体验**，不意味着把 JetLinks 的权限数据库迁移到 Casdoor。

- Casdoor 作为 OIDC Identity Provider，负责统一登录、注销、用户身份和组织级分组。
- JetLinks 继续负责本地用户、角色、维度、菜单和按钮权限，并在每个 API 上做最终授权。
- Casdoor 的 `sub` 与 JetLinks 本地用户建立绑定；邮箱、用户名、昵称只能用于展示或首次建档，不能作为稳定主键。
- 车辆 DDI、设备证书、API Key、网关 token、服务间 token 不属于人员 SSO 范围，继续使用现有认证边界。

因此，已有的用户权限体系可以保留，改造重点是“Casdoor 身份 -> JetLinks 本地用户/会话”的适配，而不是重做权限系统。

### 1.2 Casdoor UI 能否重构

可以完全重构 `ziot-web` 自己的登录页面，但不建议在 SPA 内重新收集 Casdoor 用户名和密码。

推荐的体验是：

1. `zeron-cloud-web` 显示自有品牌、背景、错误态和“统一登录”按钮。
2. 点击后跳转 JetLinks 后端的 OIDC 登录入口，由后端重定向到 Casdoor。
3. Casdoor 完成密码、多因素和账号策略；回调回 JetLinks 后端。
4. JetLinks 建立本地会话后回到自有前端，用户感觉仍是一个完整的 ziot 登录页。

这样可以保留 ziot 的视觉设计，同时避免复制 Casdoor 登录逻辑、密码接口和安全策略。Casdoor Hosted UI 仍可配置 logo、主题和语言作为兜底，但不应把 Casdoor 页面组件嵌入业务页面。

### 1.3 Authing 兼容方式

JetLinks 登录桥应实现为通用 OIDC bridge，通过 `provider=casdoor|authing`、issuer discovery 和 claim mapping 配置切换，不应把核心类命名为 Casdoor 专用实现。绑定记录的 `provider` 保存实际 provider，稳定关联仍使用该 provider 下的 `sub`。同一环境优先选一个 issuer；需要同时显示两个入口时由 broker/BFF 统一下游 token。完整跨项目方案见 `zota-unified-identity-ui-analysis.md`。

## 2. `zeron-cloud-web` 当前实际链路

### 2.1 技术和代码结构

- Vue 3、TypeScript、Vite、pnpm、Pinia、Ant Design Vue，以及 `@jetlinks-web/*` 公共包。
- 使用 `createWebHashHistory`，登录路由和服务端菜单动态路由并存。
- 业务按模块组织：认证管理、设备管理、并行驾驶、规则引擎等模块各自提供菜单、路由和 API。
- 当前前端仓库分支为 `master`，工作区已有用户修改：`vite.config.ts`；另有未跟踪 `pnpm-lock.yaml`，后续操作不得覆盖。

### 2.2 登录、会话和路由

关键事实：

- `src/views/login/right.vue` 的账号密码表单调用 `POST /authorize/login`，成功后执行 `setToken(res.result.token)`，再跳转首页。
- `@jetlinks-web/utils` 的 `setToken/getToken/removeToken` 实际通过 `localStorage` 读写 `VITE_STORE_TOKEN_KEY || VITE_TOKEN_KEY`；当前配置是 `X-Access-Token`。
- `src/router/index.ts` 的 `beforeEach` 只检查 token 是否存在。存在时调用 `/user/detail`，查询版本、系统信息、应用列表和服务端菜单；不存在时跳转 `/login`。
- `src/App.vue` 支持从 URL 查询参数 `?token=` 写入本地 token。这是历史兼容入口，不能直接用于 Casdoor 回调。
- `src/layout/components/User.vue` 调用 `GET /user-token/reset` 退出，然后清理本地 token 并跳转登录页。
- `src/views/relogin/index.vue` 复用账号密码 `Right` 组件做重新登录，并依赖当前用户名相同来恢复部分 WebSocket 状态。

这说明前端不是“登录页独立、权限另算”，而是 token、用户信息、菜单、动态路由、按钮权限和微前端初始化组成一条启动链。只替换一个按钮而不处理回调和会话恢复，会导致白屏、菜单未加载或 WebSocket 断开。

### 2.3 权限模型

- `src/store/menu.ts` 调用后端菜单查询，使用返回的菜单树生成动态路由和侧边栏。
- 同一菜单树交给 `src/store/auth.ts`，转换为 `Record<menuCode, buttonIds[]>`。
- 页面按钮使用 `menuCode:buttonCode` 检查权限，例如 `device/Product:update`。
- `src/store/user.ts` 仍以 `username === 'admin'` 判断管理员，并保存 `username` 到 `localStorage`；这属于迁移时需要收敛的旧假设。

结论是：Casdoor role/group 不应直接成为 Vue 的按钮权限。后端仍应返回 JetLinks 计算后的菜单树，前端只负责展示和体验层隐藏。

### 2.4 需要纳入统一会话适配器的遗留入口

当前源码中除 Axios 请求头外，还存在：

- 文件下载 URL 拼接 `X_Access_Token` 查询参数。
- WebSocket URL 或连接参数读取 `getToken()`。
- 子应用跳转 URL 携带 `token`。
- `window.open('/application/sso/.../login')` 和 `window.onstorage` 的旧第三方登录回调。

这些入口不能各自读取 Casdoor access token。应统一改为 `authSession.getAccessToken()`，并优先改成同源 cookie、短期一次性票据或 WebSocket CONNECT token。

## 3. 推荐认证架构

### 3.1 第一阶段：JetLinks OIDC 登录桥（推荐）

```text
ziot-web 自有登录页
        |
        | GET /authorize/casdoor?returnTo=...
        v
JetLinks 生成 state/nonce/PKCE -> Casdoor
        |
        | authorization code
        v
JetLinks 后端 confidential client
  校验 issuer/audience/nonce/signature/exp
  Casdoor sub -> 本地 UserEntity
  写入 ThirdPartyUserBindEntity
  同步/映射本地角色与维度
  签发现有 hsweb UserToken 或建立 HttpOnly 会话
        |
        v
ziot-web 恢复现有 /user/detail、/authorize/me、菜单和按钮权限
```

推荐的兼容回调方式是后端生成一次性 login ticket，前端回调页用 ticket 换取现有 JetLinks session token；不要把长期 token 放到 `?token=`。更高安全等级的实现是后端 HttpOnly、Secure、SameSite cookie，并让前端请求开启 credentials，从而逐步淘汰 localStorage token。

### 3.2 用户绑定和权限同步规则

首次登录必须预先确定以下策略，不能在代码中隐式决定：

- **预置绑定**：只有已在 JetLinks 绑定的 Casdoor `sub` 才能登录，适合生产初期。
- **登录时建档（JIT）**：首次登录创建本地用户，默认最低权限，待管理员审批或映射分组。
- **角色映射**：Casdoor `groups/roles` 只作为输入，经过显式 allow-list 映射到 JetLinks 本地角色、维度和权限；默认拒绝。
- **禁用处理**：Casdoor 用户被禁用时拒绝新登录；本地会话按短 TTL 到期，必要时通过回调/同步任务提前下线。
- **稳定主键**：绑定表使用 `provider=casdoor`、`type=oidc`、`thirdPartyUserId=sub`，禁止使用 email 作为关联键。

`ThirdPartyUserBindEntity` 已具备保存这类关系的字段，建议复用现有 `ThirdPartyUserBindService`，不要另建一套 Casdoor 用户表。

### 3.3 为什么不建议第一阶段直接接 Casdoor JWT

JetLinks 使用 hsweb v5 的 `ReactiveUserTokenParser`、`UserTokenManager` 和响应式授权事件，不是 Spring Security Resource Server。直接接入 JWT 需要同时解决 parser 顺序、JWKS 缓存和轮换、用户创建、权限装载、本地 token 撤销，以及 API Key 与 Bearer token 的兼容。登录桥只改变入口，风险和回滚范围更小。

无状态 Casdoor JWT 资源服务器可以作为第二阶段，用于确实需要跨服务直接验证用户 token 的 API；实施前必须先完成 claim、audience 和权限适配器。

## 4. `ziot-web` 统一前端改造方案

### 4.1 认证模式和接口

新增框架无关的认证契约，Vue 和 React 应用分别实现适配器：

```ts
interface AuthSession {
  login(returnTo?: string): Promise<void>
  handleCallback(): Promise<void>
  getAccessToken(): string | undefined
  getUser(): Promise<NormalizedUser>
  logout(scope: 'current' | 'all'): Promise<void>
  can(permission: string): boolean
}
```

`zeron-cloud-web` 第一阶段仍由 JetLinks session token 驱动，`zota-repo-web` 和 `zota-web` 可使用 Authorization Code + PKCE。三者共享接口和配置 schema，不强行把 Vue 工程与 React 工程合并成一个仓库。

### 4.2 登录页重构边界

- 保留 `src/views/login/index.vue` 的品牌背景、备案信息和系统配置能力。
- 将 `Right` 的账号密码表单替换为自有 SSO 状态页和“统一登录”按钮。
- 回调、加载、失败、取消、会话过期和无权限均使用现有 i18n 和 Ant Design Vue 组件。
- 旧账号密码登录保留为 staging/hybrid 或受限 break-glass 入口，不在生产主流程中显示。
- 现有 `bindings` 第三方登录可在迁移期保留，但 Casdoor 使用独立且明确的 `/authorize/casdoor` 路由，避免依赖旧 `window.onstorage` 机制。

### 4.3 请求和权限改造

- 在 `@jetlinks-web/core` 请求层接入 session adapter；业务 API 不再直接调用 `getToken()`。
- 401 只触发一次会话恢复或重新登录；403 保留当前页面并展示无权限状态；网络错误不清理会话。
- `/user/detail`、`/authorize/me` 和服务端菜单仍是用户和权限的来源；Casdoor claim 不能绕过后端菜单权限。
- 下载、WebSocket、微前端和 iframe 入口改为 cookie/短期票据/显式 CONNECT token，禁止长期 token 出现在 URL、日志和浏览器历史中。
- 去除 `username === 'admin'` 作为唯一管理员判定，改为后端返回的系统权限或角色能力。

### 4.4 退出和重新登录

- “退出当前应用”：注销 JetLinks 本地 session，清空前端会话并回到自有登录页。
- “退出全部应用”：在本地注销后跳转 Casdoor end-session；需要统一 post-logout redirect allow-list。
- `relogin` 不再收集 Casdoor 密码；改为重新发起 OIDC，或由后端检查当前会话是否仍有效。
- 多标签页使用 BroadcastChannel 或受控 storage event 同步退出，不能把 access token 本身当作同步载体。

## 5. 是否需要单独创建分支

需要按仓库分别创建分支，不能用一个 Git 分支覆盖所有项目。当前工作区是多个独立 Git 仓库：

| 仓库 | 当前状态 | 建议分支 |
|---|---|---|
| `.github` | `main`，分析文档未跟踪 | `docs/ziot-casdoor-analysis` |
| `jetlinks-community` | `mydev`，已有多份配置修改和未跟踪集群文件 | `feat/ziot-generic-oidc-bridge` |
| `zeron-cloud-web` | `master`，`vite.config.ts` 已修改，lockfile 未跟踪 | `feat/ziot-casdoor-sso` |
| Casdoor/部署配置（如独立仓库） | 以实际仓库为准 | `chore/casdoor-ziot-apps` |

分支前先保存或确认现有工作区改动，不能用切换分支、清理命令覆盖用户文件。建议以同一份 claim/回调/角色映射契约作为多个仓库 PR 的依赖，而不是创建跨仓库分支。

## 6. 分阶段、可回滚实施

### Phase 0：契约和安全阻塞项

- 固定 Casdoor issuer、三个应用的 audience、回调地址、end-session 地址和 claim 结构。
- 撤销浏览器源码中可能存在的 client secret，按环境重新生成并只放服务端 Secret。
- 决定预置绑定还是 JIT 建档，写清楚 Casdoor 分组到 JetLinks 角色/维度的 allow-list。
- 为 `/authorize/casdoor`、callback、ticket exchange、登出和错误码补 API 契约。

### Phase 1：双模式灰度

- JetLinks 后端增加 OIDC bridge；保留本地登录作为 `local`，Casdoor 作为 `casdoor`，默认 staging 使用 `hybrid`。
- `zeron-cloud-web` 先增加 SSO 按钮和回调页，再迁移 Axios、下载、WebSocket、微前端等 token 入口。
- 菜单、按钮、角色管理页面暂不重构，继续验证现有本地权限是否正确映射。

### Phase 2：生产切换

- Casdoor 成为默认登录入口，账号密码仅保留受控 break-glass 管理员通道并记录审计。
- 逐步使用 HttpOnly cookie，关闭 URL token 和不受控 localStorage token。
- 完成三套 UI 的统一 401/403、登出、会话过期和跨标签页行为。

### 回滚条件

出现 Casdoor 不可用、角色映射错误、回调循环、WebSocket/文件下载大面积失败时，将登录模式切回 `local`，保留本地用户和权限数据不动；回滚不应删除第三方绑定记录。

## 7. 验收重点和主要风险

至少验收：

- 同一 Casdoor 用户进入 ziot、zota-repo、zota-server 不再重复输入密码。
- 错误 `iss/aud/sub`、过期 token、禁用用户均被后端拒绝，前端分别处理 401/403。
- JetLinks 原有菜单、按钮、数据维度权限不因 SSO 登录而扩大；viewer 调用写 API 必须返回 403。
- Casdoor 密钥轮换、退出全部应用、回调重复提交、刷新页面和多个标签页行为可恢复。
- 车辆 DDI、API Key、网关 token 和服务间调用不受人员 SSO 改造影响。

主要风险：SPA token 继续落入 localStorage 或 URL、Casdoor role object 与本地字符串角色不兼容、直接替换 hsweb Bearer parser 造成 API Key/本地 session 回归、以及把前端隐藏菜单误当成后端授权。上述事项在进入实施阶段前必须有测试和回滚开关。

## 8. 当前阶段结论

当前只完成代码分析和方案记录，不建议马上同时重构三个前端。最稳妥的顺序是：先在 `jetlinks-community` 做 OIDC 登录桥和权限映射契约，再在 `zeron-cloud-web` 替换登录入口并收口 token 使用，最后把同一认证接口推广到 zota-repo/zota-server 前端。
