---
name: reverse-apk-analyzer
description: APK static analysis — unpack, detect packer, extract manifest, scan strings, decompile if possible
---

# Reverse APK Analyzer

Analyze an APK file to detect packer, extract metadata, find domain/key candidates, and determine the analysis strategy.

## Execution

### Step 1: Unpack
Call `apk_unpack(apk_path, output_dir)` to extract the APK. An APK is a ZIP file; this extracts all contents.

### Step 2: Detect Packer
Call `apk_detect_packer(unpacked_dir)`. Check for these .so files:
- `libjiagu.so` or `libjiagu_x86.so` → "360加固"
- `libshella-*.so` or `libtup.so` → "Tencent Legu"
- `libexec.so` or `libexecmain.so` → "爱加密"
- None of the above → "none"

### Step 3: Determine Strategy
Read `~/.claude/reverse-skills/kb/patterns/packer_patterns.md` for the detected packer → set strategy.
Read `~/.claude/reverse-skills/kb/patterns/anti_patterns.md` → mark any strategies as "skip".

### Step 4: Extract Manifest
Call `apk_extract_manifest(unpacked_dir)`. Extract:
- `package` (package name, e.g. com.qiyu.dream)
- `versionName` (version string, e.g. 6.5.7)
- `versionCode` (build number)
- `permissions` (list of Android permissions)
- `activities` (list of Activity classes — entry points)
- `network_security_config` (if present — check for `<pin>` entries)

### Step 5: String Search
Call `apk_string_search(unpacked_dir, patterns=[...])` with these regex patterns:
- URL/domain: `https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+`
- Potential keys: `[A-Za-z0-9+/=]{32,}` (Base64-like strings)
- IP addresses: `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`

Filter domain candidates: prefer domains containing "api", "web", or the app name. Remove common CDN/image domains.

### Step 6: Decompile (if no packer)
IF packer == "none":
  Call `apk_decompile(apk_path, output_dir, threads=4)` → this runs jadx.
  After decompilation:
  - Search for `Retrofit`, `OkHttp`, `baseUrl`, `BASE_URL` in .java files
  - Search for `Cipher`, `MessageDigest`, `SecretKeySpec`, `Signature` → crypto classes
  - Search for `sign`, `SignUtil`, `MD5`, `SHA` → signature utility classes

IF packer != "none":
  Skip decompilation. Mark `decompile_skipped = true`.
  List `assets/` directory. Note any `.js` or `.html` files → these are H5 analysis targets.

### Step 7: Detect Device Fingerprint SDKs

Check for third-party device fingerprint SDKs (separate from packer detection):

**数美 (Shumei/Fengkong):**
- `libsmsdk.so` in lib/ directory
- `com.fengkong` or `com.shumei` in AndroidManifest
- Generates: `smdeviceid` header (Base64 device fingerprint)

**网易 Device Token:**
- `libne.so` (standalone) or `libnesec.so` (NIS packer)
- Generates: `devicetoken` header (v3:AAAAA... format, 600+ chars)
- Critical for NIS session-bound key derivation

**TrustDevice:**
- `libtrustdevice.so` in lib/ directory
- Third-party device fingerprint solution

### Step 8: Detect Third-Party IM/Communication SDKs

Check for non-HTTP communication SDKs that may need separate protocol handling:

**融云 (RongCloud) IM:**
- `libRongIMLib.so`, `libRongCallLib.so` in lib/
- Requires TCP connection (not HTTP) for messaging
- Extract: `rongCloudToken`, `rongCloudId` from login response

**TencentIM:**
- `libImSDK.so`, `libImSDKCore.so` in lib/
- Extract: `timSig`, `timUserId` from login response

**环信 (HuanXin) IM:**
- `libhyphenate*.so` in lib/

### Step 9: Case Matching
Read `~/.claude/reverse-skills/kb/case_library/index.json`. Search for cases where:
- `tags.packer` matches detected packer
- `tags.category` matches (infer from app name, permissions, string scan)

If match found: output the matched case as a reference strategy.

## Output Format

```
{
  "packer": "360" | "Tencent" | "爱加密" | "none",
  "strategy": {
    "decompile": true | false,
    "hooks": {"frida": true|false, "gadget": true|false, "lsposed": true|false},
    "js_analysis": true | false,
    "skip_reasons": {"frida": "anti_patterns:360+frida", ...}
  },
  "manifest": {"package": "...", "version": "...", "version_code": ..., "network_pinning": true|false},
  "domain_candidates": ["api.example.com", ...],
  "key_candidates": ["possible_key_1", ...],
  "matched_cases": ["mengyin_2026-05"],
  "assets": {"has_js": true|false, "js_files": ["app.js", ...], "has_h5": true|false},
  "device_fingerprint": {
    "shumei": {"detected": true|false, "lib": "libsmsdk.so", "header": "smdeviceid"},
    "netease": {"detected": true|false, "lib": "libne.so", "header": "devicetoken"},
    "trustdevice": {"detected": true|false, "lib": "libtrustdevice.so"}
  },
  "third_party_im": {
    "rongcloud": {"detected": true|false, "libs": ["libRongIMLib.so"], "protocol": "tcp"},
    "tencentim": {"detected": true|false, "libs": ["libImSDK.so"], "protocol": "tcp"},
    "huanxin": {"detected": true|false, "libs": ["libhyphenate.so"], "protocol": "tcp"}
  }
}
```
