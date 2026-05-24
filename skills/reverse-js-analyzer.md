---
name: reverse-js-analyzer
description: Analyze JavaScript source to extract signature algorithm, encryption calls, and API endpoint patterns
---

# Reverse JS Analyzer

Analyze JavaScript source files (typically from H5/WebView assets) to find and extract signature algorithms, encryption calls, and API endpoint constructions.

## Input

- One or more `.js` file paths
- Optional: known endpoint paths (to search for URL construction near sign calls)

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

Read `kb/confidence_rules.json` and evaluate each pattern:

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
