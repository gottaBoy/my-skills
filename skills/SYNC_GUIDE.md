# Agent Skills 跨电脑同步方案

## 方案总结

| 方案 | 命令 | 适用场景 |
|------|------|---------|
| **Git Clone** | `git clone <repo>` | 团队协作，默认方案 |
| **安装脚本** | `python setup_skills.py` | 新电脑快速初始化 |
| **VS Code Sync** | 自动 | 个人多设备无缝切换 |
| **手动复制** | 见下方 | 最简单直接 |

---

## 方案一：Git Clone（推荐，本项目已支持）

Skills 存放在 `.github/skills/` 目录，随代码一起版本控制：

```bash
# 新电脑上只需克隆项目
git clone <your-repo-url>
cd autodrive
code .
# Skills 自动生效，无需额外配置
```

## 方案二：安装脚本

将 Skills 安装到 VS Code 用户目录（跨项目可用）：

```bash
# Windows / macOS / Linux 通用
python setup_skills.py
```

脚本会自动检测操作系统，将 Skills 复制到 VS Code 用户 prompts 目录。

## 方案三：VS Code Settings Sync

1. 在 VS Code 中启用 Settings Sync（`Ctrl+Shift+P` → `Settings Sync: Turn On`）
2. 登录 GitHub/Microsoft 账号
3. 用户级 Skills（`%APPDATA%/Code/User/prompts/`）自动同步到所有设备

## 方案四：手动复制（备选）

```powershell
# Windows PowerShell
$src = "C:\d\autodrive\.github\skills"
$dst = "$env:APPDATA\Code\User\prompts\skills"
Copy-Item -Recurse $src $dst
```
