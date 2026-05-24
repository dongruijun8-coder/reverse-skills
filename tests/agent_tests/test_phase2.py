"""Phase 2 tests — hook generation."""
from mcp_tools.hook_tools import hook_gen_frida


def test_hook_gen_frida_default_crypto():
    """hook_gen_frida generates valid JavaScript with default crypto hooks."""
    result = hook_gen_frida()
    assert result["status"] == "OK"
    assert "Java.perform" in result["script"]
    assert "javax.crypto.Cipher" in result["script"]
    assert "java.security.MessageDigest" in result["script"]
    assert result["script_length"] > 500


def test_hook_gen_frida_ssl_mode():
    """hook_gen_frida with script_type=ssl generates SSL unpin hooks."""
    result = hook_gen_frida(script_type="ssl")
    assert result["status"] == "OK"
    assert "javax.net.ssl.SSLContext" in result["script"]
    assert "trustManagerFactory" in result["script"]
    assert result["script_length"] > 200


def test_hook_gen_frida_custom_classes():
    """hook_gen_frida accepts custom target classes."""
    result = hook_gen_frida(target_classes=["com.example.CryptoManager.encrypt"])
    assert result["status"] == "OK"
    assert "com.example.CryptoManager" in result["script"]


def test_hook_gen_frida_output_file(tmp_path):
    """hook_gen_frida writes to file when output_path provided."""
    out = tmp_path / "hook.js"
    result = hook_gen_frida(output_path=str(out))
    assert result["status"] == "OK"
    assert out.exists()
    content = out.read_text()
    assert "Java.perform" in content
