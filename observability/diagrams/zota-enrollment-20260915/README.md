# ZOTA Enrollment 审查图与复现材料

日期：2026-09-15。此目录对应
[全链路审查报告](../../27-zota-enrollment-review-20260915.md)。
所有测试使用合成凭证、本地临时文件和内存 H2；没有使用真实车辆 token。

> 此目录保留修复前的图与探针。后续代码已优化，当前状态见
> [记录 28](../../28-zota-enrollment-compatibility-hardening-20260915.md)。
> 按用户要求未重新生成图或图片。历史 TenantProbe 使用的旧 Java API 已删除，
> Go overlay 断言的缺陷行为也已修复，不能再将下方历史命令当作当前验收命令。

## 图

- [当前架构](current.architecture.html)，源：[JSON](current.architecture.json)。
- [建议修正时序](proposed.sequence.html)，源：[JSON](proposed.sequence.json)。

HTML 可直接在浏览器打开，不需要开发服务器。JSON 是可继续维护的图源。
当前架构是逻辑图，管理 API 到共享令牌表的连线省略了服务方法转发，
并不表示 REST 绕过服务层直连数据库。建议时序尚未实现；省略的同步返回
不表示异步操作，只有服务端确认事务提交以后才能返回成功。

图中不出现 Vault，因为本次设计是 ZOTA Target 安全令牌的登记。

## 代码对应

以下路径相对于工作区根目录，行号对应审查时的未提交工作树：

| 图节点/流程 | 路径与行号 |
|---|---|
| installer | `zeol/internal/checker/zota_provision.go:114` |
| agent / local-files | `aura-ota-agent/internal/enrollment/enrollment.go:45`、`:158` |
| device-auth | `zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentSecurityConfiguration.java:38` |
| enroll-service | `zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/TargetEnrollmentManagement.java:98` |
| management | `zota-server/zota-enrollment/zota-enrollment-resource/src/main/java/org/eclipse/zota/enrollment/rest/EnrollmentManagementResource.java:40` |
| target-table | `zota-server/zota-repository/zota-repository-jpa/src/main/java/org/eclipse/zota/repository/jpa/model/JpaTarget.java:96` |
| enroll-table | `zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/JpaTargetEnrollmentToken.java:30` |
| issuance-table | `zota-server/zota-enrollment/zota-enrollment-jpa/src/main/java/org/eclipse/zota/enrollment/jpa/JpaTargetEnrollmentIssuance.java:35` |
| ddi | `zota-server/zota-ddi/zota-ddi-security/src/main/java/org/eclipse/zota/security/controller/SecurityTokenAuthenticator.java:49` |
| 建议时序 | 审查报告 R02/R04/R05/R06/R09，不是现有调用路径 |

## 交付证据

[回执](delivery-receipts.json)包含完整 SHA-256、字节数、确定性检查、
浏览器和图片审查状态。这三类证据不能互相替代。

| 项目 | 当前架构 | 建议时序 |
|---|---|---|
| 类型 | architecture | sequence |
| showcase | 9/9，0 错误，0 警告 | 9/9，0 错误，0 警告 |
| browser_evidence | passed | passed |
| visual_review | passed | passed |
| correction_rounds | 1 | 2 |

实际 Chrome 测量尺寸：1440×900、1600×1000、1920×1080、2048×1320；
均无水平/垂直页面溢出。通过图片工具人工式审查两图在 1440×900 浅色及
2048×1320 深色的实际截图：文字和节点无重叠，主路径清楚，大屏布局均衡。
其他端点主题截图由自动检查生成；此声明不覆盖未逐项操作的搜索、聚焦和所有导出格式。
自动 JSON 中的 `visualReview: pending` 保持原样，图片审查单独记录在交付回执。

- [当前架构浏览器证据](current.architecture.visual-check.json)
- [当前架构截图索引](current.architecture.visual-check.html)
- [建议时序浏览器证据](proposed.sequence.visual-check.json)
- [建议时序截图索引](proposed.sequence.visual-check.html)

## 复现

以下从 `/Users/minyi/workspace/autodrive` 执行。Maven 命令仅解析已有项目依赖，
不部署服务器；缺依赖时可能下载到本机缓存。

```bash
mvn -q -f zota-server/zota-repository/zota-repository-jpa-init/pom.xml dependency:build-classpath -Dmdep.outputFile=/private/tmp/zota-enrollment-flyway-classpath.txt
mvn -q -f zota-server/zota-enrollment/zota-enrollment-jpa/pom.xml dependency:build-classpath -DexcludeGroupIds= -Dmdep.outputFile=/private/tmp/zota-enrollment-jpa-classpath-full.txt
java --class-path "$(cat /private/tmp/zota-enrollment-flyway-classpath.txt)" .github/observability/diagrams/zota-enrollment-20260915/probes/FlywayProbe.java zota-server/zota-repository/zota-repository-jpa-flyway/src/main/resources/db/migration/H2
java --class-path "zota-server/zota-enrollment/zota-enrollment-jpa/target/classes:$(cat /private/tmp/zota-enrollment-jpa-classpath-full.txt):$(cat /private/tmp/zota-enrollment-flyway-classpath.txt)" .github/observability/diagrams/zota-enrollment-20260915/probes/TenantProbe.java zota-server/zota-repository/zota-repository-jpa-flyway/src/main/resources/db/migration/H2/B1_20_0__1.0.0_baseline__H2.sql
```

TenantProbe 要求已经编译当前 enrollment-jpa 模块；使用真实仓库事务管理器和
EntityManager，只适配了 TargetRepository 查询入口。若本机禁用 JVM attach，
需要在允许 Mockito attach 的本地测试环境执行。复现不是修复，也不是完整 HTTP 测试。

Go 探针从 `aura-ota-agent` 目录执行；overlay 仅添加测试，不写业务文件：

```bash
env GOCACHE=/Users/minyi/workspace/autodrive/.gocache go test -overlay /Users/minyi/workspace/autodrive/.github/observability/diagrams/zota-enrollment-20260915/probes/go-overlay.json ./internal/enrollment -run TestReview -v
```

overlay 使用当前工作区绝对路径；换目录时要更新 `Replace` 映射。
四个测试断言的是审查时的缺陷行为，不应原样作为修复后的期望行为加入产品 CI。
FlywayProbe 输出表存在性；它的退出码不单独判断迁移结果是否正确。

## 覆盖边界

本轮未运行 PostgreSQL/MySQL 实库、集群并发、硬件掉电和实际安装升级；
也没有替换或恢复此前已修改的 agent 二进制。既有服务/REST 测试仍通过，
但依赖 Mockito，缺少本报告暴露出的数据库、租户事务及真实安全链覆盖。
