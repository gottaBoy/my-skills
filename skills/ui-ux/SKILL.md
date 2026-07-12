---
name: ui-ux
description: 'UI/UX设计能力 — 视觉层次、间距系统、可访问性、仪表盘最佳实践。Use when: designing or reviewing UI pages, building dashboards, optimizing layout/spacing, improving visual hierarchy, ensuring accessibility.'
---

# UI/UX Design Skill — 界面与体验设计

## When to Use
- 设计或重构 Dashboard、管理页面
- 优化表格列表页的布局和可读性
- 调整颜色、间距、字体层次
- 确保可访问性（a11y）合规
- 审查 UI 代码的视觉一致性

---

## 1. 间距系统 (Spacing Scale)

> 基于 4px 基准，所有间距从以下值中选择。

| Token | 值 | 用途 |
|-------|-----|------|
| `xs` | 4px | 图标与文字间距、紧密关联元素 |
| `sm` | 8px | 卡片内部、badge 内边距 |
| `md` | **16px** | 列间距、表格行内边距 |
| `lg` | 24px | 区块间距、卡片间距 |
| `xl` | 32px | 页面主区块间距 |
| `2xl` | 48px | 页面顶部/底部留白 |

```css
/* ✅ 使用标准间距 */
.task-row { gap: 16px; padding: 12px 20px; }
.stat { padding: 12px 16px; margin-bottom: 8px; }

/* ❌ 避免随意值 */
.task-row { gap: 13px; padding: 9px 17px; }
```

---

## 2. 视觉层次 (Visual Hierarchy)

### 2.1 字体层级

| 层级 | 字号 | 粗细 | 用途 |
|------|------|------|------|
| H1 | 18-20px | 600 | 页面标题 |
| H2 | 14-15px | 600 | 区块标题、表头 |
| Body | 13-14px | 400-500 | 表格内容、正文 |
| Caption | 11-12px | 400 | 辅助信息、时间戳 |
| Micro | 10px | 400 | 最小标签 |

```css
/* ✅ 清晰层级 */
.task-name { font-size: 13px; font-weight: 500; }
.task-meta { font-size: 11px; color: #8c8c8c; }
.task-row.header { font-size: 11px; color: #888; text-transform: uppercase; }

/* ❌ 全部同字号 */
.row { font-size: 14px; }
```

### 2.2 颜色语义

| 颜色 | Hex | 语义 |
|------|-----|------|
| Success | `#52c41a` / `#f6ffed` | 成功、已完成 |
| Info | `#1890ff` / `#e6f7ff` | 进行中、信息 |
| Warning | `#faad14` / `#fff7e6` | 待处理、警告 |
| Error | `#ff4d4f` / `#fff2f0` | 失败、错误 |
| Neutral | `#8c8c8c` / `#f5f5f5` | 默认、无状态 |

> **原则**: 彩色背景上用白色文字需要至少 4.5:1 对比度。卡片用白色背景 + 彩色边框 + 深色数字更可读。

---

## 3. 卡片 vs 表格

### 卡片 — 统计概览
```css
.stat {
  background: #fff;
  border-left: 4px solid var(--color);
  padding: 12px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
}
.stat .n { font-size: 22px; font-weight: 700; }  /* 数字 */
.stat .l { font-size: 11px; color: #8c8c8c; }    /* 标签 */
```

### 表格 — 数据列表
```css
/* 固定列宽，不用 fr 导致大屏留白 */
.task-row {
  grid-template-columns: 320px 55px 145px 85px 85px 90px;
  gap: 16px;           /* 列间距 */
  padding: 10px 20px;  /* 行内边距 */
}
/* 表头居中，首列左对齐 */
.task-row.header { text-align: center; }
.task-row.header span:first-child { text-align: left; }
```

---

## 4. 交互状态

每个可交互元素必须覆盖以下状态：

| 状态 | 实现 |
|------|------|
| **默认** | 基础样式 |
| **Hover** | `background` 微变 + `cursor: pointer` |
| **Active** | 轻微缩放或加深 |
| **Disabled** | `opacity: 0.5` + `cursor: not-allowed` |
| **Loading** | Skeleton / Spinner 占位 |

```css
.btn { transition: all .15s ease; }
.btn:hover { filter: brightness(1.1); }
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .5; cursor: not-allowed; }

/* 行 hover */
.task-row { transition: background .15s; }
.task-row:hover { background: #f5f7fa; }
```

---

## 5. 状态覆盖 (State Coverage)

每个数据区域必须处理四种状态：

| 状态 | 何时显示 | UI 方案 |
|------|---------|---------|
| **Loading** | 数据加载中 | Skeleton 或居中 spinner |
| **Empty** | 无数据 | 图标 + "暂无数据" |
| **Error** | 请求失败 | "加载失败" + 重试按钮 |
| **Data** | 有数据 | 正常渲染 |

```js
// ✅ 四态覆盖
if (loading) return '<div class="loading">加载中...</div>';
if (error) return '<div class="error">加载失败 <button onclick="retry()">重试</button></div>';
if (!data.length) return '<div class="empty">暂无数据</div>';
return data.map(renderRow).join('');
```

---

## 6. 可访问性 (a11y)

| 检查项 | 最低标准 |
|--------|---------|
| 颜色对比度 | 正文 ≥ 4.5:1, 大文字 ≥ 3:1 |
| 可点击区域 | ≥ 44×44px (移动端) / ≥ 24×24px (桌面) |
| 键盘导航 | Tab 可达所有交互元素 |
| 语义化 | 用 `<button>` 而非 `<div onclick>` |
| 焦点可见 | `:focus-visible` 加轮廓 |

```css
/* ✅ 焦点可见 */
.btn:focus-visible, a:focus-visible {
  outline: 2px solid #1890ff;
  outline-offset: 2px;
}

/* ✅ 可选中复制 */
.copyable { user-select: all; cursor: pointer; }
```

---

## 7. 响应式设计

```css
/* 移动端优先：卡片堆叠 */
.stats { grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); }

/* 平板及以上：表格横向滚动 */
@media (max-width: 768px) {
  .task-row { grid-template-columns: 1fr; gap: 4px; }
  .tasks { overflow-x: auto; }
}
```

---

## 8. 仪表盘反模式 (Anti-patterns)

| ❌ 反模式 | ✅ 正确做法 |
|-----------|------------|
| 用 `fr` 单位导致大屏留白 | 用固定 `px` 宽度 |
| 列间距 < 12px 拥挤 | `gap: 16px` 标准间距 |
| 彩色背景 + 白色文字看不清 | 白色背景 + 彩色边框 + 深色字 |
| 全部同字号无层次 | 标题/正文/辅助三级字号 |
| 内容截断不提示 | 加 `title` 属性或 tooltip |
| 无 hover 反馈 | `transition: background .15s` |

---

## 9. 乘用车对标设计模式 (Automotive Benchmarking)

> 参考：Tesla OTA Platform、Bosch ESI[tronic]、Xiaomi 车机管理后台、UN R156 合规要求

### 9.1 行业设计标杆对比

| 特性 | Tesla 风格 | Bosch ESI[tronic] | Xiaomi 风格 | zota-repo 采用 |
|------|-----------|-------------------|------------|---------------|
| **整体风格** | 极简、深色主导、高对比 | 专业工业、信息密集、功能优先 | 清爽现代、卡片化、圆角 | **Glass morphism 深色 + 数据驱动** |
| **Dashboard** | 3D 车辆模型 + 状态概览 | 多面板网格，表格为主 | 大数字卡片 + 趋势迷你图 | StatCard 4 栏 + StatusRing |
| **导航** | 侧边栏图标化、层级浅 | 顶部 Tab + 侧边树形菜单 | 侧边栏图标 + 文字 | 侧边 8 项 icon+label |
| **数据展示** | 大字体关键指标 + 颜色编码 | 密集表格 + 筛选面板 | 图表为主 + 卡片摘要 | 表格 + 卡片混合 |
| **操作反馈** | Toast 顶部居中 | Modal 确认 + 状态列 | 行内操作 + 轻提示 | Popconfirm + message |

### 9.2 设计系统生成提示词（ui-ux-pro-max 风格）

对于新页面设计，使用以下提示词获取设计系统：

```bash
# Dashboard 设计系统
python3 scripts/search.py "fleet management dashboard automotive dark mode glass" --design-system -p "Fleet OS"

# 版本管理页面
python3 scripts/search.py "version control lifecycle management professional industrial" --design-system -p "Version Catalog"

# 数据表格设计
python3 scripts/search.py "data table dense information professional monitoring" --design-system -p "Data Grid"
```

### 9.3 汽车行业专用 UX 规则

| 规则 | 来源 | 实现 |
|------|------|------|
| **状态颜色编码** | Tesla | 🟢 已同步/生产 → `#52c41a`, 🟡 漂移/验证中 → `#faad14`, 🔴 已撤销/严重漂移 → `#ff4d4f` |
| **版本号格式** | Bosch | SemVer `主.次.补丁[-标签]`, 如 `4.1.0-rc1`, `2025.06` |
| **操作确认** | UN R156 | 所有不可逆操作（promote/release/revoke）MUST 二次确认 + 审计记录 |
| **数据密度** | Bosch | 默认每页 20-50 行，支持 10/20/50/100 切换 |
| **实时刷新** | Tesla | 漂移检测 30s 自动刷新，其他页面手动刷新 |
| **搜索优先** | Xiaomi | 全局搜索框置于顶部，支持 VIN/模块名/版本号模糊匹配 |
| **批量操作** | Bosch | 勾选多行 → 底部批量操作栏出现（批量 promote/sync） |
| **导出能力** | Bosch | 所有表格支持 CSV/PDF 导出 |

### 9.4 新增页面设计模板

当需要新增页面时，按以下模板生成：

```
1. [PageHeader] 标题 + 副标题 + 主操作按钮
2. [StatRow]    4 个 StatCard（如适用）
3. [FilterBar]  搜索框 + 状态筛选 + 日期范围
4. [MainContent] 表格 或 卡片网格
5. [DetailPanel] 点击行展开的详情抽屉/面板
```

### 9.5 交付前自检清单（对标 ui-ux-pro-max Pre-Delivery）

**视觉质量：**
- [ ] 间距使用 4px 基准系统（4/8/16/24/32）
- [ ] 颜色对比度 WCAG AA（正文 4.5:1+, 大文字 3:1+）
- [ ] Dark/Light 双模式一致渲染
- [ ] 无水平溢出（表格用 `overflow-x: auto`）

**交互：**
- [ ] 所有按钮有 hover/active/disabled 三态
- [ ] 加载状态有 Skeleton 或 Spinner
- [ ] 空状态有图标 + 引导文案 + CTA
- [ ] 错误状态有友好提示 + 重试按钮
- [ ] 不可逆操作有二次确认

**可访问性：**
- [ ] Tab 键可达所有交互元素
- [ ] `:focus-visible` 焦点环可见
- [ ] 颜色不是唯一的信息传达方式
- [ ] 表格有正确的 `aria-label`

**性能：**
- [ ] 表格默认分页（不一次加载全部）
- [ ] 自动刷新页面设置合理间隔（≥15s）
- [ ] 大列表使用虚拟滚动（>1000 行）
| 无 loading/empty/error 态 | 四态覆盖 |
| 不可复制的关键信息 | `user-select: all` + 点击复制 |

---

## 9. 快速检查清单

部署前自检：

- [ ] 列间距 ≥ 12px（推荐 16px）
- [ ] 表头居中 / 内容左对齐（首列同侧）
- [ ] 字号三级以上（标题 > 正文 > 辅助）
- [ ] 卡片/行有 hover 反馈
- [ ] 关键字段可点击复制
- [ ] Loading / Empty / Error 三态覆盖
- [ ] 按钮有 `:hover` `:active` `:disabled` 样式
- [ ] 颜色对比度可读（不白字浅底）
- [ ] 响应式：移动端不崩
