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

## NIS + frida-server (all variants)
- **Trigger:** libnesec.so + frida-server (spawn or attach)
- **Failure:** Spawn → InvocationTargetException; Attach → 原生层检测秒崩
- **Alternative:** Use hluda-server instead. NEVER use frida-server on NIS apps.
- **Cases:** 本次工作流 (frida spawn/attach 均崩溃, hluda attach 成功)

## NIS + 类枚举 (enumerateLoadedClasses)
- **Trigger:** libnesec.so + Frida `Java.enumerateLoadedClasses()`
- **Failure:** 大量类加载触发 NIS 检测 → 偶尔崩溃
- **Alternative:** 先用 apk_string_search + manifest 推测类名, 再针对性 hook, 不枚举

## NIS + 反射 (getDeclaredFields/setAccessible)
- **Trigger:** libnesec.so + `getDeclaredFields()` or `setAccessible(true)`
- **Failure:** NIS 检测 JNI/反射调用 → 崩溃
- **Alternative:** 先枚举方法签名 (Object.getMethods()) 确定类结构, 再直接 hook 具体方法

## NIS + Object.keys / Java.cast
- **Trigger:** libnesec.so + `Object.keys()` or `Java.cast(obj, SomeClass)`
- **Failure:** NIS 检测类型操作 → 崩溃
- **Alternative:** 使用 `.toString()` 或 hook 具体 getter 方法获取字段值

## NIS + 底层 okio/BufferedSink hook
- **Trigger:** libnesec.so + hook at okio/BufferedSink level
- **Failure:** Hook 太底层, 调用频率极高 → 崩溃或不稳定
- **Alternative:** 从应用层 API 入手 (Body.getData, HttpClientImp.createCall), 逐层下探

## Interface Hook
- **Trigger:** Hook Retrofit/OkHttp interface methods directly (e.g. HttpRequest.setParam)
- **Failure:** 接口方法不可 hook — 动态代理生成的实现类不走 interface 方法
- **Alternative:** Hook 实现类的调用点 (如 HttpClientImp.createCall(req)), 在方法体内调用 req.getPath() 等

## OkHttp 5.x API Assumption
- **Trigger:** 使用 OkHttp 3.x API (RealCall, RequestBody.create(MediaType, String)) 在 5.x app 上
- **Failure:** OkHttp 5.x 大量 API 迁移到 Kotlin, overload 数量/签名完全不同
- **Alternative:** 先枚举目标类方法签名 → 确认参数类型 → 再针对性 hook
- **Cases:** 本次工作流 (user-agent: okhttp/5.3.2, RealCall 类名变化, RequestBody.create 15个overloads)
