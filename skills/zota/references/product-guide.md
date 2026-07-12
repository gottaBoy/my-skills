# ZOTA-REPO 产品功能手册 v2.0

> **适用角色**: 产品经理、QA、运维工程师、新员工培训  
> **更新日期**: 2026-07-12  
> **对应版本**: zota-repo v2.0 (L4 Lifecycle)

---

## 一、产品概述

zota-repo 是 ZOTA 整车 OTA 平台的**软件版本全生命周期管理中枢**。它为 L4 量产自动驾驶车辆提供：

- **版本目录**：管理所有软件模块（感知、规划、标定、固件等）的版本记录
- **兼容性矩阵**：定义模块间的版本兼容约束 + 硬件约束
- **升级路径管理**：定义车辆允许的版本升级路径（如 `v1.2.3 → v1.3.0` 允许，跳过主版本禁止）
- **Release Bundle**：将兼容的模块版本打包为可发布的整车软件包
- **法规合规认证**：关联 GB 44496-2024、UN R156、ISO 21434 等认证到具体版本
- **阶段门禁**：在 promote 前强制执行质量检查（单元测试、集成测试、安全扫描等）
- **漂移检测**：实时对比车辆实际版本 vs 预期版本，发现漂移告警
- **影响分析**：推送新版本前评估影响范围（受影响车辆数、可修复漂移数、风险等级）

---

## 二、核心功能

### 2.1 版本生命周期

```
dev → staging → validation → production
  │                                    │
  └────────── revoked ←────────────────┘
```

**Hotfix 快速通道**：标记为 Hotfix 的版本可跳过 staging/validation，直接从 dev 到 production（需审批 + 安全扫描）。

**LTS 长期支持**：标记为 LTS 的版本承诺 3-5 年支持，revoke 需额外审批。

**Pre-release 标签**：支持 `alpha`、`beta`、`rc` 预发布标识。

### 2.2 兼容性矩阵

两种规则类型：

| 规则类型 | 用途 | 示例 |
|---------|------|------|
| `compatibility` | 模块间版本兼容约束 | `perception@>=2.0.0` 要求 `camera_calib@>=1.2.0` |
| `upgrade_path` | 版本升级路径约束 | `perception` 从 `>=1.0.0,<2.0.0` 可升级到 `>=2.0.0` |

支持 SemVer 范围语法：`>=1.2.0,<2.0.0`、`^1.2.3`、`~1.2.3`

### 2.3 阶段门禁（Stage Gates）

每个目标阶段可配置一组 checklist，promote 前必须全部通过：

| 目标阶段 | 默认门禁项 |
|---------|----------|
| `staging` | 单元测试通过、代码审查完成 |
| `validation` | 集成测试通过、安全扫描通过 |
| `production` | 全量回归通过、法规认证齐全、灰度验证通过 |

### 2.4 法规合规认证

为每个版本关联法规认证记录：

- 支持多法规：GB 44496-2024、UN R156、ISO 21434 等
- 认证有效期管理 + 到期提醒
- 认证文档链接关联

### 2.5 升级路径检查

在推送版本前，可查询车辆是否能从当前版本升级到目标版本：

```
GET /api/v1/compatibility/upgrade-path?module=perception&from_version=1.2.3&to_version=2.0.0
→ { "compatible": true } 或 { "compatible": false, "reason": "..." }
```

### 2.6 签名验证

支持对版本所有 artifact 进行 SHA256 完整性校验：

- 单版本验证：`GET /api/v1/catalog/modules/{module}/versions/{version}/verify-signature`
- Bundle 批量验证：`POST /api/v1/catalog/releases/{id}/verify-signature`

---

## 三、用户界面

### 3.1 模块管理页 (Modules)

- 模块卡片/列表双视图
- 版本列表 + 生命周期状态标签（LTS / Hotfix / Pre-release 徽章）
- Promote / Revoke 操作
- 版本历史 Timeline
- 文件树浏览 + 预览 + 上传

### 3.2 兼容性矩阵 (Compatibility)

- 规则表格（分 Tab：兼容性规则 / 升级路径规则）
- 快速兼容性检查表单
- 硬件感知兼容性检查

### 3.3 Release Bundles

- Bundle 创建（自动兼容性校验）
- 生命周期：draft → validated → released → revoked
- LTS 标记

### 3.4 合规认证 (Compliance) — 新增

- 认证列表（按法规筛选）
- 认证创建（关联版本 + 法规 + 有效期）
- 认证到期提醒

### 3.5 阶段门禁 (Stage Gates) — 新增

- 门禁清单配置（按目标阶段）
- 版本门禁评估 + 结果查看

---

## 四、API 速查

### 新增端点 (v2.0)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/compatibility/upgrade-path` | 升级路径检查 |
| `GET` | `/api/v1/compliance/certifications` | 列出合规认证 |
| `POST` | `/api/v1/compliance/certifications` | 创建合规认证 |
| `DELETE` | `/api/v1/compliance/certifications/{id}` | 删除合规认证 |
| `GET` | `/api/v1/stage-gates/checklists` | 列出阶段门禁清单 |
| `PUT` | `/api/v1/stage-gates/checklists/{status}` | 保存阶段门禁清单 |
| `POST` | `/api/v1/stage-gates/evaluate` | 执行门禁评估 |
| `GET` | `/api/v1/stage-gates/results/{version_id}` | 查看门禁结果 |
| `GET` | `/api/v1/catalog/modules/{m}/versions/{v}/verify-signature` | 验证版本签名 |
| `POST` | `/api/v1/catalog/releases/{id}/verify-signature` | 验证 Bundle 签名 |

---

## 五、培训要点

1. **SemVer 规范**: 理解 `主版本.次版本.修订号` 的含义及预发布标签
2. **升级路径 vs 兼容性**: 兼容性回答"能否共存"，升级路径回答"能否升级"
3. **Hotfix 流程**: Hotfix 版本标记 → 安全扫描 → 审批 → 直接发布到 production
4. **阶段门禁**: 每个阶段的门禁必须在 promote 前通过，不可跳过
5. **法规合规**: 每个 production 版本必须关联至少一条法规认证
