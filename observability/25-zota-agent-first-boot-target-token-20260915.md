# zota-agent 首次启动 Target 安全令牌获取分析

日期：2026-09-15

状态：`analysis/unverified`：本文只做代码级方案分析，未修改 `zota-server`
或 `aura-ota-agent` 业务代码，也未进行服务端与车端联调。

分析范围：

- `zota-server`：Target 的 `securityToken` 生成、存储和 DDI 认证流程
- `aura-ota-agent`：首次启动时 Target 安全令牌的加载和 bootstrap 处理

本文中的 Target 安全令牌专指 `zota-server` Target 记录里的
`securityToken`，即 DDI 接口的 `Authorization: TargetToken <token>` 凭证。
它与安装期用来换取 Target 安全令牌的 enrollment 凭证是两个概念。

## 结论

1. **VIN 可以作为 `controllerId`，但不能直接作为 Target `securityToken`。**
   `controllerId` 是身份标识，`securityToken` 是 bearer 凭证。DDI 认证只做
   字符串相等比较；如果 `securityToken=VIN`，任何知道 VIN 的人都能冒充该车。

2. **“agent 安装时默认带一个值，首次启动后向云端换取正式 Target 安全令牌”方向可行，
   但这个默认值不能是 VIN。** 需要在安装或产线阶段为车辆生成一个随机 enrollment
   凭证，并把它与 VIN/controllerId 绑定。

3. **现有 zota-server 自注册不能完成闭环。** 不存在的 controllerId 首次访问可以
   自动创建 Target 并生成随机 `securityToken`，但服务端不会把该 token 下发给
   agent；agent 下一次请求仍然不知道 token，无法继续认证。

4. **不应复用 DDI `configData` 做换取。** 当前 `PUT configData` 只是更新 Target
   attributes，没有 Token Exchange 语义，也没有向 agent 返回正式 Target 安全令牌。

5. **推荐新增专门的 Bootstrap Exchange API。** Agent 用一次性 enrollment 凭证
   和 VIN/controllerId 请求服务端；服务端验证并轮换 Target `securityToken` 后，
   在响应中返回新 token。Agent 原子持久化新 token，并删除 enrollment 凭证。

6. **agent 当前存在持久化缺口。** 即使 bootstrap 流程拿到了新的 ZOTA token，当前
   只更新内存中的 `cfg.ZOTA.Token` 和 DDI client，没有写回配置或独立 token 文件，
   进程重启后会丢失。

## 当前代码链路

### 1. Target securityToken 的生成

Target 创建时，如果调用方显式传入 `securityToken`，服务端直接使用传入值；
否则用安全随机数生成 16 字节、hex 编码后的 32 字符 token。

代码位置：

- `zota-server/zota-repository/zota-repository-api/src/main/java/org/eclipse/zota/repository/TargetManagement.java:468`
- `zota-server/zota-repository/zota-repository-api/src/main/java/org/eclipse/zota/repository/SecurityTokenGenerator.java:26`

关键逻辑：

```java
securityToken = ObjectUtils.isEmpty(builder.securityToken)
        ? SecurityTokenGenerator.generateToken()
        : builder.securityToken;
```

```java
private static final int TOKEN_LENGTH = 16;

public static String generateToken() {
    return new String(Hex.encode(SECURE_RANDOM.generateKey()));
}
```

### 2. DDI TargetToken 认证

Target 安全令牌认证在 `SecurityTokenAuthenticator` 中完成：

- 请求头格式：`Authorization: TargetToken <token>`
- 服务端从 URL 中取 tenant 和 controllerId
- 根据 controllerId 查找 Target
- 将请求 token 与 Target 的 `securityToken` 做相等比较
- 匹配则认证为该 controllerId

代码位置：

`zota-server/zota-ddi/zota-ddi-security/src/main/java/org/eclipse/zota/security/controller/SecurityTokenAuthenticator.java:39`

关键逻辑：

```java
final String presentedToken = authHeader.substring(OFFSET_TARGET_TOKEN);

return asSystemAsTenant(tenant, () -> controllerSecurityToken.getTargetId() != null
                ? controllerManagement.find(controllerSecurityToken.getTargetId())
                : controllerManagement.findByControllerId(controllerSecurityToken.getControllerId()))
        .filter(target -> presentedToken.equals(asSystemAsTenant(tenant, target::getSecurityToken)))
        .map(target -> authenticatedController(tenant, target.getControllerId()))
        .orElse(null);
```

该实现是 bearer token 语义：只要持有正确字符串即可通过认证。它不校验 token
的来源、设备身份或车辆硬件，因此不能把公开 VIN 放进该字段。

### 3. 现有自注册流程

DDI 部分路径会调用 `findOrRegisterTargetIfItDoesNotExist()`。Target 不存在时，
服务端自动创建 Target，并走上述随机 `securityToken` 生成逻辑。

代码位置：

`zota-server/zota-repository/zota-repository-jpa/src/main/java/org/eclipse/zota/repository/jpa/management/JpaControllerManagement.java:349`

关键逻辑：

```java
return targetRepository.findOne(spec)
        .map(target -> updateTarget(target, address, name, type))
        .orElseGet(() -> createTarget(controllerId, address, name, type));
```

问题是自动创建后服务端不会把生成的 `securityToken` 返回给 agent。agent 首次请求
可能触发注册，但后续请求没有 token 可用，认证闭环不成立。

### 4. configData 不是 token 下发通道

DDI `PUT /{tenant}/controller/v1/{controllerId}/configData` 当前只调用
`updateControllerAttributes()`，把上报数据写入 Target attributes。

代码位置：

`zota-server/zota-ddi/zota-ddi-resource/src/main/java/org/eclipse/zota/ddi/rest/resource/DdiRootController.java:280`

关键逻辑：

```java
controllerManagement.updateControllerAttributes(controllerId, configData.getData(), getUpdateMode(configData));
```

它没有 `GET configData` 语义，也没有服务端识别 bootstrap 请求并返回 Target
安全令牌的流程。因此不建议把 Token Exchange 塞进 `configData`。

### 5. agent 首次启动现状

Agent 启动时创建 DDI client，并尝试执行 bootstrap。若拿到新的 ZOTA token，只更新
内存和当前 client：

```go
cfg.ZOTA.Token = result.ZOTAToken
ddiClient.SetToken(result.ZOTAToken)
```

代码位置：

`aura-ota-agent/cmd/agent/main.go:93`

配置校验里虽然注释说 bootstrap 会 fetch and persist token，但当前并没有 persist；
而且 bootstrap pending 判断硬编码 `/etc/zota-agent/bootstrap-token`，没有使用配置项
`bootstrap_token_file`。

代码位置：

`aura-ota-agent/internal/config/config.go:219`

```go
// ZOTA token may be empty on first boot when bootstrap-token is present;
// the bootstrap package will fetch and persist it before the poller starts.
bootstrapPending := func() bool {
    _, err := os.Stat("/etc/zota-agent/bootstrap-token")
    return err == nil
}()
```

这会导致：

- 启动期间 token 轮换成功，进程内可用
- agent 重启后丢失新 token
- 如果原配置为空，只能重新执行 bootstrap
- 如果 enrollment 凭证已被删除，则无法恢复

## 为什么 VIN 不能直接作为 Target securityToken

VIN 是公开或可枚举的车辆身份标识，不是 secret。它可以标识“这辆车是谁”，
但不能证明“请求方就是这辆车”。

如果使用 `securityToken=VIN`：

1. 攻击者只要知道 VIN，就能向 DDI 发送：

   ```http
   Authorization: TargetToken <VIN>
   ```

2. `SecurityTokenAuthenticator` 会查到该 controllerId 对应的 Target，并因为字符串
   相等认证通过。

3. 攻击者随后可拉取部署动作、上报状态、伪造设备反馈，具体影响范围取决于 DDI 权限
   和 OTA action 生命周期。

即使对 VIN 做 base64、hash 或固定拼接，只要算法公开且无独立 secret，仍然不安全。

正确分层是：

- VIN/controllerId：身份标识
- enrollment token：首次换取正式凭证的一次性 secret
- Target securityToken：后续 DDI 通信的长期 bearer secret

## 推荐方案：一次性 Bootstrap Exchange API

以下设计不依赖任何外部密钥管理系统。

### 安装或产线阶段

1. 服务端或产线系统为车辆生成随机 enrollment token。
2. 将 enrollment token 与 `controllerId=VIN` 绑定。
3. 服务端只保存 enrollment token 的 hash，不保存明文。
4. 将 enrollment token 写入车端安装包或安装器，例如：

   ```text
   /etc/zota-agent/enrollment-token
   ```

   文件权限建议 `0600`。

### 首次启动

Agent 请求专门 API：

```http
POST /api/v1/bootstrap/exchange
Authorization: BootstrapToken <random-enrollment-token>
Content-Type: application/json
```

请求体：

```json
{
  "controller_id": "<vin>"
}
```

服务端在一个事务内完成：

1. 查找 enrollment token hash
2. 验证 token 未使用、未过期
3. 验证绑定的 controllerId 与请求体一致
4. 查找或创建 Target
5. 为 Target 轮换新的随机 `securityToken`
6. 标记 enrollment token 已使用
7. 提交事务

响应：

```json
{
  "target_token": "<new-random-target-security-token>"
}
```

Agent 收到响应后：

1. 原子写入独立 runtime token 文件，例如：

   ```text
   /etc/zota-agent/token
   ```

2. 文件权限设为 `0600`
3. 更新 DDI client 的 token
4. 确认 token 文件落盘后，删除 enrollment token 文件
5. 再进入正常 OTA poller

## 服务端设计要求

### 数据模型

建议新增 enrollment 记录，而不是复用 Target attributes：

```text
id
tenant_id
controller_id
token_hash
expires_at
used_at
issued_by
created_at
```

约束：

- `token_hash` 唯一
- `controller_id` 在同一时刻只允许一个有效 enrollment token，或定义明确的版本策略
- 已使用或已过期的 token 不能再次兑换

### 事务与并发

exchange 必须原子完成。并发请求同一个 enrollment token 时，只能有一个请求成功；
失败请求返回明确错误，例如 `409 conflict` 或 `410 gone`。

推荐实现方式：

1. 以 `token_hash` 作为查询条件
2. 使用数据库行锁或原子 UPDATE 抢占使用状态
3. 抢占成功后轮换 Target token
4. 任一步失败则整体回滚

不要先标记 used、再在事务外轮换 Target token。

### 轮换语义

exchange 成功后，服务端应立即轮换 Target `securityToken`，旧 token 应失效。
这可以避免 enrollment token 泄露后，攻击者拿到长期凭证并长期复用。

如果业务要求旧 token 平滑过渡，也必须设置很短的重叠窗口，并在窗口结束前强制失效。

### 错误与审计

- 不区分“token 不存在”和“token 已使用”的详细原因，避免泄露状态
- token 明文不得进入日志、异常消息、审计事件或 APM payload
- 记录 controllerId、时间、结果和请求 ID，不记录凭证
- 对失败次数设置限流和告警
- 生产环境必须使用 HTTPS

## agent 设计要求

### 配置加载顺序

建议 runtime token 文件优先于配置文件：

1. `/etc/zota-agent/token`
2. `ZOTA_TOKEN` 环境变量
3. config.yaml 中的 `zota.token`

如果 runtime token 文件存在且有效，则优先使用它；config 中的 token 只作为显式
覆盖或降级路径。

### exchange 成功后的持久化

写入 token 应使用原子写：

1. 写入临时文件
2. 设置 `0600`
3. `fsync`
4. rename 到 `/etc/zota-agent/token`
5. `fsync` 父目录

只有持久化成功后，才能删除 enrollment token。

### 失败行为

exchange 失败时：

- 不删除 enrollment token
- 有限次退避重试
- 连续失败后阻止 agent 进入正常 OTA poller
- 记录不含 token 明文的错误

不能在凭证不完整时继续运行 OTA 流程，否则会出现难以排查的 401/403 循环。

### 配置修正

现有 `bootstrapPending()` 硬编码 `/etc/zota-agent/bootstrap-token`，应改为读取
配置中的 `bootstrap_token_file`。否则测试环境或自定义安装目录下，空 token 会被
错误拒绝。

## 不推荐的替代方案

### securityToken 直接等于 VIN

不可行。理由见上文：VIN 是身份标识，不是 secret，且当前认证只做 bearer 字符串比较。

### 依赖 findOrRegisterTargetIfItDoesNotExist 自注册

不可行。服务端会生成 token，但不会下发给 agent，无法完成认证闭环。

### 通过 configData 交换 token

不推荐。`configData` 当前语义是设备上报属性，不是安全凭证交换接口。复用它会把
属性存储、认证引导和敏感凭证下发混在同一个通道，后续难以做审计和权限隔离。

### 使用固定算法由 VIN 派生 token

不可行。只要算法公开且没有独立 secret，攻击者可以根据 VIN 计算出 token。

## 落地检查清单

服务端：

1. 新增 enrollment token 数据表和迁移
2. 只保存 token hash
3. 新增 `POST /bootstrap/exchange`
4. 事务内完成验证、标记 used、轮换 Target token
5. 并发兑换只允许一次成功
6. 增加 API 权限、限流和审计
7. 确保响应和日志不泄露 enrollment token 或 target token
8. 增加单元测试和并发测试

agent：

1. 增加 enrollment token 读取
2. 增加 exchange client
3. 增加 runtime token 文件读取和优先级
4. exchange 成功后原子持久化 token
5. 持久化成功后删除 enrollment token
6. 修复 `bootstrapPending()` 硬编码路径
7. 失败时不启动正常 OTA poller
8. 增加首次启动、重启、exchange 失败、并发安装的测试

验收场景：

1. 新车首次启动，exchange 成功，后续 DDI 请求使用新 target token
2. agent 重启后读取 runtime token 文件，不依赖 enrollment token
3. enrollment token 只能兑换一次
4. enrollment token 过期后拒绝兑换
5. controllerId 不匹配时拒绝兑换
6. exchange 失败后 agent 可重试且不删除 enrollment token
7. runtime token 写入失败时不删除 enrollment token
8. 日志中无 token 明文

## 代码索引

- `zota-server/zota-repository/zota-repository-api/src/main/java/org/eclipse/zota/repository/TargetManagement.java:468`
  - Target 创建时决定使用传入 token 还是随机生成 token
- `zota-server/zota-repository/zota-repository-api/src/main/java/org/eclipse/zota/repository/SecurityTokenGenerator.java:26`
  - 16 字节安全随机数，hex 后为 32 字符 token
- `zota-server/zota-ddi/zota-ddi-security/src/main/java/org/eclipse/zota/security/controller/SecurityTokenAuthenticator.java:39`
  - `Authorization: TargetToken` bearer 认证
- `zota-server/zota-repository/zota-repository-jpa/src/main/java/org/eclipse/zota/repository/jpa/management/JpaControllerManagement.java:349`
  - controllerId 不存在时自动注册 Target
- `zota-server/zota-ddi/zota-ddi-resource/src/main/java/org/eclipse/zota/ddi/rest/resource/DdiRootController.java:280`
  - `configData` 只更新 Target attributes
- `aura-ota-agent/cmd/agent/main.go:93`
  - agent 启动和 bootstrap 流程；当前拿到新 token 后只更新内存
- `aura-ota-agent/internal/config/config.go:219`
  - 首次启动允许空 token 的判断；当前 bootstrap 文件路径硬编码
