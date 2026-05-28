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

## Assuming Static Encryption Key
- **Trigger:** 从 Frida Cipher.init hook 捕获 key → 硬编码到 client.py → 后续请求返回 `120001`
- **Failure:** NIS/加固 app 的 AES key 是会话绑定的（从 devicetoken + clientsession 派生），不是静态字符串
- **Root cause:** Key 不在 MMKV/SP/DB/JS 中。Cipher.init 捕获的是当次会话的派生 key，重启 app 后 key 变化。
- **Alternative:** 逆向 key 派生函数（hook SecretKeySpec stack trace → 找 caller → 逆向派生逻辑）或每次会话重新 Frida 捕获
- **Cases:** 双鱼部落 2026-05 (32-byte key 每会话固定但跨会话不同, 120001 密钥获取失败)

## Skipping Cold Start Capture
- **Trigger:** 启动 app 时用户已登录 → 直接 UI 遍历 → 缺失 App/init 和设备注册流量
- **Failure:** 设备注册（App/init）是会话绑定的关键第一步。缺失则无法理解 devicetoken、clientsession、key 派生。
- **Alternative:** Phase 2 必须包含 Cold Start 子阶段：`pm clear {package}` → 重新启动 → 抓取完整初始化流量
- **Cases:** 双鱼部落 2026-05 (App/init 返回 session 数据, devicetoken 参与 key 派生)

## Ignoring Third-Party Device Fingerprint SDK
- **Trigger:** 只检测 packer .so → 忽略 数美/TrustDevice/NetEngine 等设备指纹 SDK
- **Failure:** `smdeviceid`、`devicetoken` 等设备指纹头缺失 → 服务端拒绝请求
- **Alternative:** Phase 0 检测 数美/网易/TrustDevice SDK → Phase 3 hook 指纹生成函数 → 提取生成逻辑
- **Detection:** APK 中包含 `libsmsdk.so`(数美)、`libne.so`(网易)、`libtrustdevice.so` 等

## Blindly Implementing Non-HTTP Protocols
- **Trigger:** 登录响应包含 `rongCloudToken`、`mqttPassword` → 尝试用 HTTP client 发送 IM 消息
- **Failure:** 融云/TencentIM/MQTT 使用私有 TCP 协议，不是 HTTP API。HTTP client 无法通信。
- **Alternative:** 提取 IM 凭据（token、appKey、userId）→ 标记为外部协议 → 使用官方 SDK 或逆向 TCP 协议
- **Cases:** 双鱼部落 2026-05 (send_message 需融云 TCP，非 HTTP)
