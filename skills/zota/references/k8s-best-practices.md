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
| zota-server | — | — | — | — | 2 |

> 注册表: GOMEMLIMIT=450MiB (90% of memory limit), GOMAXPROCS=2

### 3.2 自动伸缩策略

```yaml
# HPA behavior（已配置）
scaleUp:   60s 稳定窗口, 100%/30s 步进  # 快速响应流量
scaleDown: 300s 稳定窗口, 50%/60s 步进  # 缓慢缩容防抖动
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
