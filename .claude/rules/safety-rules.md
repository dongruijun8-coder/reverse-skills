# Safety Rules

## Device Safety
- adb root only on userdebug/eng builds (check ro.build.type)
- Never adb remount on production/user builds
- Never modify /system on non-rooted devices

## Network Safety
- Never send traffic to production servers without explicit user confirmation
- Rate limit API calls: max 5 requests/second, max 50 requests/minute per endpoint
- Stop if server returns 429 (rate limit) → wait 60s → resume

## Data Safety
- Generated code (plugin.py, sign.py, crypto.py) must NOT contain hardcoded real credentials
- Use placeholder values: "YOUR_UID_HERE", "YOUR_TICKET_HERE"
- Case library (kb/case_library/) must NOT store real uid, token, ticket values
- Sanitize credentials in audit.jsonl: replace actual values with "<REDACTED>"

## File Safety
- Never overwrite existing api_spec.json without backup
- Before writing, check if file exists → if yes → backup to api_spec.json.bak
- Never delete raw_flows/ without user confirmation
