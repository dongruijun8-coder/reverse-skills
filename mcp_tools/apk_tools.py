"""APK analysis tools — unpack, detect packer, decompile, manifest, string search."""
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def apk_unpack(apk_path: str, output_dir: str) -> dict:
    """Unpack an APK (ZIP format) and return file tree summary."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    file_list = []
    with zipfile.ZipFile(apk_path, 'r') as zf:
        for name in zf.namelist():
            zf.extract(name, output)
            file_list.append(name)

    # Summarize by directory
    dirs = {}
    for f in file_list:
        top = f.split('/')[0]
        dirs[top] = dirs.get(top, 0) + 1

    return {
        "status": "OK",
        "output_dir": str(output),
        "total_files": len(file_list),
        "top_level": dirs,
        "has_manifest": "AndroidManifest.xml" in file_list,
        "has_dex": any(f.endswith('.dex') for f in file_list),
        "has_libs": any(f.startswith('lib/') for f in file_list),
        "has_assets": any(f.startswith('assets/') for f in file_list),
    }


def apk_detect_packer(unpacked_dir: str) -> dict:
    """Detect APK packer by checking for known .so files in lib/ directory."""
    lib_dir = Path(unpacked_dir) / "lib"
    if not lib_dir.exists():
        return {"packer": "unknown", "evidence": [], "confidence": 0}

    # Walk all .so files under lib/
    so_files = []
    for root, dirs, files in os.walk(lib_dir):
        for f in files:
            if f.endswith('.so'):
                so_files.append(f)

    evidence = []
    packer = "none"
    extra_flags = []

    # Check in order of specificity (strongest/most specific first)
    if any('libjiagu' in f for f in so_files):
        packer = "360加固"
        evidence = [f for f in so_files if 'libjiagu' in f]
    elif any('libnesec' in f for f in so_files):
        packer = "网易易盾"
        evidence = [f for f in so_files if 'libnesec' in f]
    elif any('libshella' in f for f in so_files):
        packer = "Tencent Legu"
        evidence = [f for f in so_files if 'libshella' in f or 'libtup' in f]
    elif any('libDexHelper' in f for f in so_files):
        packer = "梆梆加固"
        evidence = [f for f in so_files if 'libDexHelper' in f]
    elif any('libexec' in f for f in so_files):
        packer = "爱加密"
        evidence = [f for f in so_files if 'libexec' in f]
    elif any('libijmdata' in f for f in so_files):
        packer = "爱加密(legacy)"
        evidence = [f for f in so_files if 'libijmdata' in f]

    # Check for emulator detector (separate from packer — can coexist)
    emu_detect = [f for f in so_files if 'libemulatordetector' in f]
    if emu_detect:
        extra_flags.append("emulator_detection")

    return {
        "packer": packer,
        "evidence": evidence,
        "confidence": 90 if evidence else 50,
        "total_so_files": len(so_files),
        "flags": extra_flags if extra_flags else None,
    }


def apk_decompile(apk_path: str, output_dir: str, threads: int = 4) -> dict:
    """Decompile APK to Java source using jadx."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["jadx", "-d", str(output), "-j", str(threads), apk_path],
            capture_output=True, text=True, timeout=300
        )
        java_files = list(output.rglob("*.java"))
        return {
            "status": "OK",
            "output_dir": str(output),
            "java_files": len(java_files),
            "stderr": result.stderr[:500] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "output_dir": str(output), "java_files": 0}
    except FileNotFoundError:
        return {"status": "ERROR", "error": "jadx not installed. Download from https://github.com/skylot/jadx/releases"}


def apk_extract_manifest(unpacked_dir: str) -> dict:
    """Parse AndroidManifest.xml (binary XML) using aapt or androguard."""
    manifest_path = Path(unpacked_dir) / "AndroidManifest.xml"
    if not manifest_path.exists():
        return {"status": "ERROR", "error": "AndroidManifest.xml not found"}

    # Try using aapt first (most reliable for binary XML)
    try:
        # Find the original APK path by looking for a .apk file in parent dirs
        result = subprocess.run(
            ["aapt", "dump", "badging", str(unpacked_dir)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise FileNotFoundError("aapt failed")
    except (FileNotFoundError, Exception):
        # Fallback: try to parse as plain XML (works for some APKs)
        try:
            tree = ElementTree.parse(manifest_path)
            root_elem = tree.getroot()
            package = root_elem.attrib.get('package', 'unknown')
            version_name = root_elem.attrib.get('{http://schemas.android.com/apk/res/android}versionName', 'unknown')
            version_code = root_elem.attrib.get('{http://schemas.android.com/apk/res/android}versionCode', '0')
            return {
                "status": "OK",
                "package": package,
                "versionName": version_name,
                "versionCode": version_code,
                "permissions": [],
                "network_pinning": False,
                "method": "xml_parse"
            }
        except Exception:
            return {"status": "ERROR", "error": "Cannot parse manifest. Install aapt or androguard."}

    # Parse aapt output
    info = {"status": "OK", "method": "aapt"}
    for line in result.stdout.split('\n'):
        if line.startswith('package:'):
            for part in line.split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    info[k.strip()] = v.strip("'")
        elif line.startswith('uses-permission:'):
            perm = line.split("'")[1] if "'" in line else line.split(':')[1].strip()
            info.setdefault('permissions', []).append(perm)

    # Check for network security config
    network_config = Path(unpacked_dir) / "res" / "xml" / "network_security_config.xml"
    info['network_pinning'] = False
    if network_config.exists():
        content = network_config.read_text(errors='ignore')
        info['network_pinning'] = '<pin' in content or 'pin-set' in content

    return info


def apk_string_search(unpacked_dir: str, patterns: list[str] | None = None) -> dict:
    """Search all files in unpacked APK for URL/domain/key patterns."""
    if patterns is None:
        patterns = [
            (r'https?://[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+(?::\d+)?(?:/[\w\-./?%&=]*)?', 'domains'),
            (r'[A-Za-z0-9+/=]{32,}', 'keys'),
            (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'ips'),
        ]

    results = {"domains": [], "keys": [], "ips": []}
    search_dir = Path(unpacked_dir)

    text_extensions = {'.xml', '.json', '.txt', '.js', '.html', '.htm', '.css', '.properties',
                       '.smali', '.java', '.kt', '.gradle', '.yml', '.yaml', '.md'}
    skip_dirs = {'lib', 'META-INF'}

    for file_path in search_dir.rglob('*'):
        if file_path.is_dir():
            continue
        if any(skip in str(file_path) for skip in skip_dirs):
            continue

        suffix = file_path.suffix.lower()
        if suffix not in text_extensions and file_path.stat().st_size > 1024 * 1024:
            continue

        try:
            content = file_path.read_text(errors='ignore')
        except Exception:
            continue

        for pattern, key in patterns:
            for m in re.finditer(pattern, content):
                val = m.group(0)
                if val not in results[key]:
                    results[key].append(val)

    results['domains'] = results['domains'][:50]
    results['keys'] = results['keys'][:100]
    results['ips'] = results['ips'][:20]

    return {"status": "OK", **results}
