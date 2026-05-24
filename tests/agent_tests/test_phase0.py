"""Phase 0 tests — APK static analysis tools."""
import os
import shutil
import tempfile
import zipfile
from mcp_tools.apk_tools import apk_unpack, apk_detect_packer, apk_string_search


def _make_fake_apk(tmpdir: str, lib_files: list[str] | None = None) -> str:
    """Create a minimal fake APK (ZIP) for testing."""
    apk_path = os.path.join(tmpdir, "test.apk")
    with zipfile.ZipFile(apk_path, 'w') as zf:
        zf.writestr("AndroidManifest.xml",
                     '<manifest package="com.test.app" versionCode="1" versionName="1.0"/>')
        zf.writestr("classes.dex", "fake dex content")
        zf.writestr("res/values/strings.xml", "<resources></resources>")
        if lib_files:
            for lf in lib_files:
                zf.writestr(f"lib/arm64-v8a/{lf}", "fake so content")
    return apk_path


def test_detect_360_packer():
    """apk_detect_packer returns '360加固' when libjiagu.so is present."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libjiagu.so", "libjiagu_x86.so", "libnative.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        apk_unpack(apk_path, unpacked)
        result = apk_detect_packer(unpacked)
        assert result["packer"] == "360加固"
        assert len(result["evidence"]) >= 1
        assert "libjiagu.so" in str(result["evidence"])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_detect_no_packer():
    """apk_detect_packer returns 'none' when no packer .so files."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libnative.so", "libcrypto.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        apk_unpack(apk_path, unpacked)
        result = apk_detect_packer(unpacked)
        assert result["packer"] == "none"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_apk_unpack_returns_file_tree():
    """apk_unpack extracts APK and returns summary."""
    tmpdir = tempfile.mkdtemp()
    try:
        apk_path = _make_fake_apk(tmpdir, ["libnative.so"])
        unpacked = os.path.join(tmpdir, "unpacked")
        result = apk_unpack(apk_path, unpacked)
        assert result["status"] == "OK"
        assert result["has_manifest"] is True
        assert result["has_dex"] is True
        assert result["has_libs"] is True
        assert os.path.exists(os.path.join(unpacked, "AndroidManifest.xml"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_apk_string_search_finds_urls():
    """apk_string_search extracts URLs from APK files."""
    tmpdir = tempfile.mkdtemp()
    try:
        unpacked = os.path.join(tmpdir, "unpacked")
        os.makedirs(unpacked)
        with open(os.path.join(unpacked, "test.js"), 'w') as f:
            f.write('const BASE_URL = "https://api.example.com/web";\n')
            f.write('const CDN = "https://img.example.com";\n')
        result = apk_string_search(unpacked)
        assert result["status"] == "OK"
        assert any("api.example.com" in d for d in result["domains"])
        assert any("img.example.com" in d for d in result["domains"])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
