# Reverse-Skills Config-Driven Output — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify reverse-skills to produce `<app_slug>-config.json` (+ optional `frida_script.js`) instead of `plugin.py`.

**Architecture:** Three output paths based on packer + key extraction status. Phase 0-4 accumulate structured data into `config_scratch.json`. Phase 5 assembles final config.json. No new code — all changes are to Claude Code skill/rules markdown files.

**Tech Stack:** Markdown skill files, JSON Schema, Frida JS templates

**Source spec:** `docs/specs/2026-05-31-config-driven-output-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `.claude/skills/reverse-orchestrator.md` | Modify | Phase 0 path decision, Phase 0-4 config_scratch injection, Phase 5A/5B full rewrite |
| `.claude/skills/reverse-apk-analyzer.md` | Modify | Add `config_patch` to output format |
| `.claude/skills/reverse-crypto-detector.md` | Modify | Add `config_patch.encryption` to output format |
| `.claude/skills/reverse-js-analyzer.md` | Modify | Add `config_patch.signing` to output format |
| `.claude/skills/reverse-auth-flow-composer.md` | Modify | Add `config_patch.auth` to output format |
| `.claude/rules/quality-rules.md` | Modify | Replace plugin.py gates with config.json + RPC gates |
| `kb/config_schema.json` | Create | JSON Schema for config.json structure validation |
| `docs/specs/2026-05-31-config-driven-output-design.md` | Done | Design spec (reference) |

---

### Task 1: quality-rules.md — 替换质量门禁

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/rules/quality-rules.md`

- [ ] **Step 1: 替换 quality-rules.md 全部内容**

用以下内容完整替换 `e:/桌面/逆向技能/.claude/rules/quality-rules.md`：

```markdown
# Quality Gate Rules

## 全协议 config.json Quality
- 必须通过结构校验（5 个顶层字段全部存在且类型正确）
- meta.config_schema 必须为 "2.0"
- meta.platform 必须为 "Android"
- server.base_url 必须以 "https://" 开头
- server.default_headers 至少含 2 个字段，必须含 clienttype 和 appversion
- pipeline 四类处理器全部非 null
- pipeline.encryption: 字符串 "plaintext" 或 {plugin, params} 对象（非 frida-rpc）
- pipeline.signing: 字符串 "plaintext" 或 {plugin, params} 对象（非 frida-rpc）
- pipeline.auth: {plugin, params} 对象（非 frida-rpc）
- pipeline.messaging: 字符串或 {plugin, params} 对象
- endpoints.all_rooms 非 null，output_mapping 必须覆盖 id, name
- endpoints.ranking 非 null，output_mapping 必须覆盖 uid, nick
- 模板变量 {{...}} 引用字段必须在 output_mapping 或 runtime_config 中有定义
- body 中不确定的固定字段 → 填抓包中看到的字面值，不做猜测

## RPC config.json Quality (Auth-only / Full RPC)
- 全协议所有结构规则
- frida 顶层字段存在且: enabled=true, package 非空且为实际包名, device∈{usb,local}, script 为 .js 文件名
- frida.script 指向的 .js 文件存在且非空
- Auth-only: auth = {"plugin":"frida-rpc",...}; encryption + signing = 原生 processor (非 plaintext 非 frida-rpc)
- Full RPC: auth + messaging = {"plugin":"frida-rpc",...}; encryption + signing = "plaintext"
- frida_script.js: login() 存在，返回 {token, uid}；Auth-only 额外返回 {encryption_key, encryption_iv}
- frida_script.js: sendMessage() 仅在 Full RPC 模式存在，返回 {success}
- 方法引用闭环: pipeline 中所有 frida-rpc 引用的 rpc_method 必须在 script rpc.exports 中存在

## Pre-commit Gate
- 全协议: 所有结构校验通过 → Phase 5 SUCCESS
- RPC: 结构校验 + script 存在 + 方法引用闭环 → Phase 5 SUCCESS
- 任何校验失败 → 反馈回路到对应 Phase
```

- [ ] **Step 2: 验证 — 确认文件已更新**

```bash
wc -l "e:/桌面/逆向技能/.claude/rules/quality-rules.md"
```

Expected: ~35 lines (新内容)

---

### Task 2: config_schema.json — 新增 JSON Schema

**Files:**
- Create: `e:/桌面/逆向技能/kb/config_schema.json`

- [ ] **Step 1: 创建 config_schema.json**

写入 `e:/桌面/逆向技能/kb/config_schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Interceptor Framework App Config",
  "description": "配置驱动截流框架 App 配置文件 JSON Schema",
  "type": "object",
  "required": ["meta", "server", "pipeline", "endpoints", "runtime_config"],
  "properties": {
    "meta": {
      "type": "object",
      "required": ["app_name", "version", "platform", "config_schema"],
      "properties": {
        "app_name": {"type": "string", "minLength": 1},
        "version": {"type": "string"},
        "platform": {"type": "string", "const": "Android"},
        "config_schema": {"type": "string", "const": "2.0"}
      }
    },
    "frida": {
      "type": "object",
      "required": ["enabled", "device", "package", "script"],
      "properties": {
        "enabled": {"type": "boolean", "const": true},
        "device": {"type": "string", "enum": ["usb", "local"]},
        "package": {"type": "string", "minLength": 1, "pattern": "^[a-zA-Z0-9_.]+"},
        "script": {"type": "string", "pattern": "\\.js$"}
      }
    },
    "server": {
      "type": "object",
      "required": ["base_url", "default_headers"],
      "properties": {
        "base_url": {"type": "string", "pattern": "^https://"},
        "default_headers": {
          "type": "object",
          "required": ["clienttype", "appversion"],
          "minProperties": 2
        }
      }
    },
    "pipeline": {
      "type": "object",
      "required": ["encryption", "signing", "auth", "messaging"],
      "properties": {
        "encryption": {
          "oneOf": [
            {"type": "string", "enum": ["plaintext"]},
            {"type": "object", "required": ["plugin", "params"], "properties": {"plugin": {"type": "string"}, "params": {"type": "object"}}}
          ]
        },
        "signing": {
          "oneOf": [
            {"type": "string", "enum": ["plaintext"]},
            {"type": "object", "required": ["plugin", "params"], "properties": {"plugin": {"type": "string"}, "params": {"type": "object"}}}
          ]
        },
        "auth": {
          "type": "object", "required": ["plugin"],
          "properties": {"plugin": {"type": "string"}, "params": {"type": "object"}}
        },
        "messaging": {
          "oneOf": [
            {"type": "string"},
            {"type": "object", "required": ["plugin"], "properties": {"plugin": {"type": "string"}, "params": {"type": "object"}}}
          ]
        }
      }
    },
    "endpoints": {
      "type": "object",
      "required": ["all_rooms", "ranking"],
      "properties": {
        "all_rooms": {
          "oneOf": [
            {
              "type": "object",
              "required": ["path", "method", "body", "pagination", "output_mapping"],
              "properties": {
                "path": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "POST"]},
                "body": {"type": "object"},
                "pagination": {"type": "object", "required": ["type", "size", "stop_on"]},
                "output_mapping": {"type": "object", "required": ["id", "name"]}
              }
            },
            {
              "type": "object",
              "required": ["steps", "output_mapping"],
              "properties": {
                "steps": {
                  "type": "array", "minItems": 2,
                  "items": {
                    "type": "object",
                    "required": ["name", "path", "method", "body"]
                  }
                },
                "output_mapping": {"type": "object", "required": ["id", "name"]}
              }
            }
          ]
        },
        "ranking": {
          "type": "object",
          "required": ["path", "method", "body", "pagination", "output_mapping"],
          "properties": {
            "path": {"type": "string"},
            "method": {"type": "string", "enum": ["GET", "POST"]},
            "body": {"type": "object"},
            "pagination": {"type": "object", "required": ["type", "size", "stop_on"]},
            "output_mapping": {"type": "object", "required": ["uid", "nick"]}
          }
        }
      }
    },
    "runtime_config": {
      "type": "object",
      "required": ["settings", "data_sources", "periods", "genders", "templates"],
      "properties": {
        "settings": {"type": "object"},
        "data_sources": {"type": "object"},
        "periods": {"type": "object"},
        "genders": {"type": "object"},
        "templates": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

- [ ] **Step 2: 验证 — 确认文件存在且是合法 JSON**

```bash
python -c "import json; s=json.load(open(r'e:/桌面/逆向技能/kb/config_schema.json','r',encoding='utf-8')); print(f'OK: {len(s[\"properties\"])} top-level properties')"
```

Expected: `OK: 6 top-level properties` (meta, frida, server, pipeline, endpoints, runtime_config)

---

### Task 3: reverse-apk-analyzer.md — 加 config_patch 输出

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-apk-analyzer.md`

- [ ] **Step 1: 在 Output Format 章节末尾添加 config_patch**

找到 `reverse-apk-analyzer.md` 的 Output Format 代码块结束位置（`}`后），在其后追加：

```markdown

## Config Patch Output

In addition to the standard output, emit a `config_patch` for the orchestrator to merge into `config_scratch.json`:

```json
{
  "config_patch": {
    "app_slug": "<android:label→pinyin slug, 去除非[a-z0-9_-]字符>",
    "api_domain": "<首选API域名，优先含'api'，排除CDN>",
    "messaging_type": "rest-json" | "rongcloud-tcp",
    "messaging_app_key": null | "<RongCloud init中提取的appKey>",
    "path_classification": "light" | "heavy"
  }
}
```

**app_slug 规则:**
- 优先用 manifest `android:label` → 中文转拼音首字母 (梦音→mengyin) / 英文→小写
- label 为空或无意义 (如"App"/"Main") → 用 package 倒数第二段 → 再 fallback 最后一段
- 去除非 `[a-z0-9_-]` 字符

**api_domain 规则:**
- domain_candidates 中优先含 "api" 的域名
- 排除 CDN 域名 (含 cdn/img/static/upload)
- 多个候选 → 选被请求次数最多的

**messaging_type 规则:**
- 检测到 libRongIMLib.so → `"rongcloud-tcp"`
- 检测到 libImSDK.so → `"rest-json"` (TencentIM 不可直接 TCP)
- 均未检测 → `"rest-json"`

**path_classification 规则:**
- packer ∈ {none, 爱加密(轻量)} → `"light"` → 全协议路径
- packer ∈ {网易易盾, 360, Tencent Legu, 梆梆} → `"heavy"` → RPC 路径
```

- [ ] **Step 2: 验证 — 确认新增章节存在**

```bash
grep -c "config_patch" "e:/桌面/逆向技能/.claude/skills/reverse-apk-analyzer.md"
```

Expected: ≥ 3 (章节标题 + JSON key + 规则引用)

---

### Task 4: reverse-crypto-detector.md — 加 config_patch.encryption

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-crypto-detector.md`

- [ ] **Step 1: 在 Output Format 之后追加 config_patch**

找到 `reverse-crypto-detector.md` 的 Output Format 代码块结束位置，追加：

```markdown

## Config Patch Output

In addition to the standard output, emit a `config_patch` for the orchestrator:

```json
{
  "config_patch": {
    "encryption": "plaintext" | {"plugin":"aes-cbc","params":{"key":"hex或null","iv":"hex或null","key_derivation":null|"device_token"|"session_key"|"native"}},
    "key_static": true | false,
    "key_source_detail": "<key来源描述>",
    "unsupported": null | {"detected":"AES-128-ECB","reason":"config schema 2.0 仅支持 aes-cbc","requires_plugin_py":true}
  }
}
```

**encryption 填写规则:**
- 无加密 → `"plaintext"`
- AES-CBC + key 在 MMKV/SP/JS 中找到 → `{"plugin":"aes-cbc","params":{"key":"<hex>","iv":"<hex>","key_derivation":null}}`
- AES-CBC + key 仅从 hook 捕获，不在静态存储 → `{"plugin":"aes-cbc","params":{"key":null,"iv":null,"key_derivation":"device_token|session_key|native"}}`
- 其他算法 (ECB/GCM/RC4/RSA) → `"plaintext"` + unsupported 记录
- key 完全未找到 → `"plaintext"` + unsupported 记录

**key_static 规则:**
- key 在 MMKV/SP/DB/JS 中找到 → true → 路径 A 可行
- key 仅从 hook 捕获 → false → 需要路径 B (auth RPC 注入 key)

**unsupported.detected 取值:** AES-128-ECB, AES-256-GCM, RC4, RSA, AES-256-CBC(no-key), unknown
```

- [ ] **Step 2: 验证**

```bash
grep -c "config_patch" "e:/桌面/逆向技能/.claude/skills/reverse-crypto-detector.md"
```

Expected: ≥ 3

---

### Task 5: reverse-js-analyzer.md — 加 config_patch.signing

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-js-analyzer.md`

- [ ] **Step 1: 在 Output Format 之后追加 config_patch**

找到 `reverse-js-analyzer.md` 的 Output Format 代码块结束位置，追加：

```markdown

## Config Patch Output

In addition to the standard output, emit a `config_patch` for the orchestrator:

```json
{
  "config_patch": {
    "signing": "plaintext" | {"plugin":"xor-triple-sign","params":{"read_key":"hex或FIXME","write_key":"hex或FIXME","p3_key":"hex或FIXME"}},
    "keys_complete": true | false,
    "unsupported": null | {"detected":"MD5+key","reason":"config schema 2.0 仅支持 xor-triple-sign","requires_plugin_py":true}
  }
}
```

**signing 填写规则:**
- 无签名 → `"plaintext"`
- XOR triple sign + 3 个 key 全部从 so/请求头提取 → `{"plugin":"xor-triple-sign","params":{"read_key":"<hex>","write_key":"<hex>","p3_key":"<hex>"}}`
- XOR + 部分 key 提取 → 已知填入 hex，未知填 `"FIXME"`，keys_complete=false
- XOR + key 全部未找到 → `"plaintext"` + unsupported 记录
- 其他签名算法 (MD5+key/HMAC-SHA256/自定义排序/多层/原生) → `"plaintext"` + unsupported 记录

**keys_complete 规则:**
- 全部 3 个 key 已提取 → true
- 任何 key 为 "FIXME" → false → 可能需要路径 B

**unsupported.detected 取值:** MD5+key, HMAC-SHA256, custom-sort-hash, multi-layer-sign, native-sign, XOR-no-keys
```

- [ ] **Step 2: 验证**

```bash
grep -c "config_patch" "e:/桌面/逆向技能/.claude/skills/reverse-js-analyzer.md"
```

Expected: ≥ 3

---

### Task 6: reverse-auth-flow-composer.md — 加 config_patch.auth

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-auth-flow-composer.md`

- [ ] **Step 1: 在 Output Format 之后追加 config_patch**

找到 `reverse-auth-flow-composer.md` 的 Output Format 代码块结束位置，追加：

```markdown

## Config Patch Output

In addition to the standard output, emit a `config_patch` for the orchestrator:

```json
{
  "config_patch": {
    "auth": {
      "plugin": "manual-token" | "password-login" | "sms-login" | "frida-rpc",
      "params": {<plugin-specific params>}
    },
    "requires_device_init": true | false,
    "messaging_app_key": null | "<rongcloud appKey>",
    "rpc_targets": {
      "login_activity": "<LoginActivity完整类名>" | null,
      "login_viewmodel": "<LoginViewModel完整类名>" | null,
      "okhttp_intercept_class": "<OkHttp拦截器类名>" | null,
      "sp_path": "<SharedPreferences文件路径>" | null,
      "sp_token_key": "<token key名>" | null
    }
  }
}
```

**auth 填写规则:**
- manual-token: `{"plugin":"manual-token","params":{"token_field":"<登录响应token字段名>","uid_field":"<登录响应uid字段名>"}}`
- password-login: `{"plugin":"password-login","params":{"endpoint":"<登录端点路径>","fields":{"phone":"<实际key>","password":"<实际key>",...},"response_mapping":{"token":"<实际key>","uid":"<实际key>"}}}`
- sms-login: `{"plugin":"sms-login","params":{"endpoint":"<短信端点>","fields":{"phone":"<实际key>","sms_code":"<实际key>"},"response_mapping":{"token":"<实际key>","uid":"<实际key>"}}}`
- frida-rpc: `{"plugin":"frida-rpc","params":{"rpc_method":"login"}}`
  - 当 requires_device_init=true 或 packer=heavy 时选择

**fields 规则:**
- 所有 value 从实际抓包请求 body 中提取字段名，不做硬编码假设
- code 和 mobile_token 仅在抓包请求中出现时才包含

**rpc_targets 规则 (仅 RPC 路径需要):**
- login_activity: Phase 4 确认的登录界面 Activity 完整类名
- login_viewmodel: 从反编译代码中找到的 LoginViewModel/LoginPresenter 类名
- okhttp_intercept_class: OkHttp Interceptor 实现类（如 XxxInterceptor）
- sp_path: Phase 1 提取的 SharedPreferences 文件相对路径
- sp_token_key: SP 中存储 token 的 key 名
```

- [ ] **Step 2: 验证**

```bash
grep -c "config_patch" "e:/桌面/逆向技能/.claude/skills/reverse-auth-flow-composer.md"
```

Expected: ≥ 3

---

### Task 7: reverse-orchestrator.md — Phase 0 路径判定 + config_scratch 注入

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md`

This task covers Phase 0 changes only. Phases 1-5 are in Tasks 8-9.

- [ ] **Step 1: 在 Phase 0 末尾新增 Step 15 (路径判定 + config_scratch 写入)**

找到 orchestrator Phase 0 的最后一个 Step (Step 13)，在其后插入 Step 14-15：

```markdown
14. **Path Classification (NEW):** Based on packer detection:
    - packer == "none" OR packer == "爱加密" (light) → `output_path = "A"` (全协议)
    - packer ∈ {"网易易盾", "360", "Tencent Legu", "梆梆"} → `output_path = "B_or_C"` (RPC)
    - Save to workflow.json: `output_path`
    - Notify: "🔀 初步路径判定: {output_path} (Phase 4 后最终确认)"

15. **Write config_scratch (NEW):** Save initial config fragments:
    ```json
    {
      "meta": {
        "app_name": "<app_slug from apk-analyzer config_patch>",
        "version": "<manifest.versionName or '0.0.0'>",
        "platform": "Android",
        "config_schema": "2.0"
      },
      "server": {
        "base_url": "<api_domain from apk-analyzer config_patch>",
        "default_headers": {}
      },
      "pipeline": {
        "encryption": null,
        "signing": null,
        "auth": null,
        "messaging": "<messaging_type from apk-analyzer config_patch>"
      },
      "endpoints": {
        "all_rooms": null,
        "ranking": null
      },
      "runtime_config_hints": {
        "data_source_values": [],
        "period_values": [],
        "gender_values": []
      },
      "_path": "<output_path>",
      "_unsupported": {}
    }
    ```
    Save to `projects/{app_name}/config_scratch.json`.
    Use `state_save(project_dir, scratch={config_patch: <the above object>})` to persist.
```

- [ ] **Step 2: 更新 Phase 0 的 Output 描述**

找到 Phase 0 末尾的 `**Output:**` 行，追加：

```markdown
**Output:** packer type, strategy decisions, domain candidates, key candidates, device fingerprint SDKs detected, third-party IM SDKs detected, session_bound_key_likely flag, matched cases with pre-loaded hypotheses, **config_scratch.json (meta + server.base_url + pipeline.messaging)**, **output_path (A/B_or_C)**
```

- [ ] **Step 3: 验证**

```bash
grep -c "config_scratch" "e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md"
```

Expected: ≥ 2 (Step 15 + Output)

---

### Task 8: reverse-orchestrator.md — Phase 1-4 config_scratch 写入

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md`

- [ ] **Step 1: Phase 1 末尾新增 Step 12**

找到 Phase 1 最后的 Step (Step 11)，插入：

```markdown
12. **Write config_scratch server.default_headers (NEW):** Scan extracted SP/MMKV for header-like keys:
    Search (case-insensitive): clienttype, client_type, channel, build, appversion, app_version, devicetype, device_type, device_model, devicemodel
    For each match → write to config_scratch.server.default_headers (key=actual, value=extracted)
    Load existing config_scratch, merge, save.
    Do NOT overwrite existing non-empty values.
```

- [ ] **Step 2: Phase 2 末尾新增 Step 14-17**

找到 Phase 2 Step 13 (`proxy_stop` + 导出 .mitm 文件)，在其后插入：

```markdown
14. **Fill server.default_headers from traffic (NEW):**
    From any successful request:
    - Extract headers: clienttype, channel, build, appversion
    - Extract devicetype: run adb_device_info → use "ro.product.brand ro.product.model" (e.g. "Samsung SM-S9280")
    - Merge into config_scratch.server.default_headers (Phase 2 values take priority over Phase 1)

15. **Fill endpoints.all_rooms (NEW):**
    a. Identify room-list endpoint: scan all captured flows for responses that are JSON arrays where items contain ≥2 of {room_id, roomName, id, name}
    b. Prioritize candidates: path contains room/list/home > larger array response > has pagination params
    c. Determine single-step vs multi-step:
       - Body has fixed catId/id value not from another endpoint → single-step
       - Body has variable id value that comes from another endpoint's response → multi-step
    d. Single-step format:
       ```
       {
         "path": "<extracted>", "method": "GET|POST",
         "body": {<from capture, pagination fields replaced: offset→{{offset}}, page→{{page}}>},
         "pagination": {"type": "offset_limit|page_number", "size": <observed limit/size value>, "stop_on": "empty_list"},
         "output_mapping": {<field matching result>}
       }
       ```
       pagination type: offset from 0 → "offset_limit", page from 1 → "page_number"
    e. Multi-step format:
       ```
       {
         "steps": [
           {"name": "categories", "path": "<category endpoint>", "method": "GET|POST", "body": {<from capture>}},
           {"name": "room_list", "path": "<room list endpoint>", "method": "GET|POST",
            "body": {<with {{_iter.field}} references>},
            "iter_source": "categories.<list_field_name>",
            "pagination": {<same as single-step>}}
         ],
         "output_mapping": {<including category: {{_iter.key}} or {{_iter.field}}>}
       }
       ```
       iter_source: trace room_list body variable → source endpoint → response list field name
    f. output_mapping field matching (greedy, first match wins):
       id → id, roomId, unRoomId, room_id, user_id
       name → name, roomName, room_name, title, nick
       type → type, room_type, roomType, category
       Required fields (id, name) unmatched → mark "FIXME"
       API has no corresponding type field → leave "" (no hardcoded "voice")
    g. Write to config_scratch.endpoints.all_rooms

16. **Fill endpoints.ranking (NEW):**
    a. Identify ranking endpoint: scan flows for JSON array responses where items contain ≥2 of {uid, userId, nick, nickname}
    b. Format:
       ```
       {
         "path": "<extracted>", "method": "GET|POST",
         "body": {
           "room_id": "{{room.id}}",
           "mode": "{{data_source_key}}",
           "rank_type": "{{period_key}}",
           <other static fields from capture>
         },
         "pagination": {<same as all_rooms>},
         "output_mapping": {<field matching>}
       }
       ```
    c. room_id location: in body → {{room.id}} in body template; in URL path → record in _url_template note
    d. output_mapping field matching:
       uid → uid, userId, user_id, id, memberId
       nick → nick, nickname, nick_name, name, userName
       amount → amount, total, score, gold, coin, contribution, charm
       gender → gender, sex, user_gender
       Required (uid, nick) unmatched → "FIXME"
    e. Extract runtime_config_hints:
       - data_source_values: all observed "mode" values from ranking requests
       - period_values: all observed "rank_type" values from ranking requests
       - gender_values: all observed gender field values from ranking responses
    f. Write to config_scratch.endpoints.ranking + config_scratch.runtime_config_hints

17. **Fill messaging params (NEW):**
    IF pipeline.messaging == "rest-json":
      - Search captured flows for im/msg/send → set send_path
      - Search captured flows for im/msg/preCheck → set precheck_path
      - Neither found → both null
    Update config_scratch.pipeline.messaging with:
      {"plugin":"rest-json","params":{"precheck_path":null|"<path>","send_path":null|"<path>"}}
    IF pipeline.messaging == "rongcloud-tcp":
      - Leave app_key as null (Phase 0 may have found it, Phase 4 will confirm)
      - Update to: {"plugin":"rongcloud-tcp","params":{"app_key":null|"<extracted>"}}

    IF zero traffic captured:
      - endpoints: fill FIXME placeholders (path="FIXME", method="POST", body={}, pagination defaults, output_mapping with FIXME values)
      - runtime_config_hints: empty arrays
      - messaging params: null
      - Mark workflow.json: "traffic_empty": true
      - Continue to Phase 3 (do NOT abort)
```

- [ ] **Step 3: Phase 3 末尾新增 Step 11**

找到 Phase 3 Step 10，在其后插入：

```markdown
11. **Write pipeline.encryption + pipeline.signing to config_scratch (NEW):**
    a. encryption:
       - No encryption detected → "plaintext"
       - AES-CBC detected:
         IF key found in static storage (MMKV/SP/JS):
           → {"plugin":"aes-cbc","params":{"key":"<hex>","iv":"<hex>","key_derivation":null}}
         ELIF key captured via Cipher.init hook only:
           → {"plugin":"aes-cbc","params":{"key":null,"iv":null,"key_derivation":"device_token"|"session_key"|"native"}}
           key_derivation value:
           - devicetoken present in cold start headers → "device_token"
           - clientsession contains key material → "session_key"
           - derivation in native .so → "native"
         ELSE key not found:
           → "plaintext" + add to _unsupported: {"encryption":{"detected":"<algorithm>","reason":"key not found","requires_plugin_py":true}}
       - Other algorithm (ECB/GCM/RC4/RSA):
         → "plaintext" + add to _unsupported: {"encryption":{"detected":"<algorithm>","reason":"config schema 2.0 仅支持 aes-cbc","requires_plugin_py":true}}

    b. signing:
       - No signing → "plaintext"
       - XOR triple sign detected:
         → {"plugin":"xor-triple-sign","params":{"read_key":"<hex|FIXME>","write_key":"<hex|FIXME>","p3_key":"<hex|FIXME>"}}
       - Other algorithm:
         → "plaintext" + add to _unsupported: {"signing":{"detected":"<algorithm>","reason":"config schema 2.0 仅支持 xor-triple-sign","requires_plugin_py":true}}

    c. After writing, update _path if needed:
       - _path == "B_or_C" AND encryption key_static==true AND signing keys_complete==true → _path = "B"
       - _path == "B_or_C" AND (encryption key NOT found OR signing keys NOT found) → _path = "C"

    Save config_scratch.
```

- [ ] **Step 4: Phase 4 末尾新增 Step 11**

找到 Phase 4 Step 10，在其后插入：

```markdown
11. **Write pipeline.auth to config_scratch (NEW):**
    a. Select auth plugin:
       - Login requires SMS code → sms-login
       - Login requires password + token long-lived (>24h) → manual-token
       - Login requires password + token short-lived → password-login
       - All cases where output_path is "B" or "C" → frida-rpc

    b. Fill params:
       manual-token:
         "token_field": actual field name from login/user-info response
         "uid_field": actual field name from login/user-info response
       password-login:
         "endpoint": login endpoint path from captured traffic
         "fields": {phone/password/code/mobile_token → actual field names from login request body}
         "response_mapping": {token/uid → actual field names from login response}
       sms-login:
         "endpoint": SMS login endpoint path
         "fields": {phone/sms_code → actual field names}
         "response_mapping": {token/uid → actual field names}
       frida-rpc:
         "plugin":"frida-rpc","params":{"rpc_method":"login"}

    c. All field name values MUST be extracted from actual captured request/response bodies.
       DO NOT hardcode assumptions like phone→"phone", password→"password".

    d. For RPC paths (B/C), additionally record rpc_targets:
       - login_activity: confirmed login Activity class name from Phase 4
       - login_viewmodel: LoginViewModel/LoginPresenter from decompiled code
       - okhttp_intercept_class: OkHttp Interceptor implementation class
       - sp_path: SharedPreferences file path from Phase 1
       - sp_token_key: token key name in SP

    e. Update messaging app_key:
       IF messaging == rongcloud-tcp AND app_key == null:
         → Extract from login response (rongCloudToken source, appKey field)
       → Update config_scratch.pipeline.messaging.params.app_key

    f. Final path confirmation:
       - _path == "A" → confirmed Path A (全协议)
       - _path == "B" → confirmed Path B (Auth-only RPC)
       - _path == "C" → confirmed Path C (Full RPC)
       - 360加固 AND hooks_disabled AND H5 fallback failed → ABORT (Impossible)

    Save config_scratch.
```

- [ ] **Step 5: 验证**

```bash
grep -n "config_scratch" "e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md"
```

Expected: at least 6 occurrences across Phase 0, 1, 2, 3, 4

---

### Task 9: reverse-orchestrator.md — Phase 5 完全重写

**Files:**
- Modify: `e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md`

- [ ] **Step 1: 删除旧的 Phase 5 全部内容**

找到 Phase 5 章节（从 `### Phase 5: Generate Artifacts` 到 `## Progress Reporting` 之前），全部删除。

- [ ] **Step 2: 插入新 Phase 5A 和 Phase 5B**

在旧 Phase 5 位置插入：

```markdown
### Phase 5: Generate Config Output

Execution depends on `config_scratch._path` confirmed in Phase 4.

#### Phase 5A: 全协议路径 (Path A)

**Goal:** Assemble config.json from config_scratch, validate, output.

**Steps:**
1. Load config_scratch.json
2. Check required fields:
   - meta: all 4 fields non-empty
   - server.base_url: non-empty, starts with "https://"
   - server.default_headers: ≥2 fields, includes clienttype + appversion
   - pipeline: all 4 processors non-null
   - endpoints.all_rooms: non-null (if FIXME → warning, continue)
   - endpoints.ranking: non-null (if FIXME → warning, continue)
   Missing required fields → backfill from source Phase or use placeholders:
     - meta fields → "unknown"
     - server.base_url → "https://api.example.com" + FIXME warning
     - endpoints → FIXME placeholder (path="FIXME", method="POST", body={}, pagination defaults, output_mapping with FIXME)

3. Generate runtime_config from hints:
   ```json
   {
     "settings": {"send_interval": 3},
     "data_sources": {<observed values as both key and value>},
     "periods": {<observed values as both key and value>},
     "genders": {"全部": null, <observed values: inferred label>},
     "templates": ["{nick} 你好~"]
   }
   ```
   - data_sources/periods: key=API raw value, value=API raw value (user renames in Dashboard)
   - genders: all observed values from ranking responses; numeric → infer label (1→"男",2→"女",0→"未知"); string → key=value
   - No observations → empty object {}
   - user MUST be able to edit these in Dashboard

4. Assemble final config.json:
   ```json
   {
     "meta": <scratch.meta>,
     "server": <scratch.server>,
     "pipeline": <scratch.pipeline>,
     "endpoints": <scratch.endpoints>,
     "runtime_config": <generated above>
   }
   ```
   Do NOT include _unsupported, _path, runtime_config_hints in output.

5. Validate:
   a. JSON parseable
   b. 5 top-level fields present
   c. meta.config_schema == "2.0", meta.platform == "Android"
   d. server.base_url starts with "https://"
   e. pipeline 4 processors all non-null
   f. endpoints 2 entries non-null
   g. all_rooms output_mapping covers id + name
   h. ranking output_mapping covers uid + nick
   i. Template variable closure: scan all body {{...}} refs → verify definitions exist in:
      - output_mapping fields (room.id, room.name)
      - runtime_config keys (data_source_key, period_key)
      - pagination built-ins (offset, page, _iter.field, _iter.key)
      - Undefined ref → WARNING, do not block output

6. Write `projects/{app_slug}/{app_slug}-config.json`

7. Run smoke test (L1 offline):
   - Structure valid per quality-rules.md
   - Template vars closed
   - output_mapping field coverage

8. Output summary:
   - config.json path
   - Pipeline: encryption=<type>, signing=<type>, auth=<type>, messaging=<type>
   - Endpoints: all_rooms=<single/multi-step>, ranking=<path>
   - _unsupported warnings (if any):
     "⚠️  {processor} 算法 {detected} 不被 config schema 2.0 支持，需手动 plugin.py"
   - "📋 上传 config.json 到 Dashboard 即可使用"

#### Phase 5B: RPC 路径 (Path B: Auth-only / Path C: Full RPC)

**Goal:** Assemble config.json with frida section + generate frida_script.js

**Steps:**
1. Load config_scratch.json
2. Determine RPC sub-mode:
   - _path == "B" → Auth-only: encryption/signing = native processors (from Phase 3)
   - _path == "C" → Full RPC: encryption/signing = "plaintext"

3. Assemble config.json:
   Path B (Auth-only):
   ```json
   {
     "meta": <scratch.meta>,
     "frida": {"enabled": true, "device": "usb", "package": "<manifest.package>", "script": "frida_script.js"},
     "server": <scratch.server>,
     "pipeline": {
       "encryption": <scratch.pipeline.encryption>,
       "signing": <scratch.pipeline.signing>,
       "auth": {"plugin": "frida-rpc", "params": {"rpc_method": "login"}},
       "messaging": <scratch.pipeline.messaging>
     },
     "endpoints": <scratch.endpoints>,
     "runtime_config": <generated from hints, same as 5A>
   }
   ```
   Path C (Full RPC):
   ```json
   {
     "pipeline": {
       "encryption": "plaintext",
       "signing": "plaintext",
       "auth": {"plugin": "frida-rpc", "params": {"rpc_method": "login"}},
       "messaging": {"plugin": "frida-rpc", "params": {"rpc_method": "sendMessage"}}
     }
   }
   ```

4. Fill frida section:
   - package: from manifest (apk_extract_manifest in Phase 0)
   - device: "usb" (default) or "local" (if emulator)
   - script: "frida_script.js"

5. Generate frida_script.js:
   From `kb/patterns/frida_hook_templates.md` templates:
   - Select template versions that were verified successful in Phase 3/4
   - Use NIS-safe variants (T1-T5) for NIS apps
   - Assemble script structure:

   ```javascript
   // frida_script.js — {app_name} RPC Bridge
   // Generated by reverse-orchestrator Phase 5B
   // App: {app_name}, Package: {package}
   // Mode: {Auth-only | Full RPC}

   rpc.exports = {
       ping: function() { return "pong"; },

       login: function(credentials) {
           var result = {};
           Java.perform(function() {
               // Strategy: {selected strategy from Phase 4}
               // Source: T3 v{version} — {description}
               // RPC targets: {login activity/viewmodel from config_scratch rpc_targets}

               // [INJECT: Phase 4 login endpoint logic]
               // POST {login_endpoint} with {fields mapped from credentials}
               // Extract from response: {token_field} → token, {uid_field} → uid

               result = {
                   token: "...",
                   uid: "..."
                   {, encryption_key: "..." }   // Auth-only: from Phase 3 Cipher.init hook
                   {, encryption_iv: "..."  }   // Auth-only: from Phase 3 Cipher.init hook
               };
           });
           return result;
       }

       {, sendMessage: function(uid, text) {   // Full RPC only
           var result = {};
           Java.perform(function() {
               // Strategy: {RongCloud SDK hook | OkHttp intercept}
               // Source: T{template} v{version}

               result = {success: true};
           });
           return result;
       }}
   };
   ```

6. Script injection rules:
   - login(): inject actual Phase 4 confirmed login endpoint, field names, response mapping
   - login() Auth-only extras: inject Phase 3 Cipher.init hook captured key/iv as constant strings
   - sendMessage(): inject Phase 2 messaging endpoint or RongCloud SDK hook point
   - NIS apps: NO reflection/Java.cast/Object.keys/enumeration — use hluda-safe patterns only
   - Each Java.perform block: wrap in try-catch with console.log error
   - Comment every injection point with template source: "// T3 v15 — createCall NIS-safe"

7. Write output:
   - `projects/{app_slug}/{app_slug}-config.json`
   - `projects/{app_slug}/frida_script.js`

8. Validate (L1 offline):
   - config.json: all quality-rules.md RPC rules pass
   - frida_script.js: contains `rpc.exports` block
   - frida_script.js: `ping()` function exists and returns "pong"
   - frida_script.js: `login()` function exists with `Java.perform` block
   - Auth-only: `login()` returns object with encryption_key + encryption_iv fields
   - Full RPC: `sendMessage()` function exists; login() does NOT include encryption_key
   - Method closure: pipeline frida-rpc plugin's rpc_method exists in script rpc.exports

9. Output summary:
   - config.json path + frida_script.js path
   - RPC mode: Auth-only | Full RPC
   - Pipeline: which processors are frida-rpc vs native
   - Deployment instructions:
     ```
     📋 部署步骤:
       1. 将 config.json + frida_script.js 上传到 Dashboard
       2. 确保设备已连接 + {hluda-server|frida-server} 运行中
       3. Dashboard 自动通过 FridaBridge 加载脚本
       4. {如果是 Auth-only: Frida login 后 encryption_key 自动注入 HTTP pipeline}
       5. 设备需保持常亮 + USB 连接
     ```
   - _unsupported warnings (if any)
```

- [ ] **Step 2: 删除旧的 Progress Reporting 和 Audit Logging 中对 plugin.py/sign.py/crypto.py 的引用**

找到 `## Progress Reporting` 和 `## Audit Logging` 章节，将：
- `plugin.py`, `sign.py`, `crypto.py` 的引用替换为 `config.json`, `frida_script.js`

- [ ] **Step 3: 验证**

```bash
grep -c "Phase 5A\|Phase 5B\|全协议路径\|Auth-only RPC\|Full RPC" "e:/桌面/逆向技能/.claude/skills/reverse-orchestrator.md"
```

Expected: ≥ 6 (Phase 5A header + Phase 5B header + descriptions)

---

### Task 10: Final consistency check

**Files:**
- Verify: All modified files

- [ ] **Step 1: Verify all files modified**

```bash
echo "=== Files modified ===" && ls -la "e:/桌面/逆向技能/.claude/skills/"*.md "e:/桌面/逆向技能/.claude/rules/quality-rules.md" "e:/桌面/逆向技能/kb/config_schema.json"
```

Expected: 7 files listed

- [ ] **Step 2: Verify no references to deleted artifacts remain**

```bash
grep -rn "plugin\.py\|sign\.py\|crypto\.py\|toolkit_scaffold" "e:/桌面/逆向技能/.claude/skills/" "e:/桌面/逆向技能/.claude/rules/" --include="*.md" || echo "No stale references (exit code > 0 is OK)"
```

Expected: Only references in code examples/comments that say "replaced by config.json" — no active instructions to generate these files.

- [ ] **Step 3: Verify config_scratch referenced consistently across all skills**

```bash
grep -rn "config_scratch\|config_patch" "e:/桌面/逆向技能/.claude/skills/" --include="*.md" | wc -l
```

Expected: ≥ 20 (across all 5 skill files + orchestrator)

- [ ] **Step 4: Verify quality-rules.md has both gate sets**

```bash
grep -c "全协议\|RPC" "e:/桌面/逆向技能/.claude/rules/quality-rules.md"
```

Expected: ≥ 3

- [ ] **Step 5: Verify spec matches implementation**

Cross-reference spec sections against implemented changes:
- Spec §1 决策树 → orchestrator Phase 0 Step 14 (path classification) ✓
- Spec §2 全协议 → orchestrator Phase 5A ✓
- Spec §3.1 Auth-only RPC → orchestrator Phase 5B Path B ✓
- Spec §3.2 Full RPC → orchestrator Phase 5B Path C ✓
- Spec §3.3 frida_script.js → orchestrator Phase 5B Step 5 ✓
- Spec §4 Phase changes → orchestrator Phase 0-4 insertions ✓
- Spec §5 质量门禁 → quality-rules.md ✓
- Spec §6 文件清单 → 7 files tracked in this plan ✓

- [ ] **Step 6: Commit all changes**

```bash
cd "e:/桌面/逆向技能"
git add .claude/skills/reverse-orchestrator.md .claude/skills/reverse-apk-analyzer.md .claude/skills/reverse-crypto-detector.md .claude/skills/reverse-js-analyzer.md .claude/skills/reverse-auth-flow-composer.md .claude/rules/quality-rules.md kb/config_schema.json docs/specs/2026-05-31-config-driven-output-design.md
git commit -m "feat: three-path config output (全协议/Auth-only RPC/Full RPC)

Replace plugin.py generation with config.json output per
docs/specs/2026-05-31-config-driven-output-design.md.

Path A (全协议): pure config.json for light apps
Path B (Auth-only RPC): config.json + frida_script.js, encryption
  keys injected by auth RPC login
Path C (Full RPC): config.json + frida_script.js, plaintext transport

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
