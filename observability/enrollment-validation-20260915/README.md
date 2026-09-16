# 旧目标管理测试对照

时间：2026-09-15。本轮业务改动及其他验证见
[兼容性修复记录](../28-zota-enrollment-compatibility-hardening-20260915.md)。

- `target-events-with-enrollment.txt`：本轮增量迁移，41 项中 13 项事件断言失败。
- `target-events-original-baseline.txt`：仅加载原 B1_20_0，41 项中 12 项同类断言失败。
- 两次 `repository.jpa.acm.TargetManagementTest` 均 6/6 通过。
- 旧 `zota-repository-jpa` 源码和 B1_20_0 的 `git diff` 为空，未为了本轮改动调整旧逻辑。

对照不意味着每个失败都已经独立定位，也不意味着旧套件通过；
只能证明相同的事件断言问题在不加载 enrollment 迁移时也发生，数量和用例有波动。

仅原基线对照命令：

```bash
mvn -q -pl :zota-repository-jpa -am test -Dtest=TargetManagementTest -Dsurefire.failIfNoSpecifiedTests=false -Dspring.flyway.locations=filesystem:/private/tmp/zota-enrollment-baseline.9Ceg6Z
```

其中临时目录只复制了当前仓库未改动的
`zota-repository-jpa-flyway/src/main/resources/db/migration/H2/B1_20_0__1.0.0_baseline__H2.sql`，
没有 enrollment SQL。换机器复测时创建同样的独立基线目录即可。
