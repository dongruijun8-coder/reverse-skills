# Reverse Engineering Agent

> 一条命令安装，自动逆向任意移动 App 的 HTTP API

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 这是什么

基于 Claude Code 的自主逆向工程 Agent。输入一个 APK，自动完成抓包→签名破解→加密识别→认证打通→生成可执行插件。

**5 个 Skill + 28 个 MCP 工具 + 8 个知识库模式 + 自进化反馈机制。**

## 一条命令安装

```bash
# 方式 1: git clone (推荐)
git clone https://github.com/dongruijun8-coder/reverse-skills.git
cd reverse-skills
claude         # 在此目录启动 Claude Code

# 方式 2: 一键脚本 (Windows PowerShell)
irm https://raw.githubusercontent.com/YOUR_USER/reverse-skills/main/install.ps1 | iex

# 方式 3: 一键脚本 (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/reverse-skills/main/install.sh | bash
```

## 快速开始

```
Claude Code 会话中:
用户: "逆向分析这个 APK: /path/to/mengyin.apk"

Agent 自动执行:
  ✅ Phase 0: APK 静态分析 → 检测到 360加固, 跳过反编译, 转 H5 分析
  ✅ Phase 1: 环境准备 → 装证书 → 拉 DB → 提取 ticket  
  ✅ Phase 2: 流量采集 → 系统证书抓包 → 847 flows
  ⚡ Phase 2: Frida 跳过 (360加固)
  ✅ Phase 3: 算法逆向 → MD5+空key 签名 → AES-128-ECB 加密
  ✅ Phase 4: 认证打通 → /app/key → /sign/token → 验证通过
  🎉 Phase 5: 生成 plugin.py + api_spec.json + 142 端点
  📝 发现新模式 → kb/_proposals/ 已记录

总耗时: ~16 min
```

## 文件结构

```
reverse-skills/
├── CLAUDE.md                 Agent 行为准则（Claude Code 自动加载）
├── .claude/rules/            规则文件（自动生效）
├── skills/                   5 个逆向 Skill
├── kb/                       知识库（模式 + 案例 + 提案）
├── mcp_tools/                28 个 MCP 工具
└── tests/                    自测用例
```

## 前置依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| Python 3.12+ | MCP 工具运行 | `winget install python` |
| mitmproxy | HTTP 抓包 | `pip install mitmproxy` |
| adb | 设备控制 | Android SDK Platform Tools |
| jadx (可选) | APK 反编译 | `winget install jadx` |
| Frida (可选) | Runtime Hook | `pip install frida-tools` |

运行 `python preflight.py` 检查所有依赖。

## 更新知识库

Agent 在逆向中发现新模式时会自动写入 `kb/_proposals/`。定期 review 并合并：

```bash
# 查看未合并的提案
ls kb/_proposals/20*.json

# 人工 review 后合并到正式 KB
# 然后删除已合并的提案文件
```
