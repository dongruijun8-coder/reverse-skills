"""ADB tools — device info, shell, push/pull, app management, cert installation."""
import os
import subprocess
import time
from pathlib import Path


# Detect MSYS2/MINGW environment — paths like /sdcard/ get mangled to E:/Git/sdcard/
_IS_MSYS = "MSYSTEM" in os.environ or "MINGW" in os.environ.get("MSYSTEM", "")


def _adb(cmd: str, timeout: int = 30) -> dict:
    """Run an adb command and return structured result.
    Auto-adds MSYS_NO_PATHCONV=1 on MSYS2/MinGW to prevent path mangling.
    """
    prefix = "MSYS_NO_PATHCONV=1 " if _IS_MSYS else ""
    try:
        result = subprocess.run(
            f"{prefix}adb {cmd}",
            shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "status": "OK" if result.returncode == 0 else "ERROR",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"status": "ERROR", "stdout": "", "stderr": str(e), "returncode": -1}


def adb_device_info() -> dict:
    """Get connected device information."""
    r = _adb("devices")
    devices = [line for line in r['stdout'].split('\n') if '\tdevice' in line]
    if not devices:
        return {"status": "ERROR", "error": "No device connected", "devices": 0}

    info = {"status": "OK", "devices": len(devices), "serial": devices[0].split('\t')[0]}

    props = {
        "model": "ro.product.model",
        "brand": "ro.product.brand",
        "android_version": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "build_type": "ro.build.type",
        "arch": "ro.product.cpu.abi",
    }
    for key, prop in props.items():
        r = _adb(f"shell getprop {prop}")
        info[key] = r['stdout'] if r['status'] == 'OK' else 'unknown'

    r = _adb("shell whoami")
    info['rooted'] = 'root' in r.get('stdout', '')

    r = _adb("shell magisk -c 2>/dev/null")
    info['magisk'] = r['stdout'] if r['status'] == 'OK' and r['stdout'] else None

    return info


def adb_shell(cmd: str, timeout: int = 30) -> dict:
    """Execute a shell command on the device."""
    return _adb(f"shell {cmd}", timeout=timeout)


def adb_push_pull(direction: str, src: str, dst: str) -> dict:
    """Push or pull files to/from device."""
    if direction == "push":
        return _adb(f'push "{src}" "{dst}"')
    elif direction == "pull":
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return _adb(f'pull "{src}" "{dst}"')
    return {"status": "ERROR", "error": f"Unknown direction: {direction}"}


def adb_app_mgmt(action: str, package: str, apk_path: str | None = None) -> dict:
    """Manage app: install, uninstall, start, stop."""
    if action == "install" and apk_path:
        return _adb(f'install -r "{apk_path}"', timeout=120)
    elif action == "uninstall":
        return _adb(f"uninstall {package}")
    elif action == "start":
        r = _adb(f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1")
        if r['returncode'] != 0:
            r = _adb(f"shell am start -n {package}/.MainActivity")
        return r
    elif action == "stop":
        return _adb(f"shell am force-stop {package}")
    return {"status": "ERROR", "error": f"Unknown action: {action}"}


def adb_list_apps(filter_str: str | None = None) -> dict:
    """List installed third-party apps."""
    r = _adb("shell pm list packages -3")
    if r['status'] != 'OK':
        return r
    packages = [line.replace('package:', '').strip() for line in r['stdout'].split('\n') if line]
    if filter_str:
        packages = [p for p in packages if filter_str.lower() in p.lower()]
    return {"status": "OK", "packages": packages, "count": len(packages)}


def adb_install_cert(cert_path: str, cert_name: str = "mitmproxy") -> dict:
    """Install a CA certificate as a system trusted credential.

    SAFETY: Checks ro.build.type before remount. On production/user builds,
    refuses to remount and suggests MoveCertificate (Magisk module) instead.
    """
    cert = Path(cert_path)
    if not cert.exists():
        return {"status": "ERROR", "error": f"Certificate not found: {cert_path}"}

    steps = []

    # Check build type BEFORE doing anything dangerous
    r = _adb("shell getprop ro.build.type")
    build_type = r.get('stdout', 'user').strip()
    if build_type == "user":
        return {
            "status": "BLOCKED",
            "error": "Device is production/user build. Cannot remount /system.",
            "build_type": "user",
            "recommendation": "Use MoveCertificate Magisk module to move user CA to system trust store: "
                              "1. Install MoveCertificate module in Magisk "
                              "2. Install cert as user CA: adb install-mitm-ca-user "
                              "3. Reboot — MoveCertificate auto-copies user CA to system",
            "alternative": "If device is rooted, try: adb shell su -c 'mount -o rw,remount /system' manually",
        }

    r = _adb("shell whoami")
    if 'root' not in r.get('stdout', ''):
        r = _adb("root")
        time.sleep(2)

    r = _adb("remount")
    steps.append({"step": "remount", "result": r['status']})
    if r['status'] != 'OK':
        return {"status": "ERROR", "error": f"Remount failed: {r.get('stderr', '')}",
                "steps": steps, "build_type": build_type}

    dest = f"/system/etc/security/cacerts/{cert_name}"
    r = _adb(f'push "{cert_path}" "{dest}"')
    steps.append({"step": "push", "result": r['status']})

    r = _adb(f"shell chmod 644 {dest}")
    steps.append({"step": "chmod", "result": r['status']})

    r = _adb("reboot")
    steps.append({"step": "reboot", "result": "OK"})

    return {"status": "OK", "steps": steps, "build_type": build_type,
            "note": "Device rebooting. Wait 30s before next adb command."}


# ── Device health & recovery ────────────────────────────────────────

def adb_health_check(package: str | None = None,
                     check_frida: bool = False,
                     check_magisk: bool = False) -> dict:
    """Comprehensive device health check. Call before each phase that needs the device.

    Args:
        package: Target app package name. If provided, checks if app is running.
        check_frida: If True, check if frida/hluda server is running.
        check_magisk: If True, check Magisk status and DenyList.
    """
    checks = {}
    all_ok = True

    # 1. Device connectivity
    r = _adb("devices")
    devices = [l for l in r['stdout'].split('\n') if '\tdevice' in l]
    checks["device_connected"] = len(devices) > 0
    if not checks["device_connected"]:
        all_ok = False
        return {"status": "DEGRADED", "checks": checks,
                "error": "No device connected. Run: adb devices",
                "recovery": "adb_reconnect"}

    # 2. ADB root
    r = _adb("shell whoami")
    checks["adb_root"] = 'root' in r.get('stdout', '')
    if not checks["adb_root"]:
        _adb("root")
        time.sleep(1)
        r2 = _adb("shell whoami")
        checks["adb_root_retry"] = 'root' in r2.get('stdout', '')

    # 3. Build type
    r = _adb("shell getprop ro.build.type")
    checks["build_type"] = r.get('stdout', 'unknown').strip()

    # 4. App process
    if package:
        r = _adb(f"shell ps | grep {package}")
        checks["app_running"] = package in r.get('stdout', '')
        if not checks["app_running"]:
            all_ok = False

    # 5. Frida/hluda server
    if check_frida:
        r = _adb("shell ps | grep -E 'frida|hluda'")
        frida_procs = r.get('stdout', '')
        checks["frida_running"] = bool(frida_procs)
        checks["frida_processes"] = frida_procs if frida_procs else None
        if not checks["frida_running"]:
            all_ok = False

    # 6. Magisk
    if check_magisk:
        r = _adb("shell magisk -c 2>/dev/null")
        checks["magisk_version"] = r.get('stdout', '') if r.get('stdout') else None
        checks["magisk_available"] = r['status'] == 'OK' and bool(r.get('stdout'))
        # Check DenyList
        if package:
            r = _adb("shell magisk --denylist ls 2>/dev/null")
            checks["magisk_denylist"] = package in r.get('stdout', '') if r.get('stdout') else False

    # 7. Disk space
    r = _adb("shell df /data | tail -1")
    try:
        parts = r.get('stdout', '').split()
        checks["disk_free_mb"] = int(parts[3]) // 1024 if len(parts) > 3 else None
    except Exception:
        checks["disk_free_mb"] = None

    # 8. Proxy settings
    r = _adb("shell settings get global http_proxy")
    proxy = r.get('stdout', '').strip()
    checks["http_proxy"] = proxy if proxy and proxy != "null" else None

    return {
        "status": "OK" if all_ok else "DEGRADED",
        "checks": checks,
        "all_ok": all_ok,
    }


def adb_reconnect() -> dict:
    """Try to recover device connection. Restarts adb server and reconnects."""
    steps = []

    # 1. Kill and restart adb server
    r = _adb("kill-server", timeout=5)
    steps.append({"step": "kill-server", "result": "OK"})
    time.sleep(1)

    r = _adb("start-server", timeout=10)
    steps.append({"step": "start-server", "result": r['status']})
    time.sleep(2)

    # 2. Check devices
    r = _adb("devices")
    devices = [l for l in r['stdout'].split('\n') if '\tdevice' in l]
    steps.append({"step": "list-devices", "count": len(devices), "devices": devices})

    if not devices:
        return {"status": "ERROR", "error": "No devices after reconnection. Check USB cable or emulator.",
                "steps": steps}

    # 3. Try root
    r = _adb("root")
    steps.append({"step": "adb-root", "result": r['status']})
    time.sleep(1)

    # 4. Verify root
    r = _adb("shell whoami")
    steps.append({"step": "verify-root", "is_root": 'root' in r.get('stdout', '')})

    return {"status": "OK", "steps": steps, "device": devices[0].split('\t')[0] if devices else None}
