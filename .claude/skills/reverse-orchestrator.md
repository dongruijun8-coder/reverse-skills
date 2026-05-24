---
name: reverse-orchestrator
description: Master orchestrator for autonomous mobile app API reverse engineering. Invoke with an APK path to start the full 6-phase workflow. Supports --mode=plan (preview only), --mode=update (re-analyze existing app), and default full-auto mode.
---

# Reverse Orchestrator

You are the master controller for reverse engineering a mobile app's HTTP API. Your job is to coordinate 6 phases of analysis, making strategic decisions and calling specialized skills/tools as needed.

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
1. Call `apk_unpack(apk_path, output_dir)` → get file tree
2. Call `apk_detect_packer(unpacked_dir)` → get packer type
3. Read `kb/patterns/packer_patterns.md` → determine strategy
4. Read `kb/patterns/anti_patterns.md` → skip doomed strategies
5. Call `apk_extract_manifest(unpacked_dir)` → get package, version, permissions, network_config
6. Call `apk_string_search(unpacked_dir, patterns=[URL_REGEX, KEY_REGEX, IP_REGEX])` → get domain/key candidates
7. IF packer == "none": call `apk_decompile(apk_path, output_dir)` → search for API classes
8. IF packer != "none": mark decompile_skipped=true, list assets/ directory for H5/JS files
9. Read `kb/case_library/index.json` → search for similar cases by tags
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
5. IF no traffic: follow `kb/patterns/ssl_bypass_strategies.md` decision tree
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
2. Match auth flow pattern from `kb/patterns/auth_flow_patterns.md`
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
7. Write case to `kb/case_library/{app}_{date}/`
8. Update `kb/case_library/index.json`
9. Output final summary

## Progress Reporting

- Each phase complete: one-line summary
- Strategy degradation: one-line notification
- Key discovery: one-line notification with confidence
- Pause (L4): structured pause report
- Complete: full summary

## Audit Logging

Write to `projects/{app}/audit.jsonl` using these event types:
- `PHASE_START` / `PHASE_COMPLETE`: phase boundaries with timestamps
- `TOOL_CALL`: tool name, params (sanitized), result, duration_ms
- `DECISION`: decision, reason, source (which KB file)
- `ATTEMPT` / `ATTEMPT_RESULT`: strategy name, attempt number, result, reason
- `AGENT_DISPATCH` / `AGENT_RESULT`: sub-agent dispatch and findings
- `SIGN_VERIFY`: candidate, expected, actual, match result
- `SMOKE_TEST`: test name, result, duration_ms
