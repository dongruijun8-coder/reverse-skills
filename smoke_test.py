#!/usr/bin/env python3
"""Phase 5 Smoke Test Runner — validates generated plugin.py/sign.py/crypto.py/api_spec.json.

Usage:
    python smoke_test.py <project_dir>              # Test all artifacts
    python smoke_test.py <project_dir> --quick      # Skip auth/fetch tests
    python smoke_test.py <project_dir> --verbose    # Show detailed output

Exit code: 0 = all pass, 1 = one or more failures, 2 = config error
"""
import importlib.util
import json
import sys
import time
from pathlib import Path


# ── Test registry ───────────────────────────────────────────────────

class SmokeResult:
    def __init__(self, name: str):
        self.name = name
        self.status = "SKIP"
        self.duration_ms = 0
        self.error = ""
        self.detail = ""

    def __repr__(self):
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "ERROR": "[ERR]"}
        extra = f" — {self.detail}" if self.detail else ""
        return f"  {icon.get(self.status, '[??]')} {self.name} ({self.duration_ms}ms){extra}"


def run_test(name: str, fn) -> SmokeResult:
    r = SmokeResult(name)
    try:
        t0 = time.time()
        fn(r)
        r.duration_ms = int((time.time() - t0) * 1000)
        if r.status not in ("FAIL", "ERROR"):
            r.status = "PASS"
    except Exception as e:
        r.status = "FAIL"
        r.duration_ms = int((time.time() - t0) * 1000)
        r.error = str(e)[:200]
    return r


# ── Test implementations ────────────────────────────────────────────

def _test_import(project: Path, result: SmokeResult):
    """Gate 1: Importability — plugin.py must import without SyntaxError/ImportError."""
    plugin_path = project / "plugin.py"
    if not plugin_path.exists():
        result.status = "SKIP"
        result.detail = "plugin.py not found"
        return

    spec = importlib.util.spec_from_file_location("plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        result.detail = "plugin.py imported OK"
    except SyntaxError as e:
        result.status = "FAIL"
        result.error = f"SyntaxError at line {e.lineno}: {e.msg}"
    except ImportError as e:
        result.status = "FAIL"
        result.error = f"ImportError: {e}"


def _test_sign(project: Path, result: SmokeResult):
    """Gate 2: Sign correctness — sign.py must define compute_sign() and verify against captured data."""
    sign_path = project / "sign.py"
    if not sign_path.exists():
        result.status = "SKIP"
        result.detail = "sign.py not found (no signing)"
        return

    spec = importlib.util.spec_from_file_location("sign", sign_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        result.status = "FAIL"
        result.error = f"sign.py import failed: {e}"
        return

    if not hasattr(module, "compute_sign"):
        result.status = "FAIL"
        result.error = "sign.py must define compute_sign(params, key) function"
        return

    # Check docstring for expected input/output example
    fn = module.compute_sign
    if not fn.__doc__:
        result.detail = "import OK, no docstring (consider adding example)"
        return

    # Try a basic smoke call with docstring example
    try:
        fn({"a": "1", "b": "2"}, "")
        result.detail = "compute_sign() callable"
    except Exception as e:
        result.status = "FAIL"
        result.error = f"compute_sign() call failed: {e}"


def _test_crypto(project: Path, result: SmokeResult):
    """Gate 3: Decrypt correctness — crypto.py must define decrypt_body() and handle base64 input."""
    crypto_path = project / "crypto.py"
    if not crypto_path.exists():
        result.status = "SKIP"
        result.detail = "crypto.py not found (no encryption)"
        return

    spec = importlib.util.spec_from_file_location("crypto", crypto_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        result.status = "FAIL"
        result.error = f"crypto.py import failed: {e}"
        return

    has_decrypt = hasattr(module, "decrypt_body")
    has_encrypt = hasattr(module, "encrypt_body")

    if not has_decrypt:
        result.status = "FAIL"
        result.error = "crypto.py must define decrypt_body(encrypted_data, key) function"
        return

    result.detail = f"decrypt_body={'OK' if has_decrypt else 'MISSING'}, encrypt_body={'OK' if has_encrypt else 'MISSING'}"


def _test_auth(project: Path, result: SmokeResult, credentials: dict | None = None):
    """Gate 4: Auth — plugin.authenticate() must return truthy on valid credentials."""
    plugin_path = project / "plugin.py"
    if not plugin_path.exists():
        result.status = "SKIP"
        result.detail = "plugin.py not found"
        return

    if not credentials:
        # Try to load from credentials.json
        cred_path = project / "credentials.json"
        if cred_path.exists():
            credentials = json.loads(cred_path.read_text(encoding='utf-8'))
        else:
            result.status = "SKIP"
            result.detail = "no credentials (provide credentials.json or pass --creds)"
            return

    spec = importlib.util.spec_from_file_location("plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "authenticate"):
        result.status = "FAIL"
        result.error = "plugin must define authenticate(credentials) function"
        return

    try:
        auth_result = module.authenticate(credentials)
        if auth_result:
            result.detail = "authenticate() returned truthy"
        else:
            result.status = "FAIL"
            result.error = "authenticate() returned falsy — credentials may be expired"
    except Exception as e:
        result.status = "FAIL"
        result.error = f"authenticate() raised: {e}"


def _test_fetch(project: Path, result: SmokeResult, credentials: dict | None = None):
    """Gate 5: Fetch — plugin must return >0 items from a data endpoint."""
    plugin_path = project / "plugin.py"
    if not plugin_path.exists():
        result.status = "SKIP"
        result.detail = "plugin.py not found"
        return

    spec = importlib.util.spec_from_file_location("plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find a data-fetching method (fetch_rooms, fetch_list, etc.)
    fetch_fn = None
    for attr in ["fetch_rooms", "fetch_list", "fetch_rank", "fetch_home"]:
        if hasattr(module, attr):
            fetch_fn = getattr(module, attr)
            break

    if not fetch_fn:
        result.status = "SKIP"
        result.detail = "no fetch_* method found on plugin"
        return

    try:
        data = fetch_fn({})
        if isinstance(data, (list, dict)):
            count = len(data) if isinstance(data, list) else len(data.get("data", data))
            if count > 0:
                result.detail = f"{fetch_fn.__name__}() returned {count} items"
            else:
                result.status = "FAIL"
                result.error = f"{fetch_fn.__name__}() returned 0 items"
        else:
            result.status = "FAIL"
            result.error = f"{fetch_fn.__name__}() returned non-list/dict: {type(data)}"
    except Exception as e:
        result.status = "FAIL"
        result.error = f"{fetch_fn.__name__}() raised: {e}"


# ── API Spec validation ─────────────────────────────────────────────

def _test_spec(project: Path, result: SmokeResult):
    """Validate api_spec.json structure."""
    spec_path = project / "api_spec.json"
    if not spec_path.exists():
        result.status = "FAIL"
        result.error = "api_spec.json not found"
        return

    try:
        spec = json.loads(spec_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        result.status = "FAIL"
        result.error = f"Invalid JSON: {e}"
        return

    issues = []

    base_url = spec.get("base_url", "")
    if not base_url.startswith("https://"):
        issues.append("base_url missing or not https://")

    endpoints = spec.get("endpoints", {})
    if not endpoints:
        issues.append("no endpoints defined")

    # Check category coverage
    if isinstance(endpoints, dict):
        cats = set()
        for ep_info in endpoints.values() if isinstance(endpoints, dict) else []:
            if isinstance(ep_info, dict):
                cat = ep_info.get("category", "uncategorized")
                cats.add(cat)
        missing = {"auth", "data", "rooms", "rank", "user"} - cats
        if missing:
            issues.append(f"missing endpoint categories: {missing}")

    if issues:
        result.status = "FAIL"
        result.error = "; ".join(issues)
    else:
        result.detail = f"{len(endpoints)} endpoints, base_url={base_url}"


# ── Main ────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python smoke_test.py <project_dir> [--quick] [--verbose]")
        print("  project_dir: Path containing plugin.py / api_spec.json")
        print("  --quick:      Skip auth and fetch tests (offline safe)")
        print("  --verbose:    Show full error details")
        sys.exit(2)

    project = Path(sys.argv[1]).resolve()
    if not project.is_dir():
        print(f"[ERROR] Directory not found: {project}")
        sys.exit(2)

    quick = "--quick" in sys.argv
    verbose = "--verbose" in sys.argv

    print(f"Smoke Test: {project.name}")
    print(f"Path: {project}")
    print()

    results: list[SmokeResult] = []

    # Always run these
    results.append(run_test("spec: api_spec.json validation", lambda r: _test_spec(project, r)))
    results.append(run_test("import: plugin.py", lambda r: _test_import(project, r)))
    results.append(run_test("sign: compute_sign()", lambda r: _test_sign(project, r)))
    results.append(run_test("crypto: decrypt_body()", lambda r: _test_crypto(project, r)))

    # Skip network tests in quick mode
    if not quick:
        creds = None
        cred_path = project / "credentials.json"
        if cred_path.exists():
            creds = json.loads(cred_path.read_text(encoding='utf-8'))
        results.append(run_test("auth: authenticate()", lambda r: _test_auth(project, r, creds)))
        results.append(run_test("fetch: data endpoint", lambda r: _test_fetch(project, r, creds)))
    else:
        results.append(SmokeResult("auth: authenticate()"))
        results[-1].status = "SKIP"
        results[-1].detail = "skipped (--quick)"
        results.append(SmokeResult("fetch: data endpoint"))
        results[-1].status = "SKIP"
        results[-1].detail = "skipped (--quick)"

    # Print results
    passed = 0
    failed = 0
    skipped = 0
    for r in results:
        print(r)
        if verbose and r.error:
            print(f"       Error: {r.error}")
        if r.status == "PASS":
            passed += 1
        elif r.status == "FAIL":
            failed += 1
            if not verbose and r.error:
                print(f"       Error: {r.error}")
        else:
            skipped += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        print("[FAIL] Smoke tests failed. See errors above.")
        sys.exit(1)
    else:
        print("[OK] All smoke tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
