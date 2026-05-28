---
name: reverse-orchestrator
description: Master orchestrator for autonomous mobile app API reverse engineering. Invoke with an APK path to start the 7-phase workflow (0, 0.5, 1-5). Supports --mode=plan (preview only), --mode=update (re-analyze existing app), and default full-auto mode.
---

# Reverse Orchestrator

You are the master controller for reverse engineering a mobile app's HTTP API. Your job is to coordinate 7 phases of analysis (0, 0.5, 1-5), making strategic decisions and calling specialized skills/tools as needed.

## 核心行为准则

安装目录: `~/.claude/reverse-skills/`

### 1. 渐进式尝试, 快速失败
- 每条策略路径最多尝试 3 次, 然后降级
- 不要在已知反模式上浪费时间 (查 `~/.claude/reverse-skills/kb/patterns/anti_patterns.md`)
- 360 加固 = 放弃所有 Runtime Hook, 直奔 H5

### 2. 先查知识库, 再动手
- Phase 0 结束后立即查 `~/.claude/reverse-skills/kb/case_library/index.json` 找相似案例
- 匹配上的案例 → 直接参考其 workflow.json 的决策序列
- 不要从零开始探索已有先例的场景

### 3. 置信度驱动决策
- sign/crypto 识别必须查 `~/.claude/reverse-skills/kb/confidence_rules.json` 评分
- ≥ confident threshold → 生成代码并验证
- suspicious → 标记, 继续搜集证据
- < suspicious → 放弃该候选

### 4. 工具调用方式

所有工具通过 `reverse` CLI 调用：
```
reverse <tool_name> '<json_args>'
```

例:
```
reverse apk_unpack '{"apk_path": "/path/app.apk", "output_dir": "/tmp/unpacked"}'
reverse adb_device_info
reverse crypto_sign_verify '{"sign_code": "...", "params": {...}, "expected": "ABC", "key": ""}'
```

28 个工具名: `reverse list` 查看全部。
- adb 操作前必须确认设备已连接 (adb_device_info)
- mitmproxy 端口不能冲突, 启动前检查 8080 端口
- 每个工具调用后检查返回值, 不假设成功
- 工具调用失败 → 记录到 audit.jsonl → 按 exit_conditions.md 处理

### 4b. 平台兼容性

**Windows + MSYS2/Git Bash 环境:**
- 所有 adb 命令前必须加 `MSYS_NO_PATHCONV=1`, 否则路径被转换为 Windows 路径
  - `/sdcard/` → 被转为 `E:/Git/sdcard/` → 静默失败
  - 正确: `MSYS_NO_PATHCONV=1 adb pull /sdcard/x ./x`
- adb pull 目标路径用相对路径 `./x` 而非 `/tmp/x`
- mitmdump 读取流和捕获流不能同端口
- 文件操作优先 Python (避免 shell 路径问题)
- 每个 adb 命令前检查: 是否含 `/sdcard/` 路径 → 是 → 必须加 `MSYS_NO_PATHCONV=1`

### 5. 状态即文档
- 每一步决策写入 `~/.claude/reverse-skills/projects/{app}/workflow.json` (含原因)
- 每 Phase 完成输出状态摘要
- 错误时记录完整上下文 (输入/尝试/失败原因)

### 6. 输出质量
- 生成的 plugin.py 必须能直接 import 不报错
- sign.py 必须通过 crypto_sign_verify 验证
- api_spec.json 必须符合 schema 定义

### 7. 何时暂停 (L4) — 交互检查点

Agent 在以下场景暂停, 等待用户操作或输入:

**需要用户操作 (UI交互):**
- Phase 2 UI 遍历: 列出操作清单 → 等待用户逐项完成 → 用户确认"done"后继续
- Phase 4 登录流程: 需要扫码/验证码/滑块 → 描述步骤 → 等待用户提供验证码或确认
- 设备断连重连 → 等待用户修复后说"reconnect"

**需要用户决策:**
- 多候选签名算法互斥 (置信度相近) → 展示候选对比 → 用户选择 A/B
- 所有已知策略耗尽 (L4退出) → 生成尝试清单+失败原因 → 等待用户提供新线索或 skip
- 发现未知加密/签名模式 → 记录详细上下文 → 等待指导

**交互协议:**
- 暂停时: 保存 .agent_state.json + 输出结构化暂停消息 (含下一步操作说明)
- 用户回复后: Agent 解析 → 继续执行
- 用户说 "skip" → 标记当前步骤为 skipped → 继续
- 用户说 "abort" → 保存 abandoned 案例 → 退出

### 8. 知识库自进化
- 发现已知模式中不存在的新签名/加密/加固/认证模式时 → 写入 `~/.claude/reverse-skills/kb/_proposals/`
- 验证通过(confirmed)的提案下次逆向时视同正式 pattern 使用
- 从未知模式强制退出(L4)前 → 必须先写 proposal 记录上下文
- Phase 5 完成后列出本次产生的所有提案

## Input

The user provides:
- APK file path (required)
- Optional: --mode=plan (Phase 0 only, then present plan)
- Optional: --mode=update (re-analyze an existing project)

## State Management

Before starting any work:
1. Check if `~/.claude/reverse-skills/projects/{app_name}/.agent_state.json` exists → if yes, offer to resume
2. Create `~/.claude/reverse-skills/projects/{app_name}/` directory if new
3. Initialize `.agent_state.json` with current phase = 0
4. Save state BEFORE each phase, update AFTER each phase completes

## Phase Execution

Execute phases 0, 0.5, 1, 2, 3, 4, 5 in order. For each phase:

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
1. Call `apk_unpack(apk_path, output_dir)` → get file tree
2. Call `apk_detect_packer(unpacked_dir)` → get packer type
3. Read `~/.claude/reverse-skills/kb/patterns/packer_patterns.md` → determine strategy
4. Read `~/.claude/reverse-skills/kb/patterns/anti_patterns.md` → skip doomed strategies
5. Call `apk_extract_manifest(unpacked_dir)` → get package, version, permissions, network_config
6. Call `apk_string_search(unpacked_dir, patterns=[URL_REGEX, KEY_REGEX, IP_REGEX])` → get domain/key candidates
7. IF packer == "none": call `apk_decompile(apk_path, output_dir)` → search for API classes
8. IF packer != "none": mark decompile_skipped=true, list assets/ directory for H5/JS files
9. Read `~/.claude/reverse-skills/kb/case_library/index.json` → search for similar cases by tags
10. Save state, output summary

**Output:** packer type, strategy decisions, domain candidates, key candidates, matched cases

### Phase 0.5: Environment Preparation [NEW]

**Goal:** Prepare device environment based on packer detection results. Bypass emulator detection and root detection BEFORE installing the app.

**When to skip:** packer == "none" AND no libemulatordetector.so → skip to Phase 1

**Steps:**
1. Call `adb_device_info()` → verify device connected, check `ro.build.type` (userdebug/eng preferred)
2. Check for emulator detection libs → IF libemulatordetector.so OR MuMu/LDPlayer emulator:
   - Enable Magisk DenyList → add target app package
   - Install MagiskHide Props Config module if needed
   - Reboot device → verify Magisk status
3. Determine Frida server type based on packer:
   - NIS (libnesec.so) → push hluda-server ONLY (NOT frida-server). `adb push hluda-server /data/local/tmp/`
   - 360 (libjiagu.so) → skip all frida prep, mark hooks_disabled
   - Other / none → push frida-server: `adb push frida-server /data/local/tmp/`
4. Start Frida server (if not skipped):
   - `adb shell "su -c 'chmod 755 /data/local/tmp/hluda-server && /data/local/tmp/hluda-server -D &'"`  (NIS)
   - OR `adb shell "su -c '/data/local/tmp/frida-server -D &'"`  (normal)
5. Install CA certificate:
   - IF userdebug/eng build → `adb_install_cert(cert_path)` push to system CA store
   - IF production build → use MoveCertificate module (Magisk) to move user CA to system
6. Verify environment:
   - `adb shell "su -c 'ls /data/local/tmp/hluda-server'"` → exists
   - `adb shell "ps | grep hluda"` → running
   - `adb shell "settings list global | grep http_proxy"` → not set yet (Phase 2)

**Frida server selection table:**

| Packer | Server | Reason |
|--------|--------|--------|
| 网易易盾 (libnesec.so) | hluda-server | frida-server detected instantly → crash |
| 360加固 (libjiagu.so) | SKIP ALL | All frida variants detected |
| Tencent Legu | frida-gadget (in-app) | frida-server detected via port scan |
| 爱加密 | frida-server (ok) | Weak detection |
| 梆梆加固 | frida-gadget | frida-server detected |
| none | frida-server (ok) | No detection |

**Output:** device ready, frida server running (or hooks_disabled flag), CA cert installed

### Phase 1: App Install + Database Exploration

**Goal:** Install app with bypasses active, launch, pull databases, extract credentials

**Prerequisites:** Phase 0.5 complete (device ready, frida/cert in place)

**Steps:**
1. IF packer in ["网易易盾", "Tencent Legu", "梆梆加固"] OR libemulatordetector.so detected:
   - Enable Magisk DenyList for target package BEFORE install
   - IF MuMu emulator: also enable MagiskHide in Magisk settings
   - Note: DenyList may not persist across reboots — re-check after each restart
2. Call `adb_app_mgmt(action="install", apk_path=apk_path)` → install app
3. IF NIS app: wait 5s after install, verify DenyList still active for package
4. Call `adb_app_mgmt(action="start", package=package)` → launch app, wait 30s for init
5. IF app crashes on launch → check packer detection → likely emulator/root detection → re-check Phase 0.5 bypasses
6. Call `adb_push_pull(direction="pull", src="/data/data/{package}/shared_prefs/*.xml", dst=...)` → pull SP files
7. Call `adb_push_pull(direction="pull", src="/data/data/{package}/databases/*.db", dst=...)` → pull DBs
8. Call `adb_push_pull(direction="pull", src="/data/data/{package}/files/mmkv/*", dst=...)` → pull MMKV
9. For each .db file: call `db_explore(db_path, scan_patterns=[URL_REGEX, KEY_REGEX])`
10. For each share_data.xml or .ser file: call `file_parse_java_serial(file_path)` → extract ticket/uid
11. Collect all credentials into state.credentials, record sources

### Phase 2: Traffic Capture + SSL Bypass

**Goal:** Capture HTTP traffic, bypass SSL pinning if needed

**Steps:**
1. IF packer == "360": skip ALL hook strategies (anti_patterns.md)
2. Call `proxy_start(port=8080, output_dir=...)` → start mitmproxy
3. Call `adb_shell("settings put global http_proxy ...")` → set system proxy
4. Launch app, wait 60s for init, call `proxy_list_flows()` → check for initial traffic
5. **UI 遍历提示:** 生成操作清单，提示用户在模拟器上手动点击各个页面，触发更多 API 请求：
   - 根据 AndroidManifest 的 Activity 列表 + 常见泛娱乐 app 模式，生成结构化操作清单
   - 每完成一项提示用户回车确认，或一次性列出全部让用户自行遍历
   - 清单模板（按 app 类型调整）：
     ```
     □ 首页/推荐页 — 下拉刷新，等待加载完成
     □ 房间/直播间列表 — 上下滑动，点击进入任意房间
     □ 房间内 — 等待 30s，切换公屏/私聊 tab（如有）
     □ 排行榜/榜单页 — 切换日榜/周榜/总榜 tab
     □ 搜索页 — 搜索一个常见关键词
     □ 用户个人页 — 点击头像进入，查看关注/粉丝列表
     □ 设置/关于页 — 进入设置页面
     □ 充值/钱包页 — 进入（不实际支付）
     ```
   - 用户确认全部完成后继续下一步
6. Call `proxy_list_flows()` → 统计新增流量，确认覆盖了预期端点
7. IF no traffic: follow `~/.claude/reverse-skills/kb/patterns/ssl_bypass_strategies.md` decision tree
8. Run hook track in parallel (if not skipped): hook_gen_frida → hook_run → collect keys
9. Call `proxy_stop()` → export .mitm file
10. Log all strategies attempted + results to strategy_stack
11. IF all strategies exhausted: L3 path abandonment → continue with H5-only analysis

### Phase 3: Algorithm Reverse Engineering

**Goal:** Extract signature algorithm and encryption scheme. For packed apps: dynamic hook first, then static analysis.

**CRITICAL — Phase 3 execution order depends on packer:**

```
IF packer == "网易易盾" (NIS):
  3a: Dynamic Hook FIRST (app-layer → crypto-layer)
  3b: Static JS Analysis (if H5/WebView assets exist)
  3c: Cross-validate hook + JS findings

IF packer == "360加固" OR hooks_disabled:
  3a: Static JS Analysis ONLY (from Phase 0 assets)
  3b: Compare captured encrypted request/response to infer patterns

IF packer == "none" OR packer in ["爱加密", "Tencent Legu"]:
  3a: Static JS Analysis (primary)
  3b: Dynamic Hook (supplementary)
  3c: Cross-validate
```

**Steps — Dynamic Hook Path (3a, for NIS/non-360 packed apps):**

1. Read `kb/patterns/anti_patterns.md` Frida safety rules BEFORE any hook
2. Read `.claude/rules/anti-reverse-rules.md` Frida Safety Guide → mark DANGEROUS ops to avoid
3. NIS apps: DO NOT enumerate classes, reflect, Java.cast, or hook okio/BufferedSink
4. Hook from app-layer DOWN (not bottom-up):
   ```
   Step 1: RequestBuilder.header() → capture request headers ✅
   Step 2: OkHttpClient.newCall() → traffic indicator ✅
   Step 3: HttpClientImp.createCall(req) → capture request params, call req.getPath() inside hook
   Step 4: Body.getData() → response decryption ✅
   Step 5: Cipher.doFinal() + Cipher.init() → algorithm + key ✅
   Step 6: Gson.toJson() → serialization format ✅
   ```
5. Minimize hook scripts: single hook per version, no reflection, no enumeration
6. For each successful hook: run `hook_gen_frida(script, target)` → `hook_run(script_id)` → collect output
7. Compare hook output against mitmproxy captured traffic (cross-validate)

**Steps — Static JS Analysis Path (3b):**

1. Invoke `/reverse-js-analyzer` skill on all JS files (parallel agents if JS > 3 AND > 200KB)
2. Invoke `/reverse-crypto-detector` skill on captured responses and JS files
3. Run `toolkit_analyze(mitm_file, app_name)` → get endpoint list (parallel with JS analysis)

**Steps — Common (3c):**

4. For each sign candidate with confidence ≥ threshold: generate sign.py → `crypto_sign_verify()`
5. For each crypto candidate: `crypto_aes/crypto_rc4/crypto_rsa()` → verify decryption
6. IF sign_verify fails: loop back, search for more evidence (from other path)
7. IF key source unknown: search MMKV → SP → DB → API responses → ask user

**NIS Hook Iteration Safety Protocol:**
- Each hook version: ONE change at a time
- Test immediately after each change
- IF crash: revert to last working version, analyze crash cause, try different approach
- IF 3 consecutive crashes: pause, review anti_patterns.md, reconsider strategy
- Track hook versions: name scripts v1, v2, v3... with documented changes

### Phase 4: Auth Chain + Verification

**Goal:** Orchestrate authentication flow and verify everything works

**Steps:**
1. Invoke `/reverse-auth-flow-composer` skill
2. Match auth flow pattern from `~/.claude/reverse-skills/kb/patterns/auth_flow_patterns.md`
3. Execute auth chain step by step
4. Verify final authenticated request returns real data
5. IF 403 → loop back to Phase 3 (sign error)
6. IF 401 → loop back to Phase 1 (re-extract credentials)
7. IF 400 → compare with captured requests, fix params
8. Log auth result

### Phase 5: Generate Artifacts + Smoke Test

**Goal:** Generate all output files and validate them

**Steps:**
1. IF sign/crypto detected: generate plugin.py (Plugin mode) using Jinja2 template
2. IF no sign/crypto: generate api_spec.json only (Spec mode)
3. Call `toolkit_scaffold(spec_path, output_dir)` → generate plugin.py + models.py
4. Run smoke tests (5 quality gates):
   a. `python -c "import plugin"` — Importability
   b. `crypto_sign_verify()` — Sign correctness
   c. `crypto_aes(decrypt, ...)` — Decrypt correctness
   d. `plugin.authenticate(credentials)` — Auth works
   e. `plugin.fetch_rooms({})` — Returns > 0 rooms
5. IF any smoke test fails → feedback loop to corresponding phase
6. Generate audit.jsonl summary
7. **Auto-generate case library entry** (from workflow.json + state):
   - Create `kb/case_library/{app}_{date}/` directory
   - Write `workflow.json` (copy from projects/{app}/workflow.json)
   - Write `report.md` (Phase summaries + key findings + stats)
   - Update `kb/case_library/index.json`:
     ```json
     {
       "id": "{app}_{date}",
       "app": "{app_name}",
       "package": "{package}",
       "date": "{date}",
       "duration_hours": {elapsed},
       "result": "success|partial|failed",
       "tags": {
         "category": "{inferred}",
         "packer": "{packer_type}",
         "sign": "{sign_type|none}",
         "crypto": ["{crypto_types}"],
         "auth": "{auth_type}",
         "ssl_bypass": "{ssl_method}"
       },
       "similarity_keys": [extracted from packer .so names, sign keywords, crypto keywords],
       "stats": {
         "endpoints_found": {count},
         "frida_attempts": {count},
         "frida_success": {bool},
         "h5_fallback_used": {bool},
         "sign_verified": {bool},
         "total_api_calls_made": {count}
       }
     }
     ```
8. Clean up temp files, output final summary with artifact paths
9. List any `kb/_proposals/` written this session → suggest user review and merge

## Progress Reporting

- Each phase complete: one-line summary
- Strategy degradation: one-line notification
- Key discovery: one-line notification with confidence
- Pause (L4): structured pause report
- Complete: full summary

## Audit Logging

Write to `~/.claude/reverse-skills/projects/{app}/audit.jsonl` using these event types:
- `PHASE_START` / `PHASE_COMPLETE`: phase boundaries with timestamps
- `TOOL_CALL`: tool name, params (sanitized), result, duration_ms
- `DECISION`: decision, reason, source (which KB file)
- `ATTEMPT` / `ATTEMPT_RESULT`: strategy name, attempt number, result, reason
- `AGENT_DISPATCH` / `AGENT_RESULT`: sub-agent dispatch and findings
- `SIGN_VERIFY`: candidate, expected, actual, match result
- `SMOKE_TEST`: test name, result, duration_ms
