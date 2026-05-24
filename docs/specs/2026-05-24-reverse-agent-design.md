# Reverse Engineering Agent — 设计规格说明书

**日期:** 2026-05-24
**状态:** 已确认
**范围:** 逆向 Agent 完整架构 — Skills + MCP 工具 + 知识库 + Engine 集成

---

## 1. 项目概述

### 1.1 目标

构建一个基于 Claude Code 的逆向工程 Agent，输入 APK → 自主完成全流程 → 输出可用的 `api_spec.json` + `plugin.py` + `models.py`。

### 1.2 执行模型

```
用户打开新 Claude Code 会话 →
  工作目录: reverse-skills/ (含 CLAUDE.md + .claude/rules/)
  输入: "逆向分析这个 APK"
  →
  Claude Code 读取 CLAUDE.md → 加载 rules →
  调用 Skill: reverse-orchestrator →
  执行 Phase 0→5 → 输出产物
```

### 1.3 设计原则

- **全自动探索**: Agent 收到 APK 后独立工作，直到生成可用 plugin.py 或确认无法攻克
- **渐进式降级**: 每条策略路径最多尝试 3 次，失败后自动降级到下一层
- **先查知识库再动手**: Phase 0 结束后立即匹配历史案例，避免重复踩坑
- **置信度驱动**: 签名/加密识别基于可量化的评分规则，不是凭感觉
- **默认沉默**: 95% 时间静默运行，只在 3 种场景下暂停等人

---

## 2. 架构总览

### 2.1 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│                   Claude Code Agent (大脑)                    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           逆向 Skills (决策层)                           │   │
│  │  reverse-orchestrator / reverse-apk-analyzer           │   │
│  │  reverse-js-analyzer / reverse-crypto-detector         │   │
│  │  reverse-auth-flow-composer                            │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           MCP 工具层 (执行层) — 28 tools, 7 域          │   │
│  │  ADB(6) / Proxy(4) / Crypto(5) / APK(5)              │   │
│  │  Hook(3) / Data(3) / Toolkit(2)                       │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           知识层 — kb/patterns/ + kb/case_library/     │   │
│  │  模式库(6) + 反模式库(1) + 置信度规则(1)                │   │
│  │  + 退出条件(1) + 案例库(1)                              │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
reverse-skills/
├── CLAUDE.md                    Agent 行为准则
├── .claude/rules/               规则文件
│   ├── anti-reverse-rules.md    反逆向策略硬规则
│   ├── safety-rules.md          安全边界
│   ├── quality-rules.md         质量门禁
│   └── parallel-rules.md        并行决策规则
├── skills/                      5 个 Skill 定义
├── kb/                          知识库
│   ├── patterns/                静态模式库
│   │   ├── sign_patterns.md
│   │   ├── crypto_patterns.md
│   │   ├── packer_patterns.md
│   │   ├── auth_flow_patterns.md
│   │   ├── ssl_bypass_strategies.md
│   │   ├── device_fingerprint.md
│   │   ├── anti_patterns.md
│   │   └── exit_conditions.md
│   ├── confidence_rules.json
│   └── case_library/            动态案例库
│       ├── index.json
│       └── {app}_{date}/
├── mcp_tools/                   MCP 工具实现
├── tests/                       自测用例
│   ├── agent_tests/
│   └── fixtures/
└── docs/specs/                  设计文档
```

---

## 3. 六阶段工作流

```
Phase 0: APK 静态分析 (解包→加固检测→策略分流)
    │
Phase 1: 环境准备 + 数据库探查 (装证书→装App→拉DB→提取凭据)
    │
Phase 2: 流量采集 + SSL 绕过 + Runtime Hook (双轨并行)
    │
Phase 3: 算法逆向 (签名+加密) ← 最大并行加速点
    │
Phase 4: 认证打通 + 验证 ← 含反馈回路
    │
Phase 5: 生成交付物 + 凭据生命周期 + 冒烟测试 → 案例回写
```

### 3.1 反馈回路

Phase 4 验证失败时自动回退：

| 错误 | 含义 | 回退目标 | 修复策略 |
|------|------|----------|----------|
| 403 "Illegal Request" | 签名错误 | → Phase 3 | 重新分析 sign() |
| 401 / "session expired" | 凭据过期 | → Phase 1 | 重新提取 ticket |
| 400 / 参数错误 | 请求体格式不对 | → Phase 2 | 对比抓包修正 |
| 4000 / 登录失败 | 认证流程缺步骤 | → Phase 2 | 重新抓登录流程 |
| 解密乱码 | key/算法不对 | → Phase 3 | 重试其他 key/mode |

---

## 4. Skills 与 MCP 工具 — 边界定义

### 4.0 Skills vs MCP Tools

| 维度 | Skill | MCP Tool |
|------|-------|----------|
| **是什么** | Claude Code 自定义斜杠命令 (Markdown 文件) | Python 函数, 通过 MCP Server 暴露 |
| **谁调用** | Claude Code 的 `Skill` 工具加载后内联执行 | Agent 在 Skill 逻辑中决定调用 |
| **做什么** | 决策、分析、编排 (Judgment) | 执行、操作、计算 (Execution) |
| **例子** | reverse-js-analyzer: 读 JS → 识别签名 → 生成代码 | crypto_aes: 接收 key+data → 返回解密结果 |
| **存哪里** | `skills/*.md` | `mcp_tools/*.py` (注册为 MCP Server) |

**原则**: Skill 做判断, MCP Tool 做执行。Skill 永远不直接操作文件/网络/设备——它通过调用 Tool 来完成。

### 4.1 并行 Agent 的实现

多 Agent 并行通过 Claude Code 内置的 `Agent` 工具实现:
- `Agent(description="...", prompt="...", run_in_background=true)` — 启动后台子 Agent
- 子 Agent 可访问所有 MCP 工具，但看不到主会话上下文
- 主 Skill 等待所有子 Agent 完成后合并结果
- 超时 120s 自动 kill + 重新分配

---

## 5. Skills 清单 (5 个)

| Skill | 职责 | 调用阶段 |
|-------|------|----------|
| **reverse-orchestrator** | 主控循环、阶段调度、策略决策、异常处理 | Phase 0-5 全程 |
| **reverse-apk-analyzer** | APK 解包、加固检测、Manifest分析、资源提取、字符串扫描 | Phase 0 |
| **reverse-js-analyzer** | JS 源码中定位签名/加密函数、提取参数、生成 Python 等价代码 | Phase 3 |
| **reverse-crypto-detector** | 识别请求/响应加密模式、破解密钥、生成解密代码 | Phase 3 |
| **reverse-auth-flow-composer** | 编排多步认证链、提取 token/key、验证 | Phase 4 |

### 5.1 Orchestrator 主控循环

```
FOR phase in [0, 1, 2, 3, 4, 5]:
  result = execute_phase(phase, state)
  IF SUCCESS → 下一 Phase
  ELIF RETRY (≤3次) → 同 Phase 重试
  ELIF RETRY (>3次) → 策略降级 → 同 Phase
  ELIF DEGRADE → 下一 fallback 策略 → 同 Phase
  ELIF PAUSE → 生成报告 → 等人
  ELIF ABORT → 保存 abandoned 案例
```

---

## 6. MCP 工具清单 (28 个, 7 域)

### 6.1 ADB 域 (6 tools)
- `adb_shell` / `adb_push_pull` / `adb_app_mgmt` / `adb_list_apps` / `adb_device_info` / `adb_install_cert`

### 6.2 Proxy 域 (4 tools)
- `proxy_start` / `proxy_stop` / `proxy_list_flows` / `proxy_get_flow`

### 6.3 Crypto 域 (5 tools)
- `crypto_aes` / `crypto_hash` / `crypto_rc4` / `crypto_rsa` / `crypto_sign_verify`

### 6.4 APK 域 (5 tools)
- `apk_unpack` / `apk_detect_packer` / `apk_decompile` / `apk_extract_manifest` / `apk_string_search`

### 6.5 Hook 域 (3 tools)
- `hook_gen_frida` / `hook_gen_lsposed` / `hook_run`

### 6.6 Data 域 (3 tools)
- `db_explore` / `file_parse_java_serial` / `web_fetch_js`

**JS 源码获取两种路径**:
1. APK assets 内嵌 → Phase 0 的 `apk_unpack` 已提取到 `projects/{app}/assets/` → Phase 3 直接分析本地文件
2. 远程 H5 URL → `web_fetch_js(url, extract_links=true)` 下载 + 递归提取内嵌链接 → Agent 优先路径 1 (离线)，路径 1 为空时自动切换路径 2

### 6.7 Toolkit 域 (2 tools)
- `toolkit_analyze` / `toolkit_scaffold` (封装现有 reverse-toolkit/ 管线)

---

## 7. Runtime Hook 分层策略

不依赖第三方工具，Agent 按需生成自有 Hook 脚本：

```
Att 1: Frida attach (hook Cipher/MessageDigest/SecretKeySpec/SSLContext)
   │  ❌ 被检测
   ▼
Att 2: Frida Gadget (注入 so, 不走 frida-server)
   │  ❌ 端口扫描检测
   ▼
Att 3: LSPosed + 自写 Xposed 模块 (Zygote 层注入)
   │  ❌ 检测 Xposed 特征
   ▼
Att 4: 放弃 Runtime Hook → H5 JS 静态分析 + 抓包反推
```

**Phase 0 预判**: 检测到 360 加固(libjiagu.so) → 直接跳过 Att 1-2

---

## 8. 知识库结构 (10 文件)

### 8.1 静态模式库 (kb/patterns/)

| 文件 | 内容 |
|------|------|
| `sign_patterns.md` | 5 种签名模式：MD5+key / HMAC-SHA256 / 自定义排序哈希 / 多层签名 / Native sign |
| `crypto_patterns.md` | 5 种加密模式：AES-ECB / AES-CBC / RC4 / RSA / 双层加密 |
| `packer_patterns.md` | 3 种加固方案：360 / 腾讯Legu / 爱加密 + 对应策略 |
| `auth_flow_patterns.md` | 4 种认证模式：Token链 / 签名Token链 / Ticket会话 / OAuth2 |
| `ssl_bypass_strategies.md` | SSL 绕过决策树 |
| `device_fingerprint.md` | 设备指纹字段映射 |
| `anti_patterns.md` | 已知失败组合 (6+ 条) |
| `exit_conditions.md` | L1-L5 级退出规则 |

### 8.2 置信度规则 (kb/confidence_rules.json)

每种 Pattern 附带加权评分条件。例：MD5+key 模式：

| 条件 | 权重 |
|------|------|
| 有 MD5 调用 | +10 |
| 输入含 `&key=` | +40 |
| 输入有 sort/filter | +25 |
| 输出为大写 hex | +15 |
| 结果用作 header 参数 | +10 |

阈值: ≥70 confident → 生成代码验证 | 40-69 suspicious → 继续搜集证据 | <40 ignore

### 8.3 案例库 (kb/case_library/)

结构化索引 `index.json`，支持精确查询:
```
tags.packer=="360加固" AND tags.category=="直播" → [mengyin_2026-05]
similarity_keys CONTAINS "pub_sign" → [mengyin_2026-05]
```

每个案例包含: INDEX.json + workflow.json + api_spec.json + plugin.py + report.md

### 8.4 退出条件 (L1-L5)

| 级别 | 触发 | 行为 |
|------|------|------|
| L1: 自动重试 | 操作失败, retry ≤ 3 | 等 2s → 重试 |
| L2: 策略降级 | 当前层全部耗尽 | 降级到下一层 |
| L3: 路径放弃 | Phase 所有层耗尽 | 标记 exhausted, 尝试替代路径 |
| L4: Agent 暂停 | 全部策略耗尽/需物理操作/置信度全低/未知模式 | 生成报告 → 等人 |
| L5: App 放弃 | 用户 skip / 超时 | 保存 abandoned 案例 |

---

## 9. 多 Agent 并行策略

### 9.1 各 Phase 并行度

| Phase | 并行度 | 拆分策略 |
|-------|--------|----------|
| Phase 0 | 2-3x | 按文件类型拆分 (manifest / 源码 / 二进制) |
| Phase 1 | 2-3x | 按文件拆分 (每个 DB/文件一个 Agent) |
| Phase 2 | 2x (双轨) | 按目标层拆分 (网络层 vs 运行时层) |
| Phase 3 | 3-5x ⭐ | 按分析维度 + JS 文件拆分 |
| Phase 4 | 1x | 认证链有顺序依赖 |
| Phase 5 | 3x | 按产物拆分 (代码 / 文档 / 归档) |

### 9.2 并行规则

- 拆分条件: 无数据依赖 + 输入可独立分割 + 单任务 > 15s
- 批量上限: 单 Phase 最多 5 个并行 Agent
- 超时: 单 Agent > 120s 无输出 → kill + 重新分配
- 合并: 多结果冲突 → 按置信度 → 实际验证 → 代码简洁度排序

---

## 10. CLAUDE.md + Rules

### 10.1 CLAUDE.md 核心准则

1. **渐进式尝试, 快速失败** — 每条策略 ≤3 次, 不踩已知反模式
2. **先查知识库, 再动手** — Phase 0 后立即匹配 case_library
3. **置信度驱动决策** — 查 confidence_rules.json 评分
4. **工具使用纪律** — 检查前置条件, 验证返回值
5. **状态即文档** — 每一步写入 workflow.json
6. **输出质量** — plugin.py 必须 import 无报错, sign.py 必须通过 verify
7. **适时暂停** — 策略耗尽/物理操作/未知模式 → 等人

### 10.2 Rules 文件

- `anti-reverse-rules.md`: libjiagu.so → skip_all_hooks; network_config pin → skip_system_proxy
- `safety-rules.md`: 不在生产服务器写操作; 生成代码不含硬编码凭据; 案例库不存真实 token
- `quality-rules.md`: api_spec.json 必须通过 schema 验证; plugin.py 无 SyntaxError
- `parallel-rules.md`: Phase 内最多 5 Agent; JS > 3 个且 > 200KB → 拆分

---

## 11. 持久化与恢复

### 11.1 Agent 状态文件

`projects/{app}/.agent_state.json` — 每个 Phase 开始前写入，完成后更新。

```json
{
  "current_phase": 3,
  "phase_status": "IN_PROGRESS",
  "phases": {"0": "DONE", "1": "DONE", "2": "DONE", "3": "RUNNING"},
  "scratch": {"packer": "360", "credentials": {...}, "sign_candidates": [...]},
  "strategy_stack": {"phase_2_ssl": ["system_proxy(fail)", "system_cert(success)"]},
  "resume_point": {"phase": 3, "sub_phase": "3B", "pending_agents": ["B1","B2"]}
}
```

### 11.2 恢复策略

恢复是**用户手动触发**的（打开新会话 → resume）:

| 场景 | 行为 |
|------|------|
| 正常退出 | 用户下次 resume → Agent 读 .agent_state.json → 从 resume_point 继续 |
| 崩溃/会话中断 | 重启 Phase（之前 Phase 的产物保留，不重复执行） |
| 设备断连 | 暂停 → 等人重连后 resume |
| 中间产物损坏 | 自动回退一个 Phase 重新生成 |

**resume 流程**: 用户在新会话输入 "resume mengyin" → Agent 读取 projects/mengyin/.agent_state.json → 从未完成的 Phase 继续。

---

## 12. 进度上报与审计

### 12.1 进度通知 (5 级)

| 时机 | 输出 | 是否打断 |
|------|------|----------|
| Phase 完成 | ✅ 一行摘要 | 否 (通知) |
| 策略降级 | ⚡ 降级原因 | 否 (通知) |
| 关键发现 | 🔑 key/算法 + 置信度 | 否 (通知) |
| L4 暂停 | ⏸️ 完整阶段性报告 | **是 (暂停)** |
| 全部完成 | 🎉 产物路径汇总 | 是 (完成) |

### 12.2 审计日志

`projects/{app}/audit.jsonl` — 每行一个 JSON 事件，7 种类型: PHASE_START/COMPLETE, TOOL_CALL, DECISION, ATTEMPT/RESULT, AGENT_DISPATCH/RESULT, SIGN_VERIFY, SMOKE_TEST。每个决策都可追溯到原因和来源。

---

## 13. 冒烟测试 (5 项质量门禁)

Phase 5 生成代码后自动运行：

| 测试 | 用时 | 失败处理 |
|------|------|----------|
| Importability | < 1s | 🔁 修复 SyntaxError |
| sign() 单元验证 | < 1s | 🔁 回到 Phase 3B |
| decrypt() 单元验证 | < 1s | 🔁 回到 Phase 3C |
| authenticate() | < 5s | 🔁 回到 Phase 4 |
| fetch_rooms() | < 10s | 🔁 对比抓包修正 |

全部通过才标记 SUCCESS，否则进反馈回路。

---

## 14. 前置依赖检查 (Pre-flight)

Agent 启动后、Phase 0 之前运行 6 项检查: Python 包 / ADB + 设备 / mitmproxy / jadx (optional) / frida-tools (optional) / 磁盘空间 (≥2GB)。必须项失败 → abort 并给出修复指令。

---

## 15. 人机交互边界

### 15.1 原则

Agent 95% 时间静默运行。Phase 完成/策略降级/关键发现仅输出一行通知，不打断。

### 15.2 三种暂停场景

| # | 场景 | 触发条件 | Agent 输出 | 用户可回复 |
|---|------|----------|------------|------------|
| 1 | 需要物理操作 | 扫码/验证码/滑块 | 具体操作步骤 | verify_code / skip / abort |
| 2 | 策略耗尽 | L4 退出条件 | 尝试清单+失败原因+建议 | 线索 / skip / abort |
| 3 | 关键确认 | 多候选互斥 | 候选对比+建议 | A/B/帮我决定/都试试 |

### 15.3 交互协议

- 暂停时: 保存 .agent_state.json + 输出结构化暂停消息
- 用户回复: Agent 解析 → 继续执行
- 超时: 24h 无响应 → 自动标记 abandoned (可 resume 恢复)

---

## 16. Plan-First 与 Update 模式

### 16.1 Plan-First 模式

用户先看"作战计划"再决定是否执行：
- Phase 0 完成 → 暂停 → 输出计划（每项附 Why）+ 关键决策点标记 ✋
- 用户: go / 修改策略 / abort
- 用户覆盖写入 workflow.json

### 16.2 Update 模式

App 版本更新时智能复用：
- Load 旧 api_spec.json → Diff 新 APK → 仅重跑有变化的 Phase
- 优先 verify 而非 redo（先用旧 sign() 验证，通过则跳过 Phase 3）
- 全量重跑仅在: packer 变了 / base_url 变了 / sign_verify 失败 / auth 失败且无法修复

---

## 17. 自测体系

### 17.1 测试层级

| 层级 | 测试内容 | 使用案例 |
|------|----------|----------|
| 单元: Packer 检测 | apk_detect_packer + anti_patterns 触发 | 梦音 APK |
| 单元: 签名识别 | sign() 提取 + 置信度 ≥ 90 | 梦音 app.js 片段 |
| 单元: 加密识别 | AES 模式 + encrypt_key + decrypt() | 梦音加密响应 |
| 单元: SSL 决策 | packer=360 → 跳过 Frida | 梦音 manifest |
| 集成: 知识库 | case_library 检索 + anti_patterns 匹配 | 梦音特征向量 |
| 端到端: 全流程 | Phase 0→5 + 冒烟测试全通过 | 梦音 full APK |

### 17.2 测试数据

- 测试用的 APK/JS/响应样本放在 `tests/fixtures/`
- 端到端测试需要模拟器在线
- `tests/agent_tests/test_manifest.json` 定义测试用例

---

## 18. Engine 集成

### 18.1 两种消费路径

| 路径 | 适用场景 | 产物 |
|------|----------|------|
| A: Plugin 模式 | 签名/加密复杂 (梦音级别) | plugin.py + sign.py + crypto.py |
| B: Spec 模式 | 无签名/加密 (漂漂级别) | api_spec.json → GenericPlugin |

Agent 在 Phase 3 判定有签名/加密 → 生成路径 A，否则路径 B。

### 18.2 插件优先级链

```
1. engine/plugins/{app}/plugin.py → 自定义 Plugin (Agent 生成)
2. data/api_specs/{app}.json → GenericPlugin
3. projects/{app}/api_spec.json → GenericPlugin
```

### 18.3 凭据流转

Agent Phase 1 提取 → `projects/{app}/credentials.json` → Engine Dashboard 预填 → Engine db.accounts 表存储 → Plugin.authenticate() 使用。

Plugin 内置 `CREDENTIAL_SOURCES` 元数据，过期时自动尝试从设备重新提取（如 share_data.xml → ticket）。

### 18.4 Dashboard 需改项

1. Plugin/Spec 发现路径: 增加 `projects/{app}/` 搜索
2. 凭据预填: 读取 credentials.json → 自动填入 Dashboard 表单
3. Plugin 信息展示: 显示端点数量、认证类型、加密类型、生成时间
4. 凭据过期告警: check_health() → warning → 标记账号状态
5. Agent 调用提示: Dashboard 显示 CLI 命令提示（Agent 运行在其他会话）

---

## 19. 与前序项目的边界

| 组件 | 关系 | 说明 |
|------|------|------|
| `reverse-toolkit/` | Agent 调用其管线 | toolkit_analyze / toolkit_scaffold 封装现有代码 |
| `engine/` | Agent 产物的消费者 | api_spec.json + plugin.py 供 Engine 运行时使用 |
| `reverse-skills/` | **本项目** | Agent 的 Skills + KB + Tools — 三者连接点 |

`reverse-skills/` 不修改 `reverse-toolkit/` 或 `engine/` 的代码，仅读取和调用。
