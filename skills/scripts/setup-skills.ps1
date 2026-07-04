<#
.SYNOPSIS
    Setup script for autodrive-skills — clone or update the skills repo
    into the workspace root's .github/ directory.
.DESCRIPTION
    Works on Windows (PowerShell), Linux, and macOS (pwsh).
    If .github/ already exists, does a git pull. Otherwise clones fresh.
.EXAMPLE
    cd C:\d\autodrive ; .\.github\skills\scripts\setup-skills.ps1
#>
param(
    [string]$RepoUrl = "git@github.com:gottaBoy/my-skills.git",
    [string]$WorkspacePath = $PWD
)

Set-Location $WorkspacePath

if (Test-Path ".github\.git") {
    Write-Host "[UPDATE] .github already exists, pulling latest..." -ForegroundColor Yellow
    Set-Location .github
    git pull
    Set-Location ..
} else {
    Write-Host "[CLONE] Cloning skills repo..." -ForegroundColor Green
    git clone $RepoUrl .github
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Skills are ready. Reload VS Code window to use." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Something went wrong. Check your git setup and SSH keys." -ForegroundColor Red
}