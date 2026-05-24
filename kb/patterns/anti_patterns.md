# Anti-Patterns — Known Failure Combinations

> **Purpose:** Prevent the agent from wasting time on approaches known to fail.

## 360 + Frida (all variants)
- **Trigger:** libjiagu.so + any frida method
- **Failure:** SIGSEGV within 2 seconds
- **Alternative:** Skip to H5 static analysis
- **Cases:** mengyin_2026-05

## 360 + Xposed/LSPosed
- **Trigger:** libjiagu.so + LSPosed active
- **Failure:** App detects XposedBridge → immediate crash
- **Alternative:** Skip to H5 static analysis
- **Cases:** mengyin_2026-05

## jadx + Any Packer
- **Trigger:** packer != "none" + jadx decompile
- **Failure:** Only shell classes (R.java, stub Application) decompiled
- **Alternative:** Extract assets/ WebView JS files instead
- **Cases:** mengyin_2026-05

## System Proxy + Certificate Pinning
- **Trigger:** network_security_config has <pin> + system proxy
- **Failure:** SSL handshake failed, no traffic captured
- **Alternative:** Skip directly to Frida SSL unpin

## Guessing sign_key
- **Trigger:** sign_key unknown + attempting random values
- **Failure:** Infinite 403 loop
- **Alternative:** Go back to JS/native layer to find key source (MMKV, SP, API response, native .so strings)
- **Cases:** mengyin_2026-05

## web_token Assumption
- **Trigger:** Seeing Authorization header → assuming web_token is required
- **Failure:** Wasting time finding web_token endpoint that doesn't matter
- **Alternative:** Try removing the Authorization header first — it may not be required
- **Cases:** mengyin_2026-05 (pub_ticket was sufficient)
