"""ADB tools — device info, shell, push/pull, app management, cert installation."""
import subprocess
import time
from pathlib import Path


def _adb(cmd: str, timeout: int = 30) -> dict:
    """Run an adb command and return structured result."""
    try:
        result = subprocess.run(
            f"adb {cmd}",
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
    """Install a CA certificate as a system trusted credential."""
    cert = Path(cert_path)
    if not cert.exists():
        return {"status": "ERROR", "error": f"Certificate not found: {cert_path}"}

    steps = []

    r = _adb("shell whoami")
    if 'root' not in r.get('stdout', ''):
        r = _adb("root")
        time.sleep(2)

    r = _adb("remount")
    steps.append({"step": "remount", "result": r['status']})

    dest = f"/system/etc/security/cacerts/{cert_name}"
    r = _adb(f'push "{cert_path}" "{dest}"')
    steps.append({"step": "push", "result": r['status']})

    r = _adb(f"shell chmod 644 {dest}")
    steps.append({"step": "chmod", "result": r['status']})

    r = _adb("reboot")
    steps.append({"step": "reboot", "result": "OK"})

    return {"status": "OK", "steps": steps, "note": "Device rebooting. Wait 30s before next adb command."}
