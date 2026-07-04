---
name: devops-engineer
description: 'CI/CD pipeline and deployment engineer. Designs GitHub Actions pipelines, Docker configurations, Kubernetes manifests, and deployment strategies. Use when: setting up CI/CD, containerizing applications, designing deployment workflows. Tools: read + write files.'
---

# DevOps Engineer Skill — CI/CD 与部署工作流

## When to Use
- 为新服务配置 CI/CD pipeline
- 容器化应用 (Dockerfile + docker-compose)
- 设计部署策略（蓝绿、金丝雀、滚动）
- K8s manifest 生成
- 环境管理（dev/staging/prod）

## CI/CD Pipeline 模板生成

### GitHub Actions — Python 服务

```yaml
# .github/workflows/ci-python.yml
name: CI - Python Service
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint (ruff)
        run: ruff check .

      - name: Type check (mypy)
        run: mypy . --strict

      - name: Unit tests
        run: python -m pytest tests/ -v --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  build-and-push:
    needs: lint-and-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t ${{ secrets.DOCKER_REGISTRY }}/${{ github.event.repository.name }}:${{ github.sha }} .
      - name: Push
        run: docker push ${{ secrets.DOCKER_REGISTRY }}/${{ github.event.repository.name }}:${{ github.sha }}
```

### GitHub Actions — Next.js 前端

```yaml
# .github/workflows/ci-web.yml
name: CI - Web Frontend
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install
        run: cd web && npm ci

      - name: Lint
        run: cd web && npm run lint

      - name: Type check
        run: cd web && npx tsc --noEmit

      - name: Build
        run: cd web && npm run build

      - name: Test
        run: cd web && npm test
```

### GitHub Actions — Java (Maven) 服务

```yaml
# .github/workflows/ci-java.yml
name: CI - Java Service
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
          cache: 'maven'

      - name: Build & Test
        run: ./mvnw clean verify
```

## Dockerfile 生成规范

### Python (Flask)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
USER 1000
CMD ["python", "app.py"]
```

### Next.js

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --only=production

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

### Java (Spring Boot)

```dockerfile
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY target/*.jar app.jar
RUN addgroup -S app && adduser -S app -G app
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
```

## 部署策略 Checklist

### 选择策略

| 策略 | 适用场景 | 风险 | 回滚时间 |
|------|---------|------|---------|
| **滚动更新** | 无状态服务，可容忍短暂不一致 | 低 | < 1 min |
| **蓝绿部署** | 需要快速回滚 | 中（需要双倍资源） | 秒级 |
| **金丝雀** | 大流量服务，需要渐进验证 | 低 | 分钟级 |

### 部署前检查 (Pre-Deploy Checklist)

- [ ] 所有测试通过（CI 绿灯）
- [ ] Docker image 已构建并推送
- [ ] 数据库迁移已准备（有 DOWN 脚本）
- [ ] 环境变量已配置（Secrets 不硬编码）
- [ ] 健康检查端点可用 (`/health` 或 `/actuator/health`)
- [ ] 监控告警已配置
- [ ] 回滚方案已确认（上一个稳定版本 tag）

### 部署后验证 (Post-Deploy Checklist)

- [ ] 健康检查通过
- [ ] 关键 API 端点 200
- [ ] 错误率无异常上升
- [ ] 响应时间无恶化
- [ ] 数据库迁移执行成功
- [ ] 日志中无异常错误

## docker-compose 生成

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DB_HOST=mysql
      - DB_USER=${MYSQL_USER}
      - DB_PASSWORD=${MYSQL_PASSWORD}
    depends_on:
      mysql:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: autodrive
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]

volumes:
  mysql_data:
```

## 环境管理

```bash
# 配置层级
config/
├── default.yaml       # 默认值（所有环境共用）
├── development.yaml   # 开发环境覆盖
├── staging.yaml       # 预发布环境覆盖
└── production.yaml    # 生产环境覆盖（敏感值用环境变量）

# 加载逻辑
export APP_ENV=production
python app.py  # 加载 default.yaml → production.yaml → 环境变量覆盖
```
