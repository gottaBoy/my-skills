# Skill 版本化策略

## 原则

Skills 是代码——用管理代码的方式管理 Skills。

## 版本规则

### 语义化版本 (SemVer)

```
<MAJOR>.<MINOR>.<PATCH>

MAJOR: 流程步骤增减、行为不兼容变更（如删除某个 Gate 步骤）
MINOR: 新增检查项、新增命令，向后兼容
PATCH: 修正拼写、改善措辞、修复链接
```

### Git Tag 约定

```bash
# 标记稳定版本
git tag -a v1.0.0 -m "Initial stable release: 9 skills"

# 标记具体 skill 的变更
git tag -a bug-hunting/v1.1.0 -m "Add DB connection check step"
```

## 变更流程

```
1. 创建功能分支
   git checkout -b skill/update-bug-hunting

2. 修改 SKILL.md
   编辑 .github/skills/bug-hunting/SKILL.md

3. 提交
   git commit -m "skill(bug-hunting): add DB connection check step"

4. PR Review（必须）
   - 至少一人 Review
   - 确认 description 关键词准确
   - 确认命令可实际运行

5. 合并后打 Tag
   git tag -a bug-hunting/v1.1.0
   git push --tags

6. 更新 CHANGELOG
```

## CHANGELOG.md 格式

```markdown
# Changelog

## [v1.1.0] - 2026-07-04

### Added
- spec-generator: 新增结构化规格生成器
- execution-governor: 新增执行纪律框架

### Changed
- copilot-instructions: 重构为 Spec→Harness→Loop 三层模型
- SKILLS_GUIDE: 更新为 9 个 Skills 矩阵

### Fixed
- SYNC_GUIDE: 修正跨电脑同步方案描述
```

## 退役流程

```bash
# 1. 标记为 deprecated
# 在 SKILL.md frontmatter 中添加:
# deprecated: true
# replacedBy: new-skill-name

# 2. 保留一个版本周期后删除
git rm -r .github/skills/old-skill-name/
git commit -m "skill: remove deprecated old-skill-name (replaced by new-skill-name)"
git tag -a old-skill-name/v1.0.0-final

# 3. 更新所有引用此 Skill 的文档
```

## 兼容性承诺

| 版本范围 | 兼容性策略 |
|---------|-----------|
| `v1.x.x` | 不保证兼容；快速迭代阶段 |
| `v2.x.x`+ | MINOR 和 PATCH 向后兼容；MAJOR 需团队评审 |
