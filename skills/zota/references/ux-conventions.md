# zota-repo-web UX 设计规范

> **适用范围**: zota-repo-web 所有页面  
> **更新日期**: 2026-07-12  
> **强制等级**: 新增页面必须遵循，存量页面逐步改造

---

## 一、页面布局法则：三层结构

每个页面 MUST 遵循「统计区 → 功能区」两层结构，可选加「引导区」。

```
┌─────────────────────────────────────────────┐
│  PageHeader (标题 + 副标题 + 主操作按钮)     │
├─────────────────────────────────────────────┤
│  📊 统计区 (StatsRow: 4 个 StatCard)         │  ← 一眼掌握全局
├─────────────────────────────────────────────┤
│  📋 引导区 (Alert: 空态时展示使用指南)        │  ← 可选，仅在无数据时
├─────────────────────────────────────────────┤
│  ⚙️ 功能区 (Tabs / Table / Search + Actions) │  ← 足够空间操作
└─────────────────────────────────────────────┘
```

### 统计区 (StatsRow)
- **位置**: PageHeader 下方，功能区上方
- **数量**: 固定 4 个 StatCard，一行排列
- **内容**: 反映该页面核心数据的 4 个关键指标
- **响应式**: 移动端自动变为 2 列

```tsx
const StatsRow = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
  @media (max-width: 768px) { grid-template-columns: repeat(2, 1fr); }
`;
```

### 功能区 (Tabs/Table)
- **表格**: 必须有 `showTotal: t => '共 t 条'` 分页提示
- **空态**: `locale={{ emptyText: '引导文案' }}`
- **搜索**: 全局搜索框 + 按需筛选

---

## 二、各页面统计区规范

| 页面 | StatCard 1 | StatCard 2 | StatCard 3 | StatCard 4 |
|------|-----------|-----------|-----------|------------|
| Dashboard | 软件模块数 | 注册车辆数 | 版本漂移数 | 兼容规则数 |
| Modules | 模块总数 | 生产版本数 | 标定模块数 | LTS 版本数 |
| Calibrations | 标定模块数 | 生产中 | 开发中 | 待验证 |
| Releases | 发布包总数 | 已发布 | 草稿 | LTS 包数 |
| Compatibility | 兼容规则数 | 版本冲突数 | 升级路径数 | 禁止升级数 |
| Vehicles | 车辆总数 | L4 车辆数 | 数采车辆数 | 漂移车辆数 |
| Drift | 漂移总数 | 受影响车辆 | 受影响模块 | 严重程度 |
| Compliance | 认证总数 | 活跃认证 | 已过期 | 法规数 |
| Stage Gates | 门禁清单数 | 已启用 | 总检查项 | 阶段数 |
| Campaigns | 任务总数 | 进行中 | 已完成 | 已取消 |
| Rollouts | (来自 zota-server，降级展示) |
| Approvals | 待审批 | 已通过 | 已拒绝 | 总数 |
| Audit Log | 事件总数 | 今日 | 本周 | 操作类型数 |
| Impact | 车辆总数 | 受影响 | 可修复漂移 | 风险等级 |
| Files | 文件总数 | 目录数 | 总大小 | 最近上传 |
| HW Mappings | 映射总数 | 硬件配置数 | 绑定模块数 | 车型数 |
| Vehicle Calib | 已标定车辆 | VIN标定数 | Base标定数 | 车型数 |

---

## 三、表单规范

### Select 下拉框
```tsx
<Select
  placeholder="搜索并选择..."       // 操作引导
  showSearch                         // 必须支持搜索
  optionFilterProp="label"           // 按 label 搜索
  notFoundContent="暂无数据 — 引导文案"  // 空态引导
/>
```

### Input 输入框
```tsx
<Input placeholder="如：example_value" />  // 带格式示例
```

### Form.Item
```tsx
<Form.Item
  label="字段名"
  tooltip="用自然语言说明此字段的用途、数据来源、格式要求"  // 统一用 tooltip
  rules={[{ required: true, message: '请选择/输入 XXX' }]}
>
```

### 禁止使用的模式
- ❌ `extra="数据来源：XXX"` — 用 `tooltip` 替代
- ❌ 混用 `extra` 和 `tooltip` — 统一只用 `tooltip`
- ❌ 无 `placeholder` 的 Input/Select
- ❌ 无 `notFoundContent` 的 Select
- ❌ 无 `showSearch` 的数据列表 Select
- ❌ 英文界面中夹杂中文（或反之）
- ❌ 表格无 `showTotal` 分页提示

---

## 四、颜色语义

| 语义 | 颜色 | Hex |
|------|------|-----|
| 成功 / 健康 / 生产 | 绿色 | `#22c55e` |
| 信息 / 进行中 | 蓝色 | `#3b82f6` |
| 警告 / 漂移 / 待处理 | 橙色 | `#f59e0b` |
| 错误 / 冲突 / 已撤销 | 红色 | `#ef4444` |
| 紫色 / 辅助 | 紫色 | `#8b5cf6` |

---

## 五、状态覆盖

每个数据区域 MUST 覆盖四种状态：

| 状态 | 实现 |
|------|------|
| Loading | `loading={isLoading}` on Table / Spin |
| Empty | `locale={{ emptyText: '引导文案' }}` |
| Error | `{isError && <Alert type="error" ... />}` |
| Data | 正常渲染 |

---

## 六、数据流向

```
后端 API → useQuery (React Query) → StatCards + Table
                                      ↕
                               useMutation → invalidateQueries → 自动刷新
```

- 所有数据通过 REST API 获取
- 使用 `@tanstack/react-query` 管理缓存
- 写操作后 `invalidateQueries` 自动刷新列表
- 实时页面使用 `refetchInterval`（如漂移检测 30s）
