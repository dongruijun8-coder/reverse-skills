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

Read `kb/patterns/auth_flow_patterns.md` and match against discovered endpoints:

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

### Step 3: Handle Verification Failures (Feedback Loop)

| Error | Meaning | Action |
|-------|---------|--------|
| 403 "Illegal Request" | Sign wrong | → Phase 3: re-analyze sign(), check key, check excluded params |
| 401 / "session expired" | Credential expired | → Phase 1: re-extract ticket/token from device |
| 400 / param error | Request format wrong | → Compare with captured request, fix params |
| 4000 / login fail | Auth chain missing step | → Phase 2: re-capture login flow |
| Decrypt garbage | Wrong key/algo | → Phase 3: try different key, mode (ECB→CBC), padding |

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
  "auth_type": "sign_token_chain" | "token_chain" | "ticket_session" | "oauth2",
  "auth_chain": [
    {"step": 1, "endpoint": "/app/key", "method": "GET", "sign_required": true, "sign_key": ""},
    {"step": 2, "endpoint": "/login/h5/sign/token", "method": "GET", "sign_required": false},
    {"step": 3, "action": "decrypt", "key": "encrypt_key", "extract": "sign_key"},
    {"step": 4, "endpoint": "/allrank/listV2", "method": "GET", "sign_required": true, "sign_key": "active"}
  ],
  "verified": true,
  "credentials_used": ["uid", "ticket", "encrypt_key"],
  "credential_sources": {
    "uid": "share_data.xml",
    "ticket": "share_data.xml",
    "encrypt_key": "MMKV"
  }
}
```
