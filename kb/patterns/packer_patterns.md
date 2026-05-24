# Packer Detection Patterns

## 360加固 (libjiagu.so)
**Detection:** `libjiagu.so` or `libjiagu_x86.so` in lib/ directory
**Anti-Frida:** Strong — SIGSEGV within 2 seconds of frida-server detection
**Anti-Xposed:** Strong — detects XposedBridge, crashes on launch
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

## No Packer
**Detection:** No known packer .so files
**Strategy:** Full analysis suite — jadx decompile + Frida hook all crypto classes
**Evidence from cases:** popo_2026-05 (confirmed: clean decompile, no hook needed)
