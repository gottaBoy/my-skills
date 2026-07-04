#!/usr/bin/env python3
"""
Loop Runner — 把 Skills 喂给 DeepSeek，让它自主分析 CI 并生成修复方案。

核心安全锚点:
  脚本操作的是 **当前工作目录 (PWD)** 对应的项目仓库。
  在 GitHub Actions 中，PWD 由 checkout 步骤自动设定为目标项目仓库。
  Skills 仓库只提供菜谱，不参与业务变更。

用法:
  python loop_runner.py triage [--repo web]     # 分析目标项目的 CI
  python loop_runner.py fix [--repo web]        # 对目标项目生成修复
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from openai import OpenAI

# ============================================================
# 🔒 安全锚点 — 核心防护
# ============================================================

def get_target_repo() -> str:
    """返回当前操作的目标仓库路径，并验证合法性"""
    pwd = Path.cwd().resolve()

    # 1. 如果显式指定了 --repo，检查它是否是当前目录的子目录
    for i, arg in enumerate(sys.argv):
        if arg == "--repo" and i + 1 < len(sys.argv):
            repo_name = sys.argv[i + 1]
            candidate = pwd / repo_name
            if candidate.exists() and (candidate / ".git").exists():
                return str(candidate)
            print(f"❌ --repo {repo_name}: 不是有效 git 仓库")
            sys.exit(1)

    # 2. 没有 --repo → 当前目录必须是目标项目仓库
    if not (pwd / ".git").exists():
        print("❌ 安全阻断: 当前目录不是 git 仓库")
        print(f"   当前: {pwd}")
        print("   请 cd 到目标项目仓库后运行，或用 --repo 指定")
        sys.exit(1)

    return str(pwd)


def verify_not_skills_repo(target: str):
    """双重保险: 确保不会误操作 Skills 仓库自身"""
    skills_indicator = Path(target) / ".github" / "skills" / "ci-triage"
    if skills_indicator.exists():
        # 当前目标仓库里有 ci-triage skill → 这是 Skills 仓库 → 拒绝
        print("❌ 安全阻断: 检测到目标仓库是 Skills 仓库自身!")
        print(f"   {target}/.github/skills/ci-triage/ 存在")
        print("   本脚本只能操作业务项目仓库, 不能在 Skills 仓库上直接改代码.")
        sys.exit(1)


# ============================================================
# 配置
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("LOOP_MODEL", "deepseek-chat")

# Skills 菜谱位置 — 通过环境变量或自动推导
SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", Path(__file__).parent.parent / "skills"))

# ============================================================
# 核心函数：读取 Skill，调用 DeepSeek
# ============================================================

def load_skill(name: str) -> str:
    """读取指定 Skill 的 SKILL.md"""
    skill_path = SKILLS_DIR / name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


def call_deepseek(system_prompt: str, user_message: str) -> str:
    """调用 DeepSeek API"""
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def run_command(cmd: str) -> str:
    """执行 shell 命令并返回输出"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


# ============================================================
# 任务1: CI Triage — 分析 CI 失败
# ============================================================

def do_triage(target: str):
    """分析目标仓库的 CI 失败"""
    print(f"🔍 Running CI Triage...")
    print(f"   目标仓库: {target}")
    print(f"   菜谱来源: {SKILLS_DIR}")

    # Step 1: 读取 Skill 指令
    skill = load_skill("ci-triage")

    # Step 2: 获取目标仓库最近的提交日志
    os.chdir(target)
    recent_commits = run_command("git log --oneline -20 --since='3 days ago'")

    # Step 3: 把 Skill + 数据 喂给 DeepSeek
    user_msg = f"""⚠️ 重要安全声明:
你正在分析的是仓库 "{target}" 的代码。
这是业务项目仓库，不是 Skills 仓库。
你对这个仓库有完整的读权限。

请按 ci-triage skill 的格式分析以下情况：

目标仓库最近提交:
{recent_commits}

如果这些提交中有常见的 CI 失败模式（语法错误、lint问题、缺少import等），
请按 JSON 格式输出分类结果。如果没有发现明显问题，说 "no issues found"。
"""
    
    result = call_deepseek(f"你是 CI 分析专家。严格按以下 Skill 执行:\n\n{skill}", user_msg)
    
    print("=" * 60)
    print(result)
    print("=" * 60)
    
    # Step 4: 保存结果

    # Step 5: 保存结果
    report_dir = SKILLS_DIR.parent / "loop"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    if command == "triage":
        from datetime import datetime
        filename = f"triage_report_{target_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path = report_dir / filename
        report_path.write_text(f"# CI Triage Report — {target_name}\n\n> 仓库: {target}\n> 时间: {datetime.now().isoformat()}\n\n{result}", encoding="utf-8")
        print(f"📄 Report saved to {report_path}")

    elif command == "fix":
        filename = f"fix_suggestions_{target_name}.md"
        fix_path = report_dir / filename
        fix_path.write_text(f"# Fix Suggestions — {target_name}\n\n> 仓库: {target}\n\n{result}", encoding="utf-8")
        print(f"📝 Fix suggestions saved to {fix_path}")
    
    return result


# ============================================================
# 任务2: Code Fix — 自动修复
# ============================================================

def do_fix(target: str):
    """对目标仓库生成自动修复"""
    print(f"🔧 Running Code Fixer...")
    print(f"   目标仓库: {target}")

    # Step 1: 查找最新的 triage 报告
    report_files = sorted(Path(__file__).parent.parent.glob("loop/triage_report_*.md"), reverse=True)
    if not report_files:
        print("⚠️  No triage report found. Run 'triage' first.")
        return

    last_report = report_files[0].read_text(encoding="utf-8")

    # Step 2: 读取 Skill 指令
    skill = load_skill("code-fixer")

    # Step 3: 检查是否有可自动修复的问题
    if "auto_fixable" not in last_report.lower():
        print("✅ No auto-fixable issues found.")
        return

    # Step 4: 把 Skill + 报告 喂给 DeepSeek
    os.chdir(target)
    user_msg = f"""⚠️ 重要安全声明:
你正在修复仓库 "{target}" 的代码。
这是业务项目仓库，不是 Skills 仓库。
你对这个仓库的 .github/skills/ 目录应该没有写权限。

以下是该仓库最新的 CI Triage 报告。请按 code-fixer skill 的规则，
对报告中标记为 auto_fixable=true 的问题进行修复。

报告:
{last_report}

请给出具体的修复方案和代码修改。每个修改注明目标文件路径。
"""
    
    result = call_deepseek(f"你是代码修复专家。严格按以下 Skill 执行:\n\n{skill}", user_msg)
    
    print("=" * 60)
    print(result)
    print("=" * 60)
    
    # Step 5: 保存修复方案到报告目录
    fix_path = SKILLS_DIR.parent / "loop" / "fix_suggestions.md"
    fix_path.write_text(f"# Fix Suggestions\n\n{result}", encoding="utf-8")
    print(f"📝 Fix suggestions saved to {fix_path}")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("❌ 请设置环境变量: DEEPSEEK_API_KEY=sk-xxx")
        print("   在 GitHub Actions 里配置 Secrets: OPENAI_API_KEY")
        sys.exit(1)

    # 解析 --repo 参数
    command = None
    repo_name = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("triage", "fix"):
            command = arg
        elif arg == "--repo" and i + 1 < len(sys.argv):
            repo_name = sys.argv[i + 1]

    if not command:
        command = "triage"

    # 🔒 安全锚点
    target = get_target_repo()
    verify_not_skills_repo(target)

    target_name = repo_name or Path(target).name
    print(f"{'='*60}")
    print(f"🎯 目标仓库: {target}")
    print(f"📋 执行命令: {command}")
    print(f"{'='*60}")

    if command == "triage":
        do_triage(target)
    elif command == "fix":
        do_fix(target)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python loop_runner.py [triage|fix] [--repo <name>]")
        sys.exit(1)
