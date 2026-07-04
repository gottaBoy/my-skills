# Hooks 说明

## 已配置的 Hooks

| Hook 文件 | 触发时机 | 作用 |
|-----------|---------|------|
| `auto-lint.json` | `PostToolUse` (工具调用后) | 自动 ruff lint + format Python 文件 |
| `block-dangerous.json` | `PreToolUse` (工具调用前) | 阻止危险终端命令 (rm -rf 等) |

## VS Code Hooks 支持的事件

| 事件 | 触发时机 |
|------|---------|
| `SessionStart` | 会话开始 |
| `UserPromptSubmit` | 用户提交消息 |
| `PreToolUse` | 工具调用**前** |
| `PostToolUse` | 工具调用**后** |
| `PreCompact` | 上下文压缩前 |
| `Stop` | Agent 停止 |

## 自定义 Hook

```json
{
  "PreToolUse": [
    {
      "type": "command",
      "command": "<你的 shell 命令>",
      "windows": "<Windows 专用命令>",
      "linux": "<Linux 专用命令>",
      "osx": "<macOS 专用命令>",
      "cwd": "<工作目录>",
      "timeout": 10
    }
  ]
}
```

## 环境变量

Hooks 可以访问以下环境变量：
- `ARG_FILE`: 正在操作的文件路径
- `ARG_TOOL`: 被调用的工具名
- `ARG_COMMAND`: 被执行的命令（对于终端工具）
