#!/bin/bash
# Cross-Machine Skills Setup
# 从独立仓库拉取 Skills 到新机器

SKILLS_REPO="https://github.com/YOUR_ORG/autodrive-skills.git"
LOCAL_PATH=".github/skills"

echo "=== Autodrive Skills Setup ==="

# Step 1: 检查是否已存在
if [ -d "$LOCAL_PATH/.git" ]; then
    echo "Skills directory already exists. Updating..."
    git -C "$LOCAL_PATH" pull origin main
else
    echo "Cloning skills repository..."
    
    # 方式 A: git subtree (推荐)
    git subtree add --prefix="$LOCAL_PATH" "$SKILLS_REPO" main --squash
    echo "Skills installed via git subtree!"
fi

# Step 2: 验证
echo ""
echo "=== Verification ==="
SKILL_COUNT=$(find "$LOCAL_PATH" -maxdepth 1 -type d | wc -l)
echo "Skills found: $((SKILL_COUNT - 1))"
echo ""
echo "All set! Type / in Copilot Chat to see available skills."
