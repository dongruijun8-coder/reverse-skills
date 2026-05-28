# Signature Algorithm Detection Patterns

## Pattern 1: MD5 + Key Suffix
**JS Signature:** `MD5(sorted_params + "&key=" + sign_key)` or `CryptoJS.MD5(params_string + "&key=" + key)`
**Confidence clues:** `&key=` string concatenation (weight +40), sort/filter on params (weight +25)
**Key characteristics:** key appended with "&key=" separator, params sorted alphabetically, some keys excluded from sign
**Initial sign_key:** Often empty string `""` for initial `/app/key` endpoint, then replaced with API-returned key
**Python equivalent:**
```python
def compute_sign(params, key):
    excluded = {"pub_sign", "pub_uid", "pub_ticket", "sign", "ticket"}
    filtered = {k: v for k, v in params.items() if k not in excluded}
    sorted_pairs = sorted(filtered.items())
    query = "&".join(f"{k}={v}" for k, v in sorted_pairs)
    return hashlib.md5((query + "&key=" + key).encode()).hexdigest().upper()
```
**Cases:** mengyin_2026-05 (sign_key initial = "", from /login/h5/sign/token)

## Pattern 2: HMAC-SHA256
**JS Signature:** `CryptoJS.HmacSHA256(data, key).toString()`
**Confidence clues:** HmacSHA256 call (weight +15), key as separate parameter (weight +35), data is concatenated params (weight +30)
**Key characteristics:** Key is separate from data, output often Base64 or hex
**Detection:** Look for `HmacSHA256(` in JS → trace key argument → trace data argument
**Python equivalent:**
```python
import hmac, hashlib
def compute_sign(data, key):
    return hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()
```

## Pattern 3: Custom Sort + Hash
**JS Signature:** `hash(params.sort().join("") + secret)`
**Confidence clues:** sort call (weight +20), join call (weight +20), hash after join (weight +30), key concatenation (weight +30)
**Key characteristics:** Custom sort key (not just alphabetical), custom join delimiter, variable hash function
**Detection:** Look for `.sort()` followed by `.join()` followed by `MD5/SHA/Hmac`
**Python equivalent:** Adapt based on specific JS implementation

## Pattern 4: Multi-Layer Sign
**JS Signature:** `sign1(sign2(params))` — nested signature calls
**Characteristics:** Inner sign computed first, outer sign wraps result; often different keys for each layer
**Detection:** Find sign function → check if its input is another sign function call
**Strategy:** Decompose from outer to inner, verify each layer independently with `crypto_sign_verify`

## Pattern 5: XOR Pair (p1 XOR p2)

**JS/Native Signature:** `param1 XOR param2 = plaintext` (custom obfuscation, not a hash)
**Confidence clues:** Two paired encoded fields (weight +25), same-length Base64 strings (weight +20), XOR result is readable (weight +35)
**Key characteristics:** Neither field alone is meaningful. XOR produces key=value pairs or JSON. Often combined with Base64 encoding on both inputs.
**Detection:** Request has p1+p2 (or param1+param2, enc1+enc2) fields → both Base64 → decode → XOR → plaintext appears
**Python equivalent:**
```python
def xor_decode(p1_b64, p2_b64):
    b1 = base64.b64decode(p1_b64)
    b2 = base64.b64decode(p2_b64)
    result = bytes(a ^ b for a, b in zip(b1, b2))
    return result.decode('utf-8')
```
**Cases:** 双鱼部落 2026-05 (p1 XOR p2 = plaintext params, custom NetEase decryption)

**Post-Login State Transition (critical for XOR Pair):**
- Pre-login: p1 = random nonce, p2 = random nonce (p1 XOR p2 = plaintext), p3 = random
- Post-login: p1 = FIXED (derived from auth token or session), p2 = request signature (computed per-request), p3 = may change role
- Detection: Compare p1 values across pre-login and post-login requests. If p1 becomes invariant after login → token-derived.
- Strategy: Hook post-login p1 generation → trace to token → replicate derivation

## Pattern 6: Native (JS Bridge) Sign
**JS Signature:** `window.androidJsObj.sign(params)` or bridge call
**Characteristics:** JS delegates sign to native Java/Kotlin code via WebView bridge
**Detection:** Search for `androidJsObj.`, `webkit.messageHandlers.`, `jsBridge.` calls with "sign" or "encrypt" in name
**Strategy:** Cannot extract from JS alone — must hook native layer with Frida/LSPosed. Use `hook_gen_frida` targeting the bridge class.
