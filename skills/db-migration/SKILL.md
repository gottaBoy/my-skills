---
name: db-migration
description: '数据库安全迁移（UP/DOWN回滚脚本）。Database migration workflow with safety checks. Use when: creating/modifying schemas, adding tables/columns, writing migration scripts, running DDL/DML changes.'
---

# Database Migration Skill

## When to Use
- 新增表、修改表结构
- 数据迁移或转换
- 添加索引
- 修改模型后需要同步数据库

## Migration Checklist

### 创建前 (Before)
- [ ] 确认目标数据库（MySQL / TimescaleDB / TDengine）
- [ ] 检查是否有对应的 ORM 模型需要同步更新
- [ ] 评估对现有功能的影响范围
- [ ] 大表操作（>100万行）需要评估锁表时间

### SQL 规范
```sql
-- ✅ 好的写法
ALTER TABLE trips ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active';

-- ❌ 避免：直接删列（应分两次发布）
ALTER TABLE trips DROP COLUMN old_field;
```

### 必须包含回滚脚本
```sql
-- UP (forward)
ALTER TABLE trips ADD COLUMN new_field INT;

-- DOWN (rollback)
ALTER TABLE trips DROP COLUMN new_field;
```

### 创建后 (After)
- [ ] 在测试环境先执行
- [ ] 验证数据完整性
- [ ] 更新 `models.py` / Java Entity 类
- [ ] 更新 API 文档（如有字段变更）
- [ ] 运行相关测试套件

## 本项目数据库速查

| 服务 | 数据库 | ORM |
|------|--------|-----|
| trigger-server | MySQL | PyMySQL (models.py) |
| upload-hub | MySQL | PyMySQL (models.py) |
| jetlinks | MySQL + TimescaleDB | JPA/Hibernate |

## 常用命令
```bash
# trigger-server 建表
cd insight/trigger-server && python mysql_create_drop_table.py

# 查看 MySQL 表结构
mysql -e "DESCRIBE table_name"
```
