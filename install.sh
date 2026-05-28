#!/usr/bin/env bash
# Reverse Skills — 一键安装脚本 (macOS/Linux)
set -e

REPO_URL="https://github.com/dongruijun8-coder/reverse-skills.git"
INSTALL_DIR="${HOME}/.claude/reverse-skills"
USER_SKILLS="${HOME}/.claude/skills"

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

# 3. 每个 Skill 注册为独立目录 + SKILL.md
echo "[REGISTER] 注册 Skills..."
for md in "$INSTALL_DIR/.claude/skills/"*.md; do
    name=$(basename "$md" .md)
    mkdir -p "$USER_SKILLS/$name"
    cp "$md" "$USER_SKILLS/$name/SKILL.md"
    echo "  /$name"
done

# 4. 添加 CLI 到 PATH (Unix)
BIN_DIR="$INSTALL_DIR/bin"
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    echo "[PATH] 添加 reverse CLI..."
    SHELL_RC=""
    [ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"
    [ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"
    if [ -n "$SHELL_RC" ]; then
        echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_RC"
        export PATH="$PATH:$BIN_DIR"
    fi
fi

# 5. 注册 MCP Server 到 Claude Code
SETTINGS="$HOME/.claude/settings.json"
echo "[MCP] 注册 MCP Server..."
if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi
python3 -c "
import json, sys
with open('$SETTINGS') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})
cfg['mcpServers']['reverse-skills'] = {
    'command': 'python3',
    'args': ['$INSTALL_DIR/mcp_tools/server.py', '--mcp']
}
with open('$SETTINGS', 'w') as f:
    json.dump(cfg, f, indent=2)
print('  reverse-skills MCP server -> $SETTINGS')
"

# 6. 环境检查
python3 preflight.py 2>/dev/null || echo "[WARN] 可选依赖未安装"

echo ""
echo "========================================"
echo "  Install complete!"
echo "  Use anywhere: /reverse-orchestrator /path/to/app.apk"
echo "========================================"
