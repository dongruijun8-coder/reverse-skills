# Reverse Skills — 一键安装脚本 (Windows PowerShell)
# 使用方法: irm https://raw.githubusercontent.com/dongruijun8-coder/reverse-skills/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/dongruijun8-coder/reverse-skills.git"
$InstallDir = "$env:USERPROFILE\.claude\reverse-skills"
$UserSkillsDir = "$env:USERPROFILE\.claude\skills"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Reverse Skills 安装" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] 需要 git: https://git-scm.com" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] 需要 Python 3.12+: https://python.org" -ForegroundColor Red
    exit 1
}

# 1. 克隆代码
if (Test-Path $InstallDir) {
    Write-Host "[UPDATE] 更新已有安装..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
} else {
    Write-Host "[DOWNLOAD] 下载中..." -ForegroundColor Yellow
    git clone $RepoUrl $InstallDir
}

# 2. Python 依赖
Write-Host "[PIP] 安装依赖..." -ForegroundColor Yellow
Set-Location $InstallDir
pip install mitmproxy click jinja2 pycryptodome -q

# 3. 注册每个 Skill 为独立目录 (匹配 Claude Code 的 skill 发现格式)
Write-Host "[REGISTER] 注册 Skills..." -ForegroundColor Yellow
Get-ChildItem "$InstallDir\.claude\skills\*.md" | ForEach-Object {
    $skillName = $_.BaseName
    $skillDir = "$UserSkillsDir\$skillName"
    New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
    Copy-Item -Force $_.FullName "$skillDir\SKILL.md"
    Write-Host "  /$skillName" -ForegroundColor Cyan
}

# 4. 环境检查
Write-Host ""
python preflight.py 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] 部分可选依赖未安装 (jadx/frida)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Install complete! Use anywhere:" -ForegroundColor Green
Write-Host "    /reverse-orchestrator /path/to/app.apk" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
