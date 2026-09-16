# ZOTA Enrollment 兼容性修复与验证

日期：2026-09-15。对应 [审查报告 27](27-zota-enrollment-review-20260915.md)。

> 后续按用户要求已改为仅使用原 config.yaml：
> [单配置文件记录 29](29-zota-enrollment-single-config-20260915.md)。
> 正式 token 原子落盘时即删除配置中的 enrollment_token，云端仍在正式认证后确认。
> 下文的独立凭证文件/sidecar 描述保留为历史方案，不再用于新安装。

> 2026-09-16 已补齐 [前端管理与永久令牌方案 30](30-zota-enrollment-web-20260916.md)：
> 当前 admin 追加单项权限，未指定有效期即永久，列表和 VIN 使用记录接口已实现。

本轮以“不改变旧凭证和旧安装入口”为边界修复新模块。没有连接生产服务、
修改 Kubernetes 配置、安装车辆软件或提交 Git，也没有重新生成架构图或图片。
本记录不等于生产/实车验收结论。

## 兼容边界

| 旧入口 | 本轮处理 |
|---|---|
| `zota.token` / `ZOTA_TOKEN` | 优先返回显式凭证，不读取或覆盖 enrollment 凭证，不调用 exchange |
| `zota.gateway_token` | 保留原 DDI GatewayToken 行为，无正式 token 文件也能启动 |
| 旧证书 bootstrap | 仍走原入口；支持已有自定义 bootstrap token 路径，不强制改成 enrollment |
| 旧 DDI 认证与目标管理 | 未修改现有 Authenticator、TargetManagement 和 TargetRepository 实现 |
| zeol 既有安装 | 本轮没有改动；仍可预置逐车正式 token，不自动切换共享 token 安装 |
| 普通手工 target-token 文件 | 无 enrollment sidecar 时作为旧凭证使用，不擅自登记/确认 |
| enrollment 升级 | 保存正式 token 与确认 sidecar，已确认车辆不因新安装包带新共享 token 而重新 exchange |
| 服务端未启用 enrollment | 默认不注册 enrollment 接口、服务、hash secret bean 和专用认证链 |

注意：功能开关关闭的是新接口与服务，不是数据库迁移。Flyway 仍会执行新增表
的增量迁移；原有核心表及 target token 不变，已通过空库、旧库和旧凭证保留测试。

之前未发布草稿若曾实际生成“无 sidecar 的 target-token + 云端 PENDING”，
不能直接当成新状态机已经完成确认；需要核对 issuance 并做受控迁移/补确认。
程序不会为了迁移自动领取或轮换原有正式凭证。

## 已修复

### 服务端

- R01：将未发布稿的 enrollment `B1_26_0` 改为 `V1_26_0` 增量迁移，
  保持旧 `B1_20_0` 基线原样。三种数据库脚本均增加新表，不改 `sp_target`。
- R02/R04：confirm 改用现有 `SecurityTokenAuthenticator`，与 DDI 使用相同
  TargetToken 开关和认证逻辑；租户上下文先于仓库事务建立。
- R03：新平台管理操作要求独立 `ENROLLMENT_ADMIN` authority；
  普通只读用户和 `TENANT_ADMIN` 不能创建或撤销全平台 token。
- R05：issuance 绑定 `target_id` 和正式凭证 SHA-256 指纹。target 被删/重建、
  token 被轮换后不能通过原共享 token 取回新凭证。没有新增明文 token 副本。
- 修复 EclipseLink 延迟 ID 分配：仅在新登记创建路径 flush 后捕获 target ID；
  创建共享 token 时也先 flush，保证返回的管理 ID 非空。
- R12：读取目标移到 token/issuance 检查之后，新模块单独使用刷新加锁查询；
  token 校验不再在只读事务中取排他锁，exchange 使用共享锁，revoke 使用排他锁。
  H2 同 VIN 并发首次登记测试通过；各数据库实际锁行为与吞吐仍需实测。
- R14 部分：基础设施故障返回 503，不伪装为错误凭证 401；context path 使用
  框架路径解析；新设备入口复用已有 SSL 要求与 IP DoS 过滤器。
- 增加 `zota.enrollment.enabled`，默认 false。仅启用新模块时要求有效 hash
  secret，拒绝之前的 `change-me` 默认值，避免新模块影响旧服务默认启动。

新 confirm 的定义是“同一 DDI 策略下的一次正式 TargetToken 认证”。
为保持旧功能，本轮没有在所有历史 DDI 请求中加入自动登记副作用。

### Agent

- R07：显式 static/GatewayToken 保持优先级；旧 bootstrap 不因缺 enrollment
  凭证被挡住；手工正式凭证不因空的安装 token 文件而停机。
- 新车同时预置 enrollment 和证书 bootstrap 凭证时先 enrollment，再执行原证书
  初始化；只有旧 bootstrap 凭证时仍走旧入口，不强制要求 enrollment。
- R06：同步 token 文件、原子 rename、同步父目录后才确认；新建目录时同步
  上层目录。权限为 0600，拒绝非普通或权限过宽的凭证文件。
- 新增 `<target_token_file>.enrollment.json`，记录 schema version、
  server/tenant/controller、正式凭证指纹和 confirmed 状态，不含 token 明文。
- exchange 前持久化 PENDING 状态；confirm 成功后持久化 CONFIRMED，再清理
  安装凭证。确认前 enrollment 文件意外丢失时，仍可用已落盘正式凭证补 confirm。
- CONFIRMED 且正式凭证丢失时禁止重新 exchange，保留管理恢复边界。
- R13：只接受协议约定的状态码，confirm 必须 204；禁止跟随重定向；
  exchange 校验 JSON 类型、大小和尾随内容，错误响应 body 不进入日志。
- 对网络错误、408、429、5xx 做有限退避重试，服从调用方超时；
  不对 401/409 无限重试，不用新共享 token 覆盖既有 issuance。
- 确认后的安装凭证清理失败只警告，不阻止已确认车辆启动。

## 开启新登记的前提

默认配置：

```properties
zota.enrollment.enabled=false
```

只有新登记灰度环境才显式设置 `ENROLLMENT_ENABLED=true`，并注入
`ENROLLMENT_TOKEN_HASH_SECRET`（至少 32 字符的高熵随机值）。
平台管理账号必须获得 `ENROLLMENT_ADMIN`，不能仅依靠普通租户管理员身份。
确认目标租户已允许 DDI TargetToken 认证。

启用前还必须关闭 SQL 参数和 Authorization 请求头日志并验证脱敏。
本轮没有为了新模块修改全局日志配置，不能沿用会输出凭证明文的调试设置。

新车需要共享安装凭证时：

```yaml
zota:
  url: "https://your-zota-server"
  token: ""
  gateway_token: ""
  enrollment_token_file: "/etc/zota-agent/enrollment-token"
  target_token_file: "/var/lib/zota-agent/target-token"
```

这不是旧车配置迁移指令。已有 static/GatewayToken 配置不用改。
仅开发环境可通过显式 `insecure_tls` 使用 HTTP；新登记生产必须 HTTPS。
安装包保留正式 token 和 `.enrollment.json`，不要清空工作目录或覆盖它们。

如果某个试验库已实际执行错误的 B1_26_0，不要直接覆盖部署、运行 Flyway
repair 或删除登记表。先查 `schema_version`、现存表及数据，再制定修复迁移。
回退旧程序时也应验证其 Flyway history 兼容性，不自动 drop 新表。

## 本地验证

| 验证 | 结果 |
|---|---|
| 空库/旧库 Flyway 迁移及原 target token 保留 | 2/2 通过 |
| enrollment 服务状态机单测 | 15/15 通过 |
| enrollment REST 单测 | 10/10 通过 |
| 真实 Spring/JPA/EclipseLink/H2 + HTTP 过滤链集成 | 6/6 通过 |
| 默认禁用与不安全 secret 检查 | 2/2 通过 |
| 旧 DDI SecurityTokenAuthenticator 单测 | 4/4 通过 |
| 旧 TargetManagement 权限回归 | 6/6 通过 |
| 服务端 monolith starter 及依赖打包 | `mvn -pl :zota-starter -am -DskipTests package` 通过，未启动或部署生产服务 |
| Agent `go test ./...` | 通过 |
| Agent enrollment/config/ddi `go test -race` | 通过 |
| Agent enrollment/config/main `go vet` | 通过 |
| Agent Linux ARM64 构建 | 通过，输出在临时目录，没有覆盖已跟踪的 agent 二进制 |

集成测试覆盖真实 exchange、幂等重试、错误 token 不确认、正确 token 确认、
重复 confirm、确认后拒绝新旧共享 token、同 token 多车、关闭 DDI 策略、
pending 凭证轮换保护、撤销后正式凭证确认、平台权限以及同 VIN 并发登记。
这些不只是 mock service 的 HTTP 测试。

复测命令（从各仓库根目录执行）：

```bash
mvn -q -pl :zota-enrollment-starter -am test -Dtest=EnrollmentIntegrationTest,EnrollmentDisabledTest,TargetEnrollmentManagementTest,EnrollmentDeviceResourceTest,EnrollmentMigrationTest,SecurityTokenAuthenticatorTest -Dsurefire.failIfNoSpecifiedTests=false
```

```bash
go test ./...
go test -race ./internal/enrollment ./internal/config ./internal/ddi
go vet ./internal/enrollment ./internal/config ./cmd/agent
```

### 旧测试的已知限制

旧 `repository.jpa.management.TargetManagementTest` 共 41 项，本次正常迁移运行
出现 13 项 `DistributionSetTypeCreatedEvent` 数量断言失败。
使用**仅含未改动的 B1_20_0** 的目录重跑，也有 12 项同类失败，失败集合有波动；
`repository.jpa.acm.TargetManagementTest` 的 6 项权限检查两次均通过。

这说明同类异步事件测试问题在不加载 enrollment 迁移时也存在，但不能因此将
整个旧测试套件标为通过，更不能把它当成“已证明所有旧功能零影响”。
本轮未修改旧事件逻辑或旧测试断言。见
[对照证据](enrollment-validation-20260915/README.md)。

## 仍需完成

1. PostgreSQL/MySQL 实库升级、完整部署启动、多个服务实例的并发压力测试。
2. 实车安装、升级、回退，以及硬件掉电/磁盘故障验证。
3. VIN 可信登记证明与全平台 VIN/租户归属规则。共享安装 token 仍不是每车身份证明。
4. pending 阶段丢凭证且原共享 token 已过期/撤销的受控恢复流程；不能自动换新 token 解锁。
5. zeol 的新 enrollment 安装模式。为保持旧流程，本轮未替换其逐车 token 入口。
6. 平台 token/使用车辆分页查询、管理恢复与审计界面、按 token hash 的多实例限流。
7. 关闭生产 SQL 参数/请求头日志并验证脱敏；服务端 hash secret 的有版本轮换。
8. Agent 单机多进程共用同一凭证路径的互斥策略；当前仍按一车一个常驻 Agent 部署。
9. 草稿版本无 sidecar 的凭证、已跑过错误迁移的试验库，以及旧事件测试的单独处理。

本轮没有重新定义 VIN 的唯一范围，也没有将现有车辆迁移为 enrollment；
新功能应保持默认关闭，完成上述必要部署验证后再小范围启用。
