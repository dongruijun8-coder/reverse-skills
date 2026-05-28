"""Automated analysis pipelines — executable versions of the sub-skills.

These tools automate the manual analysis steps described in /reverse-js-analyzer,
/reverse-crypto-detector, and /reverse-auth-flow-composer skills.
"""
import json
import re
from pathlib import Path


# ── JS Analysis Pipeline ────────────────────────────────────────────

def pipeline_analyze_js(js_file: str, known_endpoints: list[str] | None = None) -> dict:
    """Automated JS analysis — extract sign/crypto candidates from a JavaScript file.

    Replaces manual Steps 1-4 of /reverse-js-analyzer with automated regex scanning.
    Returns candidates sorted by confidence score.

    Args:
        js_file: Path to a .js file (from APK assets or web_fetch_js)
        known_endpoints: Optional list of API paths to search for URL construction
    """
    path = Path(js_file)
    if not path.exists():
        return {"status": "ERROR", "error": f"File not found: {js_file}"}

    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return {"status": "ERROR", "error": f"Read failed: {e}"}

    findings = {
        "sign_candidates": [],
        "crypto_candidates": [],
        "key_candidates": [],
        "endpoint_candidates": [],
        "stats": {"file_size": len(content), "lines": content.count('\n')},
    }

    # ── Sign detection ──────────────────────────────────────────

    # MD5 pattern
    md5_matches = list(re.finditer(r'(?:md5|MD5)\s*\(', content))
    if md5_matches:
        score = 10 * min(len(md5_matches), 5)  # Up to 50 points for frequent MD5 calls
        # Boost if near sort/filter/join
        for m in md5_matches:
            ctx = content[max(0, m.start()-500):m.end()+200]
            if re.search(r'\.sort\s*\(', ctx): score += 25
            if re.search(r'["\']&key=["\']', ctx): score += 40
            if re.search(r'\.toUpperCase\s*\(', ctx): score += 15
            if re.search(r'(?:sign|signature|pub_sign)', ctx, re.I): score += 10
            break  # Score once from context around first match

        findings["sign_candidates"].append({
            "algorithm": "MD5_key_suffix",
            "confidence": min(score, 100),
            "evidence_count": len(md5_matches),
            "needs_sort": "sort" in content[:5000],
            "needs_key": "&key=" in content or "&key=" in content,
        })

    # XOR pattern
    xor_pattern = re.findall(r'(?:p1|p2|param1|param2|enc1|enc2)', content, re.I)
    if len(set(x.lower() for x in xor_pattern)) >= 2:
        findings["sign_candidates"].append({
            "algorithm": "XOR_p1p2",
            "confidence": 40 if len(xor_pattern) > 3 else 20,
            "evidence": list(set(xor_pattern))[:10],
        })

    # HMAC pattern
    hmac_matches = list(re.finditer(r'(?:HmacSHA|hmac|HMAC)', content))
    if hmac_matches:
        findings["sign_candidates"].append({
            "algorithm": "HMAC_SHA256",
            "confidence": min(15 * len(hmac_matches), 60),
            "evidence_count": len(hmac_matches),
        })

    # ── Crypto detection ────────────────────────────────────────

    # AES
    aes_matches = re.findall(r'(?:AES|aes|CryptoJS\.AES)\s*\.\s*(encrypt|decrypt)', content)
    if aes_matches:
        mode = "ECB"
        if "CBC" in content or re.search(r"mode\s*:\s*CryptoJS\.mode\.CBC", content):
            mode = "CBC"
        elif "GCM" in content:
            mode = "GCM"
        findings["crypto_candidates"].append({
            "algorithm": f"AES-{mode}",
            "confidence": 50 + len(aes_matches) * 10,
            "mode": mode,
            "has_iv": "iv" in content.lower() or "CBC" in content,
        })

    # RC4
    if "RC4" in content:
        findings["crypto_candidates"].append({
            "algorithm": "RC4",
            "confidence": 40,
        })

    # ── Key extraction ──────────────────────────────────────────

    key_patterns = [
        (r'(?:encryptKey|encrypt_key|ENCRYPT_KEY)\s*[:=]\s*["\']([^"\']{8,32})["\']', "encrypt_key"),
        (r'(?:signKey|sign_key|SIGN_KEY)\s*[:=]\s*["\']([^"\']{8,32})["\']', "sign_key"),
        (r'["\']([A-Za-z0-9+/=]{16,32})["\']\s*[:=]\s*["\']([^"\']{16})["\']', "key_value_pair"),
    ]
    for pattern, key_type in key_patterns:
        for m in re.finditer(pattern, content):
            findings["key_candidates"].append({
                "type": key_type,
                "value": m.group(1) if key_type != "key_value_pair" else m.group(2),
                "line_sample": content[max(0,m.start()-20):m.end()+20],
            })

    # ── Endpoint extraction ─────────────────────────────────────

    url_patterns = [
        r'["\'](/[a-z][a-z0-9_]*/[a-z][a-z0-9_/]*)["\']',
        r'\.(?:get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']',
    ]
    for pattern in url_patterns:
        for m in re.finditer(pattern, content, re.I):
            endpoint = m.group(1)
            if endpoint.startswith('/') and len(endpoint) < 200:
                findings["endpoint_candidates"].append(endpoint)

    findings["endpoint_candidates"] = list(set(findings["endpoint_candidates"][:50]))

    # Sort by confidence
    findings["sign_candidates"].sort(key=lambda x: x["confidence"], reverse=True)
    findings["crypto_candidates"].sort(key=lambda x: x["confidence"], reverse=True)

    return {"status": "OK", "file": str(path), "findings": findings}


# ── Crypto Detection Pipeline ───────────────────────────────────────

def pipeline_detect_crypto(flow_dump_file: str) -> dict:
    """Scan captured flows for encryption signals.

    Replaces manual Steps 1-2 of /reverse-crypto-detector.
    Automatically checks for Base64 bodies, pub_enc headers, and encryption indicators.

    Args:
        flow_dump_file: Path to .mitm dump file (or .json flow log)
    """
    path = Path(flow_dump_file)
    if not path.exists():
        return {"status": "ERROR", "error": f"File not found: {flow_dump_file}"}

    signals = {
        "encrypted_response": False,
        "encrypted_request": False,
        "pub_enc_header": False,
        "base64_body_not_json": False,
        "suspicious_header_patterns": [],
        "sample_flows": [],
    }

    try:
        from mitmproxy.io import FlowReader
        from mitmproxy.http import HTTPFlow

        reader = FlowReader(open(path, "rb"))
        checked = 0
        for flow in reader.stream():
            if not isinstance(flow, HTTPFlow) or checked >= 100:
                continue
            checked += 1

            req = flow.request
            resp = flow.response
            if not resp:
                continue

            # Check pub_enc header
            for hname in ["pub_enc", "x-encrypted", "encrypted"]:
                if req and req.headers.get(hname, "").lower() in ("true", "1"):
                    signals["pub_enc_header"] = True
                    signals["suspicious_header_patterns"].append(hname)
                if resp.headers.get(hname, "").lower() in ("true", "1"):
                    signals["pub_enc_header"] = True

            # Check if body is Base64 but not JSON
            if resp.content and len(resp.content) > 20:
                try:
                    json.loads(resp.content)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    import base64
                    try:
                        decoded = base64.b64decode(resp.content)
                        try:
                            json.loads(decoded)
                            signals["base64_body_not_json"] = True
                            signals["encrypted_response"] = True
                            signals["sample_flows"].append({
                                "host": req.host if req else "",
                                "path": req.path if req else "",
                                "body_len": len(resp.content),
                                "decoded_len": len(decoded),
                            })
                        except Exception:
                            pass  # Can't decode as JSON, might be binary
                    except Exception:
                        pass  # Not Base64

            if len(signals["sample_flows"]) >= 3:
                break

        reader.close()
    except ImportError:
        pass  # mitmproxy not available, skip
    except Exception:
        pass

    signals["encryption_detected"] = (
        signals["encrypted_response"] or
        signals["pub_enc_header"] or
        signals["base64_body_not_json"]
    )

    return {"status": "OK", "signals": signals, "flows_checked": checked}


# ── Case Matching Pipeline ──────────────────────────────────────────

def pipeline_match_case(packer: str = "",
                        sign_keywords: list[str] | None = None,
                        category: str = "",
                        package: str = "") -> dict:
    """Match current app against the case library and return pre-loaded hypotheses.

    Replaces the manual case_library lookup in Phase 0 step 9.
    Returns actionable hypotheses, not just a case reference.

    Args:
        packer: Detected packer type (e.g. "网易易盾")
        sign_keywords: Keywords found during string search
        category: Inferred app category (e.g. "直播")
        package: App package name (to avoid matching itself)
    """
    case_index_path = Path(__file__).resolve().parent.parent / "kb" / "case_library" / "index.json"
    if not case_index_path.exists():
        return {"status": "OK", "matches": [], "hypotheses": None,
                "note": "Case library not initialized. First run will create baseline."}

    try:
        index = json.loads(case_index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "ERROR", "error": "Failed to read case_library/index.json"}

    matches = []
    for case in index.get("cases", []):
        if package and case.get("package") == package:
            continue  # Skip self

        score = 0
        reasons = []

        tags = case.get("tags", {})
        sim_keys = case.get("similarity_keys", [])

        # Packer match (high weight)
        if packer and tags.get("packer") == packer:
            score += 40
            reasons.append(f"same packer: {packer}")

        # Category match
        if category and category in tags.get("category", ""):
            score += 20
            reasons.append(f"same category: {category}")

        # Keyword overlap
        if sign_keywords:
            overlap = set(sign_keywords) & set(sim_keys)
            keyword_score = min(len(overlap) * 10, 40)
            score += keyword_score
            if overlap:
                reasons.append(f"keyword overlap: {list(overlap)[:5]}")

        if score >= 30:
            reusable = case.get("reusable", {})
            matches.append({
                "case_id": case["id"],
                "app": case["app"],
                "score": score,
                "reasons": reasons,
                "hypotheses": {
                    "sign_algorithm": reusable.get("sign_algorithm"),
                    "sign_initial_key": reusable.get("sign_initial_key"),
                    "sign_key_source": reusable.get("sign_key_source"),
                    "sign_excluded_params": reusable.get("sign_excluded_params"),
                    "crypto_algorithm": reusable.get("crypto_algorithm"),
                    "crypto_key_source": reusable.get("crypto_key_source"),
                    "auth_pattern": reusable.get("auth_pattern"),
                    "auth_chain": reusable.get("auth_chain"),
                    "credential_sources": reusable.get("credential_sources"),
                    "hook_strategy": reusable.get("hook_strategy"),
                    "hook_templates_used": reusable.get("hook_templates_used"),
                    "notes": reusable.get("notes"),
                }
            })

    matches.sort(key=lambda x: x["score"], reverse=True)

    return {
        "status": "OK",
        "matches": matches,
        "best_match": matches[0] if matches else None,
        "hypotheses": matches[0]["hypotheses"] if matches else None,
    }
