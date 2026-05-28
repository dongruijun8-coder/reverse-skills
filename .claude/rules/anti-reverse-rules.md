# Anti-Reverse Strategy Rules

## Packer Detection → Hook Strategy

- IF libnesec.so EXISTS → skip_all_hooks=false; use hluda-server only (NOT frida-server); Magisk DenyList required; NO class enumeration/reflection/Object.keys/Java.cast; hook from app-layer down (Body.getData → Cipher.doFinal → Cipher.init)
- IF libjiagu.so OR libjiagu_x86.so EXISTS → skip_all_hooks = true → go H5 static analysis
- IF libshella-*.so OR libtup.so EXISTS → try frida_gadget first → fallback H5
- IF libexec.so OR libexecmain.so EXISTS → try lsposed first (weak anti-xposed) → fallback frida
- IF libDexHelper.so EXISTS → try frida_gadget → fallback H5
- IF libijmdata.so EXISTS → same as libexec.so (爱加密 legacy) → lsposed first
- IF no packer .so → run full hook suite (frida + lsposed both ok)

## Emulator Detection → Bypass Priority

- IF libemulatordetector.so EXISTS → configure Magisk Hide + MagiskHide Props Config BEFORE Phase 1
- IF app crashes on launch (no packer) → suspect emulator detection → check ro.build.type, ro.build.tags, sensors
- Priority: Magisk DenyList → Hide Props Config → device fingerprint spoof → real device fallback

## Frida Safety Guide (NIS / 加固 app 通用)

```
SAFE (always try first):
  - Hook 简单 getter/setter methods
  - Hook Cipher.doFinal() / Cipher.init()
  - Hook Gson.toJson() (selective, watch call frequency)
  - Hook MessageDigest.digest()
  - Hook SecretKeySpec.<init>()
  - Hook system classes (javax.crypto.*, java.security.*)

DANGEROUS (will crash NIS / 360):
  - Java.enumerateLoadedClasses() / Java.enumerateLoadedClassesSync()
  - getDeclaredFields() / setAccessible(true)
  - Java.cast(obj, SomeClass)
  - Object.keys() on Java objects
  - Java.scheduleOnMainThread() with complex closures

UNSTABLE (use with caution, depends on call frequency):
  - Hook 底层 okio/BufferedSink
  - Hook at BufferedSource level
  - Gson.toJson() on high-frequency endpoints
  - Hook UI thread methods (post, invalidate)

Hook strategy order:
  1. Enumerate method signatures first (Object.getMethods()) — SAFE if targeted
  2. Hook at app layer (HttpClientImp.createCall, Body.getData)
  3. Hook at crypto layer (Cipher, Gson)
  4. Only go to okio/BufferedSink as last resort
```

## OkHttp Version Detection

- IF user-agent contains "okhttp/5." → OkHttp 5.x (Kotlin migration, changed APIs)
  - RealCall class name may differ from OkHttp 3.x
  - RequestBody.create() has 15+ overloads — must enumerate method signatures
  - Interceptor is interface — hook implementation class, not interface
- IF user-agent contains "okhttp/3." or "okhttp/4." → standard API
  - RealCall.execute() / RealCall.enqueue() hookable
  - RequestBody.create(MediaType, String) works

## SSL Pinning Detection

- IF network_security_config.xml HAS <pin> → skip system_proxy → go frida ssl unpin first
- IF network_security_config.xml ABSENT → try system_proxy → system_cert → frida chain
- IF packer == "网易易盾" → 模拟器检测优先于 SSL pinning → 先解决 Magisk/hluda, 再处理 SSL

## Decompilation Decision

- IF packer != "none" → skip jadx → extract assets/ WebView JS instead
  - Exception: NIS app → check if partial decompilation yields API interface classes (Retrofit interfaces in assets might be extractable)
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

## Interface vs Implementation Class

- Retrofit interfaces (@GET, @POST annotations) → cannot be hooked directly (dynamic proxy)
- Must find implementation class (e.g. HttpClientImp) and hook the CALLER method
- Inside caller method: access interface method return values via .getPath() etc.
- Enumerate implementation class methods first → confirm method signatures → then hook
