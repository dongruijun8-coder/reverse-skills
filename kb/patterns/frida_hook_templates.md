# Frida Hook Template Library

Battle-tested patterns from real reverse engineering sessions. Each template includes safety level, packer compatibility, and known pitfalls.

## Template Selection Quick Reference

| Template | Safety | NIS | 360 | Purpose |
|----------|--------|-----|-----|---------|
| T1: Request Headers | Safe | Yes | No | Capture auth headers, user-agent |
| T2: Body.getData | Safe | Yes | No | Response body decryption point |
| T3: HttpClientImp.createCall | Safe | Yes | No | Request params + endpoint paths |
| T4: Cipher.doFinal | Safe | Yes | No | Encryption algorithm detection |
| T5: Cipher.init | Safe | Yes | No | Key + IV capture |
| T6: Gson.toJson | Unstable | Caution | No | Serialization format |
| T7: OkHttp newCall | Safe | Yes | No | Traffic indicator |
| T8: SecretKeySpec init | Safe | Yes | No | Key material capture |

## Core Principle: App-Layer First, Not Bottom-Up

```
WRONG (bottom-up):  okio/BufferedSink → BufferedSource → ... → CRASH
RIGHT (top-down):   Headers → newCall → createCall → Body → Cipher → Gson
```

Start from application-layer APIs. Only go to crypto layer after confirming app-layer hooks are stable.

---

## T1: Request Headers Capture

**Target:** `okhttp3.Request$Builder.header(String, String)` or app-specific header builder
**Captures:** Authorization, pub_sign, pub_ticket, pub_enc, user-agent headers
**Safety:** Safe — simple method hook, no reflection
**Pitfalls:** OkHttp 5.x class names may differ from 4.x
**Strategy:** Hook this FIRST. Confirms Frida is working before attempting more complex hooks.

```javascript
// T1: Request Header Capture (NIS-safe)
Java.perform(function() {
    var RequestBuilder = Java.use("okhttp3.Request$Builder");
    RequestBuilder.header.overload('java.lang.String', 'java.lang.String').implementation = function(name, value) {
        console.log("[T1] header: " + name + " = " + value);
        send({"hook": "header", "name": name, "value": value});
        return this.header(name, value);
    };

    // Also hook addHeader for multi-value headers
    RequestBuilder.addHeader.overload('java.lang.String', 'java.lang.String').implementation = function(name, value) {
        console.log("[T1] addHeader: " + name + " = " + value);
        return this.addHeader(name, value);
    };
});
```

---

## T2: Response Body Capture (Minimal, NIS-Safe)

**Target:** `okhttp3.ResponseBody.getData()` or Kotlin data class getter
**Captures:** Raw response bytes → hex dump for encryption analysis
**Safety:** Safe — single getter hook, no reflection, no enumeration
**Pitfalls:** Return type may be ByteString (OkHttp 5.x) not byte[]. Check method signature first.
**Strategy:** The most successful hook from the 18-version iteration. v14 was this single hook.

```javascript
// T2: Body.getData — Minimal Response Capture (NIS-safe, v14 pattern)
Java.perform(function() {
    // NOTE: Enumerate method signatures FIRST before hooking.
    // The class and method names depend on OkHttp version and obfuscation.
    // Search unpacked APK strings for "RequestBody" or "getData" to find actual class.

    var Body = Java.use("okhttp3.ResponseBody");  // Adjust class name as needed

    // Try getData() — may be in parent class or Kotlin synthetic
    Body.getData.implementation = function() {
        var result = this.getData();
        console.log("[T2] Body.getData() = " + result.length + " bytes");

        // Hex dump first 128 bytes for crypto analysis
        var hex = "";
        for (var i = 0; i < Math.min(result.length, 128); i++) {
            hex += ("0" + (result[i] & 0xFF).toString(16)).slice(-2);
        }
        send({"hook": "Body.getData", "bytes": result.length, "hex": hex});
        return result;
    };
});
```

---

## T3: Request Parameter Capture (createCall)

**Target:** App-specific HTTP client implementation class (e.g. `com.example.http.HttpClientImp`)
**Captures:** Request method, path, query params
**Safety:** Safe — hooks implementation class method, calls interface methods inside hook
**Pitfalls:** Must find the IMPLEMENTATION class, not the Retrofit interface.
**Strategy:** v15 pattern. Enumerate methods of HttpClientImp first, then hook createCall.

```javascript
// T3: createCall — Request Capture (NIS-safe, v15 pattern)
Java.perform(function() {
    // Step 1: Find the implementation class (NOT the interface!)
    // Search APK strings for "createCall" or "HttpClient" to find class name.
    var HttpCli = Java.use("com.example.http.HttpClientImp");

    // Step 2: Enumerate method signatures first to find createCall overload
    // Look for: createCall(HttpRequest), createCall(String, HttpRequest), etc.

    // Step 3: Hook createCall — call interface methods INSIDE the hook
    HttpCli.createCall.overload('com.example.http.HttpRequest').implementation = function(req) {
        var path = "";
        var method = "";
        // Call INTERFACE methods on the request object — these work when called from inside the hook
        try { path = req.getPath(); } catch(e) {}
        try { method = req.getHttpMethod(); } catch(e) {}

        console.log("[T3] createCall: " + method + " " + path);
        send({"hook": "createCall", "method": method, "path": path});

        var result = this.createCall(req);
        return result;
    };
});
```

---

## T4: Cipher.doFinal — Encryption Detection

**Target:** `javax.crypto.Cipher.doFinal(byte[])`
**Captures:** Input/output byte arrays → algorithm detection
**Safety:** Safe — system class hook, never triggers detection
**Pitfalls:** Very high call frequency. Filter by stack trace or calling class to reduce noise.
**Strategy:** Used in crypto_detector preset. Combine with T5 for key capture.

```javascript
// T4: Cipher.doFinal — Algorithm Detection (safe for all packers)
Java.perform(function() {
    var Cipher = Java.use("javax.crypto.Cipher");
    var String = Java.use("java.lang.String");

    Cipher.doFinal.overload('[B').implementation = function(input) {
        var result = this.doFinal(input);
        var algo = this.getAlgorithm();
        var mode = "";

        // Only log AES operations (too many for RSA/ECDH)
        if (algo.indexOf("AES") !== -1) {
            console.log("[T4] Cipher.doFinal algo=" + algo +
                        " in=" + input.length + "B out=" + result.length + "B");
            send({"hook": "Cipher.doFinal", "algorithm": algo,
                  "input_len": input.length, "output_len": result.length});
        }
        return result;
    };
});
```

---

## T5: Cipher.init — Key + IV Capture

**Target:** `javax.crypto.Cipher.init(int, Key, ...)`
**Captures:** AES key bytes + IV (AlgorithmParameterSpec)
**Safety:** Safe — system class hook
**Pitfalls:** Must handle multiple overloads (init(mode, key), init(mode, key, params), etc.)
**Strategy:** Critical for Phase 3. This is where the encryption key material appears.

```javascript
// T5: Cipher.init — Key + IV Capture (safe for all packers)
Java.perform(function() {
    var Cipher = Java.use("javax.crypto.Cipher");
    var Arrays = Java.use("java.util.Arrays");

    Cipher.init.overload('int', 'java.security.Key', 'java.security.spec.AlgorithmParameterSpec').implementation = function(opmode, key, params) {
        var algo = this.getAlgorithm();
        if (algo.indexOf("AES") !== -1) {
            var keyBytes = key.getEncoded();
            var keyHex = "";
            for (var i = 0; i < keyBytes.length; i++) {
                keyHex += ("0" + (keyBytes[i] & 0xFF).toString(16)).slice(-2);
            }
            console.log("[T5] Cipher.init AES key=" + keyHex + " (" + (keyBytes.length * 8) + "bit)");

            // Try to get IV from params
            var ivHex = "none";
            try {
                var IvSpec = Java.use("javax.crypto.spec.IvParameterSpec");
                var ivBytes = Java.cast(params, IvSpec).getIV();  // CAUTION: Java.cast may crash NIS
                ivHex = "";
                for (var j = 0; j < ivBytes.length; j++) {
                    ivHex += ("0" + (ivBytes[j] & 0xFF).toString(16)).slice(-2);
                }
            } catch(e) {}

            send({"hook": "Cipher.init", "algorithm": algo, "opmode": opmode,
                  "key": keyHex, "key_bits": keyBytes.length * 8, "iv": ivHex});
        }
        return this.init(opmode, key, params);
    };

    // Simpler overload (without AlgorithmParameterSpec — ECB mode)
    Cipher.init.overload('int', 'java.security.Key').implementation = function(opmode, key) {
        var algo = this.getAlgorithm();
        if (algo.indexOf("AES") !== -1) {
            var keyBytes = key.getEncoded();
            var keyHex = "";
            for (var i = 0; i < keyBytes.length; i++) {
                keyHex += ("0" + (keyBytes[i] & 0xFF).toString(16)).slice(-2);
            }
            console.log("[T5] Cipher.init ECB key=" + keyHex);
            send({"hook": "Cipher.init", "algorithm": algo, "opmode": opmode,
                  "key": keyHex, "key_bits": keyBytes.length * 8});
        }
        return this.init(opmode, key);
    };
});
```

---

## T6: Gson Serialization

**Target:** `com.google.gson.Gson.toJson(Object)`
**Captures:** Request body serialization → confirms JSON format and field names
**Safety:** Unstable — high call frequency on NIS apps
**Pitfalls:** Don't hook all toJson calls. Filter by class name or stack trace.
**Strategy:** Use selectively. Only enable when you need to confirm serialization format.

```javascript
// T6: Gson.toJson — Serialization Confirmation (UNSTABLE on NIS)
Java.perform(function() {
    var Gson = Java.use("com.google.gson.Gson");

    Gson.toJson.overload('java.lang.Object').implementation = function(obj) {
        var result = this.toJson(obj);
        var className = obj.getClass().getName();

        // Only log API-related classes (filter out UI, internal)
        if (className.indexOf("Request") !== -1 || className.indexOf("Param") !== -1) {
            console.log("[T6] Gson.toJson class=" + className + " -> " + result);
            send({"hook": "Gson.toJson", "class": className, "json": result});
        }
        return result;
    };
});
```

---

## T7: OkHttpClient.newCall — Traffic Indicator

**Target:** `okhttp3.OkHttpClient.newCall(Request)`
**Captures:** Every HTTP request URL + method → traffic count
**Safety:** Safe — high-level API, no reflection
**Pitfalls:** None. Use as first hook to confirm Frida is working.
**Strategy:** Always hook this first. Confirms hook is alive and counts API calls.

```javascript
// T7: OkHttpClient.newCall — Traffic Indicator (safest hook, do this first)
Java.perform(function() {
    var OkHttpClient = Java.use("okhttp3.OkHttpClient");

    OkHttpClient.newCall.overload('okhttp3.Request').implementation = function(request) {
        var url = request.url().toString();
        var method = request.method();
        console.log("[T7] newCall: " + method + " " + url);
        send({"hook": "newCall", "method": method, "url": url});
        return this.newCall(request);
    };
});
```

---

## T8: SecretKeySpec — Key Material

**Target:** `javax.crypto.spec.SecretKeySpec.<init>(byte[], String)`
**Captures:** Raw key bytes at construction time
**Safety:** Safe — system class hook
**Pitfalls:** May fire for non-API crypto (TLS, WebView). Filter by algorithm.
**Strategy:** Use as backup if Cipher.init doesn't fire (key might be set via SecretKeySpec).

```javascript
// T8: SecretKeySpec — Key Material Capture
Java.perform(function() {
    var SecretKeySpec = Java.use("javax.crypto.spec.SecretKeySpec");

    SecretKeySpec.$init.overload('[B', 'java.lang.String').implementation = function(key, algorithm) {
        if (algorithm.indexOf("AES") !== -1) {
            var keyHex = "";
            for (var i = 0; i < Math.min(key.length, 32); i++) {
                keyHex += ("0" + (key[i] & 0xFF).toString(16)).slice(-2);
            }
            console.log("[T8] SecretKeySpec AES key=" + keyHex + " (" + (key.length * 8) + "bit)");
            send({"hook": "SecretKeySpec", "algorithm": algorithm,
                  "key": keyHex, "key_bits": key.length * 8});
        }
        return this.$init(key, algorithm);
    };
});
```

---

## Composition: Recommended Hook Orders

### NIS App (libnesec.so) — Minimal Safe Chain
```
1. T7 (newCall)        → confirm Frida alive
2. T1 (Headers)        → capture auth headers
3. T3 (createCall)     → capture request params + endpoints
4. T2 (Body.getData)   → capture response body
5. T4+T5 (Cipher)      → algorithm + key
6. T6 (Gson)           → ONLY if needed, selective
```

### No Packer — Full Suite
```
1. T7 (newCall)        → traffic indicator
2. T1 (Headers)        → auth headers
3. T3 (createCall)     → request params
4. T2 (Body.getData)   → response body
5. T8 (SecretKeySpec)  → key material
6. T4+T5 (Cipher)      → algorithm + key (cross-validate with T8)
7. T6 (Gson)           → serialization format
```

### 360加固 — Skip All Hooks
```
→ Skip to H5/WebView JS static analysis
```
