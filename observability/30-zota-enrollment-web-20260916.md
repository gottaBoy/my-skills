# Enrollment 前端管理与永久令牌

日期：2026-09-16。

本轮补齐 `zota-web` 登记令牌管理界面及所需查询接口，沿用现有 admin 账号。
未引入用户/角色管理页面、未接入 Casdoor、未修改 Agent 的单 config.yaml 流程。
没有发布或修改线上配置。

## 前端入口与操作

入口：右上角用户菜单的“登记令牌”，路由 `/system/enrollments`。
菜单只在服务端启用模块且当前用户有管理能力时显示。直接进入路由也会重新
校验能力，不依赖前端把用户名映射为 Admin 的旧逻辑。

功能：

- 分页展示 ID、创建人、创建/到期/撤销时间、有效/过期/撤销状态。
- 分别展示 `pendingCount` 和 `confirmedCount`，后者才是“已使用”数量。
- 按令牌状态筛选，手动刷新和页面内定期刷新。
- 创建令牌，明文仅显示在本次成功弹窗，支持复制 token 或 Agent 配置片段。
- 查看该 token 的关联 VIN、租户、换取时间、确认时间和登记状态，支持精确查询。
- 撤销需确认，已撤销项不可重复点击；撤销不会删除历史登记或正式凭证。
- 区分模块未启用/旧后端不支持、权限不足、接口异常、空数据和加载状态。
- 中文/英文及桌面/移动端布局。

没有提供“再次查看旧 enrollment token 明文”、target token 下载、
删除已确认登记或重置车辆入口，避免绕过原来的永久登记规则。

## 不选过期就是永久

创建弹窗默认关闭“设置有效期”：

```http
POST /rest/v1/enrollments
Content-Type: application/json

{}
```

也接受 `{"expiresInDays":null}`，两者都返回 `expiresAt:null`。
开启“设置有效期”后可填写 1 至 3650 天，仍兼容原 `{"expiresInDays":30}`。
0、负数和超过 3650 的值不代表永久，会返回 400。

数据库用 SQL NULL 表示永久：

- 未撤销且 `expires_at IS NULL`：有效，不会自然到期。
- 未撤销且指定到期时间已到：过期。
- `revoked_at` 非空：撤销优先，不论是否设置了到期时间。

永久 token 仍可撤销，不意味着不可管理或可绕过 VIN 的登记次数限制。
一个 token 可以给多辆车使用，每辆车只有正式 token 认证确认后才计为已使用。

新增迁移：

```text
V1_26_1__enrollment_optional_expiry__H2.sql
V1_26_1__enrollment_optional_expiry__MYSQL.sql
V1_26_1__enrollment_optional_expiry__POSTGRESQL.sql
```

只允许 enrollment 表的 `expires_at` 为空，不改旧 target 凭证，
不把旧的限时 token 批量转成永久，也不改写 V1_26_0 迁移内容。
该迁移仍会随升级运行，不取决于 enrollment 功能开关。

## 现有 admin 和未来统一身份

沿用现有 admin 账号，保持角色不变，追加一项权限：

```properties
zota.security.user.admin.roles=TENANT_ADMIN
zota.security.user.admin.permissions=ENROLLMENT_ADMIN
```

仓库默认 application.properties 已追加 permission。这里不能将
`ENROLLMENT_ADMIN` 加到 roles 后就认为生效：静态认证器给 roles 自动加
`ROLE_` 前缀，而新接口校验的是原样的 `ENROLLMENT_ADMIN` authority。

无需新建账号或现在搭建完整权限系统。管理端创建、撤销、列表和 VIN 查询均由
后端校验这项权限。未来切换统一身份时可在后端身份映射中授予同一 authority，
前端继续只读取能力结果。此次没有改变现有 Basic 登录或提前实现 Casdoor 对接。

若部署环境覆盖了 admin 的权限配置，需同步追加该项，不能仅更新前端。

## 接口

| 接口 | 权限与作用 |
|---|---|
| `GET /rest/v1/enrollments/capabilities` | 已登录用户；返回 enabled/canManage，不泄露完整权限表 |
| `GET /rest/v1/enrollments?page=0&size=20&status=ACTIVE` | 管理权限；分页 token 元数据，status 可省略 |
| `POST /rest/v1/enrollments` | 管理权限；创建，明文只返回一次 |
| `DELETE /rest/v1/enrollments/{id}` | 管理权限；撤销，重复调用保留首次撤销时间 |
| `GET /rest/v1/enrollments/{id}/issuances` | 管理权限；分页关联 VIN |

issuances 可带 `page`、`size`、`status=PENDING/CONFIRMED`、
`controllerId`、`tenant`。VIN/租户是精确匹配，租户转为大写；
省略筛选时返回该 token 下全部登记。跨租户记录仅供平台 enrollment 管理权限读取。

分页返回：

```json
{"content": [], "total": 0, "page": 0, "size": 20}
```

page 从 0 开始，size 为 1..100，顺序固定为 ID 倒序。
列表仅对本页 token IDs 分组统计登记数量，避免逐 token 逐车读取凭证。
查询 DTO 不包含 token 明文、token hash 或 target token 指纹。
响应禁用缓存；不存在的管理 ID 返回 404，不伪装成 401 导致管理用户退出登录。

模块仍默认关闭。关闭或旧服务没有 capability 接口时，前端将 404 显示为
未启用/未部署；503 或网络故障不是“未启用”，会显示错误并允许重试。

## 前端秘密处理

创建请求不使用 React Query mutation，避免把新令牌放进 mutation cache。
明文仅存在创建组件的内存 state，关闭组件即清除；切换登录会话时重新挂载，
退出后迟到的创建响应不会再次显示。

列表/能力查询按不含凭证的本地会话编号区分，不把 Basic token 放进 query key。
不会把 enrollment secret 写入 localStorage、URL 或通知消息。
用户主动复制到剪贴板的内容不会被应用擅自清除。

创建不自动重试：响应丢失时服务器可能已创建 token，前端会提示先查列表，
而不是悄悄创建第二个令牌。找不到原明文时只能撤销该 ID 并创建新的 token。

复制的 Agent 片段保持 [单配置方案 29](29-zota-enrollment-single-config-20260915.md)：

```yaml
zota:
  enrollment_token: "<shared-installation-token>"
```

这是待合入原配置的片段，不是带 URL/VIN 的完整配置，也不会创建额外凭证文件。
enrollment_token 与正式 token 不应同时配置。

## 验证

截至本轮，已执行：

| 验证 | 结果 |
|---|---|
| 前端完整 Vitest | 5 个文件、94 项通过，其中新增 15 项 |
| 新页面及改动文件 ESLint | 通过 |
| 前端 TypeScript/Vite 构建 | 通过；原有大 chunk 警告仍存在 |
| enrollment 服务单测 | 17 项通过 |
| 原设备 REST 单测 | 10 项通过 |
| 默认关闭测试 | 2 项通过 |
| 真实 JPA/H2/认证集成 | 12 项通过，包括查询、权限、计数、永久创建/撤销 |
| Flyway 空库/旧库/可空到期升级 | 3 项通过 |
| 服务端 starter 及依赖打包 | 通过 |

浏览器脚本：`zota-web/scripts/check-enrollment.mjs`。
用本地 Vite 页面与隔离 API 模拟数据验证入口、创建永久/限时令牌、复制片段、
明文关闭清除、VIN 查询、撤销确认、状态筛选、权限拒绝与未启用/异常页面。
覆盖桌面 1440×900、移动 390×844，移动浅色/深色。截图只保存在本机临时目录，
没有重新生成架构图或提交图片。

浏览器 mock 不能代表真实前后端已部署联调；后端协议与数据库行为由单独的
真实集成测试覆盖。尚未验证 PostgreSQL/MySQL 实库迁移、生产账号覆盖配置和实车操作。
前一轮的旧事件测试问题及 VIN 身份证明/管理恢复等限制没有因新增 UI 自动解决。

本地预览：

```bash
npm run dev
```

默认前端在 `http://localhost:5174`，代理后端 `http://localhost:8090`；
后端未启动时仍可打开前端，但不能真实登录或创建令牌。
需要部署并启用新后端、注入 hash secret 后，现有 admin 才会看到管理入口。
