# Reverse Engineering Agent — 一键安装脚本 (Windows PowerShell)
# 使用方法: irm https://.../install.ps1 | iex

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/YOUR_USER/reverse-agent.git"
$InstallDir = "$env:USERPROFILE\.claude\reverse-agent"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Reverse Engineering Agent 安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 需要 git. 请先安装: https://git-scm.com" -ForegroundColor Red
    exit 1
}

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 需要 Python 3.12+. 请先安装: https://python.org" -ForegroundColor Red
    exit 1
}

# 克隆
if (Test-Path $InstallDir) {
    Write-Host "📁 目录已存在, 正在更新..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
} else {
    Write-Host "📥 正在下载..." -ForegroundColor Yellow
    git clone $RepoUrl $InstallDir
}

# 安装 Python 依赖
Write-Host ""
Write-Host "📦 安装 Python 依赖..." -ForegroundColor Yellow
Set-Location $InstallDir
pip install mitmproxy click jinja2 pycryptodome -q

# 运行环境检查
Write-Host ""
python preflight.py 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  部分可选依赖未安装 (jadx/frida), 不影响核心功能" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ 安装完成!" -ForegroundColor Green
Write-Host ""
Write-Host "  使用方法:" -ForegroundColor White
Write-Host "    cd $InstallDir" -ForegroundColor White
Write-Host "    claude" -ForegroundColor White
Write-Host ""
Write-Host "  然后输入: 逆向分析这个 APK: C:\path\to\app.apk" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green
