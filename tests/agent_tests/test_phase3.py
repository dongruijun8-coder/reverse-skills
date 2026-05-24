"""Phase 3 tests — crypto tools, sign verification, data exploration."""
import json
import tempfile
import os
from mcp_tools.crypto_tools import crypto_aes, crypto_hash, crypto_sign_verify
from mcp_tools.data_tools import db_explore


def test_crypto_aes_ecb_roundtrip():
    """AES-ECB encrypt then decrypt returns original data."""
    key = "vt5i9pn9dwxj8na8"
    plain = '{"status":"OK","data":"test"}'

    enc = crypto_aes("ECB", key, plain, operation="encrypt")
    assert enc["status"] == "OK"

    dec = crypto_aes("ECB", key, enc["result"], operation="decrypt")
    assert dec["status"] == "OK"
    assert dec["is_json"] is True
    assert dec["result"]["status"] == "OK"


def test_crypto_hash_md5_uppercase():
    """MD5 hash with uppercase returns expected format."""
    result = crypto_hash("md5", "test&key=", uppercase=True)
    assert result["status"] == "OK"
    assert len(result["result"]) == 32
    assert result["result"] == result["result"].upper()


def test_crypto_sign_verify_match():
    """crypto_sign_verify returns match=True for correct sign code."""
    sign_code = """
import hashlib
def compute_sign(params, key):
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.md5((q + "&key=" + key).encode()).hexdigest().upper()
"""
    # Pre-compute expected value
    import hashlib
    expected = hashlib.md5("a=1&b=2&key=test".encode()).hexdigest().upper()

    result = crypto_sign_verify(sign_code, {"a": "1", "b": "2"}, expected, "test")
    assert result["status"] == "OK"
    assert result["match"] is True


def test_crypto_sign_verify_mismatch():
    """crypto_sign_verify returns match=False for incorrect sign code."""
    sign_code = """
def compute_sign(params, key):
    return "wrong_signature"
"""
    result = crypto_sign_verify(sign_code, {"a": "1"}, "expected_sign", "")
    assert result["status"] == "OK"
    assert result["match"] is False
    assert result["expected"] == "expected_sign"
    assert result["actual"] == "wrong_signature"


def test_db_explore_finds_urls():
    """db_explore scans SQLite text fields for URLs."""
    import sqlite3
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE messages (id INTEGER, content TEXT)")
        conn.execute("INSERT INTO messages VALUES (1, 'API: https://api.test.com/v1/rooms')")
        conn.execute("INSERT INTO messages VALUES (2, 'CDN: https://img.test.com/avatar.png')")
        conn.commit()
        conn.close()

        result = db_explore(db_path)
        assert result["status"] == "OK"
        assert result["type"] == "sqlite"
        urls = result["findings"]["urls"]
        assert any("api.test.com" in u for u in urls)
        assert any("img.test.com" in u for u in urls)
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
