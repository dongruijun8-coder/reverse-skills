---
name: reverse-js-analyzer
description: Analyze JavaScript source to extract signature algorithm, encryption calls, and API endpoint patterns
---

# Reverse JS Analyzer

Analyze JavaScript source files (typically from H5/WebView assets) to find and extract signature algorithms, encryption calls, and API endpoint constructions.

## Role in Phase 3

Execution order depends on packer — see orchestrator Phase 3 for details:
- **NIS app:** Dynamic hook runs FIRST (3a). JS analysis (3b) is supplementary — cross-validate findings from hook output.
- **360加固:** JS analysis is PRIMARY (only path available). All hooks skipped.
- **No packer:** JS analysis runs first (3a), dynamic hook supplementary (3b).

## Input

- One or more `.js` file paths
- Optional: known endpoint paths (to search for URL construction near sign calls)
- Optional: hook output from Phase 3a (cross-reference sign candidates against actual captured sign values)

## Execution

### Step 1: Search for Crypto/Sign Patterns

Search each JS file for these keywords:
- `MD5`, `md5`, `CryptoJS.MD5`
- `SHA`, `sha256`, `HmacSHA`, `SHA256`
- `encrypt`, `decrypt`, `AES`, `CryptoJS.AES`
- `sign`, `signature`, `getSign`, `computeSign`
- `&key=`, `"&key="`, `'&key='` (key concatenation)
- `.sort()`, `.filter()`, `.join()` near hash calls

### Step 2: For Each Candidate — Compute Confidence

Read `~/.claude/reverse-skills/kb/confidence_rules.json` and evaluate each pattern:

MD5_key_pattern:
- Has MD5 call? (+10)
- Input contains `&key=`? (+40)
- Input has sort/filter? (+25)
- Output is uppercase hex? (+15)
- Result used as header/body param named "sign"? (+10)

Confidence thresholds:
- ≥ 70: confident → generate Python code
- 40-69: suspicious → mark, keep searching for corroborating evidence
- < 40: ignore → probably just a regular hash

### Step 3: Trace Key Source

For confident candidates, trace the sign key origin:
1. Is `sign_key` initialized as empty string `""`?
2. Is it loaded from an API response?
3. Is it loaded from localStorage/MMKV/SP?
4. Is it a constant?
5. Is it passed from native via JS Bridge?

### Step 4: Extract Parameter Filtering Rules

Find which parameters are excluded from the signature:
- Search for array of excluded keys near the sign function
- Search for `delete params.xxx` or filter calls
- Common exclusions: sign, ticket, token, uid, timestamp headers, device info fields

### Step 5: Generate Python sign()

Generate a `sign.py` file with:
```python
import hashlib

def compute_sign(params: dict, key: str) -> str:
    """[Description of algorithm from JS analysis]
    
    Example:
        >>> compute_sign({"pub_timestamp": "123", "a": "1"}, "")
        "ABC123DEF456..."
    """
    # Exclude these keys from signing
    excluded = {[extracted excluded keys]}
    
    # Filter and sort
    filtered = {k: v for k, v in params.items() if k not in excluded}
    pairs = sorted(filtered.items())
    
    # Build query string
    query = "&".join(f"{k}={v}" for k, v in pairs)
    
    # Append key
    query += "&key=" + key
    
    # Hash and return
    return hashlib.md5(query.encode()).hexdigest().upper()
```

### Step 6: Verify with crypto_sign_verify

Call `crypto_sign_verify(sign_code, captured_params, expected_sign)` to validate against actual captured traffic. Only mark complete when at least 3 different requests verify correctly.

## Output Format

```
{
  "sign_function": "MD5(params + &key= + key)",
  "confidence": 90,
  "file": "app.js",
  "line": 4523,
  "function_name": "I",
  "sign_key_source": "API response (/login/h5/sign/token)",
  "sign_key_initial": "",
  "excluded_keys": ["pub_sign", "pub_uid", "pub_ticket", ...],
  "sort_rule": "alphabetical_by_key",
  "hash_algorithm": "MD5",
  "output_format": "uppercase_hex",
  "verified": true,
  "verification_count": 3
}
```

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
