"""Crypto tools — AES/RC4/RSA encrypt/decrypt, hash, sign verification."""
import base64
import hashlib
import hmac
import json
from Crypto.Cipher import AES, ARC4
from Crypto.Cipher import PKCS1_v1_5 as PKCS1
from Crypto.PublicKey import RSA as RSAKey
from Crypto.Util.Padding import pad, unpad


def crypto_aes(mode: str, key: str, data: str, iv: str | None = None,
               operation: str = "decrypt", key_size: int = 128) -> dict:
    """AES encrypt/decrypt. Supports ECB, CBC, GCM modes.

    Args:
        mode: "ECB", "CBC", or "GCM"
        key: Key string. For AES-128: 16 chars. For AES-256: 32 chars.
        data: Base64-encoded input for decrypt, plain text for encrypt
        iv: IV/nonce string. 16 bytes for CBC. 12 bytes recommended for GCM.
        operation: "encrypt" or "decrypt"
        key_size: 128 or 256 (bits). Determines key length: 16 or 32 bytes.
    """
    expected_len = 32 if key_size == 256 else 16
    try:
        if len(key) >= expected_len:
            key_bytes = key[:expected_len].encode()
        elif len(key) >= 16:
            key_bytes = key[:16].encode()
        else:
            key_bytes = key.encode().ljust(16, b'\x00')
    except Exception as e:
        return {"status": "ERROR", "error": f"Invalid key: {e}"}

    try:
        if mode.upper() == "ECB":
            cipher = AES.new(key_bytes, AES.MODE_ECB)
        elif mode.upper() == "CBC":
            iv_bytes = (iv.encode() if iv else key_bytes)[:16]
            cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv_bytes)
        elif mode.upper() == "GCM":
            iv_bytes = (iv.encode() if iv else key_bytes)[:16]
            if len(iv_bytes) < 8:
                return {"status": "ERROR", "error": "GCM nonce too short (min 8 bytes recommended)"}
            cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=iv_bytes)
        else:
            return {"status": "ERROR", "error": f"Unknown mode: {mode}. Supported: ECB, CBC, GCM"}
    except Exception as e:
        return {"status": "ERROR", "error": f"Cipher init failed: {e}"}

    try:
        if operation == "decrypt":
            raw = base64.b64decode(data)
            if mode.upper() == "GCM":
                if len(raw) < 17:
                    return {"status": "ERROR", "error": "GCM data too short (need ciphertext + 16-byte tag)"}
                ct_bytes = raw[:-16]
                tag = raw[-16:]
                plain = cipher.decrypt_and_verify(ct_bytes, tag)
                result = plain.decode('utf-8')
            else:
                plain = cipher.decrypt(raw)
                unpadded = unpad(plain, 16)
                result = unpadded.decode('utf-8')

            is_json = False
            try:
                parsed = json.loads(result)
                is_json = True
            except json.JSONDecodeError:
                parsed = result
            return {"status": "OK", "result": parsed, "is_json": is_json, "raw": result, "mode": mode.upper()}
        else:
            plain = data.encode()
            if mode.upper() == "GCM":
                ct_bytes, tag = cipher.encrypt_and_digest(plain)
                encrypted = ct_bytes + tag
            else:
                padded = pad(plain, 16)
                encrypted = cipher.encrypt(padded)
            return {"status": "OK", "result": base64.b64encode(encrypted).decode(), "mode": mode.upper()}
    except Exception as e:
        return {"status": "ERROR", "error": f"Operation failed: {e}"}


def crypto_hash(algo: str, data: str, uppercase: bool = False) -> dict:
    """Compute MD5/SHA1/SHA256 hash.

    Args:
        algo: "md5", "sha1", "sha256"
        data: String to hash
        uppercase: If True, return uppercase hex
    """
    if algo.lower() == "md5":
        h = hashlib.md5(data.encode()).hexdigest()
    elif algo.lower() == "sha1":
        h = hashlib.sha1(data.encode()).hexdigest()
    elif algo.lower() == "sha256":
        h = hashlib.sha256(data.encode()).hexdigest()
    else:
        return {"status": "ERROR", "error": f"Unknown algorithm: {algo}"}

    return {"status": "OK", "result": h.upper() if uppercase else h}


def crypto_rc4(key: str, data: str, input_format: str = "hex") -> dict:
    """RC4 encrypt/decrypt.

    Args:
        key: Hex-encoded key string
        data: Data to encrypt/decrypt (hex or base64)
        input_format: "hex" or "base64"
    """
    try:
        key_bytes = bytes.fromhex(key)
    except ValueError:
        key_bytes = key.encode()

    try:
        if input_format == "hex":
            data_bytes = bytes.fromhex(data)
        elif input_format == "base64":
            data_bytes = base64.b64decode(data)
        else:
            data_bytes = data.encode()
    except Exception as e:
        return {"status": "ERROR", "error": f"Data decode failed: {e}"}

    try:
        cipher = ARC4.new(key_bytes)
        result = cipher.decrypt(data_bytes)
        return {"status": "OK", "result": result.hex(), "raw_bytes": len(result)}
    except Exception as e:
        return {"status": "ERROR", "error": f"RC4 failed: {e}"}


def crypto_rsa(key_pem: str, data: str, direction: str = "encrypt") -> dict:
    """RSA encrypt/decrypt.

    Args:
        key_pem: PEM-format RSA key string
        data: Base64-encoded data
        direction: "encrypt" or "decrypt"
    """
    try:
        key = RSAKey.import_key(key_pem)
    except Exception as e:
        return {"status": "ERROR", "error": f"Key import failed: {e}"}

    try:
        cipher = PKCS1.new(key)
        data_bytes = base64.b64decode(data)
        if direction == "encrypt":
            result = cipher.encrypt(data_bytes)
        else:
            result = cipher.decrypt(data_bytes, None)
        return {"status": "OK", "result": base64.b64encode(result).decode()}
    except Exception as e:
        return {"status": "ERROR", "error": f"RSA {direction} failed: {e}"}


def crypto_sign_verify(sign_code: str, params: dict, expected_sign: str, key: str = "") -> dict:
    """Verify a generated sign function against a captured request.

    This is the critical feedback loop tool. Agent generates sign() code,
    then calls this to verify it reproduces the captured signature.

    Args:
        sign_code: Python code string defining `def compute_sign(params, key):`
        params: The exact parameters from the captured request
        expected_sign: The signature value from the captured request
        key: The sign key to use (default empty string)
    """
    namespace = {}
    try:
        exec(sign_code, namespace)
    except Exception as e:
        return {"status": "ERROR", "error": f"sign_code exec failed: {e}"}

    if "compute_sign" not in namespace:
        return {"status": "ERROR", "error": "sign_code must define compute_sign(params, key) function"}

    try:
        actual = namespace["compute_sign"](dict(params), key)
    except Exception as e:
        return {"status": "ERROR", "error": f"compute_sign() call failed: {e}"}

    return {
        "status": "OK",
        "match": actual == expected_sign,
        "expected": expected_sign,
        "actual": actual,
        "expected_length": len(expected_sign),
        "actual_length": len(actual)
    }
