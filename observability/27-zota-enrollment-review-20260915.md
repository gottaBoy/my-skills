# ZOTA Enrollment 全链路审查

日期：2026-09-15。范围：当前未提交工作树中的 `zota-server/zota-enrollment`、
`aura-ota-agent` 启动集成，以及 `zeol` 安装入口。

> 后续修复已在同日继续进行，本文保留审查时的问题快照。
> 当前修复范围、兼容策略及测试限制以
> [兼容性修复记录 28](28-zota-enrollment-compatibility-hardening-20260915.md) 为准。

**结论：不建议按当前代码直接上线。** 两阶段状态机的方向可以保留，但当前仍有
数据库迁移、confirm 认证和管理授权问题。此前通过的 12 个服务单测、7 个 REST
单测及编译检查不能覆盖这些问题。本轮仅新增分析、复现材料和图，未修业务代码，
未连接生产数据库、Kubernetes 或车辆，也不涉及 Vault 方案。

## 图与证据

- [当前实现架构图](diagrams/zota-enrollment-20260915/current.architecture.html)
- [建议修正时序图，待实现](diagrams/zota-enrollment-20260915/proposed.sequence.html)
- [图源、代码映射、验证回执与复现说明](diagrams/zota-enrollment-20260915/README.md)

图中的“当前”是代码逻辑连接关系，不表示已成功部署；“建议”不能当成当前能力。

## 必须保留的业务语义

1. 共享 enrollment token 不按车消耗；一台车确认不影响其他车使用。
2. 首次 exchange 只建立 `PENDING`，不算已使用。
3. 未完成确认且客户端未拿到或未存好凭证时，只允许恢复原 issuance，
   不能发一份新的正式凭证。现实现用同一 enrollment token 做幂等重试。
4. 只有换出的正式凭证通过目标认证、服务端确认事务提交，才算 `CONFIRMED`。
5. 确认响应丢失时允许重复 confirm，不允许重新 exchange。
6. `CONFIRMED` 永久封闭 enrollment；新安装包、新共享 token 都不能解锁。
7. 凭证遗失后的管理端恢复必须是另一条有审计的凭证恢复/轮换通道，
   不能简单删除 issuance 或把 `CONFIRMED` 改回 `PENDING`。

其中，“已经换取过禁止再次换取”应区分 **新发放** 和 **原发放结果恢复**。
若连响应丢失后的幂等读取也禁止，网络错误或落盘失败就无法自动恢复。

## 按优先级排列的发现

### R01 · P0 · Flyway 增量脚本错误地使用 B 前缀

证据：[H2 脚本，后续已从 B 改为 V](../../zota-server/zota-repository/zota-repository-jpa-flyway/src/main/resources/db/migration/H2/V1_26_0__1.0.0_enrollment__H2.sql)；
MySQL、PostgreSQL 同名脚本也用 `B1_26_0`；
[Flyway 配置](../../zota-server/zota-repository/zota-repository-jpa-flyway/src/main/resources/zota-jpa-flyway-defaults.properties)。

已用仓库依赖和真实 H2/Flyway 复现：

| 场景 | sp_target | enrollment token 表 | issuance 表 |
|---|---:|---:|---:|
| 空库，扫描当前两份 B 脚本 | 不存在 | 存在 | 存在 |
| 已执行 B1_20_0 的库，再扫描当前目录 | 存在 | 不存在 | 不存在 |

新脚本是部分建表，不是完整基线。空库只执行较新的基线，漏建旧核心表；
已有历史的库则不把它作为增量执行。因此“migrate 成功”也不代表应用可用。

修正：保留原完整基线，用版本化增量迁移增加两张表；先检查目标环境实际迁移历史。
若错误脚本已运行，不可仅改文件名后直接部署，更不能靠 `repair` 补缺表。
必须分别验收空库和存量库升级。H2 已复现；MySQL/PostgreSQL 未实库执行。

### R02 · P1 · confirm 的租户上下文建立得太晚

证据：[TargetAuthenticationFilter.java:70](../../zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/TargetAuthenticationFilter.java#L70)、
[TargetEnrollmentManagement.java:89](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L89)、
[TransactionManager.java:62](../../zota-server/zota-repository/zota-repository-jpa-eclipselink/src/main/java/org/eclipse/zota/repository/jpa/TransactionManager.java#L62)。

过滤器先调用带 `@Transactional` 的 `verifyTargetToken`，认证身份尚未放入
SecurityContext。仓库事务管理器在事务开始时读取 tenant；方法内部再
`asSystemAsTenant(...)` 已经晚了，不能补写该 EntityManager 的租户属性。

真实 EclipseLink/H2 对照复现：

```text
当前顺序：transaction -> asSystemAsTenant -> query
No value was provided for the session property [eclipselink.tenant-id]

对照顺序：asSystemAsTenant -> transaction -> query
PASS
```

之后过滤器把该数据库异常转为 `401`。车辆可能已经成功 exchange 和落盘，却
永远无法 confirm。此项不是错误密码，是服务端事务上下文错误。

修正：在进入事务之前建立受控租户上下文，再调用独立事务服务；认证成功以后
才设置“已认证”身份。增加从无 SecurityContext 开始的真实过滤链集成测试。
复现探针仅对 TargetRepository 接口使用适配 mock，查询、事务管理器和
EclipseLink EntityManager 均为实际实现；它不是完整 HTTP 端到端测试。

### R03 · P1 · 平台级 token 的创建/撤销缺少权限门槛

证据：[EnrollmentManagementResource.java:40](../../zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentManagementResource.java#L40)、
[TargetEnrollmentManagement.java:61](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L61)、
[MgmtSecurityConfiguration.java:114](../../zota-server/zota-mgmt/zota-mgmt-starter/src/main/java/org/eclipse/zota/autoconfigure/mgmt/MgmtSecurityConfiguration.java#L114)。

现有 REST 过滤链只要求 `authenticated()`；新资源和服务方法均没有
`@PreAuthorize` 或等效平台管理检查。一般已登录账号也能调用创建和按 ID
撤销方法。token 已改成全局资源，撤销也没有租户范围限制，影响会跨租户。
是否有部署层额外拦截未验证，不能依靠它作为代码授权。

修正：增加专门的平台 enrollment 管理权限，普通租户管理员不能默认获得；
服务层、HTTP 入口和角色映射一起验收。至少测试未认证、只读用户、
普通租户管理员、平台 enrollment 管理员四类身份。

### R04 · P1 · confirm 成功不等价于当前 DDI 策略允许登录

证据：[verifyTargetToken / confirm](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L89)、
[SecurityTokenAuthenticator.java:49](../../zota-server/zota-ddi/zota-ddi-security/src/main/java/org/eclipse/zota/security/controller/SecurityTokenAuthenticator.java#L49)、
[main.go:73](../../aura-ota-agent/cmd/agent/main.go#L73)。

新 confirm 认证只是比较 `sp_target.sec_token`。现有 DDI 认证还检查
`AUTHENTICATION_TARGET_SECURITY_TOKEN_ENABLED`。因此即使修好 R02，
在 TargetToken 登录被关闭的租户中，confirm 仍可能成功并删安装凭证，
随后真正 DDI 登录却失败。

此外，自定义客户端可先 exchange，再直接使用 DDI 而不调用 confirm；
当前 DDI 成功认证不会更新 issuance，该车可能长期仍是 `PENDING`。

修正：明确什么是业务上的“登录成功”。建议 confirm 复用同一套 DDI
认证策略，并在状态更新事务内复核凭证绑定。若要求“任意首次成功 DDI
登录都算使用”，需要在 DDI 成功认证路径增加幂等确认挂点，而非只依赖
Agent 主动调用。建议图采用“confirm 即一次同策略 TargetToken 登录”的定义。

### R05 · P1 · issuance 没有绑定实际发放的 target 与凭证版本

证据：[JpaTargetEnrollmentIssuance.java:53](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/JpaTargetEnrollmentIssuance.java#L53)、
[exchange:113](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L113)、
[confirm:136](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L136)。

issuance 只保存 `tenant + controllerId + enrollmentTokenId`。重试时返回的是
**当前** `sp_target.sec_token`，不是被 issuance 约束的凭证：

- `PENDING` 时管理员轮换 target token，旧共享 token 再试会取得轮换后的新 token。
- `PENDING` 时 target 被删，exchange 会为原 VIN 新建 target 和新凭证。
- 原 VIN 的 target 被删除并重建，旧 issuance 没有 target ID 校验。

所以“重试永远是同一个 token”和“必须拿换出的 token 确认”只在 target
完全不变时成立。这是代码路径推导，未模拟管理端并发轮换。

修正：绑定不可变 target ID 与 credential generation/version，必要时保存正式
凭证的单向指纹用于一致性验证。目标丢失或版本变化进入管理恢复状态，
不能通过共享 enrollment token 读到新的正式凭证。不必额外保存 token 明文。

### R06 · P1 · 原子重命名不等于掉电后的持久化保证

证据：[enrollment.go:158](../../aura-ota-agent/internal/enrollment/enrollment.go#L158)。

实现同步临时文件后 `rename`，没有同步父目录。源码只能证明不会读到半个文件，
不能证明目录项在掉电后仍保留。危险窗口是：rename 返回 -> confirm 提交 ->
断电 -> target-token 目录项丢失；云端已永久封闭 exchange，车辆无法自动恢复。
本轮未做硬件掉电或文件系统故障注入，属于持久化协议缺口。

修正：在目标平台按文件系统语义完成文件同步、rename、父目录同步，再 confirm。
新建凭证目录时也要考虑上层目录的持久化。保留绑定 URL/tenant/VIN/issuance
的恢复状态，升级不能删除；不能仅以 enrollment 文件是否存在判断已确认。

### R07 · P1 · Agent 无条件 enrollment 导致旧配置回归

证据：[main.go:73](../../aura-ota-agent/cmd/agent/main.go#L73)、
[enrollment.go:45](../../aura-ota-agent/internal/enrollment/enrollment.go#L45)、
[config.go:230](../../aura-ota-agent/internal/config/config.go#L230)。

已用 Go overlay 测试复现，未改仓库业务文件：

| 输入 | 当前行为 |
|---|---|
| 仅有有效 `gateway_token`，无 target/enrollment 文件 | Validate 通过，EnsureCredentials 报缺凭证，启动退出 |
| 老车 `zota.token` 已配置，新安装包又带 enrollment 文件 | 无 target 文件就先 exchange，忽略静态 token，已存在 target 会 409 |
| target 文件存在，但 enrollment 文件为空 | 先读 enrollment 报错，正式凭证无法使用 |

声明“优先已有 target token”与实际先读取 enrollment 文件不一致。已有独立
bootstrap 路径也会受无条件前置检查影响，但它不属于本次 token 方案。

修正：显式选择凭证来源，已有本车正式凭证优先；仅确实缺凭证时进入 enrollment。
升级需要识别并迁移老 `zota.token`，保留 GatewayToken 兼容性。
“有旧 target 凭证”不意味着必须拿它调用不存在 issuance 的 confirm。

### R08 · P1 · 实际安装入口尚未接上共享 token

证据：[zeol/zota_provision.go:114](../../zeol/internal/checker/zota_provision.go#L114)。

zeol 仍从逐 VIN token 文件、环境变量或旧车配置取得正式 token，然后写
`zota.token`；没有写入 enrollment 文件的分支。配置示例有新字段，不等于
用户当前安装流程已经支持“只带一个通用 token”。

已有管理端 target 却无 issuance 的车辆被 server 明确拒绝 exchange，这个
保护不能简单删除，否则共享 token 持有者可领取历史车辆凭证。必须补上：
新车安装、旧静态 token 升级、已 enrollment 车辆升级、管理端预创建 target
四种不同路径，以及是否允许受控预登记的规则。

### R09 · P1（设计边界）· 共享 token + 自报 VIN 无法证明真车身份

证据：[EnrollmentAuthenticationFilter.java:70](../../zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentAuthenticationFilter.java#L70)、
[requireControllerId:196](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L196)。

当前任何共享 token 持有者都能提交别人的 VIN，抢先换取并确认；真车后到会
被永久拒绝。`PENDING` 的幂等取回也无法区分真车和另一位共享 token 持有者。
VIN 只校验非空和长度，并不是车辆所有权校验。限流不能解决冒名登记。

这是共享安装凭证模型的固有限制，不是要求取消“一 token 多车”。
建议共享 token 仅作安装资格，另外引入受控工厂审批/登记许可，
或可信每车密钥的签名证明。单纯首次请求时自生成密钥只能绑定后续重试者，
不能证明第一次请求者就是真车；还需要可信 VIN 绑定来源。

### R10 · P2（需确认）· 当前禁止重登的单位不是全平台 VIN

证据：[JpaTargetEnrollmentIssuance.java:35](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/JpaTargetEnrollmentIssuance.java#L35)、
[platformTokenCanEnrollTargetsInDifferentTenants](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/test/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagementTest.java)。

当前唯一键是 `(tenant, controller_id)`，测试也允许同 VIN 在不同 tenant 登记。
若你的“同一辆车永远不得再换”指全平台 VIN，改 URL 中 tenant 就能建立另一条
issuance，不满足要求。若所有车辆固定 DEFAULT，当前效果仅在这个前提下成立。

建议确认身份范围：如果 VIN 是全平台实体，增加 `VIN -> owner tenant` 的唯一
映射，由服务端决定租户，不能让请求随意选择。不要只放开全平台 token，
却宣称已经保留了完整的租户授权边界。此项在产品范围明确前不做静默变更。

### R11 · P2 · PENDING 在共享 token 过期/撤销后可能无法恢复

证据：[exchange:102](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L102)、
[lockValidToken:150](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L150)。

exchange 已提交但响应丢失或本地落盘失败，若旧共享 token 此时失效，
原 token 重试 401；新 token 重试又会因 issuance 已绑定旧 token 而 409。
因此不能笼统保证“所有 exchange/落盘失败都可恢复”。

如果 token 已安全落盘，confirm 不依赖 enrollment token，撤销后仍应可确认。
如果 token 未落盘，则必须明确恢复策略：带额外设备证明的受限 resume，
或单独的人工凭证恢复。不能为了可用性无条件忽略撤销，也不能拿新共享 token
覆盖原 issuance。到期关闭新登记与允许原设备恢复是两个权限。

### R12 · P2 · 全平台 token 行锁形成瓶颈，首次并发读取顺序不可靠

证据：[TargetEnrollmentJpaRepository.java:25](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentJpaRepository.java#L25)、
[exchange:101](../../zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java#L101)。

validate 和 exchange 都对共享 token 使用排他锁。同一 token 下不同 VIN
也竞争同一行，实际串行进入关键区；并不是文档暗示的互不影响并发。

同 VIN 并发首次请求还在拿锁之前读取 target。第二个事务可能先读到空值，
等待后拿到已有 PENDING，却继续依据旧 Optional 创建 target，引发唯一键错误，
而非直接幂等返回。恢复可能需要另一次请求；不能只靠唯一键声明并发已处理完。

修正：按目标身份组织事务，锁后读取目标最新状态；对冲突明确重试或返回可恢复
错误。避免长时间持有全平台 token 排他锁，同时维持撤销生效的一致性语义。
这部分需要 PostgreSQL/MySQL 实库、至少两实例的并发测试，本轮未执行压测。

### R13 · P2 · HTTP 成功判定和凭证配置校验不严格

证据：[post:100](../../aura-ota-agent/internal/enrollment/enrollment.go#L100)、
[config.go:213](../../aura-ota-agent/internal/config/config.go#L213)。

Go 探针已复现：confirm 返回 HTML `200`，Agent 也视为成功并删除 enrollment
文件。默认 HTTP client 允许跟随重定向，错误代理/登录页的 200 可能造成假确认。
已落盘凭证并未丢失，但云端保持 PENDING，Agent 又失去补 confirm 的本地标记。

其他缺口：token 文件路径未要求绝对、非空且不同；两路径相同会把 enrollment
明文当 TargetToken 发送。正式 token 文件没有绑定 VIN/tenant/服务地址，
换配置后可能误用前一身份。错误响应 body 直接进入异常，随后被 main 记录日志，
没有响应体脱敏保证。

修正：按协议验证确切响应（当前 confirm 约定为 204），禁用登记请求的自动
重定向；持久化可验证的状态；限制响应大小及结构；校验路径、文件类型、
权限和身份绑定。已有正式凭证不能因共享 token 文件清理失败而无限停机。

### R14 · P2 · 安全与运维功能没有完整接入

证据：[EnrollmentSecurityConfiguration.java:38](../../zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentSecurityConfiguration.java#L38)、
[EnrollmentAuthenticationFilter.java:78](../../zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentAuthenticationFilter.java#L78)、
[application.properties:92](../../zota-server/zota-monolith/zota-update-server/src/main/resources/application.properties#L92)。

- 所有 RuntimeException 都转 401，数据库不可用与非法凭证不可区分；需保留
  脱敏错误码/request ID，并对可重试故障返回 5xx。
- 新设备链未接入已有 require-SSL 配置或设备 DoS 过滤器；Agent 接受 HTTP
  及 insecure TLS。TLS/限流是否由入口代理保障，需按部署配置验证。
- hash secret 有固定默认值，且不支持 key ID/轮换；更换服务端 secret 会让
  既有 enrollment token 查找失败。默认 secret 不等于能猜中随机 token，
  但生产应显式配置并在缺失时拒绝启用模块。
- 管理 API 只有 create/revoke，没有 token 列表、每 token 对应 VIN 的
  PENDING/CONFIRMED 分页、成功使用量及审计。表中能存“用过”，不等于平台
  管理员已经能查询“哪些车用过”。只能用 CONFIRMED 计成功使用，不能统计 issuance 总数。
- `requestURI.split("/")` 固定五段，不扣除 servlet context path；部署在
  非根 context 时过滤器会跳过认证。应统一使用框架的路径匹配结果。
- validate 是只读事务却执行排他锁；不同 JPA/数据库配置的兼容性需要实测。
  未实测前不将其单独宣称为 PostgreSQL 已复现故障。

## 建议的数据与模块边界

保留独立 enrollment 模块，但区分以下职责：

| 职责 | 建议约束 |
|---|---|
| 平台 token 管理 | 专用平台权限；共享 token 可轮换/撤销；不可通过新 token 重开已确认车辆 |
| VIN 资格管理 | 明确全局 VIN 或 tenant+VIN；绑定归属和可信登记依据 |
| issuance 服务 | 事务、唯一键、target ID、credential version、PENDING/CONFIRMED、状态审计 |
| 目标认证适配 | 复用 DDI 策略；租户上下文先于事务；认证与登记版本一致 |
| Agent 凭证存储 | 原子且持久、身份绑定、升级兼容、明确 pending-confirm 状态 |
| 管理凭证恢复 | 独立权限与流程；保留原 CONFIRMED 登记，不重新消费共享 token |
| 安装集成 | 新车只发安装凭证；升级保留正式凭证；不得把共享 token 放进 `zota.token` |

“全平台共享 token”仍可保留。真正需要加强的是 **谁能登记哪个 VIN**、
**本次到底发放了哪份凭证**、**谁有权发起平台级管理操作**。

## 失败恢复矩阵

| 故障点 | 应保留状态 | 正确下一步 | 当前缺口 |
|---|---|---|---|
| exchange 前断网 | 无 issuance 或请求结果未知 | 带退避重试 | 无 enrollment 专用退避/错误分类 |
| 事务提交但响应丢失 | PENDING | 恢复同一 issuance | 失效 token 不能恢复；无设备证明 |
| 本地写文件失败 | PENDING | 不 confirm，恢复原凭证 | 原 token 到期后可能卡死 |
| 本地写好但 confirm 请求丢失 | 本地凭证 + PENDING | 只重试 confirm | R02 阻塞；状态依赖 enrollment 文件 |
| confirm 已提交但响应丢失 | CONFIRMED + 本地凭证 | 幂等 confirm | 核心服务意图正确，需真实过滤链验收 |
| confirm 后掉电 | CONFIRMED + 持久本地凭证 | 正常启动 | 父目录未同步 |
| 已确认车辆安装新包 | 保留本地正式凭证/确认状态 | 不 exchange | 安装/旧配置迁移未闭环 |
| 已确认车辆凭证全丢 | CONFIRMED | 独立受控管理恢复 | 还没有对应操作面 |
| 管理端轮换 target token | 原 issuance 保留审计 | 管理通道更新设备凭证 | 当前共享 token 可取回新凭证 |

## 验证与验收门禁

本轮实际执行：

- 服务层原有单测：12/12 通过；REST 原有单测：7/7 通过。
- Agent config/enrollment 原有单测通过。
- FlywayProbe：真实 H2，复现空库/存量库迁移问题。
- TenantProbe：真实仓库事务管理器 + EclipseLink + H2，复现租户顺序错误，
  先设租户的对照通过。需要允许本地 Mockito JVM attach；不访问云端。
- Agent 四项 overlay 探针：验证 GatewayOnly、空 enrollment 文件、
  静态 token 被新安装凭证覆盖、HTML 200 假确认的当前行为。
- 两张 archify 图：各 9/9 showcase，0 errors / 0 warnings；
  Chrome 四种桌面尺寸无溢出，已检查大小桌面的明暗主题截图。

注意：探针的 PASS 表示 **缺陷行为成功被复现**，不是修复后验收通过。

仍缺少的验收：

1. 空库启动完整应用、存量库迁移、真实 POST exchange -> confirm -> DDI。
2. 平台与普通租户的真实 Spring Security 授权矩阵。
3. 多实例同 VIN/不同 VIN、同 token/不同 token 同时登记。
4. exchange 与 revoke、confirm、target 删除/轮换交错。
5. 断网、超时、响应丢失、磁盘满、目录 fsync 失败、掉电与安装回滚。
6. 旧 static/GatewayToken 配置升级、重复安装、VIN/tenant/URL 改变。
7. enrollment token 过期/撤销后，区分新登记和持有正式凭证的确认。
8. 已确认 target 删除重建、换新 enrollment token 仍不能重新登记。
9. 秘密不进日志、代理响应不被误判、HTTPS/限流及审计查询。

建议修复顺序：R01/R02 -> R03/R04/R05 -> R06/R07/R08 -> 身份范围与登记
证明的产品决定 -> 并发、恢复、观测与管理面验收。不得只补限流后就上线。
