#!/usr/bin/env bash
# setup-skills.sh — Clone or update autodrive-skills into workspace .github/
#
# Usage:
#   chmod +x setup-skills.sh
#   ./setup-skills.sh                           # uses current dir as workspace
#   ./setup-skills.sh ~/workspace/autodrive      # specify workspace path

set -euo pipefail

REPO_URL="${SKILLS_REPO_URL:-git@github.com:gottaBoy/my-skills.git}"
WORKSPACE="${1:-$PWD}"

cd "$WORKSPACE" || { echo "ERROR: cannot access $WORKSPACE"; exit 1; }

if [ -d ".github/.git" ]; then
    echo "[UPDATE] .github already exists, pulling latest..."
    cd .github && git pull && cd ..
else
    echo "[CLONE] Cloning skills repo into .github/..."
    git clone "$REPO_URL" .github
fi

if [ $? -eq 0 ]; then
    echo "[OK] Skills are ready. Reload VS Code window to use."
else
    echo "[FAIL] Something went wrong. Check your git setup and SSH keys."
    exit 1
fi
