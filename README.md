# Reverse Skills

> Claude Code 逆向工程 Skill 套件 — 输入 APK，输出可执行插件

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 解决什么问题

移动 App API 逆向常规流程：抓包→绕过 SSL pinning→破解签名算法→破解加密→打通认证→写插件。每个环节都靠人工摸索，加固 App 还要应对检测/崩溃/反调试。一个 App 耗时数小时到数天。

Reverse Skills 把这套流程做成 Claude Code 的 Skill，输入 APK 路径，Claude 自动执行 7 个 Phase，过程中查知识库、匹案例、写 Frida hook、生成插件代码。加固/反检测/签名/加密都有预置策略，失败自动降级。产出 `plugin.py` + `api_spec.json`，可直接接入 Engine 使用。

## 一条命令安装

```bash
git clone https://github.com/dongruijun8-coder/reverse-skills.git
cd reverse-skills
python preflight.py          # 检查依赖
claude                       # 启动 Claude Code
```

安装脚本自动完成：注册 5 个 Skill、注册 41 个 MCP 工具到 Claude Code、添加 `reverse` CLI 到 PATH。

```powershell
# Windows 一键（PowerShell）
irm https://raw.githubusercontent.com/dongruijun8-coder/reverse-skills/main/install.ps1 | iex
```

```bash
# macOS/Linux 一键
curl -fsSL https://raw.githubusercontent.com/dongruijun8-coder/reverse-skills/main/install.sh | bash
```

## 快速开始

```
Claude Code 中:
用户: /reverse-orchestrator /path/to/app.apk

Claude 自动执行:
  Phase 0:   静态分析 → 加固检测 → 策略分流 → 案例匹配
  Phase 0.5: 环境准备 → 启动 hluda/frida → 装证书 → Magisk 绕过
  Phase 1:   装 App → 拉数据库 → 提取凭据
  Phase 2:   抓包 → SSL 绕过 → UI 遍历 → Hook 采集
  Phase 3:   算法逆向 → 签名破解 → 加密破解 → 密钥提取
  Phase 4:   认证打通 → 多步链验证 → Token/IM/MQTT
  Phase 5:   生成 plugin.py + api_spec.json → 冒烟测试 → 案例回写

输出: projects/<app>/plugin.py + api_spec.json + sign.py + crypto.py
```

**断点恢复：** 会话中断后，下次打开 Claude Code 输入 `resume <app名>` 即可从上次中断的 Phase 继续，不丢进度。

## 覆盖能力

### 加固方案（8 种）

| 加固 | .so 特征 | 绕过策略 |
|------|----------|----------|
| 网易易盾 | libnesec.so | hluda attach + Magisk DenyList + 最小化 hook |
| 360 加固 | libjiagu.so | 跳过所有 Hook，纯 H5 静态分析 |
| 腾讯乐固 | libshella-*.so | Frida Gadget → H5 降级 |
| 爱加密 | libexec.so | LSPosed → Frida Gadget 降级 |
| 梆梆加固 | libDexHelper.so | Frida Gadget → H5 降级 |
| 爱加密(旧) | libijmdata.so | 同爱加密 |
| 模拟器检测 | libemulatordetector.so | Magisk Hide + Props Config |
| 无加固 | — | jadx 反编译 + Frida 全量 Hook |

### 签名算法（6 种）

MD5+Key 后缀、HMAC-SHA256、自定义排序哈希、多层嵌套签名、XOR Pair、Native Bridge 签名

### 加密方案（6 种）

AES-128-ECB、AES-128-CBC、AES-GCM、RC4、RSA 公钥、双层加密

### 认证模式（5 种）

Token 链、Sign Token 链、Ticket 会话、多通道认证（HTTP+IM+MQTT+WebSocket）、标准 OAuth2

## 架构

```
Skills（决策层）
  reverse-orchestrator        # 主控 — 7 Phase 调度/策略决策
  reverse-apk-analyzer        # Phase 0 — APK 静态分析
  reverse-js-analyzer         # Phase 3 — JS 签名提取
  reverse-crypto-detector     # Phase 3 — 加密识别
  reverse-auth-flow-composer  # Phase 4 — 认证链编排
       │
MCP 工具层（执行层）— 41 tools
  adb(8)  apk(5)  crypto(5)  data(3)  hook(3)
  pipeline(3)  proxy(4)  state(8)  toolkit(2)
       │
知识层
  kb/patterns/      12 模式库 + 8 Frida 模板 + 退出条件
  kb/case_library/   自动累积案例（含可复用策略）
  kb/_proposals/     自进化提案（Agent 发现新模式自动写入）
```

### Skill vs MCP 工具

| 维度 | Skill（.md 文件） | MCP 工具（.py 函数） |
|------|-------------------|---------------------|
| 做什么 | 决策、编排、分析 | 执行、操作、计算 |
| 谁调用 | Claude 加载后内联执行 | Skill 逻辑中决定调用 |
| 例子 | "匹配案例库 → 加载假设" | `crypto_aes(mode="GCM", ...)` |

## 功能亮点

- **Phase 0.5 环境准备** — 根据加固类型自动选择 hluda/frida-server/Gadget，配 Magisk DenyList
- **Frida 安全指南** — Safe/Dangerous/Unstable 三级操作分类，NIS App 8 条反模式规则
- **Hook 模板库** — T1-T8 共 8 个实战验证模板，一键生成，含 packer 兼容性标注
- **案例复用** — Phase 0 匹配历史案例后自动预加载 sign/crypto/auth/hook 假设
- **分析管线** — JS 自动扫描（sign/key/endpoint 提取）、流量加密信号检测、案例自动匹配
- **断点恢复** — 每个 Phase 前后自动存档，会话中断可恢复，失败自动追踪重试次数
- **冒烟测试** — Phase 5 自动跑 5 项质量门禁，`--quick` 跳过网络测试
- **自进化** — Agent 发现新模式自动写提案到 `kb/_proposals/`，人工 review 后合并
- **平台兼容** — Windows MSYS2 路径自动处理，adb 命令自动加 `MSYS_NO_PATHCONV=1`

## 前置依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| Python 3.12+ | MCP 工具运行 | `winget install python` |
| mitmproxy | HTTP 抓包 | `pip install mitmproxy` |
| adb | 设备控制 | Android SDK Platform Tools |
| jadx (可选) | APK 反编译 | `winget install jadx` |
| Frida (可选) | Runtime Hook | `pip install frida-tools` |

运行 `python preflight.py` 检查所有依赖。

## 文件结构

```
reverse-skills/
├── .claude/
│   ├── skills/                 5 个 Skill 定义（Claude Code 自动发现）
│   └── rules/                  5 个规则文件（auto-loaded）
├── kb/
│   ├── patterns/               12 模式库 + 8 Frida 模板 + 退出条件
│   ├── case_library/           案例索引 + 可复用策略
│   ├── confidence_rules.json   置信度评分规则（10+ 种模式）
│   └── _proposals/             自进化提案
├── mcp_tools/                  41 个 MCP 工具（8 类）+ Server
├── bin/reverse                 CLI 入口（28→41 tools）
├── smoke_test.py               Phase 5 冒烟测试 runner
├── preflight.py                前置依赖检查
├── install.ps1 / install.sh    一键安装脚本
└── skill_workflow_report.md    实战术报告（双鱼部落/60轮/18版Frida）
```

## 更新知识库

逆向过程中 Agent 发现新模式时会自动提交提案到 `kb/_proposals/`，人工 review 后合并：

```bash
ls kb/_proposals/20*.json       # 查看待合并提案
# review → 合并到正式 KB → 删除已合并提案
```
