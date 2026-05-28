"""Proxy tools — start/stop mitmproxy, list/get flows with .mitm file parsing."""
import json
import os
import subprocess
import time
from pathlib import Path

# Track the current dump file path for flow listing
_current_dump_file = None


def proxy_start(port: int = 8080, filter_domain: str | None = None, output_dir: str = ".") -> dict:
    """Start mitmproxy in recording mode. Returns immediately; proxy runs in background."""
    global _current_dump_file

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dump_file = output / "flows.mitm"

    cmd = ["mitmdump", "-p", str(port), "-w", str(dump_file), "--set", "flow_detail=0"]
    if filter_domain:
        cmd.extend(["--ignore-hosts", f"^(?!.*{filter_domain}).*$"])

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        if proc.poll() is not None:
            return {"status": "ERROR", "error": "mitmdump failed to start. Is port already in use?"}
        _current_dump_file = str(dump_file)
        return {
            "status": "OK",
            "port": port,
            "pid": proc.pid,
            "dump_file": str(dump_file),
            "note": "Proxy running in background. Use proxy_stop() to stop."
        }
    except FileNotFoundError:
        return {"status": "ERROR", "error": "mitmdump not found. Install: pip install mitmproxy"}


def proxy_stop() -> dict:
    """Kill all mitmdump processes. Cross-platform."""
    results = []

    # Windows
    try:
        r = subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"],
                          capture_output=True, text=True, timeout=10)
        results.append({"platform": "win32", "result": "OK" if r.returncode == 0 else r.stderr.strip()})
    except Exception as e:
        results.append({"platform": "win32", "result": str(e)})

    # Unix
    try:
        r = subprocess.run(["pkill", "-f", "mitmdump"],
                          capture_output=True, text=True, timeout=10)
        results.append({"platform": "unix", "result": "OK" if r.returncode in (0, 1) else r.stderr.strip()})
    except Exception as e:
        results.append({"platform": "unix", "result": str(e)})

    # Verify no mitmdump processes remain
    try:
        check = subprocess.run(["pgrep", "mitmdump"], capture_output=True, text=True, timeout=5)
        if check.returncode == 0 and check.stdout.strip():
            results.append({"verify": "WARNING", "remaining_pids": check.stdout.strip()})
        else:
            results.append({"verify": "OK"})
    except Exception:
        results.append({"verify": "OK (pgrep not available)"})

    return {"status": "OK", "results": results}


def proxy_list_flows(dump_file: str | None = None, filter_host: str | None = None,
                     limit: int = 50) -> dict:
    """List captured flows from a .mitm dump file.

    Uses mitmproxy's FlowReader to parse the dump file.
    Falls back to a basic binary scan if FlowReader fails.

    Args:
        dump_file: Path to .mitm dump file. Uses the last proxy_start dump_file if omitted.
        filter_host: Optional hostname filter (e.g. "api.example.com")
        limit: Max flows to return (default 50)
    """
    global _current_dump_file
    path = dump_file or _current_dump_file

    if not path or not Path(path).exists():
        return {"status": "ERROR", "error": f"Dump file not found: {path or 'unknown'}. "
                                             "Start proxy first with proxy_start().",
                "flows": []}

    flows = []
    try:
        from mitmproxy.io import FlowReader
        from mitmproxy.http import HTTPFlow

        reader = FlowReader(open(path, "rb"))
        for i, flow in enumerate(reader.stream()):
            if not isinstance(flow, HTTPFlow):
                continue

            request = flow.request
            response = flow.response

            host = request.host or ""
            url = request.pretty_url or ""
            method = request.method or ""
            status = response.status_code if response else 0

            if filter_host and filter_host not in host:
                continue

            flows.append({
                "id": i,
                "host": host,
                "method": method,
                "path": request.path or "",
                "url": url,
                "status": status,
                "has_response": response is not None,
                "timestamp": flow.timestamp_start,
            })

            if len(flows) >= limit:
                break

        reader.close()
    except ImportError:
        return {"status": "ERROR",
                "error": "mitmproxy not installed. pip install mitmproxy",
                "flows": []}
    except Exception as e:
        # Fallback: basic file scan for URLs
        try:
            content = Path(path).read_text(errors='ignore')
            import re
            urls = re.findall(rb'https?://[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+(?::\d+)?(?:/[\w\-./?%&=]*)?',
                            Path(path).read_bytes())
            hosts = list(set(re.findall(rb'https?://([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)',
                                       b' '.join(urls))))
            return {
                "status": "PARTIAL",
                "error": f"FlowReader failed: {e}. Basic scan results below.",
                "hosts_found": [h.decode() for h in hosts[:30]],
                "url_count": len(urls),
            }
        except Exception:
            return {"status": "ERROR", "error": f"Flow parsing failed: {e}", "flows": []}

    return {
        "status": "OK",
        "total_flows": len(flows),
        "flows": flows,
        "dump_file": path,
    }


def proxy_get_flow(flow_index: int, dump_file: str | None = None) -> dict:
    """Get full request/response details for a specific flow by index.

    Args:
        flow_index: The flow index (from proxy_list_flows output)
        dump_file: Path to .mitm dump file. Uses the last proxy_start dump_file if omitted.
    """
    global _current_dump_file
    path = dump_file or _current_dump_file

    if not path or not Path(path).exists():
        return {"status": "ERROR", "error": f"Dump file not found: {path or 'unknown'}"}

    try:
        from mitmproxy.io import FlowReader
        from mitmproxy.http import HTTPFlow

        reader = FlowReader(open(path, "rb"))
        target = None
        for i, flow in enumerate(reader.stream()):
            if i == flow_index and isinstance(flow, HTTPFlow):
                target = flow
                break
        reader.close()

        if not target:
            return {"status": "ERROR", "error": f"Flow {flow_index} not found or not an HTTP flow"}

        request = target.request
        response = target.response

        # Parse request body
        req_body = None
        if request.content:
            try:
                req_body = request.content.decode('utf-8', errors='replace')
            except Exception:
                req_body = f"<binary {len(request.content)} bytes>"

        # Parse response body
        resp_body = None
        if response and response.content:
            try:
                resp_body = response.content.decode('utf-8', errors='replace')
            except Exception:
                resp_body = f"<binary {len(response.content)} bytes>"

        return {
            "status": "OK",
            "flow_index": flow_index,
            "request": {
                "method": request.method,
                "url": request.pretty_url,
                "host": request.host,
                "path": request.path,
                "headers": dict(request.headers),
                "body": req_body,
                "timestamp": target.timestamp_start,
            },
            "response": {
                "status": response.status_code if response else 0,
                "headers": dict(response.headers) if response else {},
                "body": resp_body,
                "timestamp": target.timestamp_end if hasattr(target, 'timestamp_end') else None,
            } if response else None,
        }
    except ImportError:
        return {"status": "ERROR", "error": "mitmproxy not installed. pip install mitmproxy"}
    except Exception as e:
        return {"status": "ERROR", "error": f"Flow retrieval failed: {e}"}
