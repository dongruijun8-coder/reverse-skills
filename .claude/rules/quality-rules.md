# Quality Gate Rules

## api_spec.json Quality
- Must pass schema validation
- Must have at least 1 endpoint in each category (auth, rooms, rank)
- Must have base_url starting with "https://"
- Must have non-empty common_params.headers

## plugin.py Quality
- Must pass `python -c "import plugin"` without SyntaxError or ImportError
- Must pass `python -c "from plugin import *Plugin; assert issubclass(*Plugin, BasePlugin)"`
- Must implement all 5 BasePlugin abstract methods
- authenticate() must return AuthResult (not raise exception) on invalid credentials

## sign.py Quality
- Must have compute_sign(params, key) -> str function
- Must pass verify against at least 3 different captured requests
- Must include docstring with expected input/output example

## crypto.py Quality
- Must have decrypt_body(encrypted_data, key) -> dict function
- Must have encrypt_body(plain_data, key) -> str function (symmetric)
- Must handle both Base64 and hex input formats

## Pre-commit Gate
- All smoke tests pass before marking Phase 5 SUCCESS
- If any smoke test fails → feedback loop to corresponding Phase
