# Reverse-Skills 输出三路径 — 设计规格说明书

**日期:** 2026-06-01
**状态:** 待审核
**范围:** 逆向完 APK 后，根据加固/加密复杂度走全协议、Auth-only RPC 或 Full RPC 路径产出

---

## 1. 决策树

**判定时机**: Phase 0 加固检测做初步判定，Phase 4 完成后根据实际 key 提取结果最终确认。

```
Phase 0 初步判定         Phase 4 最终确认           产出
  │
  ├─ 无加固 + 静态 key (漂漂级)
  │   → 路径 A: 全协议
  │   → 产出: config.json (5 段完整)
  │   → pipeline 全部使用原生 Python 处理器
  │
  ├─ 加固(NIS等) + encryption/signing key 已提取 (双鱼级)
  │   → 路径 B: Auth-only RPC
  │   → 产出: config.json + frida_script.js
  │   → encryption/signing 用原生处理器 (key 从 config 或 auth RPC 注入)
  │   → auth 用 frida-rpc (login 返回 token+uid+encryption_key)
  │   → messaging 可用原生或 frida-rpc
  │
  └─ 加固 + encryption/signing key 完全无法提取
      → 路径 C: Full RPC
      → 产出: config.json + frida_script.js
      → encryption/signing = "plaintext"
      → auth/messaging = frida-rpc
      → (360 加固且 H5 fallback 失败 → 放弃)
```

判定条件:

| 条件 | 路径 A | 路径 B | 路径 C |
|------|--------|--------|--------|
| Packer | none/轻量 | NIS/Legu/爱加密/梆梆 | 任意加固 |
| encryption key | 静态提取 ✅ | 静态提取 ✅ 或 hook 捕获到 | 完全无法提取 |
| signing key | 静态提取 ✅ | 静态提取 ✅ 或 hook 捕获到 | 完全无法提取 |
| key_derivation | null | null 或 device_token (auth RPC 可注入) | native 且 hook 失败 |
| 360 加固 | — | — | ❌ RPC 不可用 → 放弃 |

## 2. 全协议路径 — config.json

### 2.1 产物

- `projects/{app_slug}/{app_slug}-config.json`

### 2.2 映射关系

```
逆向产出                        →  config.json 字段
─────────────────────────────────────────────────
抓包/静态分析 API 域名           → server.base_url
APK 版本号                       → meta.version
请求头 (clienttype 等)           → server.default_headers

加密算法识别                     → pipeline.encryption
  - 明文 JSON                    → "plaintext"
  - AES-CBC (抓到 key/iv)       → {"plugin":"aes-cbc","params":{"key":"...","iv":"..."}}

签名算法识别                     → pipeline.signing
  - 无签名                       → "plaintext"
  - XOR 签名 (抓到 3 个 key)    → {"plugin":"xor-triple-sign","params":{...}}

认证方式                         → pipeline.auth
  - 抓到固定 token               → {"plugin":"manual-token","params":{"token_field":"...","uid_field":"..."}}
  - 密码登录接口                 → {"plugin":"password-login","params":{"endpoint":"...","fields":{...},"response_mapping":{...}}}
  - 短信登录                     → {"plugin":"sms-login","params":{"endpoint":"...","fields":{...},"response_mapping":{...}}}

私信方式                         → pipeline.messaging
  - HTTP preCheck→send          → {"plugin":"rest-json","params":{"precheck_path":"...","send_path":"..."}}
  - 融云 SDK                     → {"plugin":"rongcloud-tcp","params":{"app_key":"..."}}

房间列表 API                     → endpoints.all_rooms
  - 单接口                       → {path, method, body, pagination, output_mapping}
  - 多步骤 (先分类再列表)        → {steps: [{name, path, ...iter_source}], output_mapping}

排行 API                         → endpoints.ranking
  - 带模板变量                   → body 中用 {{room.id}} {{data_source_key}} {{period_key}}

筛选选项                         → runtime_config
  - 数据源/时段/性别             → data_sources / periods / genders
  - 私信模板                     → templates
```

### 2.3 关键提取规则

**server.default_headers**: 从 Phase 1 (SP/MMKV) + Phase 2 (抓包 headers) 提取
- 必含: clienttype, channel, build, appversion, devicetype
- devicetype 从 `adb_device_info` 获取真实设备型号

**pipeline.encryption**:
- 无加密或请求体明文 → `"plaintext"`
- AES-CBC: key/iv 从 Phase 3 Cipher.init hook 提取
  - key 在静态存储 (MMKV/SP/JS) 中找到 → 直接填入 hex
  - key 仅从 hook 捕获 → 填入但标注来源
  - key 完全未找到 → `"plaintext"` + 记录到 `_unsupported`

**pipeline.signing**:
- 无签名 → `"plaintext"`
- XOR triple sign: 3 个 key 从 so 层或请求头提取
  - 全部提取到 → 填入 hex
  - 部分提取 → 已知填入，未知填 `"FIXME"`
  - 全部未提取 → `"plaintext"` + 记录到 `_unsupported`

**pipeline.auth**:
- `fields` 的值从实际抓包请求 body 中提取，不做硬编码
- `response_mapping` 从实际登录响应中提取字段名
- `mobile_token` 仅在 App/init 冷启动抓包中存在时包含

**endpoints.all_rooms**:
- 单步骤: path/method/body 从流量提取，分页参数替换为模板变量
- 多步骤: step1 为分类列表，step2 为房间列表，iter_source 指向 step1 响应中的列表字段名
- output_mapping 字段匹配优先级:
  ```
  统一字段 → 候选 API 字段 (按优先级)
  id      → id, roomId, unRoomId, room_id
  name    → name, roomName, room_name, title
  ```
- 未匹配到的必填字段 → 标记 FIXME

**endpoints.ranking**:
- 从流量识别排行榜/用户列表端点
- body 中 room_id 用 `{{room.id}}`，mode 用 `{{data_source_key}}`，rank_type 用 `{{period_key}}`
- output_mapping 字段匹配:
  ```
  uid    → uid, userId, user_id, memberId
  nick   → nick, nickname, nick_name, name
  amount → amount, total, score, gold, coin, contribution
  gender → gender, sex, user_gender
  ```

**runtime_config**:
- data_sources: 从 ranking 请求中提取 mode 参数所有观测值，key 和 value 都用 API 原始值
- periods: 从 ranking 请求中提取 rank_type 参数所有观测值
- genders: ranking 响应 gender 字段观测值 + `{"全部": null}`
- templates: 默认 `["{nick} 你好~"]`

### 2.4 不支持的模式

当加密/签名算法不被截流框架支持时 (如 AES-ECB, MD5+key):
- pipeline 对应字段输出 `"plaintext"`
- 在最终摘要中警告用户该部分需手动处理
- 不阻塞 config.json 输出 (其余部分仍可用)

---

## 3. RPC 路径 — Auth-only 与 Full RPC

截流框架支持两种 RPC 模式，共用 FridaBridge。

### 3.1 路径 B: Auth-only RPC (双鱼模式)

**适用**: encryption/signing key 已提取，但登录需要设备侧实时运算 (session-bound、设备注册、加固检测)

**config.json 结构** (参考 shuangyu):

```json
{
  "meta": {"app_name": "双鱼部落", "version": "2.47.1", "platform": "Android", "config_schema": "2.0"},
  "frida": {"enabled": true, "device": "usb", "package": "com.sybl.voiceroom", "script": "frida_script.js"},
  "server": {"base_url": "https://...", "default_headers": {...}},
  "pipeline": {
    "encryption": {"plugin": "aes-cbc", "params": {"key": "<placeholder>", "iv": "<placeholder>", "key_derivation": null}},
    "signing": {"plugin": "xor-triple-sign", "params": {"read_key": "01528e5f", "write_key": "015357de", "p3_key": "0001d981"}},
    "auth": {"plugin": "frida-rpc", "params": {"rpc_method": "login"}},
    "messaging": {"plugin": "rongcloud-tcp", "params": {"app_key": "m7ua80gbmdddm"}}
  },
  "endpoints": {...},
  "runtime_config": {...}
}
```

**关键机制**: frida-rpc login 返回 `{token, uid, encryption_key, encryption_iv}` → auth processor 注入到 `client.config` → aes-cbc 的 `derive_key()` 读取 → HTTP pipeline 用正确的 key 加解密。

**Pipeline 数据流**:
```
1. FridaBridge.start() → 连接设备 → attach 进程 → 加载 frida_script.js
2. auth frida-rpc.login() → 返回 {token, uid, encryption_key, encryption_iv}
3. encryption_key/iv 注入 client.config
4. aes-cbc derive_key() → 从 config 读取 frida 注入的 key
5. HTTP pipeline 正常运行: encrypt → sign → POST → decrypt
```

### 3.2 路径 C: Full RPC

**适用**: encryption/signing key 完全无法提取 (native .so, 复杂混淆, hook 未捕获)

```json
{
  "meta": {"app_name": "xxx", "version": "x.x", "platform": "Android", "config_schema": "2.0"},
  "frida": {"enabled": true, "device": "usb", "package": "com.xxx", "script": "frida_script.js"},
  "server": {"base_url": "https://...", "default_headers": {...}},
  "pipeline": {
    "encryption": "plaintext",
    "signing": "plaintext",
    "auth": {"plugin": "frida-rpc", "params": {"rpc_method": "login"}},
    "messaging": {"plugin": "frida-rpc", "params": {"rpc_method": "sendMessage"}}
  },
  "endpoints": {...},
  "runtime_config": {...}
}
```

**限制**: encryption/signing 走 plaintext → 请求体明文。路径 C 仅适用于 App 本身无加密/签名（但被加固无法确认），或用户明确接受明文传输。大多数加固 App 应走路径 B。

### 3.3 frida_script.js 结构

```javascript
// frida_script.js — {app_name} RPC Bridge
// Generated by reverse-orchestrator Phase 5B
// Package: {package}
// Mode: Auth-only | Full RPC

rpc.exports = {
    ping: function() { return "pong"; },

    login: function(credentials) {
        // 策略 (按优先级):
        // 1. hook OkHttp/Retrofit → 构造登录请求 → 拦截响应
        // 2. hook App LoginViewModel.login() → 直接调登录方法
        // 3. 读 SharedPreferences → 返回已登录 token
        var result = {};
        Java.perform(function() {
            // [注入从 Phase 4 提取的登录逻辑]
            result = {
                token: "...",
                uid: "...",
                // Auth-only 模式额外返回:
                encryption_key: "...",  // Phase 3 Cipher.init hook 捕获
                encryption_iv: "..."    // Phase 3 Cipher.init hook 捕获
            };
        });
        return result;
    },

    // 仅 Full RPC 模式包含:
    sendMessage: function(uid, text) {
        var result = {};
        Java.perform(function() {
            // 策略:
            // 1. hook 融云 SDK RongIMClient.sendPrivateMessage()
            // 2. hook OkHttp 拦截私信 API
            result = {success: true};
        });
        return result;
    }
};
```

**Auth-only 模式**: 仅导出 ping + login。encryption_key/iv 由 Phase 3 Cipher.init hook 捕获的 key 值注入。
**Full RPC 模式**: 导出 ping + login + sendMessage。

### 3.4 RPC 脚本生成规则

**login()**:
- Phase 4 确认的登录 endpoint + 字段映射
- NIS App: 使用 hluda 安全模板，禁止反射/类枚举/Java.cast
- 来源: T3 createCall hook (v15 已验证版本) + auth-flow-composer 输出
- encryption_key/iv 来源: Phase 3 Cipher.init hook 捕获值 (路径 B)

**sendMessage()** (仅路径 C):
- 融云 SDK: hook RongIMClient.sendPrivateMessage() — Phase 0 检测到 libRongIMLib.so
- HTTP 私信: hook OkHttp 拦截 send API — Phase 2 捕获私信端点
- 来源: T3 createCall hook + T7 newCall hook

**安全规则**:
- NIS (libnesec.so): hluda-server only, T1-T5 安全模板，禁止 DANGEROUS ops
- 360 (libjiagu.so): RPC 路径全部不可用 → Phase 0 即判定放弃
- 每个 RPC 方法包 try-catch，单方法崩溃不影响其他
- 注释标注模板来源: `// T3 v15 — createCall NIS-safe`

---

## 4. Phase 改动摘要

### Phase 0
- 加固检测 → 判定路径（无加固→轻量，加固→重保护）
- 写入 config_scratch: meta + server.base_url + pipeline.messaging 类型
- apk-analyzer 输出新增 config_patch

### Phase 1
- 从 SP/MMKV 扫描 default_headers 候选值
- 提取已登录 token (供 RPC login 策略 2 使用)

### Phase 2
- 写入 server.default_headers (流量补充) + endpoints + messaging params + runtime_config_hints
- 冷启动抓包提取 mobile_token 候选字段名

### Phase 3
- 写入 pipeline.encryption + pipeline.signing
- 不支持的模式 → `"plaintext"` + _unsupported 记录

### Phase 4
- 写入 pipeline.auth
- RPC 路径: 记录登录 Activity/ViewModel 类名、OkHttp 拦截点、SP 路径
- 写入 messaging app_key 二次确认

### Phase 5A — 全协议
- 拼装 config.json → 离线校验 → 输出

### Phase 5B — RPC (Auth-only 或 Full)
- 路径 B (Auth-only): encryption/signing 用原生 processor (key 从 config 或 auth RPC 注入)，auth=frida-rpc
- 路径 C (Full RPC): encryption/signing=plaintext，auth+messaging=frida-rpc
- 拼装 config.json (含 frida 顶层字段)
- 从 frida_hook_templates.md T1-T9 选取成功版本生成 frida_script.js
- Auth-only: script 仅导出 ping + login (含 encryption_key/iv)
- Full RPC: script 导出 ping + login + sendMessage
- 离线校验 + 输出

---

## 5. 质量门禁

### 全协议

| 检查项 | 要求 |
|--------|------|
| 顶层字段 | 5 个全部存在 |
| meta.config_schema | `"2.0"` |
| server.base_url | 以 `https://` 开头 |
| pipeline 四类 | 全部非 null |
| endpoints 两个 | 全部非 null |
| output_mapping | id/name (rooms), uid/nick (ranking) 覆盖 |
| 模板变量闭环 | `{{...}}` 引用在 output_mapping 或 runtime_config 中有定义 |

### RPC (Auth-only / Full)

| 检查项 | 要求 |
|--------|------|
| 全协议所有规则 | ✅ |
| frida 字段 | `{enabled:true, package, device, script}` 全部存在 |
| frida.script | 指向的 .js 文件存在且非空 |
| frida.package | 非 Android 占位符，为实际包名 |
| frida.device | `"usb"` 或 `"local"` |
| Auth-only: pipeline | auth = `{"plugin":"frida-rpc"}`; encryption/signing = 原生 processor (非 plaintext 非 frida-rpc) |
| Full RPC: pipeline | auth + messaging = `{"plugin":"frida-rpc"}`; encryption + signing = `"plaintext"` |
| script login() | 存在且返回 `{token, uid}`; Auth-only 额外返回 `{encryption_key, encryption_iv}` |
| script sendMessage() | Full RPC: 存在且返回 `{success}`; Auth-only: 不存在此方法 |
| 方法引用闭环 | pipeline 引用的 rpc_method 在 script rpc.exports 中存在 |

---

## 6. 改动文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `reverse-orchestrator.md` | 重度 | Phase 0 路径判定; Phase 0-4 config_scratch 写入; Phase 5A/5B 双路径 |
| `reverse-apk-analyzer.md` | 轻度 | 输出加 config_patch + 加固路径标记 |
| `reverse-crypto-detector.md` | 轻度 | 输出加 config_patch.encryption |
| `reverse-js-analyzer.md` | 轻度 | 输出加 config_patch.signing |
| `reverse-auth-flow-composer.md` | 轻度 | 输出加 config_patch.auth + RPC 类名/SP 路径 |
| `quality-rules.md` | 重度 | 全协议 + RPC 双门禁 |
| `kb/config_schema.json` | 新增 | JSON Schema |

---

## 7. 案例验证

| 案例 | 加固 | 路径 | encryption | signing | auth | messaging | frida_script |
|------|------|------|-----------|---------|------|-----------|-------------|
| 漂漂 | 无 | A: 全协议 | plaintext | plaintext | manual-token | rest-json | — |
| 双鱼 | 易盾(NIS) | B: Auth-only RPC | aes-cbc (key由auth RPC注入) | xor-triple-sign (静态key) | frida-rpc | rongcloud-tcp | ping+login |
| 梦音 | 360 | 放弃 | AES-ECB ❌ 框架不支持 | MD5+key ❌ 框架不支持 | ticket_session | rest-json | RPC 不可用 |

### 双鱼 (路径 B) 数据流验证

```
FridaBridge.start()
  → frida-rpc login() 注入 encryption_key
  → aes-cbc derive_key() 读取注入的 key
  → xor-triple-sign sign() 使用静态 key
  → HTTP POST 加密+签名请求
  → 解密响应 → JSON ✓
```
