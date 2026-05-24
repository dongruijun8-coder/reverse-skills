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

## Pattern 4: Standard OAuth2
**Flow:** Authorize → get code → exchange code for token → refresh token on expiry
**Endpoints:** `/oauth/authorize`, `/oauth/token`, `/oauth/refresh`
**Detection:** Standard OAuth2 parameter names: client_id, client_secret, grant_type, redirect_uri, code, refresh_token
**Extract:** access_token from token endpoint response
**Refresh:** POST /oauth/token with grant_type=refresh_token
**Complexity:** Low. Standard protocol, well-documented. Rare in Chinese live-streaming apps.
