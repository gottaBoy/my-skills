# ZOTA Enrollment 单配置文件

日期：2026-09-15。

本记录替代 [28](28-zota-enrollment-compatibility-hardening-20260915.md) 中 Agent 的
多凭证文件方案。服务端 API、启用开关、权限和永久登记规则不变；本轮没有改服务端、
部署车辆、修改线上配置或生成架构图片。

## 安装端只设置一个凭证

保留原 config.yaml 的 URL、VIN、车型和其他配置，新登记车辆只使用：

```yaml
zota:
  url: "https://your-zota-server"
  enrollment_token: "<shared-installation-token>"
```

不要同时设置非空 `zota.token` 和 `zota.enrollment_token`；配置加载会拒绝这种输入。
不需要 `enrollment_token_file`、`target_token_file` 或额外的状态文件。
使用 enrollment 时不配置 GatewayToken，也不要通过 ZOTA_TOKEN 覆盖认证方式。

## 用户要求的互斥语义

| 阶段 | config.yaml 中的凭证 | 云端状态 |
|---|---|---|
| 尚未换取 | 只有 enrollment_token | 无 issuance 或 PENDING |
| 响应丢失、正式凭证尚未写入 | 仍只有 enrollment_token | PENDING，可恢复原发放结果 |
| 正式凭证原子落盘成功 | 只有 token，enrollment_token 键已删除 | PENDING，尚不算已使用 |
| 正式 token 登录确认失败 | 仍只有 token | PENDING，重启只补 confirm |
| 正式 token 认证成功并确认 | 仍只有 token | CONFIRMED，禁止再 exchange |
| 确认响应丢失或本地确认标记写入失败 | 仍只有 token | 可能已 CONFIRMED，重启幂等 confirm |

关键点：**凭证互斥与云端使用确认是两件事。**
删除 enrollment_token 的时机是正式凭证原子落盘，不是云端提前登记已使用。
已经成功落盘的正式 token 足以重试确认，不需要保留安装凭证。

正式 token 和删除安装 token 在同一次配置文件替换中完成，没有“先删旧 token，
再写新 token”的空窗。常规写入失败保留旧配置；若 rename 已成功而目录同步报错，
磁盘可见的新配置也只含正式 token 和待确认状态，Agent 不会继续 confirm。
下次启动从实际保留下来的原子快照恢复。

## 同一文件内自动维护确认进度

Agent 自动写入 `zota.enrollment_state`，包括 schema version、实际 server、
tenant、controller、正式 token 指纹和 confirmed 标志。安装端无需填写这些字段。
状态不能简单省略，否则“已有静态 token”与“刚换取成功但尚未确认”无法区分。

原子更新只修改以下内容：

- `zota.token`
- `zota.enrollment_token`
- `zota.enrollment_state`
- 兼容迁入后移除旧的两个 token 文件路径选项

其他配置值、未知扩展字段、注释和字符串样式通过 yaml.Node 保留。
YAML 的空白和缩进可能被编码器规范化，不承诺字节级排版不变。

## 文件安全与并发

- 使用原配置目录中的短暂临时文件、文件 fsync、原子 rename 和父目录 fsync。
- 配置更新后权限为 0600，并保留原文件所有者；目录和配置必须支持写入。
- 不新增永久 lock 文件。原配置 inode 与替换 inode 都使用文件锁，锁在 rename
  期间连续覆盖，避免两个 Agent 同时登记并互相覆盖配置。
- 启动快照 hash 及每次写入前的内容/inode 检查会拒绝并发修改，不覆盖已经观察到的
  人工改动。文件锁是协作式锁，安装器和其他编辑程序仍不能在登记期间覆盖 config。
- 新登记拒绝符号链接配置、多个 YAML 文档及凭证字段的 alias/merge 写法，
  避免错误更新其他配置或留下安装密钥的引用。
- 更新完成及正常失败后目录中不留下临时凭证文件。异常断电可能留下尚未 rename
  的私有临时文件；这不是额外配置，硬件故障恢复仍需实车验证。

只读 ConfigMap/只读绑定挂载不适合首次 enrollment 写回。
已有 static token/GatewayToken 路径不会触发配置重写，仍可使用只读配置。

## 旧功能与旧布局

- 老 static token 不会因字符串内容被误当作 enrollment token。
- GatewayToken 保持原优先级；环境变量 ZOTA_TOKEN 覆盖不会写回配置。
- 只有旧证书 bootstrap 时仍走旧入口；新车同时有 enrollment 和证书 bootstrap
  时先取得 ZOTA 正式凭证，再继续旧证书流程。
- 旧 token 文件及 sidecar 可兼容读取，并将凭证与状态迁入 config.yaml；
  新流程不会再写入或创建这些文件。
- 已存在的旧凭证文件不自动删除，避免破坏旧版本回退。迁入成功后，
  Agent 不再依赖这些旧文件；测试验证移除旧文件后仍可独立启动。
- 云端已确认且本地正式 token 丢失时仍禁止重新交换，不因为配置里出现新
  enrollment token 就重开登记。
- 升级必须保留本车完整 config.yaml，不删除其中的 token 和自动确认状态。

## 验证

本轮已通过：

```bash
go test ./...
go test -race ./internal/config ./internal/enrollment ./internal/ddi
go vet ./internal/config ./internal/enrollment ./cmd/agent
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o /private/tmp/zota-agent-single-config-linux-arm64 ./cmd/agent
```

重点用例覆盖：

1. exchange 前仅安装凭证，confirm 前仅正式凭证。
2. 正式凭证成功落盘后安装凭证键已删除，不只是写成空字符串。
3. 登录确认失败及最终确认状态写入失败后，重启不再 exchange。
4. exchange 响应丢失仍保留原安装凭证。
5. rename 失败、目录同步失败、并发配置修改不会留下两份凭证或提前 confirm。
6. 原始和替换 inode 的锁连续有效，不产生永久锁文件。
7. 配置注释、Docker 参数、额外字段、版本字符串引号不丢失。
8. 旧 static/GatewayToken 只读配置、环境变量覆盖、证书 bootstrap 回归。
9. 旧凭证布局迁入、VIN/tenant/server/凭证变化保护、已确认后缺 token 拒绝重领。
10. 新装正常流程结束后，配置目录只有 config.yaml。

本轮没有验证真实车辆掉电、生产文件系统特性或远程安装升级。
服务端实库/灰度、VIN 可信登记、管理恢复和旧事件测试等前一轮限制仍有效，
详见记录 28。不能将本地通过解释为生产已经启用。
