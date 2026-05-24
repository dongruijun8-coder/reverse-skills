#!/usr/bin/env python3
"""Pre-flight dependency checker for Reverse Engineering Agent.
Run: python preflight.py
"""
import os
import shutil
import subprocess
import sys


def check(name, cmd, required=True, fix="") -> bool:
    """Run a check and report status. Returns True if pass (or optional fail)."""
    try:
        subprocess.run(cmd, shell=True, capture_output=True, timeout=10, check=True)
        print(f"  [OK] {name}")
        return True
    except Exception:
        tag = "[REQUIRED]" if required else "[OPTIONAL]"
        print(f"  [MISSING] {name} {tag}")
        if fix:
            print(f"         Fix: {fix}")
        return not required  # True for optional fails, False for required fails


def main():
    print("=" * 48)
    print("  Reverse Agent - Environment Check")
    print("=" * 48)
    print()

    failed = 0

    # Python version (check directly, not via subprocess)
    print("Python packages:")
    if sys.version_info >= (3, 12):
        print(f"  [OK] Python {sys.version}")
    else:
        print(f"  [MISSING] Python 3.12+ (current: {sys.version}) [REQUIRED]")
        failed += 1

    if not check("mitmproxy", f'"{sys.executable}" -c "import mitmproxy"'):
        failed += 1
    if not check("click", f'"{sys.executable}" -c "import click"'):
        failed += 1
    if not check("Jinja2", f'"{sys.executable}" -c "import jinja2"'):
        failed += 1
    if not check("pycryptodome", f'"{sys.executable}" -c "from Crypto.Cipher import AES"',
                 fix="pip install pycryptodome"):
        failed += 1

    print()
    print("External tools:")
    if not check("adb", "adb version", fix="Download Android SDK Platform Tools"):
        failed += 1
    check("jadx", "jadx --version", required=False,
          fix="winget install jadx or https://github.com/skylot/jadx/releases")
    check("frida", "frida --version", required=False,
          fix="pip install frida-tools")

    print()
    free_gb = shutil.disk_usage(".").free / (1024 ** 3)
    if free_gb < 2:
        print(f"  [MISSING] Disk space: {free_gb:.1f} GB (need >= 2 GB) [REQUIRED]")
        failed += 1
    else:
        print(f"  [OK] Disk space: {free_gb:.1f} GB")

    print()
    if failed > 0:
        print(f"[FAIL] {failed} required dependencies missing. Fix and re-run.")
        sys.exit(1)
    else:
        print("[OK] All required dependencies satisfied!")
        print()
        print("To start:")
        print("  cd reverse-skills")
        print("  claude")
        print('  Then type: "Reverse engineer this APK: /path/to/app.apk"')


if __name__ == "__main__":
    main()
