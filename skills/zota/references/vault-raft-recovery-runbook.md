# Vault Raft 集群恢复 Runbook

## 故障现象

Argo Workflows GitLab SSO 登录报错：
```
The requested scope is invalid, unknown, or malformed.
```

## 根因

集群重启后 Vault Raft 集群分裂，无 Active Leader，导致整条依赖链断裂：

```
集群重启
  → Vault Raft 选主失败（3 节点都 stuck at "raft retry join"）
  → Vault 集群不可用
  → External Secrets Operator 连不上 Vault
  → ClusterSecretStore "vault-backend" 状态: InvalidProviderConfig
  → ExternalSecret "argo-server-sso" 无法同步
  → Argo Server 用过期 client-id/secret 请求 GitLab OIDC
  → GitLab 返回 "scope is invalid"
```

## 诊断命令

```bash
export KUBECONFIG=/Users/minyi/kube.conf

# 1. 检查 Vault Pod 状态
kubectl -n pki get pods -l app.kubernetes.io/name=vault
# 症状: vault-1, vault-2 显示 0/1 Ready

# 2. 检查 Vault Raft 集群
kubectl -n pki exec vault-0 -- vault status
# 症状: "local node not active but active cluster node not found"

# 3. 检查 ExternalSecret
kubectl -n argo get externalsecret
# 症状: STATUS=SecretSyncedError, READY=False

# 4. 检查 ClusterSecretStore
kubectl get clustersecretstore vault-backend
# 症状: Ready: False - unable to create client

# 5. 确认 Vault auth 配置还在
ROOT_TOKEN=$(kubectl -n pki get secret vault-root-token -o jsonpath='{.data.token}' | base64 -d)
kubectl -n pki exec vault-1 -- sh -c "VAULT_TOKEN=$ROOT_TOKEN vault auth list"
# 应看到 kubernetes/ auth method
```

## 恢复步骤

### Step 1: 重启 Vault StatefulSet

```bash
kubectl -n pki rollout restart statefulset vault
# 如果 rollout restart 不生效（Pod AGE 不变），强制删除：
kubectl -n pki delete pod vault-0 vault-1 vault-2
```

### Step 2: 解封 Vault（需要 Unseal Keys）

Vault 使用 Shamir seal，重启后必须手动解封。需要 5 个 Unseal Key 中的任意 3 个。

```bash
# 优先解封 Active Node（IP 在 vault-0 status 中显示）
kubectl -n pki exec vault-0 -- vault operator unseal <KEY1>
kubectl -n pki exec vault-0 -- vault operator unseal <KEY2>
kubectl -n pki exec vault-0 -- vault operator unseal <KEY3>

# 解封其他节点
kubectl -n pki exec vault-1 -- vault operator unseal <KEY1>
kubectl -n pki exec vault-1 -- vault operator unseal <KEY2>
kubectl -n pki exec vault-1 -- vault operator unseal <KEY3>

kubectl -n pki exec vault-2 -- vault operator unseal <KEY1>
kubectl -n pki exec vault-2 -- vault operator unseal <KEY2>
kubectl -n pki exec vault-2 -- vault operator unseal <KEY3>
```

### Step 3: 重启 External Secrets Operator

```bash
kubectl -n external-secrets rollout restart deployment external-secrets
kubectl -n external-secrets rollout status deployment external-secrets --timeout=60s
```

### Step 4: 验证恢复

```bash
# Vault
kubectl -n pki get pods -l app.kubernetes.io/name=vault  # 全部 1/1 Ready

# ClusterSecretStore
kubectl get clustersecretstore vault-backend  # Ready: True

# ExternalSecret
kubectl -n argo get externalsecret  # STATUS=SecretSynced, READY=True

# Argo SSO 登录测试
open https://argo.intra.zeron.ai
```

## 预防措施

### 1. 启用 KMS Auto-Unseal（推荐）

当前 `platform/vault/values-cloud.yaml` 中 KMS 已注释。启用后可避免手动解封：

```yaml
# 取消注释并填入真实的 KMS key ID
seal "awskms" {
  region     = "cn-shanghai"
  kms_key_id = "REPLACE_KMS_KEY_ID"
}
```

### 2. 安全存储 Unseal Keys

- 5 个 Unseal Key + Root Token 必须离线安全存储
- 不能只存在一个人的电脑上
- 建议用 1Password/Vaultwarden 等团队密码管理器

### 3. 监控告警

添加 Prometheus 告警规则：
```yaml
- alert: VaultSealed
  expr: vault_core_unsealed == 0
  for: 5m

- alert: VaultClusterNotReady
  expr: vault_raft_leader == 0
  for: 2m
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `my-infra/scripts/cloud-ops.sh` | vault-init / vault-unseal 脚本 |
| `my-infra/platform/vault/values-cloud.yaml` | Vault KMS auto-unseal 配置 |
| `my-infra/pki/vault-config/vault-pki-setup-wf.yaml` | PKI + K8s auth 自动配置 Workflow |
