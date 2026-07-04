# Agent Skills 跨电脑同步方案

> **前置知识**：本 Skills 仓库（`autodrive-skills`）是一个独立的 Git 仓库，clone 到工作空间根目录 `c:\d\autodrive\.github\` 位置。
> VS Code Copilot 基于文件路径发现 skills，不关心 `.github` 是否在某个 git 仓库内。

---

## 四种同步方案

| 方案 | 一句话 | 适用场景 | 技术要求 |
|------|--------|---------|---------|
| **① Clone 到工作空间** | 新电脑上 git clone 到 `.github/` | 团队统一规范 | git |
| **② Clone 到用户目录** | 跨项目、跨 workspace 通用 | 个人多项目 | git |
| **③ VS Code Settings Sync** | 登录账号自动同步 | 个人多设备 | VS Code 账号 |
| **④ 手动复制** | 最简单粗暴 | 临时/离线 | 无 |

---

## 方案①：Clone 到工作空间 `.github/`（推荐）

原理：VS Code Copilot 自动扫描**工作空间根目录**下的 `.github/skills/`，找到 `SKILL.md` 就加载。

```powershell
# 新电脑初始化（一行命令）
cd c:\d\autodrive
git clone git@github.com:gottaBoy/my-skills.git .github

# 完成后打开 VS Code — Skills 自动生效
code .
```

```bash
# 日常更新
cd c:\d\autodrive\.github
git pull   # 拉取最新的 skills
```

⚠️ **注意**：`c:\d\autodrive` 是工作空间根目录，不是 git 仓库。`.github/` 是独立 clone 进来的。

---

## 方案②：Clone 到用户目录（跨项目）

原理：VS Code Copilot 也会扫描用户级 skills 目录。放到这里所有 workspace 都能用。

```powershell
# 安装到用户目录
git clone git@github.com:gottaBoy/my-skills.git $env:APPDATA\Code\User\prompts

# 之后任何 VS Code workspace 都能用到这些 skills
```

| 位置 | 生效范围 |
|------|---------|
| `c:\d\autodrive\.github\skills\` | 仅当前 workspace |
| `%APPDATA%\Code\User\prompts\skills\` | 当前电脑所有 workspace |
| `%APPDATA%\Code\User\prompts\instructions\` | 同上（用户级 instructions） |

---

## 方案③：VS Code Settings Sync

内置能力，无需脚本：
1. `Ctrl+Shift+P` → `Settings Sync: Turn On`
2. 登录 GitHub 或 Microsoft 账号
3. `%APPDATA%\Code\User\` 目录自动同步到所有登录了同一账号的设备

适用场景：个人在多台电脑（公司 + 家里 + 笔记本）无缝切换。

---

## 方案④：手动复制（离线/临时）

```powershell
# 从一台电脑导出
Compress-Archive -Path "c:\d\autodrive\.github\skills\*" -DestinationPath "skills.zip"

# 到另一台电脑导入
Expand-Archive -Path "skills.zip" -DestinationPath "c:\d\autodrive\.github\skills"
```

---

## 方案选择决策树

```
你是团队还是个人？
  ├─ 团队 → 方案①（Clone 到工作空间 .github/）
  │         每个人 clone 到同一个位置，git pull 统一更新
  │
  └─ 个人 → 几台电脑？
              ├─ 1 台 → 方案①（最简单）
              └─ 多台 → 方案③（Settings Sync 自动同步）
                        可选方案②（用户目录 + git）
```
