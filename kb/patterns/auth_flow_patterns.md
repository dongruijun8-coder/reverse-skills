# Authentication Flow Detection Patterns

## Pattern 1: Token Chain (Simple)
**Flow:** SMS code → login → get token → all requests with token
**Endpoints:** `/sms`, `/login`, subsequent requests carry token in body or header
**Detection:** Look for sequential `/sms` → `/login` calls. Login response contains "token" field. All other requests include token.
**Extract:** token from login response.data.token
**Refresh:** Token usually long-lived or refreshes via `/login` with stored credentials
**Cases:** popo_2026-05 (S_OK on valid token, F_BAN on room ban)
**Complexity:** Low. No signing required. Standard JSON body with token field.

## Pattern 2: Sign Token Chain
**Flow:** Get initial key → exchange for sign_token → decrypt → get active sign_key → sign all requests
**Endpoints:** `/app/key` (initial, empty-key signed) → `/sign/token` → decrypt response → all requests signed with active key
**Detection:**
- Endpoint named "key" or "sign/token" or "getSign"
- Response from key endpoint is encrypted (not plain JSON)
- All subsequent requests carry `sign` or `signature` header/body param
- sign param is 32-char uppercase hex (MD5)
**Extract:** sign_key from decrypted sign_token response (format: `sign_key_timestamp`)
**Refresh:** sign_key from API is session-scoped; re-run full chain on session expiry
**Cases:** mengyin_2026-05 (initial sign_key = "", key from /login/h5/sign/token, AES-ECB decrypted)
**Complexity:** High. Requires sign algorithm + encryption algorithm + multi-step chain.

## Pattern 3: Ticket Session
**Flow:** No login API. Ticket extracted from device local storage → injected into request headers → server validates ticket
**Endpoints:** No dedicated login endpoints. First API call already carries ticket.
**Detection:**
- No `/login` or `/sms` endpoints in captured traffic
- Requests carry `pub_ticket` or `ticket` header
- Ticket is long (100+ chars), looks like serialized Java object
- Ticket source: share_data.xml (Java serialization), MMKV, or SharedPreferences
**Extract:** adb pull app data → file_parse_java_serial or db_explore → extract ticket
**Refresh:** Ticket expires after hours → re-extract from device (adb pull) or app restart
**Cases:** mengyin_2026-05 (ticket from share_data.xml, pub_ticket header, ~hours lifetime)
**Complexity:** Medium. No login flow to reverse, but ticket extraction is device-dependent.

## Pattern 4: Multi-Channel Auth (IM + Push)

**Flow:** HTTP login → extract multiple credentials → connect IM SDK (RongCloud/TencentIM) → connect MQTT push → connect WebSocket

**Endpoints:** `/login` (HTTP) → IM SDK connect (TCP/proprietary) → MQTT broker (TCP) → WebSocket (WSS)

**Detection:**
- Login response contains `im_token`, `chat_token`, `rong_token`, or `tim_token` alongside HTTP token
- APK contains IM SDK libraries: RongCloud (`libRong*`), TencentIM (`libImSDK*`), 环信 (`libhyphenate*`)
- Multiple persistent connections after login (MQTT port 1883/8883, WebSocket)
- Push service initialization in Application.onCreate()

**Extract:**
- im_token from login response (used for IM SDK auth)
- mqtt_credentials (clientId, username, password) from login response or separate endpoint
- websocket_token for real-time updates

**Chain:**
1. HTTP POST /login with phone/SMS → get HTTP token + IM token + MQTT credentials
2. Connect RongCloud: `RongIMClient.connect(token, callback)`
3. Connect MQTT: `MqttClient.connect(broker, clientId, username, password)`
4. Connect WebSocket with auth token for push notifications
5. All three channels stay alive simultaneously

**Complexity:** Very High. Three independent auth chains. Each has different token lifecycle. IM/MQTT tokens may refresh independently of HTTP token.

**Cases:** 双鱼部落 2026-05 (HTTP login → RongCloud IM + MQTT + TencentIM + WebSocket, plaintext password)

**Key indicator in traffic:** Login response JSON has 5+ distinct token/credential fields. Look for `rongToken`, `imToken`, `mqttClientId`, `mqttPassword`, `timSig`.

## Pattern 5: Standard OAuth2
**Flow:** Authorize → get code → exchange code for token → refresh token on expiry
**Endpoints:** `/oauth/authorize`, `/oauth/token`, `/oauth/refresh`
**Detection:** Standard OAuth2 parameter names: client_id, client_secret, grant_type, redirect_uri, code, refresh_token
**Extract:** access_token from token endpoint response
**Refresh:** POST /oauth/token with grant_type=refresh_token
**Complexity:** Low. Standard protocol, well-documented. Rare in Chinese live-streaming apps.

## Pattern 6: Device-Bound Session Auth

**Flow:** App/init (device registration) → establish session → derive encryption key → login → get auth token

**Endpoints:** `App/init` or `device/register` → `/login` (or `/UI/PasswordLoginPage/passwordLogin`)

**Detection:**
- First request after app install is to `/App/init` or `/device/register` or `*/init`
- Request carries `devicetoken` header (long Base64, format like `v3:AAAAA...`)
- Request may carry `smdeviceid` (数美 device fingerprint) or other device ID headers
- Response returns `sessionId`, `token`, or sets `clientsession` cookie/header
- All subsequent requests include `clientsession` or `token` header from init response
- AES key derived from devicetoken/clientsession (NOT a static string in code)
- Login request fails with `120001 密钥获取失败` if session key doesn't match

**Extract:**
- `devicetoken` from App/init request headers (cold start capture)
- `clientsession` from App/init response or subsequent request headers
- `smdeviceid` from request headers (数美 SDK generated)
- AES key via Frida `Cipher.init` hook (per-session, must re-extract)

**Chain:**
1. Generate/obtain devicetoken (device fingerprint) → format `v3:AAAAA...` Base64
2. Generate/obtain smdeviceid (数美 fingerprint) → Base64 encoded
3. POST App/init with devicetoken, smdeviceid → get clientsession
4. Derive AES key from devicetoken + clientsession (algorithm TBD per-app)
5. Encrypt login request with derived key, include clientsession in headers
6. POST /login with encrypted credentials → get auth token
7. All subsequent requests: clientsession + auth token + derived key encryption

**Key indicators:**
- `devicetoken` header format: `v3:AAAAA...` (version prefix + Base64 data, 600+ chars)
- `smdeviceid` header: Base64-encoded device data from 数美 SDK
- `clientsession` header: session identifier (UUID or custom format)
- Error code `120001` = session key mismatch → key derivation wrong or session expired

**Complexity:** Very High. Requires: device fingerprint generation (or extraction from real device), key derivation reversal, session management. Cold start capture ESSENTIAL — cannot skip App/init phase.

**Cases:** 双鱼部落 2026-05 (App/init → devicetoken v3 format → AES key derived per-session → 120001 on mismatch)

**IM SDK Side-Channels:** Login response may also return credentials for non-HTTP protocols:
- `rongCloudToken` + `rongCloudId` → 融云 IM TCP connection
- `mqttClientId` + `mqttPassword` → MQTT push channel
- `timSig` → TencentIM SDK auth
- These require SEPARATE protocol implementation beyond HTTP plugin scope
