"""Bridge to existing reverse-toolkit — wrap analyzer and generator pipelines."""
import json
import subprocess
import sys
from pathlib import Path


# Path to the reverse-toolkit src directory
_TOOLKIT_SRC = Path(__file__).resolve().parent.parent.parent / "reverse-toolkit" / "src"


def toolkit_analyze(mitm_file: str, app_name: str, output_dir: str | None = None) -> dict:
    """Run the reverse-toolkit analyzer pipeline on a .mitm flow file.

    Primary: Uses reverse-toolkit (parse_flows → extract_endpoints → classify → build_spec).
    Fallback: Parses .mitm file directly with mitmproxy FlowReader when toolkit unavailable.

    Args:
        mitm_file: Path to the .mitm flow dump file
        app_name: App name for the output spec
        output_dir: Directory to write api_spec.json (default: projects/{app_name}/)
    """
    mitm_path = Path(mitm_file)
    if not mitm_path.exists():
        return {"status": "ERROR", "error": f"Flow file not found: {mitm_file}"}

    output = Path(output_dir) if output_dir else Path(f"projects/{app_name}")
    output.mkdir(parents=True, exist_ok=True)

    # Try primary: reverse-toolkit
    try:
        sys.path.insert(0, str(_TOOLKIT_SRC))
        from toolkit.analyzer.flow_parser import parse_flows
        from toolkit.analyzer.endpoint_extractor import extract_endpoints
        from toolkit.analyzer.classifier import classify_endpoints
        from toolkit.analyzer.spec_builder import build_spec

        flows = parse_flows(str(mitm_path))
        endpoints = extract_endpoints(flows)
        classified = classify_endpoints(endpoints)
        spec = build_spec(app_name, classified, flows)

        spec_path = output / "api_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

        return {
            "status": "OK",
            "method": "reverse-toolkit",
            "spec_path": str(spec_path),
            "total_flows": len(flows),
            "unique_endpoints": len(endpoints),
            "categories": {cat: len(eps) for cat, eps in classified.items()},
            "base_url": spec.get("base_url", "unknown"),
            "has_auth": bool(spec.get("auth", {}).get("login_flow"))
        }
    except ImportError:
        pass  # Fall through to fallback
    except Exception as e:
        pass  # Fall through to fallback
    finally:
        try:
            sys.path.remove(str(_TOOLKIT_SRC))
        except (ValueError, Exception):
            pass

    # Fallback: parse .mitm with mitmproxy FlowReader
    try:
        from mitmproxy.io import FlowReader
        from mitmproxy.http import HTTPFlow

        endpoints = {}
        hosts = set()
        base_urls = set()

        reader = FlowReader(open(mitm_path, "rb"))
        for flow in reader.stream():
            if not isinstance(flow, HTTPFlow):
                continue
            req = flow.request
            resp = flow.response
            if not req or not req.host:
                continue

            hosts.add(req.host)
            key = f"{req.method} {req.path.split('?')[0]}"
            if key not in endpoints:
                endpoints[key] = {
                    "method": req.method,
                    "path": req.path.split('?')[0],
                    "full_path": req.path,
                    "host": req.host,
                    "count": 0,
                    "has_response": resp is not None,
                    "status_codes": [],
                    "example_params": list(req.query.keys()) if req.query else [],
                    "response_is_json": False,
                    "response_is_encrypted": False,
                }
            ep = endpoints[key]
            ep["count"] += 1
            if resp:
                ep["status_codes"].append(resp.status_code)
                if resp.content and len(resp.content) < 100 * 1024:
                    try:
                        json.loads(resp.content)
                        ep["response_is_json"] = True
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        if resp.content and len(resp.content) > 20:
                            ep["response_is_encrypted"] = True

            if req.scheme and req.host:
                base_urls.add(f"{req.scheme}://{req.host}")

        reader.close()

        # Classify endpoints
        classified = {"auth": [], "rooms": [], "rank": [], "user": [], "other": []}
        auth_keywords = ["login", "sms", "sign", "token", "key", "auth", "verify", "register"]
        room_keywords = ["room", "live", "stream", "chat", "broadcast"]
        rank_keywords = ["rank", "list", "top", "hot", "recommend", "home"]
        user_keywords = ["user", "profile", "info", "avatar", "follow", "fan", "setting"]

        for key, ep in endpoints.items():
            path_lower = key.lower()
            if any(kw in path_lower for kw in auth_keywords):
                classified["auth"].append(key)
            elif any(kw in path_lower for kw in room_keywords):
                classified["rooms"].append(key)
            elif any(kw in path_lower for kw in rank_keywords):
                classified["rank"].append(key)
            elif any(kw in path_lower for kw in user_keywords):
                classified["user"].append(key)
            else:
                classified["other"].append(key)

        # Build basic spec
        best_base = sorted(base_urls, key=lambda u: 0 if "api" in u else 1)[0] if base_urls else "unknown"
        spec = {
            "app": app_name,
            "base_url": best_base,
            "endpoints": {k: {kk: vv for kk, vv in v.items() if kk != "host"}
                         for k, v in endpoints.items()},
            "common_params": {
                "headers": {},
                "query_params": ["pub_timestamp", "pub_sid"],
            },
            "auth": {"type": "unknown"},
            "encryption": {"detected": any(ep["response_is_encrypted"] for ep in endpoints.values())},
            "generated_by": "toolkit_analyze (fallback — mitmproxy FlowReader)",
        }

        spec_path = output / "api_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

        return {
            "status": "OK",
            "method": "fallback",
            "spec_path": str(spec_path),
            "total_hosts": len(hosts),
            "unique_endpoints": len(endpoints),
            "categories": {cat: len(eps) for cat, eps in classified.items()},
            "base_url": best_base,
            "encryption_detected": spec["encryption"]["detected"],
            "has_auth": len(classified["auth"]) > 0,
        }
    except ImportError:
        return {"status": "ERROR",
                "error": "Neither reverse-toolkit nor mitmproxy available. Install: pip install mitmproxy"}
    except Exception as e:
        return {"status": "ERROR", "error": f"Flow analysis failed: {e}"}


def toolkit_scaffold(spec_path: str, output_dir: str) -> dict:
    """Run the reverse-toolkit generator on an api_spec.json file.

    Args:
        spec_path: Path to api_spec.json
        output_dir: Directory to write plugin.py and models.py
    """
    spec_file = Path(spec_path)
    if not spec_file.exists():
        return {"status": "ERROR", "error": f"Spec file not found: {spec_path}"}

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    try:
        spec = json.loads(spec_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        return {"status": "ERROR", "error": f"Invalid JSON in spec: {e}"}

    try:
        sys.path.insert(0, str(_TOOLKIT_SRC))
        from toolkit.generator.scaffold import generate
    except ImportError as e:
        return {"status": "ERROR", "error": f"Failed to import toolkit: {e}"}

    try:
        plugin_code, models_code = generate(spec)

        plugin_path = output / "plugin.py"
        models_path = output / "models.py"
        plugin_path.write_text(plugin_code, encoding='utf-8')
        models_path.write_text(models_code, encoding='utf-8')

        return {
            "status": "OK",
            "plugin_path": str(plugin_path),
            "models_path": str(models_path),
            "plugin_lines": len(plugin_code.split('\n')),
            "models_lines": len(models_code.split('\n'))
        }
    except Exception as e:
        return {"status": "ERROR", "error": f"Scaffold failed: {e}"}
    finally:
        sys.path.remove(str(_TOOLKIT_SRC))
