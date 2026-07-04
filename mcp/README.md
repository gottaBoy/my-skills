# MCP Connectors 配置

> MCP (Model Context Protocol) 是 AI Agent 连接外部工具的通用协议。
> 就像 USB-C 连接外设一样，MCP 连接你的工具。

## 推荐安装的 MCP Servers

### 1. GitHub — 让 Agent 操作 Issue 和 PR
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### 2. PostgreSQL — 让 Agent 直接查询数据库
```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/autodrive"
      }
    }
  }
}
```

### 3. Playwright — 让 Agent 操作浏览器做 E2E 测试
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp"]
    }
  }
}
```

### 4. Filesystem — 让 Agent 安全访问文件系统
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "args": ["/path/to/allowed/directory"]
    }
  }
}
```

## 三层发现模式（来自 SoloEngine 的渐进式披露）

| 层级 | 用途 | Token 成本 |
|------|------|-----------|
| 标准发现 | 自动扫描可用 MCP 服务器 | 低（仅元数据） |
| 深度发现 | 按需加载特定工具集 | 中（工具描述） |
| 自定义发现 | 接入自研业务系统 | 高（完整文档） |

## 当前项目推荐连接

| 工具 | MCP Server | 用途 |
|------|-----------|------|
| MySQL | `server-mysql` | 数据库查询、迁移检查 |
| Argo Workflows | 自定义 MCP | 触发分析工作流 |
| Docker | `server-docker` | 容器管理和部署 |
| Slack | `server-slack` | 通知和告警 |
