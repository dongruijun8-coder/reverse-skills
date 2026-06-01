---
name: reverse-auth-flow-composer
description: Orchestrate multi-step authentication flows, extract tokens/keys, verify the chain works end-to-end
---

# Reverse Auth Flow Composer

Orchestrate the authentication flow discovered during reverse engineering. Execute multi-step chains, extract session tokens and signing keys, verify the complete chain works.

## Input

- Endpoint list (from Phase 3 / toolkit_analyze)
- Sign function (sign.py from Phase 3)
- Crypto function (crypto.py from Phase 3)
- Credentials (from Phase 1 / state.credentials)
- Captured flows (from Phase 2)

## Execution

### Step 1: Match Auth Pattern

Read `~/.claude/reverse-skills/kb/patterns/auth_flow_patterns.md` and match against discovered endpoints:

**Sign Token Chain indicators:**
- Endpoint named "key", "sign/token", "getSign"
- Response from key endpoint is base64 (not plain JSON)
- All requests carry `sign` or `signature` header

**Ticket Session indicators:**
- No login/sms endpoints in captured traffic
- Requests carry `ticket` or `pub_ticket` header
- Ticket found in Phase 1 (share_data.xml, MMKV, SP)

**Token Chain indicators:**
- Sequential `/sms` → `/login` calls in captured traffic
- Login response contains `token` field
- All other requests include `token` in body

**Device-Bound Session indicators (NEW):**
- First request is to `/App/init`, `/device/register`, or similar init endpoint
- Request carries `devicetoken` header (format: `v3:AAAAA...`, 600+ chars Base64)
- Request may carry `smdeviceid` header (数美 device fingerprint)
- Response returns `sessionId` or sets session cookie
- All subsequent requests carry `clientsession` or `token` header from init response
- AES key NOT found in static storage → derived from devicetoken + clientsession
- Service returns `120001 密钥获取失败` when key doesn't match session

### Step 2: Execute Auth Chain

**For Sign Token Chain (梦音 pattern):**

Step 1: Build initial request to `/app/key`
- Merge common_params + {uid, ticket, deviceId, app}
- Compute sign with initial key (usually empty string "")
- Send GET `/app/key?params...&pub_sign=...`
- Expected: response contains encrypted key material (k0, k1, k2, k3)

Step 2: Request sign token from `/login/h5/sign/token`
- No sign needed (isIgnoreSign: true in JS)
- Send GET `/login/h5/sign/token?uid=...&ticket=...&deviceId=...`
- Expected: response is AES-encrypted sign_token

Step 3: Decrypt sign_token
- Use crypto_aes(mode="ECB", key=encrypt_key, data=response_text)
- Parse decrypted result: format is `sign_key_timestamp`
- Extract sign_key (string before last underscore)

Step 4: Verify with a known endpoint
- Pick a simple endpoint (e.g. `/allrank/listV2`)
- Build params, compute sign with active sign_key
- Send request → expect 200 with real data
- 403 → sign_key wrong → loop back to Phase 3
- 401 → ticket expired → loop back to Phase 1

**For Token Chain (漂漂 pattern):**

Step 1: Request SMS code
- POST `/sms` with {phone, app, build, ...}
- SMS sent to device (user intervention needed → L4 pause)

Step 2: Login with SMS code
- POST `/login` with {phone, smsCode, app, build, ...}
- Extract `token` from response.data.token

Step 3: Verify
- Send any authenticated request with token
- 200 → token valid

**For Ticket Session (梦音 pattern, no login API):**

Step 1: Load ticket from Phase 1
- ticket was extracted from share_data.xml / MMKV

Step 2: Test ticket validity
- Send a simple authenticated request with ticket header + sign
- 200 → ticket valid
- 401 → ticket expired → re-extract from device (Phase 1)

**For Device-Bound Session (双鱼部落 pattern — NEW):**

Pre-requisites from earlier phases:
- `devicetoken` from Phase 2 cold start capture (or hook output)
- `clientsession` from App/init response (Phase 2 cold start)
- AES key derivation function from Phase 3 (Pattern 7)

Step 0: Establish device session
1. Build App/init request with:
   - `devicetoken` header (from cold start capture, format `v3:AAAAA...`)
   - `smdeviceid` header (from cold start capture, if 数美 SDK detected)
   - `clientsession` (new UUID or empty for first request)
2. Send App/init → extract response: sessionId, token
3. Store `token` header value as `clientsession` for all subsequent requests

Step 1: Derive AES key
1. Hook `SecretKeySpec.<init>()` with stack trace (T9) to capture derived key
2. From stack trace: identify derivation function
3. Check if devicetoken/clientsession appear as derivation inputs
4. IF derivation replicable: implement `derive_key(devicetoken, clientsession)` in Python
5. IF derivation native/unknown: mark as session-scoped, key must be re-captured each session

Step 2: Verify session + key
1. Send any authenticated request with:
   - `clientsession` header (from App/init)
   - `devicetoken` header
   - Request body encrypted with derived key
2. Expected: 200 with real data
3. 120001 → key mismatch → re-derive or re-capture key
4. -8 / "系统繁忙" → clientsession empty → re-run App/init

Step 3: Login
1. Encrypt login request with derived AES key
2. POST /UI/PasswordLoginPage/passwordLogin (or detected login endpoint)
3. Extract auth token from response
4. Extract IM credentials: rongCloudToken, rongCloudId (融云), timSig (TencentIM)

Step 4: Verify authenticated state
1. Send any business request with auth token
2. 200 → auth valid
3. Re-verify post-login p1/p2/p3 state transition (Pattern 5 — XOR Pair)
   - p1 should now be fixed (token-derived)
   - p2 should now be request signature (not XOR nonce)

### Step 3: Handle Verification Failures (Feedback Loop)

| Error | Meaning | Action |
|-------|---------|--------|
| 403 "Illegal Request" | Sign wrong | → Phase 3: re-analyze sign(), check key, check excluded params |
| 401 / "session expired" | Credential expired | → Phase 1: re-extract ticket/token from device |
| 400 / param error | Request format wrong | → Compare with captured request, fix params |
| 4000 / login fail | Auth chain missing step | → Phase 2: re-capture login flow |
| 120001 / "密钥获取失败" | Session key mismatch | → Device-bound session: AES key doesn't match devicetoken. Re-derive key or re-extract from new session |
| Decrypt garbage | Wrong key/algo | → Phase 3: try different key, mode (ECB→CBC), padding |

**For Device-Bound Session (Pattern 6 — 120001 error):**

Step 0 (before auth chain): Establish device session
- Replay `App/init` request with devicetoken from cold start capture
- IF devicetoken rejected → need to reverse devicetoken generation (hook device fingerprint SDK)
- IF App/init succeeds → extract sessionId/clientsession from response
- Derive AES key from devicetoken + clientsession (use derivation function from Phase 3)
- All subsequent requests MUST use derived key + clientsession header
- IF key derivation unknown → fallback: capture key per-session via Frida T9 hook

### Step 4: Generate auth.py

```python
"""Authentication module — handles multi-step auth chain."""
from sign import compute_sign
from crypto import decrypt_body, ENCRYPT_KEY


class AuthManager:
    def __init__(self, base_url, headers, credentials):
        self.base_url = base_url
        self.headers = headers
        self.credentials = credentials
        self.sign_key = ""  # Initial sign key (usually empty string)

    def authenticate(self):
        # Step 1: Get key material
        resp = self._get("/app/key", sign=True)
        
        # Step 2: Get sign token
        resp = self._get("/login/h5/sign/token", sign=False)
        
        # Step 3: Decrypt sign token
        decrypted = decrypt_body(resp.text, ENCRYPT_KEY)
        self.sign_key = decrypted.split("_")[0]
        
        # Step 4: Verify
        test = self._get("/allrank/listV2", sign=True)
        return test.status_code == 200

    def _get(self, path, sign=False):
        params = self._build_params()
        if sign:
            params["pub_sign"] = compute_sign(params, self.sign_key)
        return requests.get(self.base_url + path, params=params, headers=self.headers)

    def _build_params(self):
        return {
            "pub_uid": self.credentials["uid"],
            "pub_ticket": self.credentials["ticket"],
            "pub_timestamp": str(int(time.time() * 1000)),
            "pub_sid": str(uuid.uuid4()),
            "pub_app": "dream",
            "pub_enc": "true",
            "deviceId": self.credentials.get("deviceId", ""),
        }
```

## Output Format

```
{
  "auth_type": "sign_token_chain" | "token_chain" | "ticket_session" | "device_bound_session" | "oauth2",
  "device_registration_required": true,  // NEW — for device_bound_session
  "device_init_endpoint": "/App/init",   // NEW — device registration endpoint
  "auth_chain": [
    {"step": 0, "endpoint": "/App/init", "method": "POST", "headers": ["devicetoken", "smdeviceid"], "extract": "clientsession"},
    {"step": 1, "endpoint": "/app/key", "method": "GET", "sign_required": true, "sign_key": ""},
    {"step": 2, "endpoint": "/login/h5/sign/token", "method": "GET", "sign_required": false},
    {"step": 3, "action": "decrypt", "key": "encrypt_key", "extract": "sign_key"},
    {"step": 4, "endpoint": "/allrank/listV2", "method": "GET", "sign_required": true, "sign_key": "active"}
  ],
  "key_derivation": {                    // NEW — for device_bound_session
    "type": "session_derived",
    "inputs": ["devicetoken", "clientsession"],
    "function": "com.app.crypto.KeyGenerator.generate",
    "replicable": false
  },
  "non_http_protocols": {               // NEW — third-party SDK credentials
    "rongcloud": {"token": "<extracted>", "userId": "<extracted>", "appKey": "m7ua80gbmdddm"},
    "mqtt": {"clientId": "<extracted>", "password": "<extracted>", "broker": "<host>:<port>"}
  },
  "verified": true,
  "credentials_used": ["uid", "ticket", "encrypt_key", "devicetoken"],
  "credential_sources": {
    "uid": "share_data.xml",
    "ticket": "share_data.xml",
    "encrypt_key": "MMKV",
    "devicetoken": "cold_start_capture"
  }
}
```

## Config Patch Output

In addition to the standard output, emit a `config_patch` for the orchestrator:

```json
{
  "config_patch": {
    "auth": {
      "plugin": "manual-token" | "password-login" | "sms-login" | "frida-rpc",
      "params": {}
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
