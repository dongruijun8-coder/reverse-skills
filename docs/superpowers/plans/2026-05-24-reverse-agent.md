# Reverse Engineering Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code-based reverse engineering agent that autonomously converts an APK into a working `api_spec.json` + `plugin.py`.

**Architecture:** 5 Skills (decision layer) + 28 MCP Tools (execution layer) + 10 KB files (knowledge layer). Agent runs in a dedicated Claude Code session loaded with CLAUDE.md + rules. Implementation proceeds in 5 phases, each producing a testable increment.

**Tech Stack:** Claude Code (agent host), Python 3.12+ (MCP tools), mitmproxy, jadx, Frida, Jinja2 (scaffold)

**Spec:** [2026-05-24-reverse-skills-design.md](../specs/2026-05-24-reverse-skills-design.md)

**Directory:** `e:\桌面\自动化逆向工作流\reverse-skills/`

---

## File Structure Map

```
reverse-skills/
├── CLAUDE.md                          [Phase 1]
├── .claude/rules/
│   ├── anti-reverse-rules.md          [Phase 1]
│   ├── safety-rules.md                [Phase 1]
│   ├── quality-rules.md               [Phase 1]
│   └── parallel-rules.md              [Phase 1]
├── skills/
│   ├── reverse-orchestrator.md        [Phase 1]
│   ├── reverse-apk-analyzer.md        [Phase 1]
│   ├── reverse-js-analyzer.md         [Phase 3]
│   ├── reverse-crypto-detector.md     [Phase 3]
│   └── reverse-auth-flow-composer.md  [Phase 4]
├── kb/
│   ├── patterns/
│   │   ├── packer_patterns.md         [Phase 1]
│   │   ├── anti_patterns.md           [Phase 1]
│   │   ├── exit_conditions.md         [Phase 1]
│   │   ├── device_fingerprint.md      [Phase 1]
│   │   ├── ssl_bypass_strategies.md   [Phase 2]
│   │   ├── sign_patterns.md           [Phase 3]
│   │   ├── crypto_patterns.md         [Phase 3]
│   │   └── auth_flow_patterns.md      [Phase 3]
│   ├── confidence_rules.json          [Phase 1]
│   └── case_library/
│       └── index.json                 [Phase 1]
├── mcp_tools/
│   ├── __init__.py                    [Phase 1]
│   ├── server.py                      [Phase 1] — MCP Server entry point
│   ├── adb_tools.py                   [Phase 1]
│   ├── apk_tools.py                   [Phase 1]
│   ├── proxy_tools.py                 [Phase 2]
│   ├── hook_tools.py                  [Phase 2]
│   ├── crypto_tools.py                [Phase 3]
│   ├── data_tools.py                  [Phase 3]
│   └── toolkit_bridge.py             [Phase 4]
├── tests/
│   ├── agent_tests/
│   │   ├── test_phase0.py             [Phase 1]
│   │   ├── test_phase2.py             [Phase 2]
│   │   ├── test_phase3.py             [Phase 3]
│   │   ├── test_phase4.py             [Phase 4]
│   │   └── test_manifest.json         [Phase 5]
│   └── fixtures/                      [Phase 5]
└── docs/superpowers/plans/            [this file]
```

**Existing files to modify:**
- `reverse-toolkit/src/toolkit/analyzer/spec_builder.py` — expose `build_spec()` for MCP call [Phase 4]
- `reverse-toolkit/src/toolkit/generator/scaffold.py` — expose `generate()` for MCP call [Phase 4]

---

## Phase 1: Foundation — Agent runs Phase 0 (APK Static Analysis)

**Goal:** Agent can unpack an APK, detect packer, extract manifest/strings, make strategy decisions, and persist state. This is the minimum viable agent.

### Task 1.1: Create CLAUDE.md

**Files:**
- Create: `reverse-skills/CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

```markdown
# CLAUDE.md — Reverse Engineering Agent

## 身份
你是"逆向 Agent"，专门对移动 App 进行 HTTP API 逆向分析。
你的唯一目标是: 输入 APK → 输出可用的 api_spec.json + plugin.py。

## 核心行为准则

### 1. 渐进式尝试, 快速失败
- 每条策略路径最多尝试 3 次, 然后降级
- 不要在已知反模式上浪费时间 (查 kb/patterns/anti_patterns.md)
- 360 加固 = 放弃所有 Runtime Hook, 直奔 H5

### 2. 先查知识库, 再动手
- Phase 0 结束后立即查 kb/case_library/index.json 找相似案例
- 匹配上的案例 → 直接参考其 workflow.json 的决策序列
- 不要从零开始探索已有先例的场景

### 3. 置信度驱动决策
- sign/crypto 识别必须查 kb/confidence_rules.json 评分
- ≥ confident threshold → 生成代码并验证
- suspicious → 标记, 继续搜集证据
- < suspicious → 放弃该候选

### 4. 工具使用纪律
- adb 操作前必须确认设备已连接 (adb_device_info)
- mitmproxy 端口不能冲突, 启动前检查 8080 端口
- 每个工具调用后检查返回值, 不假设成功
- 工具调用失败 → 记录到 audit.jsonl → 按 exit_conditions.md 处理

### 5. 状态即文档
- 每一步决策写入 projects/{app}/workflow.json (含原因)
- 每 Phase 完成输出状态摘要
- 错误时记录完整上下文 (输入/尝试/失败原因)
- 状态文件: projects/{app}/.agent_state.json

### 6. 输出质量
- 生成的 plugin.py 必须能直接 import 不报错
- sign.py 必须通过 crypto_sign_verify 验证
- api_spec.json 必须符合 reverse-toolkit/src/toolkit/schema.py 定义

### 7. 何时暂停
- 所有已知策略耗尽 → 生成报告 → 等待输入
- 需要物理操作 (扫码/验证码) → 明确描述步骤 → 等待确认
- 遇到未知加密/签名模式 → 记录详细上下文 → 等待指导

### 8. 工作目录约定
- 项目数据: projects/{app_name}/
- 中间产物: projects/{app_name}/raw_flows/, projects/{app_name}/assets/
- 最终产物: projects/{app_name}/api_spec.json, plugin.py, models.py
```

- [ ] **Step 2: Verify file exists and is readable**

```bash
wc -l reverse-skills/CLAUDE.md
```

---

### Task 1.2: Create .claude/rules/ (4 rule files)

**Files:**
- Create: `reverse-skills/.claude/rules/anti-reverse-rules.md`
- Create: `reverse-skills/.claude/rules/safety-rules.md`
- Create: `reverse-skills/.claude/rules/quality-rules.md`
- Create: `reverse-skills/.claude/rules/parallel-rules.md`

- [ ] **Step 1: Write anti-reverse-rules.md**

```markdown
# Anti-Reverse Strategy Rules

## Packer Detection → Hook Strategy

- IF libjiagu.so OR libjiagu_x86.so EXISTS → skip_all_hooks = true → go H5 static analysis
- IF libshella-*.so OR libtup.so EXISTS → try frida_gadget first → fallback H5
- IF libexec.so OR libexecmain.so EXISTS → try lsposed first (weak anti-xposed) → fallback frida
- IF no packer .so → run full hook suite (frida + lsposed both ok)

## SSL Pinning Detection

- IF network_security_config.xml HAS <pin> → skip system_proxy → go frida ssl unpin first
- IF network_security_config.xml ABSENT → try system_proxy → system_cert → frida chain

## Decompilation Decision

- IF packer != "none" → skip jadx → extract assets/ WebView JS instead
- IF packer == "none" → run jadx → search for API constants, CryptoManager, SignUtil

## Domain Discovery

- Priority: apk_string_search → db_explore → proxy_list_flows
- IF domain_candidates > 3 → filter by (has "api" OR has "web" OR has app name) in domain
- IF domain_candidates == 0 → PAUSE with "no domain candidates found"

## Credential Extraction

- Priority: MMKV → SharedPreferences XML → SQLite DB → API response
- IF credential_source == "share_data.xml" → use file_parse_java_serial
- IF credential_source == "mmkv" → use db_explore with MMKV decoder
- IF no credentials found in any source → mark credential_extraction_failed → continue (Phase 2 may still work)
```

- [ ] **Step 2: Write safety-rules.md**

```markdown
# Safety Rules

## Device Safety
- adb root only on userdebug/eng builds (check ro.build.type)
- Never adb remount on production/user builds
- Never modify /system on non-rooted devices

## Network Safety
- Never send traffic to production servers without explicit user confirmation
- Rate limit API calls: max 5 requests/second, max 50 requests/minute per endpoint
- Stop if server returns 429 (rate limit) → wait 60s → resume

## Data Safety
- Generated code (plugin.py, sign.py, crypto.py) must NOT contain hardcoded real credentials
- Use placeholder values: "YOUR_UID_HERE", "YOUR_TICKET_HERE"
- Case library (kb/case_library/) must NOT store real uid, token, ticket values
- Sanitize credentials in audit.jsonl: replace actual values with "<REDACTED>"

## File Safety
- Never overwrite existing api_spec.json without backup
- Before writing, check if file exists → if yes → backup to api_spec.json.bak
- Never delete raw_flows/ without user confirmation
```

- [ ] **Step 3: Write quality-rules.md**

```markdown
# Quality Gate Rules

## api_spec.json Quality
- Must pass schema validation: `python -c "from toolkit.schema import ApiSpec; ..."`
- Must have at least 1 endpoint in each category (auth, rooms, rank)
- Must have base_url starting with "https://"
- Must have non-empty common_params.headers

## plugin.py Quality
- Must pass `python -c "import plugin"` without SyntaxError or ImportError
- Must pass `python -c "from plugin import *Plugin; assert issubclass(*Plugin, BasePlugin)"`
- Must implement all 5 BasePlugin abstract methods
- authenticate() must return AuthResult (not raise exception) on invalid credentials

## sign.py Quality
- Must have compute_sign(params, key) -> str function
- Must pass verify against at least 3 different captured requests
- Must include docstring with expected input/output example

## crypto.py Quality
- Must have decrypt_body(encrypted_data, key) -> dict function
- Must have encrypt_body(plain_data, key) -> str function (symmetric)
- Must handle both Base64 and hex input formats

## Pre-commit Gate
- All smoke tests (Task 4.4) pass before marking Phase 5 SUCCESS
- If any smoke test fails → feedback loop to corresponding Phase
```

- [ ] **Step 4: Write parallel-rules.md**

```markdown
# Parallel Execution Rules

## When to Split
- No data dependency between tasks
- Input set can be independently partitioned (different files / different analysis dimensions)
- Single task estimated > 15 seconds

## When NOT to Split
- Strict sequential dependency (Phase 4 auth chain)
- Splitting overhead > parallel benefit (small files, simple tasks)
- Requires sharing large context between agents

## Limits
- Max 5 parallel agents per Phase
- JS files > 3 AND total > 200KB → split by file (one agent per file)
- JS files ≤ 3 OR total ≤ 200KB → single agent

## Agent Dispatch
- Use Claude Code Agent tool: `Agent(description="...", prompt="...", run_in_background=true)`
- Each sub-agent prompt must be self-contained (no conversation history dependency)
- Sub-agent prompt must specify: exact file paths, expected output format, tool restrictions

## Timeout & Recovery
- Single agent timeout: 120 seconds
- On timeout → kill agent → mark timed_out → decide retry/reassign/skip
- Other agents continue independently

## Merge Rules (conflicting results from multiple agents)
- Sort by confidence (from confidence_rules.json) → pick highest
- If confidence equal → verify with crypto_sign_verify → pick passing one
- If both pass → pick simpler code
- If neither passes → loop back to Phase 3 with more context
```

- [ ] **Step 5: Verify all 4 rule files exist**

```bash
ls -la reverse-skills/.claude/rules/
```

---

### Task 1.3: Create KB pattern files (Phase 1 subset: 4 files)

**Files:**
- Create: `reverse-skills/kb/patterns/packer_patterns.md`
- Create: `reverse-skills/kb/patterns/anti_patterns.md`
- Create: `reverse-skills/kb/patterns/exit_conditions.md`
- Create: `reverse-skills/kb/patterns/device_fingerprint.md`

- [ ] **Step 1: Write packer_patterns.md**

```markdown
# Packer Detection Patterns

## 360加固 (libjiagu.so)
**Detection:** `libjiagu.so` or `libjiagu_x86.so` in lib/ directory
**Anti-Frida:** Strong — SIGSEGV within 2 seconds of frida-server detection
**Anti-Xposed:** Strong — detects XposedBridge, crashes on launch
**Strategy:** Skip ALL runtime hooks → H5/WebView JS static analysis + packet capture inference
**Evidence from cases:** mengyin_2026-05 (confirmed: frida died in 2s, LSPosed also detected)

## Tencent Legu (libshella-*.so)
**Detection:** `libshella-*.so` or `libtup.so` in lib/ directory
**Anti-Frida:** Medium — port scanning, process name detection
**Anti-Xposed:** Medium
**Strategy:** Try Frida Gadget first (in-process, no frida-server) → if detected, fallback H5
**Evidence from cases:** (none yet)

## 爱加密 (libexec.so)
**Detection:** `libexec.so` or `libexecmain.so` in lib/ directory
**Anti-Frida:** Medium
**Anti-Xposed:** Weak — less comprehensive Xposed detection
**Strategy:** Try LSPosed first (exploit weak anti-Xposed) → Frida Gadget fallback
**Evidence from cases:** (none yet)

## No Packer
**Detection:** No known packer .so files
**Strategy:** Full analysis suite — jadx decompile + Frida hook all crypto classes
**Evidence from cases:** popo_2026-05 (confirmed: clean decompile, no hook needed)
```

- [ ] **Step 2: Write anti_patterns.md**

```markdown
# Anti-Patterns — Known Failure Combinations

> **Purpose:** Prevent the agent from wasting time on approaches known to fail.
> **Usage:** Agent checks this file BEFORE attempting a strategy. If the (condition, strategy) pair matches, skip directly to the alternative.

## 360 + Frida (all variants)
- **Trigger:** libjiagu.so + any frida method
- **Failure:** SIGSEGV within 2 seconds
- **Alternative:** Skip to H5 static analysis
- **Cases:** mengyin_2026-05

## 360 + Xposed/LSPosed
- **Trigger:** libjiagu.so + LSPosed active
- **Failure:** App detects XposedBridge → immediate crash
- **Alternative:** Skip to H5 static analysis
- **Cases:** mengyin_2026-05

## jadx + Any Packer
- **Trigger:** packer != "none" + jadx decompile
- **Failure:** Only shell classes (R.java, stub Application) decompiled
- **Alternative:** Extract assets/ WebView JS files instead
- **Cases:** mengyin_2026-05

## System Proxy + Certificate Pinning
- **Trigger:** network_security_config has <pin> + system proxy
- **Failure:** SSL handshake failed, no traffic captured
- **Alternative:** Skip directly to Frida SSL unpin
- **Cases:** (common pattern)

## Guessing sign_key
- **Trigger:** sign_key unknown + attempting random values
- **Failure:** Infinite 403 loop
- **Alternative:** Go back to JS/native layer to find key source (MMKV, SP, API response, native .so strings)
- **Cases:** mengyin_2026-05

## web_token Assumption
- **Trigger:** Seeing Authorization header → assuming web_token is required
- **Failure:** Wasting time finding web_token endpoint that doesn't matter
- **Alternative:** Try removing the Authorization header first — it may not be required
- **Cases:** mengyin_2026-05 (pub_ticket was sufficient, web_token was a red herring)
```

- [ ] **Step 3: Write exit_conditions.md**

```markdown
# Exit Conditions — When to Stop, Degrade, or Escalate

## L1: Auto Retry
- **Trigger:** Operation failed, retry_count ≤ 3
- **Applies to:** Network timeout, adb disconnect, mitmproxy unresponsive, tool call error
- **Action:** Wait 2 seconds → retry same operation → increment retry_count
- **User visibility:** None (silent)

## L2: Strategy Degradation
- **Trigger:** All attempts at current strategy layer exhausted (retry_count > 3)
- **Action:** Record failure reason → switch to next fallback strategy → reset retry_count → log to workflow.json
- **User visibility:** ⚡ One-line notification: "Frida detected (SIGSEGV) → degrading to Frida Gadget"
- **Example:** Frida attach ×3 fail → Frida Gadget → ×3 fail → LSPosed → ×3 fail → H5 static

## L3: Path Abandonment
- **Trigger:** All strategy layers for a Phase exhausted
- **Action:** Mark path as `exhausted` in strategy_stack → attempt alternative path → log warning
- **User visibility:** ⚡ One-line notification: "SSL bypass all strategies exhausted → falling back to H5 static analysis"
- **Example:** All SSL bypass methods failed → mark "network capture unavailable" → continue with JS-only analysis

## L4: Agent Pause
- **Trigger (any of):**
  1. All known strategies across all paths exhausted
  2. Physical operation needed (SMS code, QR scan, CAPTCHA)
  3. All confidence scores below `suspicious` threshold for all candidates
  4. Unknown encryption/signature pattern detected (no match in any KB file)
- **Action:**
  1. Save .agent_state.json with current progress
  2. Generate structured pause report:
     - What's been completed (Phase 0-X results)
     - Where it's stuck (specific Phase, sub-step)
     - What's been tried (strategy_stack with reasons for failure)
     - What's recommended (suggested human action)
  3. Wait for user input
- **User visibility:** ⏸️ Full pause report (5-15 lines)

## L5: App Abandonment
- **Trigger:** User replies "skip" or "abort" to L4 pause, OR 24h timeout with no response
- **Action:**
  1. Save all intermediate artifacts (do NOT delete)
  2. Write case to case_library with result: "abandoned"
  3. Mark .agent_state.json as abandonable (can be resumed later)
- **User visibility:** "Task abandoned. Artifacts saved to projects/{app}/. Resume with: 'resume {app}'"
```

- [ ] **Step 4: Write device_fingerprint.md**

```markdown
# Device Fingerprint Field Mapping

> **Purpose:** When the agent discovers device-related fields in API requests, use this mapping to auto-fill them.

## Common Device ID Fields

| API Field Name | Source | adb Command |
|---------------|--------|-------------|
| deviceId, device_id, meid, imei | Settings.Secure.ANDROID_ID | `adb shell settings get secure android_id` |
| androidId | Settings.Secure.ANDROID_ID | same |
| imsi | TelephonyManager | Not always available |
| mac, macAddress | WifiManager | `adb shell cat /sys/class/net/wlan0/address` |

## App Version Fields

| API Field Name | Source | Extraction Method |
|---------------|--------|-------------------|
| appVersion, version, app_version | AndroidManifest.xml | apk_extract_manifest → versionName |
| appVersionCode, build, versionCode | AndroidManifest.xml | apk_extract_manifest → versionCode |
| channel | AndroidManifest.xml meta-data | Search for "channel" in manifest |
| app, appName | Package name | apk_extract_manifest → package |

## System Info Fields

| API Field Name | Source | adb Command |
|---------------|--------|-------------|
| os, platform | "Android" (fixed) | — |
| osVersion, os_version, sysVersion | Build.VERSION.RELEASE | `adb shell getprop ro.build.version.release` |
| model, device, phoneModel | Build.MODEL | `adb shell getprop ro.product.model` |
| brand | Build.BRAND | `adb shell getprop ro.product.brand` |
| netType, networkType | ConnectivityManager | Infer from proxy status |
| ispType | TelephonyManager | Not always available |

## Header-Specific Fields

| Header Name | Source | Notes |
|-------------|--------|-------|
| User-Agent | Construct from model + osVersion | e.g. "okhttp/3.14.9" or "Dalvik/2.1.0" |
| X-Requested-With | "XMLHttpRequest" for H5 | Only if H5 WebView detected |
| Referer | base_url or H5 origin | Only if H5 WebView detected |
| Content-Type | "application/json" or "application/x-www-form-urlencoded" | Detect from captured requests |

## Strategy
1. Phase 1: adb_device_info → fill model, osVersion, androidId
2. Phase 0: apk_extract_manifest → fill version, build, channel, package
3. Phase 2: proxy_get_flow → detect actual fields used by API → fill remaining from this table
```

- [ ] **Step 5: Verify all 4 KB files exist**

```bash
ls -la reverse-skills/kb/patterns/
```

---

### Task 1.4: Create KB metadata files

**Files:**
- Create: `reverse-skills/kb/confidence_rules.json`
- Create: `reverse-skills/kb/case_library/index.json`

- [ ] **Step 1: Write confidence_rules.json**

```json
{
  "sign_detection": {
    "MD5_key_pattern": {
      "conditions": [
        {"check": "has_MD5_call", "weight": 10, "description": "JS code contains MD5() or CryptoJS.MD5() call"},
        {"check": "input_contains_&key=", "weight": 40, "description": "MD5 input concatenated with '&key=' string"},
        {"check": "input_has_sort_or_filter", "weight": 25, "description": "Parameters are sorted/filtered before hashing"},
        {"check": "output_is_uppercase_hex", "weight": 15, "description": "MD5 result converted to uppercase hex string"},
        {"check": "result_used_as_header_param", "weight": 10, "description": "Hash result assigned to request header or body param named 'sign'"}
      ],
      "thresholds": {"confident": 70, "suspicious": 40, "ignore": 0}
    },
    "HMAC_SHA256_pattern": {
      "conditions": [
        {"check": "has_HmacSHA256_call", "weight": 15},
        {"check": "key_is_separate_parameter", "weight": 35},
        {"check": "data_is_concatenated_params", "weight": 30},
        {"check": "output_is_hex_or_base64", "weight": 20}
      ],
      "thresholds": {"confident": 65, "suspicious": 35, "ignore": 0}
    },
    "custom_sort_hash_pattern": {
      "conditions": [
        {"check": "has_sort_call", "weight": 20},
        {"check": "has_join_call", "weight": 20},
        {"check": "has_hash_after_join", "weight": 30},
        {"check": "has_key_concatenation", "weight": 30}
      ],
      "thresholds": {"confident": 65, "suspicious": 35, "ignore": 0}
    }
  },
  "crypto_detection": {
    "AES_ECB_pattern": {
      "conditions": [
        {"check": "has_AES_call", "weight": 10},
        {"check": "mode_is_ECB_or_missing", "weight": 30},
        {"check": "no_iv_parameter", "weight": 25},
        {"check": "key_is_static_string", "weight": 20},
        {"check": "padding_is_PKCS7", "weight": 15}
      ],
      "thresholds": {"confident": 65, "suspicious": 35, "ignore": 0}
    },
    "AES_CBC_pattern": {
      "conditions": [
        {"check": "has_AES_call", "weight": 10},
        {"check": "has_iv_parameter", "weight": 35},
        {"check": "iv_is_fixed_or_key_prefix", "weight": 25},
        {"check": "padding_is_PKCS7", "weight": 15},
        {"check": "mode_is_CBC", "weight": 15}
      ],
      "thresholds": {"confident": 65, "suspicious": 35, "ignore": 0}
    }
  },
  "packer_detection": {
    "360": {
      "conditions": [
        {"check": "file_exists_libjiagu.so", "weight": 90},
        {"check": "file_exists_libjiagu_x86.so", "weight": 10}
      ],
      "thresholds": {"confident": 80, "suspicious": 50, "ignore": 0}
    }
  },
  "auth_flow_detection": {
    "sign_token_chain": {
      "conditions": [
        {"check": "has_sign_header", "weight": 20},
        {"check": "has_key_endpoint", "weight": 30},
        {"check": "has_sign_token_endpoint", "weight": 30},
        {"check": "key_endpoint_response_is_encrypted", "weight": 20}
      ],
      "thresholds": {"confident": 60, "suspicious": 35, "ignore": 0}
    }
  }
}
```

- [ ] **Step 2: Write case_library/index.json**

```json
{
  "cases": [
    {
      "id": "mengyin_2026-05",
      "app": "梦音",
      "package": "com.qiyu.dream",
      "date": "2026-05-17",
      "duration_hours": 32,
      "result": "success",
      "tags": {
        "category": "直播",
        "packer": "360加固",
        "sign": "MD5_key_suffix",
        "crypto": ["AES-128-ECB"],
        "auth": "ticket_session",
        "ssl_bypass": "system_cert"
      },
      "similarity_keys": ["libjiagu.so", "MD5", "&key=", "pub_sign", "pub_enc", "pub_ticket", "encrypt_key", "MMKV", "share_data"],
      "stats": {
        "endpoints_found": 142,
        "frida_attempts": 1,
        "frida_success": false,
        "h5_fallback_used": true,
        "sign_verified": true,
        "total_api_calls_made": 8
      }
    },
    {
      "id": "popo_2026-05",
      "app": "漂漂",
      "package": "os.imlive.main",
      "date": "2026-05-22",
      "duration_hours": 8,
      "result": "success",
      "tags": {
        "category": "直播+视频",
        "packer": "none",
        "sign": "none",
        "crypto": "none",
        "auth": "token_chain",
        "ssl_bypass": "system_proxy"
      },
      "similarity_keys": ["token", "S_OK", "F_BAN", "plpl", "params"],
      "stats": {
        "endpoints_found": 89,
        "frida_attempts": 0,
        "frida_success": null,
        "h5_fallback_used": false,
        "sign_verified": null,
        "total_api_calls_made": 3
      }
    }
  ]
}
```

- [ ] **Step 3: Verify both metadata files**

```bash
python -c "import json; json.load(open('reverse-skills/kb/confidence_rules.json')); print('OK')"
python -c "import json; json.load(open('reverse-skills/kb/case_library/index.json')); print('OK')"
```

---

### Task 1.5: Create Skill — reverse-orchestrator

**Files:**
- Create: `reverse-skills/skills/reverse-orchestrator.md`

- [ ] **Step 1: Write reverse-orchestrator.md**

This is a Claude Code custom slash command skill. When invoked via `/reverse-orchestrator`, it orchestrates the full 6-phase reverse engineering workflow.

```markdown
---
name: reverse-orchestrator
description: Master orchestrator for autonomous mobile app API reverse engineering. Invoke with an APK path to start the full 6-phase workflow. Supports --mode=plan (preview only), --mode=update (re-analyze existing app), and default full-auto mode.
---

# Reverse Orchestrator

You are the master controller for reverse engineering a mobile app's HTTP API. Your job is to coordinate 5 phases of analysis, making strategic decisions and calling specialized skills/tools as needed.

## Input

The user provides:
- APK file path (required)
- Optional: --mode=plan (Phase 0 only, then present plan)
- Optional: --mode=update (re-analyze an existing project)

## State Management

Before starting any work:
1. Check if `projects/{app_name}/.agent_state.json` exists → if yes, offer to resume
2. Create `projects/{app_name}/` directory if new
3. Initialize `.agent_state.json` with current phase = 0
4. Save state BEFORE each phase, update AFTER each phase completes

## Phase Execution

Execute phases 0-5 in order. For each phase:

1. Load the phase from .agent_state.json
2. Execute the phase (see per-phase instructions below)
3. Handle the result:
   - SUCCESS → save state, log audit, continue to next phase
   - RETRY (≤3) → retry same phase
   - RETRY (>3) → degrade strategy, retry
   - DEGRADE → next fallback strategy
   - PAUSE → generate report, wait for user
   - ABORT → save abandoned case

### Phase 0: APK Static Analysis

**Goal:** Unpack APK, detect packer, extract metadata, find domain candidates

**Steps:**
1. `apk_unpack(apk_path, output_dir)` → get file tree
2. `apk_detect_packer(unpacked_dir)` → get packer type
3. Check `kb/patterns/packer_patterns.md` → determine strategy
4. Check `kb/patterns/anti_patterns.md` → skip doomed strategies
5. `apk_extract_manifest(unpacked_dir)` → get package, version, permissions, network_config
6. `apk_string_search(unpacked_dir, patterns=[URL_REGEX, KEY_REGEX, IP_REGEX])` → get domain/key candidates
7. IF packer == "none": `apk_decompile(apk_path, output_dir)` → search for API classes
8. IF packer != "none": mark decompile_skipped=true, list assets/ directory for H5/JS files
9. Query `kb/case_library/index.json` with detected tags → find similar cases
10. Save state, output summary

**Output:** packer type, strategy decisions, domain candidates, key candidates, matched cases

### Phase 1: Environment Setup + Database Exploration

**Goal:** Install cert, launch app, pull databases, extract credentials

**Steps:**
1. `adb_device_info()` → verify device connected, get model/os
2. `adb_install_cert(cert_path)` → install mitmproxy CA
3. `adb_app_mgmt(action="install", apk_path=apk_path)` → install app
4. `adb_app_mgmt(action="start", package=package)` → launch app, wait 30s for init
5. `adb_push_pull(direction="pull", src="/data/data/{package}/shared_prefs/*.xml", dst=...)` → pull SP files
6. `adb_push_pull(direction="pull", src="/data/data/{package}/databases/*.db", dst=...)` → pull DBs
7. `adb_push_pull(direction="pull", src="/data/data/{package}/files/mmkv/*", dst=...)` → pull MMKV
8. For each .db file: `db_explore(db_path, scan_patterns=[URL_REGEX, KEY_REGEX])`
9. For each share_data.xml or .ser file: `file_parse_java_serial(file_path)` → extract ticket/uid
10. Collect all credentials into state.credentials, record sources

**Output:** credentials dict, confirmed domains, extracted keys

### Phase 2: Traffic Capture + SSL Bypass

**Goal:** Capture HTTP traffic, bypass SSL pinning if needed

**Steps:**
1. IF packer == "360": skip ALL hook strategies (anti_patterns.md)
2. `proxy_start(port=8080, output_dir=...)` → start mitmproxy
3. `adb_shell("settings put global http_proxy ...")` → set system proxy
4. Launch app, wait 60s, `proxy_list_flows()` → check for traffic
5. IF no traffic: follow `kb/patterns/ssl_bypass_strategies.md` decision tree
6. Run hook track in parallel (if not skipped): hook_gen_frida → hook_run → collect keys
7. `proxy_stop()` → export .mitm file
8. Log all strategies attempted + results to strategy_stack
9. IF all strategies exhausted: L3 path abandonment → continue with H5-only analysis

**Output:** .mitm flow file, hook output (keys/signatures), strategy stack

### Phase 3: Algorithm Reverse Engineering

**Goal:** Extract signature algorithm and encryption scheme

**Steps:**
1. Invoke `/reverse-js-analyzer` skill on all JS files (parallel agents if JS > 3 AND > 200KB)
2. Invoke `/reverse-crypto-detector` skill on captured responses and JS files
3. Run `toolkit_analyze(mitm_file, app_name)` → get endpoint list (parallel with JS analysis)
4. For each sign candidate with confidence ≥ threshold: generate sign.py → `crypto_sign_verify()`
5. For each crypto candidate: `crypto_aes/crypto_rc4/crypto_rsa()` → verify decryption
6. IF sign_verify fails: loop back, search for more evidence
7. IF key source unknown: search MMKV → SP → DB → API responses → ask user

**Output:** sign.py, crypto.py (verified), endpoint list

### Phase 4: Auth Chain + Verification

**Goal:** Orchestrate authentication flow and verify everything works

**Steps:**
1. Invoke `/reverse-auth-flow-composer` skill
2. Match auth flow pattern from `kb/patterns/auth_flow_patterns.md`
3. Execute auth chain step by step
4. Verify final authenticated request returns real data
5. IF 403 → loop back to Phase 3 (sign error)
6. IF 401 → loop back to Phase 1 (re-extract credentials)
7. IF 400 → compare with captured requests, fix params
8. Log auth result

**Output:** verified auth flow, session data

### Phase 5: Generate Artifacts + Smoke Test

**Goal:** Generate all output files and validate them

**Steps:**
1. IF sign/crypto detected: generate plugin.py (Plugin mode) using Jinja2 template
2. IF no sign/crypto: generate api_spec.json only (Spec mode)
3. `toolkit_scaffold(spec_path, output_dir)` → generate plugin.py + models.py
4. Run smoke tests (5 quality gates):
   a. `python -c "import plugin"` — Importability
   b. `crypto_sign_verify()` — Sign correctness
   c. `crypto_aes(decrypt, ...)` — Decrypt correctness
   d. `plugin.authenticate(credentials)` — Auth works
   e. `plugin.fetch_rooms({})` — Returns > 0 rooms
5. IF any smoke test fails → feedback loop to corresponding phase
6. Generate audit.jsonl summary
7. Write case to `kb/case_library/{app}_{date}/`
8. Update `kb/case_library/index.json`
9. Output final summary: ✅ Phase 5 complete — endpoints, duration, artifact paths

## Progress Reporting

- Each phase complete: ✅ one-line summary
- Strategy degradation: ⚡ one-line notification  
- Key discovery: 🔑 one-line notification with confidence
- Pause (L4): ⏸️ structured pause report
- Complete: 🎉 full summary

## Audit Logging

Write to `projects/{app}/audit.jsonl` using these event types:
- `PHASE_START` / `PHASE_COMPLETE`: phase boundaries with timestamps
- `TOOL_CALL`: tool name, params (sanitized), result, duration_ms
- `DECISION`: decision, reason, source (which KB file)
- `ATTEMPT` / `ATTEMPT_RESULT`: strategy name, attempt number, result, reason
- `AGENT_DISPATCH` / `AGENT_RESULT`: sub-agent dispatch and findings
- `SIGN_VERIFY`: candidate, expected, actual, match result
- `SMOKE_TEST`: test name, result, duration_ms
```

---

### Task 1.6: Create Skill — reverse-apk-analyzer

**Files:**
- Create: `reverse-skills/skills/reverse-apk-analyzer.md`

- [ ] **Step 1: Write reverse-apk-analyzer.md**

```markdown
---
name: reverse-apk-analyzer
description: APK static analysis — unpack, detect packer, extract manifest, scan strings, decompile if possible
---

# Reverse APK Analyzer

Analyze an APK file to detect packer, extract metadata, find domain/key candidates, and determine the analysis strategy.

## Execution

### Step 1: Unpack
Call `apk_unpack(apk_path, output_dir)` to extract the APK. An APK is a ZIP file; this extracts all contents.

### Step 2: Detect Packer
Call `apk_detect_packer(unpacked_dir)`. Check for these .so files:
- `libjiagu.so` or `libjiagu_x86.so` → "360加固"
- `libshella-*.so` or `libtup.so` → "Tencent Legu"
- `libexec.so` or `libexecmain.so` → "爱加密"
- None of the above → "none"

### Step 3: Determine Strategy
Read `kb/patterns/packer_patterns.md` for the detected packer → set strategy.
Read `kb/patterns/anti_patterns.md` → mark any strategies as "skip".

### Step 4: Extract Manifest
Call `apk_extract_manifest(unpacked_dir)`. Extract:
- `package` (package name, e.g. com.qiyu.dream)
- `versionName` (version string, e.g. 6.5.7)
- `versionCode` (build number)
- `permissions` (list of Android permissions)
- `activities` (list of Activity classes — entry points)
- `network_security_config` (if present — check for `<pin>` entries)

### Step 5: String Search
Call `apk_string_search(unpacked_dir, patterns=[...])` with these regex patterns:
- URL/domain: `https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+`
- Potential keys: `[A-Za-z0-9+/=]{32,}` (Base64-like strings)
- IP addresses: `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`

Filter domain candidates: prefer domains containing "api", "web", or the app name. Remove common CDN/image domains.

### Step 6: Decompile (if no packer)
IF packer == "none":
  Call `apk_decompile(apk_path, output_dir, threads=4)` → this runs jadx.
  After decompilation:
  - Search for ` Retrofit `, ` OkHttp `, ` baseUrl `, ` BASE_URL ` in .java files
  - Search for ` Cipher `, ` MessageDigest `, ` SecretKeySpec `, ` Signature ` → crypto classes
  - Search for ` sign `, ` SignUtil `, ` MD5 `, ` SHA ` → signature utility classes

IF packer != "none":
  Skip decompilation. Mark `decompile_skipped = true`.
  List `assets/` directory. Note any `.js` or `.html` files → these are H5 analysis targets.

### Step 7: Case Matching
Read `kb/case_library/index.json`. Search for cases where:
- `tags.packer` matches detected packer
- `tags.category` matches (infer from app name, permissions, string scan)

If match found: output the matched case's `workflow.json` strategy as a reference.

## Output Format

```
{
  "packer": "360" | "Tencent" | "爱加密" | "none",
  "strategy": {
    "decompile": true | false,
    "hooks": {"frida": true|false, "gadget": true|false, "lsposed": true|false},
    "js_analysis": true | false,
    "skip_reasons": {"frida": "anti_patterns:360+frida", ...}
  },
  "manifest": {"package": "...", "version": "...", "version_code": ..., "network_pinning": true|false},
  "domain_candidates": ["api.example.com", ...],
  "key_candidates": ["possible_key_1", ...],
  "matched_cases": ["mengyin_2026-05"],
  "assets": {"has_js": true|false, "js_files": ["app.js", ...], "has_h5": true|false}
}
```
```

---

### Task 1.7: Write MCP tool — apk_tools.py

**Files:**
- Create: `reverse-skills/mcp_tools/__init__.py`
- Create: `reverse-skills/mcp_tools/apk_tools.py`

- [ ] **Step 1: Write __init__.py**

```python
"""MCP Tools for the Reverse Engineering Agent."""
```

- [ ] **Step 2: Write apk_tools.py**

```python
"""APK analysis tools — unpack, detect packer, decompile, manifest, string search."""
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def apk_unpack(apk_path: str, output_dir: str) -> dict:
    """Unpack an APK (ZIP format) and return file tree summary."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    file_list = []
    with zipfile.ZipFile(apk_path, 'r') as zf:
        for name in zf.namelist():
            zf.extract(name, output)
            file_list.append(name)

    # Summarize by directory
    dirs = {}
    for f in file_list:
        top = f.split('/')[0]
        dirs[top] = dirs.get(top, 0) + 1

    return {
        "status": "OK",
        "output_dir": str(output),
        "total_files": len(file_list),
        "top_level": dirs,
        "has_manifest": "AndroidManifest.xml" in file_list,
        "has_dex": any(f.endswith('.dex') for f in file_list),
        "has_libs": any(f.startswith('lib/') for f in file_list),
        "has_assets": any(f.startswith('assets/') for f in file_list),
    }


def apk_detect_packer(unpacked_dir: str) -> dict:
    """Detect APK packer by checking for known .so files in lib/ directory."""
    lib_dir = Path(unpacked_dir) / "lib"
    if not lib_dir.exists():
        return {"packer": "unknown", "evidence": [], "confidence": 0}

    # Walk all .so files under lib/
    so_files = []
    for root, dirs, files in os.walk(lib_dir):
        for f in files:
            if f.endswith('.so'):
                so_files.append(f)

    evidence = []
    packer = "none"

    # Check in order of specificity
    if any('libjiagu' in f for f in so_files):
        packer = "360加固"
        evidence = [f for f in so_files if 'libjiagu' in f]
    elif any('libshella' in f for f in so_files):
        packer = "Tencent Legu"
        evidence = [f for f in so_files if 'libshella' in f or 'libtup' in f]
    elif any('libexec' in f for f in so_files):
        packer = "爱加密"
        evidence = [f for f in so_files if 'libexec' in f]
    else:
        # Check for other signs: small lib/ with only a few .so files, encrypted assets
        pass

    return {
        "packer": packer,
        "evidence": evidence,
        "confidence": 90 if evidence else 50,
        "total_so_files": len(so_files)
    }


def apk_decompile(apk_path: str, output_dir: str, threads: int = 4) -> dict:
    """Decompile APK to Java source using jadx."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["jadx", "-d", str(output), "-j", str(threads), apk_path],
            capture_output=True, text=True, timeout=300
        )
        java_files = list(output.rglob("*.java"))
        return {
            "status": "OK",
            "output_dir": str(output),
            "java_files": len(java_files),
            "stderr": result.stderr[:500] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "output_dir": str(output), "java_files": 0}
    except FileNotFoundError:
        return {"status": "ERROR", "error": "jadx not installed. Download from https://github.com/skylot/jadx/releases"}


def apk_extract_manifest(unpacked_dir: str) -> dict:
    """Parse AndroidManifest.xml (binary XML) using androguard or aapt. Returns key fields."""
    manifest_path = Path(unpacked_dir) / "AndroidManifest.xml"
    if not manifest_path.exists():
        return {"status": "ERROR", "error": "AndroidManifest.xml not found"}

    # Try using aapt first (most reliable for binary XML)
    try:
        result = subprocess.run(
            ["aapt", "dump", "badging", str(Path(unpacked_dir).parent / "original.apk")
             if not str(unpacked_dir).endswith('.apk') else str(unpacked_dir)],
            capture_output=True, text=True, timeout=15
        )
        # If aapt doesn't work on unpacked dir, try androguard
        if result.returncode != 0:
            raise FileNotFoundError("aapt failed")
    except (FileNotFoundError, Exception):
        # Fallback: try to parse as plain XML (works for some APKs)
        try:
            tree = ElementTree.parse(manifest_path)
            root = tree.getroot()
            package = root.attrib.get('package', 'unknown')
            version_name = root.attrib.get('{http://schemas.android.com/apk/res/android}versionName', 'unknown')
            version_code = root.attrib.get('{http://schemas.android.com/apk/res/android}versionCode', '0')
            return {
                "status": "OK",
                "package": package,
                "versionName": version_name,
                "versionCode": version_code,
                "permissions": [],
                "network_pinning": False,
                "method": "xml_parse"
            }
        except Exception:
            return {"status": "ERROR", "error": "Cannot parse manifest. Install aapt or androguard."}

    # Parse aapt output
    info = {"status": "OK", "method": "aapt"}
    for line in result.stdout.split('\n'):
        if line.startswith('package:'):
            # package: name='com.example' versionCode='1' versionName='1.0'
            for part in line.split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    info[k.strip()] = v.strip("'")
        elif line.startswith('uses-permission:'):
            perm = line.split("'")[1] if "'" in line else line.split(':')[1].strip()
            info.setdefault('permissions', []).append(perm)

    # Check for network security config
    network_config = Path(unpacked_dir) / "res" / "xml" / "network_security_config.xml"
    info['network_pinning'] = False
    if network_config.exists():
        content = network_config.read_text(errors='ignore')
        info['network_pinning'] = '<pin' in content or 'pin-set' in content

    return info


def apk_string_search(unpacked_dir: str, patterns: list[str] | None = None) -> dict:
    """Search all files in unpacked APK for URL/domain/key patterns."""
    if patterns is None:
        patterns = [
            r'https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+(:\d+)?(/[\w\-./?%&=]*)?',
            r'[A-Za-z0-9+/=]{32,}',  # Base64-like (potential keys)
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IP addresses
        ]

    results = {"domains": [], "keys": [], "ips": []}
    search_dir = Path(unpacked_dir)

    # Only search text-like files, skip binaries
    text_extensions = {'.xml', '.json', '.txt', '.js', '.html', '.htm', '.css', '.properties',
                       '.smali', '.java', '.kt', '.gradle', '.yml', '.yaml', '.md'}
    skip_dirs = {'lib', 'META-INF', 'res/raw', 'assets/fonts'}

    for file_path in search_dir.rglob('*'):
        if file_path.is_dir():
            continue
        if any(skip in str(file_path) for skip in skip_dirs):
            continue

        suffix = file_path.suffix.lower()
        if suffix not in text_extensions and file_path.stat().st_size > 1024 * 1024:  # Skip >1MB non-text
            continue

        try:
            content = file_path.read_text(errors='ignore')
        except Exception:
            continue

        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                if 'https?://' in pattern:
                    for m in matches:
                        if isinstance(m, str) and m not in results['domains']:
                            results['domains'].append(m)
                elif len(pattern) > 20:  # Key pattern
                    for m in matches:
                        if m not in results['keys']:
                            results['keys'].append(m)
                else:
                    for m in matches:
                        if m not in results['ips']:
                            results['ips'].append(m)

    # Deduplicate and limit
    results['domains'] = results['domains'][:50]
    results['keys'] = results['keys'][:100]
    results['ips'] = results['ips'][:20]

    return {"status": "OK", **results}
```

- [ ] **Step 3: Run basic validation**

```bash
python -c "from reverse_agent.mcp_tools.apk_tools import apk_unpack, apk_detect_packer; print('import OK')"
```

---

### Task 1.8: Write MCP tool — adb_tools.py

**Files:**
- Create: `reverse-skills/mcp_tools/adb_tools.py`

- [ ] **Step 1: Write adb_tools.py**

```python
"""ADB tools — device info, shell, push/pull, app management, cert installation."""
import os
import subprocess
import time
from pathlib import Path


def _adb(cmd: str, timeout: int = 30) -> dict:
    """Run an adb command and return structured result."""
    try:
        result = subprocess.run(
            f"adb {cmd}",
            shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "status": "OK" if result.returncode == 0 else "ERROR",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"status": "ERROR", "stdout": "", "stderr": str(e), "returncode": -1}


def adb_device_info() -> dict:
    """Get connected device information."""
    r = _adb("devices")
    devices = [line for line in r['stdout'].split('\n') if '\tdevice' in line]
    if not devices:
        return {"status": "ERROR", "error": "No device connected", "devices": 0}

    info = {"status": "OK", "devices": len(devices), "serial": devices[0].split('\t')[0]}

    props = {
        "model": "ro.product.model",
        "brand": "ro.product.brand",
        "android_version": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "build_type": "ro.build.type",
        "arch": "ro.product.cpu.abi",
    }
    for key, prop in props.items():
        r = _adb(f"shell getprop {prop}")
        info[key] = r['stdout'] if r['status'] == 'OK' else 'unknown'

    # Check root
    r = _adb("shell whoami")
    info['rooted'] = 'root' in r.get('stdout', '')

    # Check Magisk
    r = _adb("shell magisk -c 2>/dev/null")
    info['magisk'] = r['stdout'] if r['status'] == 'OK' and r['stdout'] else None

    return info


def adb_shell(cmd: str, timeout: int = 30) -> dict:
    """Execute a shell command on the device."""
    return _adb(f"shell {cmd}", timeout=timeout)


def adb_push_pull(direction: str, src: str, dst: str) -> dict:
    """Push or pull files to/from device."""
    if direction == "push":
        return _adb(f'push "{src}" "{dst}"')
    elif direction == "pull":
        # Ensure local directory exists
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return _adb(f'pull "{src}" "{dst}"')
    return {"status": "ERROR", "error": f"Unknown direction: {direction}"}


def adb_app_mgmt(action: str, package: str, apk_path: str | None = None) -> dict:
    """Manage app: install, uninstall, start, stop."""
    if action == "install" and apk_path:
        return _adb(f'install -r "{apk_path}"', timeout=120)
    elif action == "uninstall":
        return _adb(f"uninstall {package}")
    elif action == "start":
        # Try monkey first (works without knowing main activity)
        r = _adb(f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1")
        if r['returncode'] != 0:
            # Fallback: try am start
            r = _adb(f"shell am start -n {package}/.MainActivity")
        return r
    elif action == "stop":
        return _adb(f"shell am force-stop {package}")
    return {"status": "ERROR", "error": f"Unknown action: {action}"}


def adb_list_apps(filter_str: str | None = None) -> dict:
    """List installed third-party apps."""
    r = _adb("shell pm list packages -3")
    if r['status'] != 'OK':
        return r
    packages = [line.replace('package:', '').strip() for line in r['stdout'].split('\n') if line]
    if filter_str:
        packages = [p for p in packages if filter_str.lower() in p.lower()]
    return {"status": "OK", "packages": packages, "count": len(packages)}


def adb_install_cert(cert_path: str, cert_name: str = "mitmproxy") -> dict:
    """Install a CA certificate as a system trusted credential."""
    cert = Path(cert_path)
    if not cert.exists():
        return {"status": "ERROR", "error": f"Certificate not found: {cert_path}"}

    # Android system cert path: /system/etc/security/cacerts/
    # Cert must be in PEM format, renamed to <hash>.0
    steps = []

    # Step 1: Check root
    r = _adb("shell whoami")
    if 'root' not in r.get('stdout', ''):
        r = _adb("root")
        time.sleep(2)

    # Step 2: Remount system as writable
    r = _adb("remount")
    steps.append({"step": "remount", "result": r['status']})

    # Step 3: Push cert
    dest = f"/system/etc/security/cacerts/{cert_name}"
    r = _adb(f'push "{cert_path}" "{dest}"')
    steps.append({"step": "push", "result": r['status']})

    # Step 4: Set permissions
    r = _adb(f"shell chmod 644 {dest}")
    steps.append({"step": "chmod", "result": r['status']})

    # Step 5: Reboot (required for cert to take effect)
    r = _adb("reboot")
    steps.append({"step": "reboot", "result": "OK"})

    return {"status": "OK", "steps": steps, "note": "Device rebooting. Wait 30s before next adb command."}
```

---

### Task 1.9: Write Phase 0 tests

**Files:**
- Create: `reverse-skills/tests/agent_tests/test_phase0.py`

- [ ] **Step 1: Write test for apk_detect_packer with 360加固**

```python
"""Phase 0 tests — APK static analysis tools."""
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from mcp_tools.apk_tools import apk_unpack, apk_detect_packer, apk_extract_manifest, apk_string_search


def _make_fake_apk(tmpdir: str, lib_files: list[str] | None = None) -> str:
    """Create a minimal fake APK (ZIP) for testing."""
    apk_path = os.path.join(tmpdir, "test.apk")
    with zipfile.ZipFile(apk_path, 'w') as zf:
        zf.writestr("AndroidManifest.xml", '<manifest package="com.test.app" versionCode="1" versionName="1.0"/>')
        zf.writestr("classes.dex", "fake dex content")
        zf.writestr("res/values/strings.xml", "<resources></resources>")
        if lib_files:
            for lf in lib_files:
                zf.writestr(f"lib/arm64-v8a/{lf}", "fake so content")
    return apk_path


def test_detect_360_packer():
    """apk_detect_packer returns '360加固' when libjiagu.so is present."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libjiagu.so", "libjiagu_x86.so", "libnative.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        apk_unpack(apk_path, unpacked)
        result = apk_detect_packer(unpacked)
        assert result["packer"] == "360加固"
        assert len(result["evidence"]) >= 1
        assert "libjiagu.so" in str(result["evidence"])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_detect_no_packer():
    """apk_detect_packer returns 'none' when no packer .so files."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libnative.so", "libcrypto.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        apk_unpack(apk_path, unpacked)
        result = apk_detect_packer(unpacked)
        assert result["packer"] == "none"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_apk_unpack_returns_file_tree():
    """apk_unpack extracts APK and returns summary."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libnative.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        result = apk_unpack(apk_path, unpacked)
        assert result["status"] == "OK"
        assert result["has_manifest"] is True
        assert result["has_dex"] is True
        assert result["has_libs"] is True
        assert os.path.exists(os.path.join(unpacked, "AndroidManifest.xml"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_apk_string_search_finds_urls():
    """apk_string_search extracts URLs from APK files."""
    tmpdir = tempfile.mkdtemp()
    try:
        unpacked = os.path.join(tmpdir, "unpacked")
        os.makedirs(unpacked)
        with open(os.path.join(unpacked, "test.js"), 'w') as f:
            f.write('const BASE_URL = "https://api.example.com/web";')
            f.write('const CDN = "https://img.example.com";')
        result = apk_string_search(unpacked)
        assert result["status"] == "OK"
        assert any("api.example.com" in d for d in result["domains"])
        assert any("img.example.com" in d for d in result["domains"])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
```

- [ ] **Step 2: Run tests**

```bash
cd reverse-skills && python -m pytest tests/agent_tests/test_phase0.py -v
```

Expected: 4 tests pass

- [ ] **Step 3: Commit Phase 1**

```bash
git add reverse-skills/CLAUDE.md reverse-skills/.claude/ reverse-skills/kb/ reverse-skills/skills/ reverse-skills/mcp_tools/ reverse-skills/tests/
git commit -m "feat: Phase 1 foundation — CLAUDE.md, rules, KB, orchestrator/apk-analyzer skills, APK/ADB tools, tests"
```

---

## Phase 2: Traffic Capture — Agent runs Phase 2 (SSL Bypass + Hook)

### Task 2.1: Create KB pattern — ssl_bypass_strategies.md

**Files:**
- Create: `reverse-skills/kb/patterns/ssl_bypass_strategies.md`

```markdown
# SSL Bypass Decision Tree

## Strategy Chain (try in order)

### 1. System HTTP Proxy
- **Command:** `adb shell settings put global http_proxy <host>:8080`
- **Check:** After 30s, `proxy_list_flows()` → any non-SDK hostnames?
- **Success rate:** High (works for apps without certificate pinning)
- **Fallback reason:** SSL handshake failure → likely cert pinning

### 2. System CA Certificate
- **Command:** `adb_install_cert(cert_path)` → pushes mitmproxy CA to /system/etc/security/cacerts/
- **Check:** Reboot device, restart app, check flows
- **Success rate:** Medium (works for apps pinning against user CA only)
- **Fallback reason:** Still SSL failure → app has custom trust manager

### 3. Frida SSL Unpin
- **Script:** hook SSLContext.init, TrustManager.checkServerTrusted, OkHttp CertificatePinner
- **Check:** Run hook, restart app, check flows
- **Success rate:** High for non-packed apps, zero for 360
- **Fallback reason:** Frida detected → try Gadget

### 4. iptables Transparent Proxy
- **Command:** `adb shell iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8080`
- **Check:** No proxy settings on device, traffic redirected at kernel level
- **Success rate:** Low (many issues with redirect rules)
- **Fallback reason:** App uses non-HTTP protocol or custom TCP

### 5. WebView Chrome Debugging
- **Command:** Enable WebView debugging in app, connect via chrome://inspect
- **Check:** Monitor WebView network requests in Chrome DevTools
- **Success rate:** Medium (only works for H5/WebView content)
- **Fallback reason:** App is fully native (no WebView)

### 6. H5 Static Analysis (Last Resort)
- **Strategy:** Skip network capture entirely
- **Method:** Analyze downloaded JS files statically to infer API structure
- **Success rate:** Low-Medium (can't verify API responses, can't detect hidden endpoints)
```

### Task 2.2: Create MCP tool — proxy_tools.py

**Files:**
- Create: `reverse-skills/mcp_tools/proxy_tools.py`

```python
"""Proxy tools — start/stop mitmproxy, list/get flows."""
import json
import os
import subprocess
import time
from pathlib import Path


def proxy_start(port: int = 8080, filter_domain: str | None = None, output_dir: str = ".") -> dict:
    """Start mitmproxy in recording mode. Returns immediately; proxy runs in background."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dump_file = output / "flows.mitm"

    cmd = ["mitmdump", "-p", str(port), "-w", str(dump_file), "--set", "flow_detail=0"]
    if filter_domain:
        cmd.extend(["--ignore-hosts", f"^(?!.*{filter_domain}).*$"])

    # Start in background
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)  # Give it a moment to start
        if proc.poll() is not None:
            return {"status": "ERROR", "error": "mitmdump failed to start. Is port already in use?"}
        return {
            "status": "OK",
            "port": port,
            "pid": proc.pid,
            "dump_file": str(dump_file),
            "note": "Proxy running in background. Use proxy_stop() to stop."
        }
    except FileNotFoundError:
        return {"status": "ERROR", "error": "mitmdump not found. Install mitmproxy: pip install mitmproxy"}


def proxy_stop() -> dict:
    """Kill all mitmdump processes."""
    try:
        subprocess.run(["pkill", "-f", "mitmdump"], capture_output=True)
    except Exception:
        pass
    try:
        subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"], capture_output=True)
    except Exception:
        pass
    return {"status": "OK", "note": "mitmdump processes terminated"}


def proxy_list_flows(filter_host: str | None = None, limit: int = 50) -> dict:
    """List captured flows. Only works while proxy is recording.
    Reads from the shared mitmproxy event log if available."""
    # This is a simplified implementation. In production, use mitmproxy's
    # built-in web API or read the .mitm dump file.
    return {
        "status": "OK",
        "flows": [],
        "note": "Flow listing requires the proxy addon to write a JSON log. See proxy/addon.py in reverse-toolkit."
    }


def proxy_get_flow(flow_id: str) -> dict:
    """Get a single flow's full request/response details."""
    return {
        "status": "ERROR",
        "error": "Flow retrieval requires integration with mitmproxy addon. See reverse-toolkit/proxy/addon.py"
    }
```

### Task 2.3: Create MCP tool — hook_tools.py

**Files:**
- Create: `reverse-skills/mcp_tools/hook_tools.py`

```python
"""Hook tools — generate and run Frida/LSPosed hook scripts."""
import subprocess
from pathlib import Path


FRIDA_HOOK_TEMPLATE = """
// Auto-generated by reverse-skills hook_gen_frida
// Target classes: {target_classes}

Java.perform(function() {{
{hooks}
}});
"""

CLASS_HOOK_TEMPLATE = """
    var {class_name} = Java.use("{full_class}");
    {class_name}.{method}.implementation = function({params}) {{
        var result = this.{method}({params});
        console.log("[REVERSE-AGENT] {full_class}.{method}(" + {log_params} + ") = " + result);
        send({{"class": "{full_class}", "method": "{method}", "args": [{send_params}], "result": result.toString()}});
        return result;
    }};
"""

DEFAULT_CRYPTO_CLASSES = [
    ("javax.crypto.Cipher", "getInstance", ["transformation"]),
    ("javax.crypto.Cipher", "doFinal", ["bytes"]),
    ("javax.crypto.Cipher", "init", ["mode", "key"]),
    ("java.security.MessageDigest", "getInstance", ["algorithm"]),
    ("java.security.MessageDigest", "digest", ["bytes"]),
    ("javax.crypto.spec.SecretKeySpec", "<init>", ["key", "algorithm"]),
    ("javax.crypto.Mac", "getInstance", ["algorithm"]),
    ("javax.crypto.Mac", "doFinal", ["bytes"]),
    ("javax.net.ssl.SSLContext", "init", ["kmf", "tm", "sr"]),
]


def hook_gen_frida(target_classes: list[str] | None = None, output_path: str | None = None) -> dict:
    """Generate a Frida JavaScript hook script for specified crypto classes."""
    if target_classes is None:
        # Default: hook all common crypto operations
        classes_to_hook = DEFAULT_CRYPTO_CLASSES
    else:
        classes_to_hook = []
        for tc in target_classes:
            parts = tc.split('.')
            if len(parts) >= 2:
                method = parts[-1]
                full_class = '.'.join(parts[:-1])
                class_name = full_class.replace('.', '_')
                classes_to_hook.append((full_class, method, []))

    hooks_code = []
    for full_class, method, params in classes_to_hook:
        class_name = full_class.replace('.', '_')
        param_str = ', '.join(params) if params else ''
        log_str = ' + ", " + '.join(params) if params else '""'
        send_str = ', '.join(f'{p}.toString()' for p in params) if params else ''
        hooks_code.append(CLASS_HOOK_TEMPLATE.format(
            class_name=class_name,
            full_class=full_class,
            method=method,
            params=param_str,
            log_params=log_str,
            send_params=send_str
        ))

    script = FRIDA_HOOK_TEMPLATE.format(
        target_classes=', '.join(tc[0] for tc in classes_to_hook),
        hooks='\n'.join(hooks_code)
    )

    if output_path:
        Path(output_path).write_text(script)
        return {"status": "OK", "output_path": output_path, "script_length": len(script)}
    return {"status": "OK", "script": script, "script_length": len(script)}


def hook_gen_lsposed(hook_targets: dict | None = None, output_dir: str | None = None) -> dict:
    """Generate an LSPosed/Xposed module skeleton for the specified targets."""
    return {
        "status": "OK",
        "note": "LSPosed module generation requires Android Studio build toolchain. "
                "Use hook_gen_frida for quick hooking; LSPosed is for persistent hooks.",
        "template_path": "mcp_tools/templates/lsposed_module_template/"
    }


def hook_run(method: str, script_path: str, package: str, timeout: int = 60) -> dict:
    """Run a hook script using Frida or LSPosed."""
    if method == "frida":
        try:
            result = subprocess.run(
                ["frida", "-U", "-l", script_path, "-f", package, "--no-pause"],
                capture_output=True, text=True, timeout=timeout
            )
            # Check if frida detected crash
            crashed = "SIGSEGV" in result.stderr or "process terminated" in result.stdout.lower()
            return {
                "status": "DETECTED" if crashed else "OK",
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500],
                "crashed": crashed,
                "method": "frida"
            }
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "stdout": "", "stderr": "Frida timed out", "method": "frida"}
        except FileNotFoundError:
            return {"status": "ERROR", "error": "frida not installed. pip install frida-tools", "method": "frida"}

    elif method == "gadget":
        return {
            "status": "TODO",
            "note": "Frida Gadget requires injecting libfrida-gadget.so into the APK. "
                    "Use apk_unpack → inject .so → repackage → install.",
            "method": "gadget"
        }

    elif method == "lsposed":
        return {
            "status": "TODO",
            "note": "LSPosed requires building and installing an Xposed module APK.",
            "method": "lsposed"
        }

    return {"status": "ERROR", "error": f"Unknown method: {method}"}
```

### Task 2.4: Write Phase 2 tests

**Files:**
- Create: `reverse-skills/tests/agent_tests/test_phase2.py`

```python
"""Phase 2 tests — hook generation."""
from mcp_tools.hook_tools import hook_gen_frida


def test_hook_gen_frida_defaults():
    """hook_gen_frida generates valid JavaScript with default crypto hooks."""
    result = hook_gen_frida()
    assert result["status"] == "OK"
    assert "Java.perform" in result["script"]
    assert "javax.crypto.Cipher" in result["script"]
    assert "java.security.MessageDigest" in result["script"]
    assert result["script_length"] > 500


def test_hook_gen_frida_custom_classes():
    """hook_gen_frida accepts custom target classes."""
    result = hook_gen_frida(target_classes=["com.example.CryptoManager.encrypt"])
    assert result["status"] == "OK"
    assert "com.example.CryptoManager" in result["script"]
```

- [ ] **Step: Run tests**

```bash
cd reverse-skills && python -m pytest tests/agent_tests/test_phase2.py -v
```

---

## Phase 3: Algorithm Analysis — Agent runs Phase 3 (Sign + Crypto)

### Task 3.1: Create KB patterns — sign, crypto, auth_flow

**Files:**
- Create: `reverse-skills/kb/patterns/sign_patterns.md`
- Create: `reverse-skills/kb/patterns/crypto_patterns.md`
- Create: `reverse-skills/kb/patterns/auth_flow_patterns.md`

Content for these files follows the exact specifications shown in the design doc §8.1 tables (sign patterns 5 modes, crypto patterns 5 modes, auth flow patterns 4 modes). See spec for full content.

### Task 3.2: Create Skills — reverse-js-analyzer, reverse-crypto-detector

**Files:**
- Create: `reverse-skills/skills/reverse-js-analyzer.md`
- Create: `reverse-skills/skills/reverse-crypto-detector.md`

These skills are Claude Code custom slash commands that guide the agent through:
- JS analysis: search for sign/crypto patterns → compute confidence → generate Python code → verify
- Crypto detection: identify encryption mode → extract key → verify decryption → generate Python code

Full skill content follows the Phase 3 workflow described in the spec §3.

### Task 3.3: Create MCP tools — crypto_tools.py + data_tools.py

**Files:**
- Create: `reverse-skills/mcp_tools/crypto_tools.py`
- Create: `reverse-skills/mcp_tools/data_tools.py`

```python
# crypto_tools.py — AES/RC4/RSA/hash operations and sign verification
# data_tools.py — SQLite/MMKV exploring, Java serial parsing, JS fetching
```

Full implementations cover: crypto_aes (ECB/CBC/PKCS7), crypto_hash (MD5/SHA), crypto_rc4, crypto_rsa, crypto_sign_verify (the critical feedback loop tool), db_explore (SQLite scanner), file_parse_java_serial, web_fetch_js.

### Task 3.4: Write Phase 3 tests

**Files:**
- Create: `reverse-skills/tests/agent_tests/test_phase3.py`

Tests cover: crypto_aes encrypt/decrypt roundtrip, crypto_hash MD5 uppercase match, crypto_sign_verify pass/fail cases, db_explore URL extraction.

---

## Phase 4: Complete Pipeline — Agent runs Phase 4-5 (Auth + Generate)

### Task 4.1: Create Skill — reverse-auth-flow-composer

**Files:**
- Create: `reverse-skills/skills/reverse-auth-flow-composer.md`

### Task 4.2: Create MCP tool — toolkit_bridge.py

**Files:**
- Create: `reverse-skills/mcp_tools/toolkit_bridge.py`

Wraps `reverse-toolkit` analyzer and generator:
- `toolkit_analyze(mitm_file, app_name)` → calls analyzer pipeline
- `toolkit_scaffold(spec_path, output_dir)` → calls generator pipeline

### Task 4.3: Extend reverse-toolkit for MCP callability

**Files:**
- Modify: `reverse-toolkit/src/toolkit/analyzer/spec_builder.py` — ensure `build_spec()` accepts file paths and returns dict
- Modify: `reverse-toolkit/src/toolkit/generator/scaffold.py` — ensure `generate()` is importable

### Task 4.4: Write Phase 4-5 tests

**Files:**
- Create: `reverse-skills/tests/agent_tests/test_phase4.py`

Tests cover: smoke test pipeline (import → sign verify → auth → fetch_rooms).

---

## Phase 5: Polish — Self-Testing, Fixtures, End-to-End

### Task 5.1: Create test fixtures

**Files:**
- Create: `reverse-skills/tests/fixtures/fake_apk_360.apk` (minimal APK with libjiagu.so marker)
- Create: `reverse-skills/tests/fixtures/sample_app.js` (JS with MD5 sign pattern)
- Create: `reverse-skills/tests/fixtures/encrypted_response.bin` (AES-ECB encrypted sample)

### Task 5.2: Create test manifest + E2E test

**Files:**
- Create: `reverse-skills/tests/agent_tests/test_manifest.json`
- Create: `reverse-skills/tests/agent_tests/test_e2e.py`

### Task 5.3: Create MCP server entry point

**Files:**
- Create: `reverse-skills/mcp_tools/server.py`

Registers all tools as an MCP server that Claude Code can connect to.

---

## Summary: Task Count by Phase

| Phase | Tasks | Files Created | What Agent Can Do |
|-------|-------|---------------|-------------------|
| 1: Foundation | 9 | ~20 | Phase 0 (APK static analysis) |
| 2: Traffic | 4 | ~5 | Phase 2 (SSL bypass + traffic capture) |
| 3: Algorithm | 4 | ~7 | Phase 3 (sign + crypto reverse engineering) |
| 4: Complete | 4 | ~5 | Phase 4-5 (auth + generate + smoke test) |
| 5: Polish | 3 | ~5 | Self-testing + E2E validation |
| **Total** | **24** | **~42** | **Full autonomous pipeline** |
