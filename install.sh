#!/usr/bin/env bash
# Reverse Skills — 一键安装脚本 (macOS/Linux)
set -e

REPO_URL="https://github.com/dongruijun8-coder/reverse-skills.git"
INSTALL_DIR="${HOME}/.claude/reverse-skills"
SKILLS_DIR="${HOME}/.claude/skills/reverse-skills"

echo "========================================"
echo "  Reverse Skills 安装"
echo "========================================"
echo ""

command -v git >/dev/null 2>&1 || { echo "[FAIL] 需要 git"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[FAIL] 需要 Python 3.12+"; exit 1; }

# 1. 克隆
if [ -d "$INSTALL_DIR" ]; then
    echo "[UPDATE] 更新已有安装..."
    cd "$INSTALL_DIR" && git pull
else
    echo "[DOWNLOAD] 下载中..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 2. Python 依赖
echo "[PIP] 安装依赖..."
cd "$INSTALL_DIR"
pip3 install mitmproxy click jinja2 pycryptodome -q

# 3. 注册 Skills 到全局
echo "[REGISTER] 注册 Skills..."
mkdir -p "$SKILLS_DIR"
cp "$INSTALL_DIR/.claude/skills/"*.md "$SKILLS_DIR/"

# 4. 环境检查
python3 preflight.py 2>/dev/null || echo "[WARN] 可选依赖未安装"

echo ""
echo "========================================"
echo "  Install complete!"
echo ""
echo "  Skills:"
for f in "$SKILLS_DIR"/*.md; do
    echo "    /$(basename "$f" .md)"
done
echo ""
echo "  Use anywhere: /reverse-orchestrator /path/to/app.apk"
echo "========================================"
