# JetLinks Casdoor OIDC 集成方案

> 创建: 2026-07-19 | 状态: ⏸ 待实现
> 关联: `.github/skills/zota/references/casdoor-integration-proposal.md`

---

## 一、架构差异

**关键事实**: JetLinks **不使用** Spring Security。它的认证体系基于 **hsweb-framework v5**（项目内本地模块 `hsweb-framework/`），一个完全响应式（WebFlux）的事件驱动安全框架。

```
Spring Security (zota-repo)        hsweb (JetLinks)
─────────────────────              ─────────────────────
@EnableWebSecurity                 @Authorize 注解
SecurityFilterChain                AuthorizationDecodeEvent → ... → AuthorizationSuccessEvent
http.oauth2Login()                 自定义 ReactiveUserTokenParser
OAuth2UserService                  事件监听器
```

这意味着 **JetLinks 无法使用标准的 `spring-security-oauth2-client` OIDC 登录流程**，需要自定义集成。

---

## 二、认证架构（hsweb 事件驱动）

```
请求 → ReactiveAuthenticationManager
        │
        ├── AuthorizationDecodeEvent ──→ CaptchaController（验证码）
        │                                   UserLoginLogicInterceptor（密码解密）
        │
        ├── AuthorizationBeforeEvent ──→ 检查是否已预授权
        │
        ├── Authentication.flux().authenticate()
        │
        ├── AuthorizationSuccessEvent ──→ LoginEvent（添加权限/角色）
        │
        └── AuthorizationFailedEvent  ──→ UserLoginLogicInterceptor（记录失败）
```

---

## 三、现有基础设施

| 组件 | 位置 | 用途 |
|:----|:----|:----|
| `ThirdPartyUserBindEntity` | `authentication-manager/.../entity/` | 第三方用户绑定表 `s_third_party_user_bind` |
| `ThirdPartyUserBindService` | `authentication-manager/.../service/` | 绑定 CRUD |
| `ThirdPartyUserController` | `authentication-manager/.../web/` | 绑定 API（`/user/third-party/{type}/{provider}/_bind`） |
| `UserLoginLogicInterceptor` | `authentication-manager/.../login/` | 登录拦截器，可扩展 |

目前 `ThirdPartyUserBind` 用于钉钉/企业微信绑定，可以直接复用 OIDC。

---

## 四、集成方案（推荐）

### 方式一：自定义 ReactiveUserTokenParser（推荐）

**原理**: hsweb 允许多种 token 解析方式（cookie、header、API Key）。实现一个 `CasdoorOidcTokenParser` 从 `Authorization: Bearer <JWT>` 解析并验证 Casdoor token。

**涉及文件**:

| 文件 | 变更 | 
|:----|:----|
| `authentication-manager/pom.xml` | 加 `nimbus-jose-jwt` JWT 解析依赖 |
| `authentication-manager/.../auth/casdoor/CasdoorOidcTokenParser.java` | **新增** — 实现 `ReactiveUserTokenParser` |
| `authentication-manager/.../auth/casdoor/CasdoorOidcConfiguration.java` | **新增** — 配置 Bean |
| `authentication-manager/.../auth/casdoor/CasdoorOidcProperties.java` | **新增** — 配置属性 | 
| `jetlinks-standalone/src/main/resources/application.yml` | 加 `casdoor.oidc` 配置节 |

**核心代码思路**:

```java
@Component
public class CasdoorOidcTokenParser implements ReactiveUserTokenParser {
    
    @Override
    public Mono<TokenInfo> parse(ServerWebExchange exchange) {
        String auth = exchange.getRequest().getHeaders()
            .getFirst("Authorization");
        if (auth == null || !auth.startsWith("Bearer ")) {
            return Mono.empty();
        }
        String token = auth.substring(7);
        // 1. 获取 Casdoor JWKS 公钥
        // 2. 验证 JWT 签名
        // 3. 解析 claims (sub, email, type, isAdmin)
        // 4. 查找/创建本地用户映射 (ThirdPartyUserBind)
        // 5. 返回 TokenInfo
        return validateAndMap(token);
    }
}
```

### 方式二：扩展 LoginEvent 监听器（适用于 Web 登录流程）

如果 JetLinks 需要作为 Casdoor OIDC 客户端（用户通过浏览器跳转到 Casdoor 登录），则在 hsweb 的登录控制器前加一个 OIDC 重定向过滤器。

---

## 五、配置设计

```yaml
casdoor:
  oidc:
    enabled: false
    endpoint: https://casdoor.intra.zeron.ai
    client_id: ${CASDOOR_CLIENT_ID:}
    client_secret: ${CASDOOR_CLIENT_SECRET:}
    certificate: file:///etc/jetlinks/casdoor-cert.pem
    organization: zota-org
    application: jetlinks
    # 用户映射: Casdoor 角色 → JetLinks 角色
    role-mapping:
      admin: admin
      developer: dev
      operator: ops
      viewer: view
```

---

## 六、依赖

```xml
<!-- JWT 解析（nimbus-jose-jwt，轻量无框架依赖） -->
<dependency>
    <groupId>com.nimbusds</groupId>
    <artifactId>nimbus-jose-jwt</artifactId>
    <version>9.37.3</version>
</dependency>
```

不引入 `spring-security-oauth2-client` 等重型依赖——hsweb 的事件驱动模式不需要它。

---

## 七、实现步骤

| 步骤 | 内容 | 估时 |
|:----|:-----|:----:|
| 1 | `authentication-manager/pom.xml` 加 `nimbus-jose-jwt` | 0.1d |
| 2 | `CasdoorOidcProperties.java` — 配置属性绑定 | 0.2d |
| 3 | `CasdoorOidcTokenParser.java` — JWT 验证 + 用户映射 | 1d |
| 4 | `CasdoorOidcConfiguration.java` — 条件 Bean 注册 | 0.2d |
| 5 | `application.yml` — 配置加 `casdoor.oidc` 节 | 0.1d |
| 6 | 测试：mock Casdoor JWKS + 模拟 Bearer 请求 | 0.5d |
| **合计** | | **~2.1d** |

---

## 八、回滚方案

| 场景 | 操作 |
|:----|:-----|
| Casdoor 不可用 | 设 `casdoor.oidc.enabled: false`，恢复原有账号密码登录 |
| JWT 验证失败 | 检查证书是否过期，更新 `certificate` 配置 |
| 用户映射错误 | 调整 `role-mapping` 配置，无需重启（可热加载） |
