"""Data tools — SQLite/MMKV explorer, Java serial parser, JS file fetcher."""
import json
import os
import re
import sqlite3
import struct
from pathlib import Path


def db_explore(db_path: str, scan_patterns: list[str] | None = None) -> dict:
    """Open SQLite/MMKV file, list tables, scan text fields for URL/keys.

    Args:
        db_path: Path to .db, .sqlite, or MMKV file
        scan_patterns: Optional list of regex patterns to scan for
    """
    if scan_patterns is None:
        scan_patterns = [
            r'https?://[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+',
            r'[A-Za-z0-9]{16,}',
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        ]

    path = Path(db_path)
    if not path.exists():
        return {"status": "ERROR", "error": f"File not found: {db_path}"}

    # Try as SQLite first
    tables = []
    findings = {"urls": [], "keys": [], "ips": []}

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in cursor.fetchall()]

        for table in table_names:
            try:
                cursor.execute(f"SELECT * FROM [{table}] LIMIT 1")
                cols = [desc[0] for desc in cursor.description]
                tables.append({"name": table, "columns": cols})

                # Scan text columns
                cursor.execute(f"SELECT * FROM [{table}] LIMIT 200")
                for row in cursor.fetchall():
                    for i, val in enumerate(row):
                        if isinstance(val, str) and len(val) > 3:
                            for pattern in scan_patterns:
                                for m in re.finditer(pattern, val):
                                    v = m.group(0)
                                    if 'https?://' in pattern and v not in findings['urls']:
                                        findings['urls'].append(v)
                                    elif len(v) >= 16 and v not in findings['keys']:
                                        findings['keys'].append(v)
            except sqlite3.OperationalError:
                continue

        conn.close()
        return {"status": "OK", "type": "sqlite", "tables": tables, "findings": findings}

    except sqlite3.DatabaseError:
        # Not SQLite, try as MMKV or raw text
        try:
            content = path.read_text(errors='ignore')
            for pattern in scan_patterns:
                for m in re.finditer(pattern, content):
                    v = m.group(0)
                    if 'https?://' in pattern and v not in findings['urls']:
                        findings['urls'].append(v)
                    elif len(v) >= 16 and v not in findings['keys']:
                        findings['keys'].append(v)
            return {"status": "OK", "type": "text", "size": len(content), "findings": findings}
        except Exception as e:
            return {"status": "OK", "type": "unknown", "findings": findings, "note": str(e)}


def file_parse_java_serial(file_path: str) -> dict:
    """Parse a Java serialized file to extract string fields.

    This handles the common case of share_data.xml containing Java serialized
    TicketInfo objects (like in 梦音).
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "ERROR", "error": f"File not found: {file_path}"}

    try:
        raw = path.read_bytes()
    except Exception as e:
        return {"status": "ERROR", "error": f"Read failed: {e}"}

    # Java serialization magic: 0xAC 0xED 0x00 0x05
    if raw[:4] != b'\xac\xed\x00\x05':
        # Maybe it's XML-wrapped (share_data.xml pattern)
        content = raw.decode('utf-8', errors='ignore')
        # Try to extract base64/binary blob between XML tags
        strings = re.findall(r'<string[^>]*>([^<]+)</string>', content)
        if strings:
            parsed = {}
            for s in strings:
                if '=' in s:
                    k, v = s.split('=', 1)
                    parsed[k.strip()] = v.strip()
                elif len(s) > 20:
                    parsed[f"field_{len(parsed)}"] = s
            return {"status": "OK", "format": "xml_wrapped", "fields": parsed, "field_count": len(parsed)}
        # Try extracting any long alphanumeric strings
        candidates = re.findall(r'[A-Za-z0-9+/=._\-]{40,}', content)
        return {"status": "OK", "format": "xml_text", "candidates": candidates[:20], "candidate_count": len(candidates)}

    # Binary Java serialization — extract string constants
    strings = []
    pos = 4  # skip magic
    try:
        while pos < len(raw):
            # TC_STRING = 0x74, TC_LONGSTRING = 0x7C
            if raw[pos] in (0x74, 0x7C):
                pos += 1
                if pos + 2 > len(raw):
                    break
                length = struct.unpack('>H', raw[pos:pos+2])[0]
                pos += 2
                if pos + length > len(raw):
                    break
                s = raw[pos:pos+length].decode('utf-8', errors='ignore')
                if len(s) > 3:
                    strings.append(s)
                pos += length
            else:
                pos += 1
    except Exception:
        pass

    # Extract likely credential fields
    fields = {}
    for s in strings:
        if len(s) > 20 and not s.startswith('[') and not s.startswith('<'):
            if '=' in s:
                k, v = s.split('=', 1)
                fields[k.strip()] = v.strip()
            elif re.match(r'^[A-Za-z0-9+/=._\-]{32,}$', s):
                fields[f"token_{len(fields)}"] = s

    return {
        "status": "OK",
        "format": "java_serial",
        "strings_found": len(strings),
        "fields": fields,
        "field_count": len(fields)
    }


def web_fetch_js(url: str, output_dir: str, extract_links: bool = False) -> dict:
    """Fetch JavaScript files from a URL, optionally extracting embedded links.

    Args:
        url: URL to fetch (can be a .js file or an HTML page)
        output_dir: Directory to save downloaded files
        extract_links: If True, find <script src="..."> or import(...) links and download those too
    """
    import urllib.request
    import urllib.error

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            content_type = resp.headers.get('Content-Type', '')
    except urllib.error.URLError as e:
        return {"status": "ERROR", "error": f"Fetch failed: {e}"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

    # Save the main file
    filename = url.split('/')[-1].split('?')[0] or "index.html"
    filepath = out / filename
    filepath.write_bytes(content)

    downloaded = [str(filepath)]
    links = []

    if extract_links:
        text = content.decode('utf-8', errors='ignore')
        # Extract <script src="...">
        script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text)
        # Extract import(...) or require(...)
        imports = re.findall(r'(?:import|require)\s*\(\s*["\']([^"\']+)["\']', text)
        links = script_srcs + imports

    return {
        "status": "OK",
        "url": url,
        "downloaded": downloaded,
        "size": len(content),
        "content_type": content_type,
        "links_found": links if extract_links else None
    }
