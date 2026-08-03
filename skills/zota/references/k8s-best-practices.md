# ZOTA K8s 部署 — 安全 · 可维护 · 高效最佳实践

> 适用版本：2026-07-12 | 覆盖服务：zota-repo, zota-repo-web, zota-server, hawkbit-updater-ui

---

## 一、安全 (Security)

### 1.1 纵深防御层

```
Layer 1: NetworkPolicy    → 仅允许 ingress-nginx 入站，按服务限制出站
Layer 2: Pod Security     → runAsNonRoot + readOnlyRootFS + seccomp
Layer 3: Secrets          → ESO + Vault KV-v2，Git 零明文
Layer 4: Reloader         → Secret 变更自动滚动重启 Pod（无人工窗口）
Layer 5: PriorityClass    → zota-critical/zota-high 防止资源耗尽时被驱逐
```

### 1.2 检查清单

| 检查项 | zota-repo | zota-repo-web | zota-server | hawkbit-ui |
|--------|:---:|:---:|:---:|:---:|
| readOnlyRootFilesystem | ✅ (except /tmp,/data) | ✅ (tmpfs for nginx) | ⚠️ need check | ⚠️ need check |
| runAsNonRoot | ✅ | ✅ | ⚠️ | ⚠️ |
| allowPrivilegeEscalation=false | ✅ | ✅ | ⚠️ | ⚠️ |
| seccompProfile: RuntimeDefault | ✅ | ❌ (nginx:特例) | ❌ | ❌ |
| NetworkPolicy restrict egress | ✅ (PG+DNS+zota) | — | — | — |
| Secrets via ESO+Vault | ✅ | — | ✅ | — |
| Probe protected | ✅ (/health) | ✅ (/health) | ✅ (/actuator) | ✅ (/) |

### 1.3 待改进（非阻塞）

- [ ] zota-server: 添加 `readOnlyRootFilesystem` + tmpfs 卷
- [ ] hawkbit-updater-ui: 添加 NetworkPolicy
- [ ] 全服务: 启用 `seccompProfile: RuntimeDefault`
- [ ] 镜像扫描: 集成 Trivy 到 Harbor（CI 阶段扫描 CVE）

---

## 二、可维护性 (Maintainability)

### 2.1 约定优于配置

```
{project}/k8s/
├── base/                        ← 通用：跨环境共享
│   ├── deployment.yaml          ← 2 副本 + RollingUpdate (maxUnavailable:0)
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── networkpolicy.yaml
│   ├── hpa.yaml                 ← min:2, max:6, CPU 70%
│   ├── pdb.yaml                 ← minAvailable:1
│   ├── servicemonitor.yaml      ← Prometheus Operator
│   ├── externalsecret.yaml      ← ESO → Vault
│   ├── priorityclass.yaml       ← zota-critical / zota-high
│   ├── resourcequota.yaml       ← 命名空间总资源上限
│   └── kustomization.yaml
└── overlays/production/
    ├── kustomization.yaml        ← 3 副本 + harbor 镜像 + patches
    └── ingress.yaml              ← TLS + 域名
```

### 2.2 部署自动化

| 层 | 工具 | 职责 |
|----|------|------|
| 服务发现 | ApplicationSet (*/k8s/overlays/production) | 新项目零配置上线 |
| CI | GitHub Actions (ci.yml) | 构建 + vet/test + type-check |
| CD (手动) | deploy.sh | docker build → push → git tag → ArgoCD sync |
| CD (未来) | cd-auto.yml | push main 自动构建+推送+触发 ArgoCD |

### 2.3 版本策略

- 镜像标签: 日期戳 `20260712-a1b2c3d`（CI 自动）或 semver `0.2.0`（手动）
- Kustomize `newTag`: 在 kustomization.yaml 中，ArgoCD 检测 Git 变更自动同步
- 回滚: `kubectl -n zota rollout undo deployment/zota-repo`

---

## 三、高效性 (Efficiency)

### 3.1 资源优化

| 服务 | CPU 请求 | CPU 限制 | 内存请求 | 内存限制 | 副本 |
|------|:---:|:---:|:---:|:---:|:---:|
| zota-repo | 100m | 500m | 128Mi | 512Mi | 3 |
| zota-repo-web | 50m | 200m | 64Mi | 128Mi | 3 |
| zota-server | 500m | 2000m | 1Gi | 2Gi | 1 |

> zota-server (Java): 实际内存 ~650MB，request 设 1Gi（≈1.5x 实际），给 HPA 内存伸缩留余量。
> zota-repo (Go): GOMEMLIMIT=450MiB (90% of memory limit), GOMAXPROCS=2

### 3.2 自动伸缩策略（HPA）

#### 部署原则
- **HPA 跟 Deployment 放一起**：哪个 k8s 目录管 Deployment，就在哪放 hpa.yaml
  - `hawkbit/k8s/base/hpa.yaml` → zota-server
  - `zota-repo/k8s/base/hpa.yaml` → zota-repo
- **避免外部 HPA**：所有 HPA 通过 kustomization.yaml 管理，防止外部控制器（Helm/ArgoCD）覆盖副本数

#### zota-server HPA（Java 应用）

```yaml
# hawkbit/k8s/base/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: zota-server
spec:
  scaleTargetRef: { kind: Deployment, name: zota-server }
  minReplicas: 1
  maxReplicas: 3            # 小服务 1-3 足够，不需要 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
    - type: Resource
      resource:
        name: memory
        target: { type: Utilization, averageUtilization: 80 }
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - { type: Percent, value: 50, periodSeconds: 60 }
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - { type: Percent, value: 100, periodSeconds: 30 }
```

#### ⚠️ 内存 HPA 的关键约束

| 规则 | 说明 |
|------|------|
| **request ≥ 实际用量** | 否则 HPA 利用率恒 >100%，永远触发扩容 |
| **request ≈ 1.2-1.5x 实际** | 给 JVM 波动留余量，同时保持 HPA 有效 |
| **不要设 memory target=200%** | 200% = 禁用内存伸缩，等于没配 |

> 反例：request=512Mi 但 Java 实际用 650MB → 利用率 127% → HPA 一直认为需要扩容。
> 正例：request=1Gi 实际用 650MB → 利用率 ~63% → 超过 ~820Mi 才触发扩容。

#### zota-repo HPA（Go 应用，CPU only）

```yaml
# zota-repo/k8s/base/hpa.yaml
minReplicas: 1
maxReplicas: 3
metrics:
  - type: Resource
    resource:
      name: cpu
      target: { type: Utilization, averageUtilization: 70 }
```

> Go 应用内存稳定，不需要内存 HPA。Java 应用（如 zota-server）需要 CPU + 内存双指标。

#### 运维命令

```bash
# 查看 HPA 状态
kubectl -n zota get hpa
# NAME          REFERENCE                TARGETS            MINPODS  MAXPODS  REPLICAS
# zota-server   Deployment/zota-server   31%/70%, 64%/80%   1        3        1

# 清理旧 HPA（如果被外部控制器覆盖）
kubectl -n zota delete hpa zota-server zota-repo
kubectl -n zota apply -f hawkbit/k8s/base/hpa.yaml
kubectl -n zota apply -f zota-repo/k8s/base/hpa.yaml
```

### 3.3 高可用

| 机制 | zota-repo | zota-repo-web |
|------|:---:|:---:|
| PDB (minAvailable:1) | ✅ | ✅ |
| TopologySpread (跨节点) | ✅ | ✅ |
| HPA (2→6) | ✅ | ❌ (静态 3 副本) |
| RollingUpdate (maxUnavailable:0) | ✅ | ✅ |

### 3.4 PriorityClass 驱逐优先级

```
系统关键进程 (2B) > zota-critical (1B) > zota-high (100M) > default (0)
                       ↑ zota-server       ↑ zota-repo/web
```

资源紧张时，低优先级 Pod 先被驱逐，核心服务最后受影响。

---

## 四、反模式警示

| 反模式 | 风险 | 纠正 |
|--------|------|------|
| `:latest` 标签 + `imagePullPolicy: Always` | 无法回滚，自愈时拉坏镜像 | 生产 overlay 用 Harbor 固定 tag |
| 无 ResourceQuota | 一个服务内存泄漏拖垮整个 namespace | `resourcequota.yaml` |
| ConfigMap 存密码 | Git 明文泄露 | ESO+Vault |
| 无 PDB | 节点维护时全挂 | `pdb.yaml` minAvailable:1 |
| 无 NetworkPolicy | 被入侵后横向移动 | deny-all + 白名单 |
| 无 PriorityClass | 低优服务抢占高优资源 | zota-critical → zota-server |

---

## 五、部署顺序

```
1. Vault PKI (my-infra/pki)          → 证书 + 密钥
2. ESO (my-infra/platform)           → Secret 同步基础设施
3. vault-seed.sh                     → 填充 ZOTA 密钥
4. ArgoCD ApplicationSet             → 自动发现以下服务:
   ├── zota-server (HawkBit)
   ├── zota-repo (版本管理)
   ├── zota-repo-web (React 前端)
   └── hawkbit-updater-ui (管理 UI)
```

---

## 六、CORS 配置

### 6.1 zota-server CORS

zota-server 基于 Spring Security，CORS 由 `hawkbit.server.security.cors.*` 属性控制。

**application.properties：**
```properties
hawkbit.server.security.cors.enabled=true
hawkbit.server.security.cors.allowedOrigins=${CORS_ORIGINS:https://zota-web.intra.zeron.ai,https://zota-repo-web.intra.zeron.ai,http://localhost:3000,http://localhost:5173}
```

**ConfigMap（覆盖默认值）：**
```yaml
CORS_ORIGINS: "http://zota-web.intra.zeron.ai,https://zota-repo-web.intra.zeron.ai,http://localhost:3000,http://localhost:5173"
```

### 6.2 常见 CORS 排障

| 现象 | 根因 | 修复 |
|------|------|------|
| 403 "Invalid CORS request" | Origin 不在 allowedOrigins 列表 | 加对应域名 |
| DELETE/PUT 被 CORS 拦截 | Spring 默认允许，但 origin 不匹配 | 检查 scheme（http vs https）|
| K8s ConfigMap 改完不生效 | 未 `kubectl rollout restart` | restart deployment |

### 6.3 默认的 CORS 方法（无需额外配置）
Spring Security CORS 默认允许：DELETE, GET, POST, PATCH, PUT, HEAD, OPTIONS

---

## 七、RabbitMQ 配置

### 7.1 本地开发
RabbitMQ 在火山引擎 VPC 内网，本地开发机连不上。**本地 MUST 关闭：**
```properties
hawkbit.events.remote.enabled=false
hawkbit.dmf.enabled=false
hawkbit.dmf.rabbitmq.enabled=false
```

否则事件发布（如创建 DS）时会 `SocketTimeoutException: Connect timed out`，导致事务回滚。

### 7.2 生产环境
```properties
hawkbit.events.remote.enabled=true
hawkbit.dmf.enabled=true
hawkbit.dmf.rabbitmq.enabled=true
spring.rabbitmq.connection-timeout=3000  # 3 秒快速失败
```

> 端口 5671 = AMQPS (TLS)，5672 = AMQP (plain)。K8s 集群内需确认 VPC 网络可达。
