# Encryption Scheme Detection Patterns

## Pattern 1: AES-128-ECB
**JS Signature:** `CryptoJS.AES.encrypt(data, key, {mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7})`
**Java Signature:** `Cipher.getInstance("AES/ECB/PKCS7Padding")`
**Confidence clues:** AES call (weight +10), no iv parameter (weight +25), key is static string (weight +20), PKCS7 padding (weight +15)
**Key characteristics:** No IV needed, same plaintext → same ciphertext (deterministic), 16-byte key
**Detection:** Find CryptoJS.AES or Cipher.getInstance → check mode parameter → check for iv presence
**Python equivalent:**
```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def decrypt_body(encrypted_b64, key):
    cipher = AES.new(key.encode(), AES.MODE_ECB)
    raw = cipher.decrypt(base64.b64decode(encrypted_b64))
    return json.loads(unpad(raw, 16).decode())
```
**Cases:** mengyin_2026-05 (key: vt5i9pn9dwxj8na8, encrypt_key from MMKV)

## Pattern 2: AES-128-CBC
**JS Signature:** `CryptoJS.AES.encrypt(data, key, {iv: iv, mode: CryptoJS.mode.CBC})`
**Java Signature:** `Cipher.getInstance("AES/CBC/PKCS7Padding")`
**Confidence clues:** AES call (weight +10), has iv parameter (weight +35), iv is fixed or key prefix (weight +25)
**Key characteristics:** Requires 16-byte IV, IV often = key[:16] or fixed string, PKCS7 padding
**Python equivalent:**
```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def decrypt_body(encrypted_b64, key, iv=None):
    if iv is None:
        iv = key[:16].encode() if isinstance(key, str) else key[:16]
    cipher = AES.new(key.encode(), AES.MODE_CBC, iv=iv)
    raw = cipher.decrypt(base64.b64decode(encrypted_b64))
    return json.loads(unpad(raw, 16).decode())
```

## Pattern 3: RC4 Stream Cipher
**JS Signature:** Custom RC4 implementation (rare in JS, more common in native)
**Java Signature:** `Cipher.getInstance("RC4")`
**Key characteristics:** Same key for encrypt and decrypt (symmetric stream), no IV, key as hex string
**Detection:** Look for "RC4" in Java classes or native hook output. May appear as custom function with swap/keystream logic.
**Python equivalent:**
```python
from Crypto.Cipher import ARC4

def rc4_crypt(data, key):
    cipher = ARC4.new(bytes.fromhex(key) if all(c in '0123456789abcdef' for c in key) else key.encode())
    return cipher.decrypt(data)
```

## Pattern 4: RSA Public Key Encryption
**JS Signature:** `JSEncrypt.encrypt(data)` or `forge.pki` or `window.androidJsObj.rsaEncrypt(data)`
**Java Signature:** `Cipher.getInstance("RSA/ECB/PKCS1Padding")`
**Detectio**Key characteristics:** 1024/2048-bit key, public key for encrypt (client → server), private key on server
**Detection:** Long base64 public key strings, "RSA" or "PKCS1" in cipher initialization
**Strategy:** Extract public key from JS/Java → use for verification, not for decryption (server holds private key)

## Pattern 5: Double-Layer Encryption
**JS/API Signature:** Outer body AES-encrypted + inner data field also AES-encrypted, OR pub_enc header triggers body encryption
**Detection:** Response has `pub_enc: true` header AND `data` field is base64 (not plain JSON)
**Strategy:** Decrypt outer layer first → check if inner data is still encrypted → decrypt inner layer
**Python approach:** Chain decrypt calls, check if result is valid JSON after each layer
**Cases:** mengyin_2026-05 (pub_enc header triggers body AES-ECB, data field may also be AES-encrypted)
