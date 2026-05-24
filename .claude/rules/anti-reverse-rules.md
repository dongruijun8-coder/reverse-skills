# Anti-Reverse Strategy Rules

## Packer Detection → Hook Strategy

- IF libjiagu.so OR libjiagu_x86.so EXISTS → skip_all_hooks = true → go H5 static analysis
- IF libshella-*.so OR libtup.so EXISTS → try frida_gadget first → fallback H5
- IF libexec.so OR libexecmain.so EXISTS → try lsposed first (weak anti-xposed) → fallback frida
- IF no packer .so → run full hook suite (frida + lsposed both ok)

## SSL Pinning Detection

- IF network_security_config.xml HAS <pin> → skip system_proxy → go frida ssl unpin first
- IF network_security_config.xml ABSENT → try system_proxy → system_cert → frida chain

## Decompilation Decision

- IF packer != "none" → skip jadx → extract assets/ WebView JS instead
- IF packer == "none" → run jadx → search for API constants, CryptoManager, SignUtil

## Domain Discovery

- Priority: apk_string_search → db_explore → proxy_list_flows
- IF domain_candidates > 3 → filter by (has "api" OR has "web" OR has app name) in domain
- IF domain_candidates == 0 → PAUSE with "no domain candidates found"

## Credential Extraction

- Priority: MMKV → SharedPreferences XML → SQLite DB → API response
- IF credential_source == "share_data.xml" → use file_parse_java_serial
- IF credential_source == "mmkv" → use db_explore with MMKV decoder
- IF no credentials found in any source → mark credential_extraction_failed → continue (Phase 2 may still work)
