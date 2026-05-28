# Packer Detection Patterns

## 网易易盾 NIS (libnesec.so)
**Detection:** `libnesec.so` + `MyApplication` class wraps NIS Application in manifest
**Anti-Frida:** Extreme — frida spawn → InvocationTargetException; frida-server attach → 原生层检测秒崩
**Anti-Xposed:** Strong — 检测 XposedBridge
**Anti-Reflection:** Extreme — `getDeclaredFields`, `Java.cast`, `Object.keys` 任意触发 → 崩溃
**Bypass:** hluda-server attach only (NOT frida-server). Magisk DenyList 隐藏 root. 禁止类枚举/反射.
**Hook 安全操作:** 简单 getter/setter, Cipher.doFinal/init, Gson.toJson (选择性)
**Hook 危险操作:** 类枚举, getDeclaredFields, setAccessible, Java.cast, Object.keys, 底层 okio/BufferedSink
**Strategy:** Magisk DenyList + hluda-server + 最小化 hook (应用层→加密层, 不碰底层)
**Evidence from cases:** 本次工作流 — 18版Frida脚本迭代, hluda是关键突破点

## 360加固 (libjiagu.so)
**Detection:** `libjiagu.so` or `libjiagu_x86.so` in lib/ directory
**Anti-Frida:** Strong — SIGSEGV within 2 seconds of frida-server detection
**Anti-Xposed:** Strong — detects XposedBridge, crashes on launch
**Bypass:** None known for Runtime Hook
**Strategy:** Skip ALL runtime hooks → H5/WebView JS static analysis + packet capture inference
**Evidence from cases:** mengyin_2026-05 (confirmed: frida died in 2s, LSPosed also detected)

## Tencent Legu (libshella-*.so)
**Detection:** `libshella-*.so` or `libtup.so` in lib/ directory
**Anti-Frida:** Medium — port scanning, process name detection
**Anti-Xposed:** Medium
**Strategy:** Try Frida Gadget first (in-process, no frida-server) → if detected, fallback H5

## 爱加密 (libexec.so)
**Detection:** `libexec.so` or `libexecmain.so` in lib/ directory
**Anti-Frida:** Medium
**Anti-Xposed:** Weak — less comprehensive Xposed detection
**Strategy:** Try LSPosed first (exploit weak anti-Xposed) → Frida Gadget fallback

## 梆梆加固 (libDexHelper.so)
**Detection:** `libDexHelper.so` or `libDexHelper-x86.so` in lib/ directory
**Anti-Frida:** Strong — DEX 抽取 + so 加密
**Anti-Xposed:** Medium
**Strategy:** Try Frida Gadget → fallback H5 static analysis

## 爱加密 (libijmdata.so)
**Detection:** `libijmdata.so` in lib/ directory (legacy variant)
**Anti-Frida:** Medium
**Anti-Xposed:** Weak
**Strategy:** Same as 爱加密 (libexec.so) — LSPosed first, then Frida Gadget

## 模拟器检测 (libemulatordetector.so)
**Detection:** `libemulatordetector.so` — not a packer, but critical for env setup
**Impact:** App detects emulator → crashes or refuses to run
**Bypass:** Magisk Hide + MagiskHide Props Config module + device fingerprint spoofing
**Note:** Check for this BEFORE Phase 1 — if present, emulator bypass must be solved first

## No Packer
**Detection:** No known packer .so files
**Strategy:** Full analysis suite — jadx decompile + Frida hook all crypto classes
**Evidence from cases:** popo_2026-05 (confirmed: clean decompile, no hook needed)
