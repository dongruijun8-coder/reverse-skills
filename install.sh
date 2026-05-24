#!/usr/bin/env bash
# Reverse Engineering Agent — 一键安装脚本 (macOS/Linux)
set -e

REPO_URL="https://github.com/YOUR_USER/reverse-agent.git"
INSTALL_DIR="${HOME}/.claude/reverse-agent"

echo "========================================"
echo "  Reverse Engineering Agent 安装脚本"
echo "========================================"
echo ""

# 检查 git
if ! command -v git &> /dev/null; then
    echo "❌ 需要 git. 请先安装: https://git-scm.com"
    exit 1
fi

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3.12+. 请先安装: https://python.org"
    exit 1
fi

# 克隆
if [ -d "$INSTALL_DIR" ]; then
    echo "📁 目录已存在, 正在更新..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "📥 正在下载..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 安装 Python 依赖
echo ""
echo "📦 安装 Python 依赖..."
cd "$INSTALL_DIR"
pip3 install mitmproxy click jinja2 pycryptodome -q

# 运行环境检查
echo ""
python3 preflight.py 2>/dev/null || true

echo ""
echo "========================================"
echo "  ✅ 安装完成!"
echo ""
echo "  使用方法:"
echo "    cd ${INSTALL_DIR}"
echo "    claude"
echo ""
echo "  然后输入: 逆向分析这个 APK: /path/to/app.apk"
echo "========================================"
