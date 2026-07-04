---
description: "Use when writing Java code in the jetlinks-community IoT platform. Covers Spring Boot conventions, JPA patterns, module structure, and Maven build practices."
applyTo: "jetlinks-community/**/*.java"
---

# Java Coding Standards — autodrive jetlinks

> 本文件属于 Spec 层 — 提供编码规范。执行时配合 `execution-governor` 确保 TDD 和 Scope Fence。

## Project Structure
```
jetlinks-community/
├── jetlinks-components/   # 可复用组件（protocol, rule-engine, iot, etc.）
│   └── <component>/
│       ├── pom.xml
│       └── src/main/java/org/jetlinks/
├── jetlinks-manager/      # 管理模块（device, authentication, network, etc.）
│   └── <manager>/
│       ├── pom.xml
│       └── src/main/java/org/jetlinks/
└── jetlinks-standalone/   # 独立运行入口
```

## Spring Boot Conventions
- 使用 `@RestController` 标注 API 控制器
- 使用 `@Service` 标注业务逻辑层
- 使用 `@Repository` 标注数据访问层
- 使用 Lombok `@Data`, `@Builder`, `@AllArgsConstructor` 减少样板代码
- 配置文件使用 `application.yml` 而非 `.properties`

## JPA / Database
```java
// ✅ 使用 Spring Data JPA
@Repository
public interface DeviceRepository extends JpaRepository<Device, Long> {
    Optional<Device> findByDeviceId(String deviceId);
}

// ✅ 使用 @Transactional 管理事务
@Transactional
public void updateDeviceStatus(String deviceId, Status status) {
    // ...
}
```

## 模块依赖规则
- `jetlinks-components` 之间可以互相依赖
- `jetlinks-manager` 可以依赖 `jetlinks-components`
- `jetlinks-standalone` 可以依赖所有模块
- 不允许反向依赖（components 不能依赖 manager）

## Build
```bash
# 编译整个项目（跳过测试）
./mvnw clean package -DskipTests

# 只编译某个模块
./mvnw clean package -DskipTests -pl jetlinks-manager/device-manager

# 运行测试
./mvnw test

# 启动独立服务
cd jetlinks-standalone && ../mvnw spring-boot:run
```

## Code Quality
- 每个 public 方法必须有 Javadoc
- 不要捕获 `Exception` 而不处理
- 使用 `log.debug/warn/error` 而不是 `System.out.println`
- 魔法字符串提取为常量
