---
name: reverse-crypto-detector
description: Identify request/response encryption mode, extract encryption keys, generate decryption code
---

# Reverse Crypto Detector

Identify encryption schemes used for API request/response bodies, extract keys, and generate Python decryption code.

## Input

- Captured API responses (from mitmproxy flows or `.mitm` file)
- JS source files (if H5/WebView)
- Hook output (if runtime hook was successful in Phase 2)
- Extracted keys from Phase 1 (MMKV/SP/DB)

## Hook Safety (NIS / 加固 app)

Before recommending hooks for crypto detection, check packer type:
- **NIS (libnesec.so):** Safe to hook Cipher.doFinal() + Cipher.init() (system classes). NEVER enumerate, reflect, or hook okio.
- **360 (libjiagu.so):** Skip all hooks. Use JS static analysis only.
- Hook priority for crypto: Cipher.doFinal → Cipher.init (captures key+IV) → SecretKeySpec.<init> → Gson.toJson (serialization)
- See `kb/patterns/anti_patterns.md` for full safety rules and `~/.claude/rules/anti-reverse-rules.md` Frida Safety Guide.

## Execution

### Step 1: Detect Encryption Presence

Check for these signals:
- Response header `pub_enc: true` or similar → response body is encrypted
- Response body is Base64 but not valid JSON when decoded → encrypted
- Request body contains `pub_enc: true` → request is also encrypted
- JS code contains `CryptoJS.AES.encrypt` or `CryptoJS.AES.decrypt`
- Java hook output shows `Cipher.doFinal()` calls on API response data

### Step 2: Identify Algorithm

Read `~/.claude/reverse-skills/kb/patterns/crypto_patterns.md` and match:

AES-ECB indicators:
- `mode: CryptoJS.mode.ECB` or no mode specified → ECB
- No `iv` parameter in JS encrypt call
- Cipher.getInstance("AES/ECB/...")
- Key exactly 16 characters (AES-128)

AES-CBC indicators:
- `mode: CryptoJS.mode.CBC`
- `iv` parameter present in encrypt call
- Cipher.getInstance("AES/CBC/...")
- IV often = key[:16] or a fixed string

RC4 indicators:
- "RC4" in Cipher.getInstance or hook output
- Custom swap-based keystream function

RSA indicators:
- Long base64 public key strings
- "RSA" in Cipher.getInstance

### Step 3: Extract Encryption Key

Priority order for finding the encrypt_key:
1. JS source: search for `key = "..."`, `const KEY = "..."`, `encryptKey = "..."`
2. MMKV files (Phase 1): scan for 16-char alphanumeric strings
3. SharedPreferences XML: scan string values
4. Hook output: `SecretKeySpec(key, "AES")` → key bytes
5. Hardcoded in Java (if decompiled): `static final String KEY = "..."`

### Step 3b: Check for Session-Bound Key Derivation

IF key found via hook (step 3.4) but NOT found in static sources (steps 3.1-3.5):
→ Key is likely SESSION-BOUND (derived, not stored). Read `kb/patterns/crypto_patterns.md` Pattern 7.

1. Hook `SecretKeySpec.<init>(byte[], String)` with Java stack trace (use T9 template)
2. From stack trace: identify derivation caller class/method
3. Check cold start headers for derivation inputs:
   - `devicetoken` → device fingerprint (v3:AAAAA... format)
   - `clientsession` → session ID
   - `smdeviceid` → 数美 device fingerprint
4. Hook the derivation caller → capture inputs → replicate in Python
5. IF derivation is native (.so): mark `key_derivation: "native"` → either:
   a. Call .so function via Frida NativeFunction
   b. Accept session-scoped key (mark plugin as "requires Frida for key")

**Session-bound key output format:**
```
{
  "key_type": "session_derived",
  "key_length": 32,
  "derivation_source": "devicetoken + clientsession",
  "derivation_function": "com.app.crypto.KeyGenerator.generate",
  "derivation_layer": "native|java",
  "session_scoped": true,
  "can_replicate": false
}
```

### Step 4: Verify with crypto_aes

For each candidate key:
```
crypto_aes(mode="ECB", key=candidate, data=encrypted_response)
→ result is valid JSON? → KEY CONFIRMED
→ result is garbage? → try CBC / next candidate
```

### Step 5: Generate Python crypto.py

```python
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

ENCRYPT_KEY = "[extracted key]"
ENCRYPT_MODE = "ECB"  # or "CBC"

def decrypt_body(encrypted_data: str, key: str = ENCRYPT_KEY) -> dict:
    """Decrypt API response body.
    
    Args:
        encrypted_data: Base64-encoded encrypted response
        key: 16-byte AES key (default: extracted key)
    Returns:
        Decrypted JSON as dict
    """
    cipher = AES.new(key.encode(), AES.MODE_ECB)
    raw = cipher.decrypt(base64.b64decode(encrypted_data))
    return json.loads(unpad(raw, 16).decode())

def encrypt_body(data: dict, key: str = ENCRYPT_KEY) -> str:
    """Encrypt request body (symmetric).
    
    Args:
        data: Dict to encrypt
        key: 16-byte AES key
    Returns:
        Base64-encoded encrypted string
    """
    plain = json.dumps(data, separators=(',', ':')).encode()
    cipher = AES.new(key.encode(), AES.MODE_ECB)
    padded = pad(plain, 16)
    return base64.b64encode(cipher.encrypt(padded)).decode()
```

## Output Format

```
{
  "encryption_detected": true,
  "algorithm": "AES-128-ECB",
  "encrypt_key": "vt5i9pn9dwxj8na8",
  "key_source": "MMKV",
  "key_verified": true,
  "response_encrypted": true,
  "request_encrypted": false,
  "double_layer": true,
  "double_layer_note": "pub_enc header triggers outer; inner data field may also be encrypted"
}
```
