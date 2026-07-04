# Cross-Machine Skills Setup
# 从独立仓库拉取 Skills 到新机器

$SKILLS_REPO = "https://github.com/YOUR_ORG/autodrive-skills.git"
$LOCAL_PATH = ".github/skills"

Write-Host "=== Autodrive Skills Setup ===" -ForegroundColor Cyan

# Step 1: 检查是否已存在
if (Test-Path "$LOCAL_PATH/.git") {
    Write-Host "Skills directory already exists. Updating..." -ForegroundColor Yellow
    git -C $LOCAL_PATH pull origin main
} else {
    Write-Host "Cloning skills repository..." -ForegroundColor Green
    
    # 方式 A: git subtree (推荐——保持 monorepo 结构)
    git subtree add --prefix=$LOCAL_PATH $SKILLS_REPO main --squash
    Write-Host "Skills installed via git subtree!" -ForegroundColor Green
}

# Step 2: 创建 Claude Code agents 符号链接 (Windows)
$CLAUDE_SOURCE = ".claude"
if (Test-Path $CLAUDE_SOURCE) {
    Write-Host "Claude Code agents found in $CLAUDE_SOURCE" -ForegroundColor Green
} else {
    Write-Host "No .claude/ directory found. Create via: mkdir .claude/agents" -ForegroundColor Yellow
}

# Step 3: 验证安装
Write-Host "`n=== Verification ===" -ForegroundColor Cyan
$skillCount = (Get-ChildItem -Path $LOCAL_PATH -Directory).Count
Write-Host "Skills found: $skillCount" -ForegroundColor $(if ($skillCount -gt 0) { "Green" } else { "Red" })
Write-Host "`nAll set! Type / in Copilot Chat to see available skills." -ForegroundColor Cyan
