# SSL Bypass Decision Tree

## IMPORTANT: Packer-Aware Priority

Before SSL bypass, check packer type. For NIS/360 apps, environment bypass (emulator detection, root hiding) takes priority over SSL:

- **NIS (libnesec.so):** 先解决模拟器检测 (Magisk DenyList + hluda) → 再处理 SSL. 否则 app 直接崩溃, SSL 策略无意义.
- **360 (libjiagu.so):** 跳过所有 Runtime Hook SSL 策略. 仅尝试 system cert → iptables → Chrome DevTools.
- **无加固:** 按标准链进行.

## Certificate Installation Note

- **userdebug/eng build:** `adb_install_cert` → push to `/system/etc/security/cacerts/` directly
- **production build (user):** 需要 MoveCertificate 模块 (Magisk) 将用户 CA 移动到系统信任区. Skill 默认假设有此模块.

## Strategy Chain (try in order, stop on first success)

### 1. System HTTP Proxy
- **Command:** `adb shell settings put global http_proxy <host>:8080`
- **Check:** After 30s, `proxy_list_flows()` → any non-SDK hostnames?
- **Success rate:** High (works for apps without certificate pinning)
- **Fallback reason:** SSL handshake failure → likely cert pinning
- **Evidence from cases:** popo_2026-05 (confirmed: direct proxy worked)

### 2. System CA Certificate
- **Command:** `adb_install_cert(cert_path)` → pushes mitmproxy CA to /system/etc/security/cacerts/
- **Check:** Reboot device, restart app, wait 30s, check flows
- **Success rate:** Medium (works for apps pinning against user CA only)
- **Fallback reason:** Still SSL failure → app has custom TrustManager or pins against system CA
- **Evidence from cases:** mengyin_2026-05 (confirmed: H5 pages loaded after system cert install)

### 3. Frida SSL Unpin
- **Script targets:** SSLContext.init, TrustManager.checkServerTrusted, OkHttp CertificatePinner, Cronet
- **Check:** Run hook, restart app, wait 60s, check flows
- **Success rate:** High for non-packed apps, zero for 360-packed apps
- **Fallback reason:** Frida detected (process crash) → try Frida Gadget
- **Skip condition:** packer == "360加固" → skip directly (anti_patterns.md)
- **Script generation:** `hook_gen_frida(target_classes=["javax.net.ssl.SSLContext", "javax.net.ssl.TrustManager", "okhttp3.CertificatePinner"])`

### 4. Frida Gadget SSL Unpin
- **Method:** Inject libfrida-gadget.so into APK, no frida-server needed
- **Check:** Repackage APK, install, launch, check flows
- **Success rate:** Medium (harder to detect, but more complex setup)
- **Fallback reason:** Port scanning detection or gadget crash
- **Skip condition:** packer == "360加固" → skip directly

### 5. iptables Transparent Proxy
- **Command:** `adb shell iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8080`
- **Check:** No proxy settings on device, all 443 traffic redirected at kernel level
- **Success rate:** Low (many issues with redirect rules, TLS SNI problems)
- **Fallback reason:** App uses non-HTTP protocol or custom TCP stack
- **Cleanup:** `adb shell iptables -t nat -F OUTPUT`

### 6. WebView Chrome Debugging
- **Method:** Enable WebView debugging, connect via `chrome://inspect` in Chrome
- **Check:** Monitor WebView network requests in Chrome DevTools Network panel
- **Success rate:** Medium (only works for H5/WebView content, not native HTTP)
- **Fallback reason:** App is fully native (no WebView) or WebView debugging disabled

### 7. H5 Static Analysis (Last Resort)
- **Strategy:** Skip network capture entirely
- **Method:** Analyze downloaded JS files statically to infer API structure from code
- **Success rate:** Low-Medium (can infer API paths and params, but can't verify responses or detect hidden endpoints)
- **When used:** All capture methods exhausted + JS files available from Phase 0 assets

## Decision Metadata

| Factor | Decision |
|--------|----------|
| packer == "360加固" | Skip strategies 3-4 (Frida). Start at strategy 2 (system cert) or 5 (iptables) |
| network_config has <pin> | Skip strategy 1 (system proxy). Start at strategy 2 (system cert) |
| no JS files in assets | Strategy 7 (H5 static) is not viable |
| userdebug/eng build | Strategy 2 (system cert) has higher chance of success |
