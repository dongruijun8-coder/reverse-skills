"""Proxy tools — start/stop mitmproxy, list/get flows."""
import json
import os
import subprocess
import time
from pathlib import Path


def proxy_start(port: int = 8080, filter_domain: str | None = None, output_dir: str = ".") -> dict:
    """Start mitmproxy in recording mode. Returns immediately; proxy runs in background."""
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
    """Kill all mitmdump processes."""
    try:
        subprocess.run(["pkill", "-f", "mitmdump"], capture_output=True)
    except Exception:
        pass
    try:
        subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"], capture_output=True)
    except Exception:
        pass
    return {"status": "OK", "note": "mitmdump processes terminated"}


def proxy_list_flows(filter_host: str | None = None, limit: int = 50) -> dict:
    """List captured flows. Requires the proxy addon JSON log from reverse-toolkit."""
    return {
        "status": "OK",
        "flows": [],
        "note": "Flow listing needs proxy addon JSON log. See reverse-toolkit/proxy/addon.py"
    }


def proxy_get_flow(flow_id: str) -> dict:
    """Get a single flow's full request/response details."""
    return {
        "status": "ERROR",
        "error": "Flow retrieval needs integration with mitmproxy addon. See reverse-toolkit/proxy/addon.py"
    }
