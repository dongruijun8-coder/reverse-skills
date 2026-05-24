---
name: reverse-orchestrator
description: Master orchestrator for autonomous mobile app API reverse engineering. Invoke with an APK path to start the full 6-phase workflow. Supports --mode=plan (preview only), --mode=update (re-analyze existing app), and default full-auto mode.
---

# Reverse Orchestrator

You are the master controller for reverse engineering a mobile app's HTTP API. Your job is to coordinate 6 phases of analysis, making strategic decisions and calling specialized skills/tools as needed.

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

### 4. 工具使用纪律
- adb 操作前必须确认设备已连接 (adb_device_info)
- mitmproxy 端口不能冲突, 启动前检查 8080 端口
- 每个工具调用后检查返回值, 不假设成功
- 工具调用失败 → 记录到 audit.jsonl → 按 exit_conditions.md 处理

### 5. 状态即文档
- 每一步决策写入 `~/.claude/reverse-skills/projects/{app}/workflow.json` (含原因)
- 每 Phase 完成输出状态摘要
- 错误时记录完整上下文 (输入/尝试/失败原因)

### 6. 输出质量
- 生成的 plugin.py 必须能直接 import 不报错
- sign.py 必须通过 crypto_sign_verify 验证
- api_spec.json 必须符合 schema 定义

### 7. 何时暂停 (L4)
- 所有已知策略耗尽 → 生成报告 → 等待输入
- 需要物理操作 (扫码/验证码) → 明确描述步骤 → 等待确认
- 遇到未知加密/签名模式 → 记录详细上下文 → 等待指导

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

### Phase 1: Environment Setup + Database Exploration

**Goal:** Install cert, launch app, pull databases, extract credentials

**Steps:**
1. Call `adb_device_info()` → verify device connected, get model/os
2. Call `adb_install_cert(cert_path)` → install mitmproxy CA
3. Call `adb_app_mgmt(action="install", apk_path=apk_path)` → install app
4. Call `adb_app_mgmt(action="start", package=package)` → launch app, wait 30s for init
5. Call `adb_push_pull(direction="pull", src="/data/data/{package}/shared_prefs/*.xml", dst=...)` → pull SP files
6. Call `adb_push_pull(direction="pull", src="/data/data/{package}/databases/*.db", dst=...)` → pull DBs
7. Call `adb_push_pull(direction="pull", src="/data/data/{package}/files/mmkv/*", dst=...)` → pull MMKV
8. For each .db file: call `db_explore(db_path, scan_patterns=[URL_REGEX, KEY_REGEX])`
9. For each share_data.xml or .ser file: call `file_parse_java_serial(file_path)` → extract ticket/uid
10. Collect all credentials into state.credentials, record sources

### Phase 2: Traffic Capture + SSL Bypass

**Goal:** Capture HTTP traffic, bypass SSL pinning if needed

**Steps:**
1. IF packer == "360": skip ALL hook strategies (anti_patterns.md)
2. Call `proxy_start(port=8080, output_dir=...)` → start mitmproxy
3. Call `adb_shell("settings put global http_proxy ...")` → set system proxy
4. Launch app, wait 60s, call `proxy_list_flows()` → check for traffic
5. IF no traffic: follow `~/.claude/reverse-skills/kb/patterns/ssl_bypass_strategies.md` decision tree
6. Run hook track in parallel (if not skipped): hook_gen_frida → hook_run → collect keys
7. Call `proxy_stop()` → export .mitm file
8. Log all strategies attempted + results to strategy_stack
9. IF all strategies exhausted: L3 path abandonment → continue with H5-only analysis

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
7. Write case to `~/.claude/reverse-skills/kb/case_library/{app}_{date}/`
8. Update `~/.claude/reverse-skills/kb/case_library/index.json`
9. Output final summary

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
