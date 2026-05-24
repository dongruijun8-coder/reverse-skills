"""MCP Server entry point — registers all tools for the Reverse Engineering Agent.

To use: Add this server to Claude Code's MCP configuration.
The agent's CLAUDE.md and skills will call these tools via MCP.
"""
import json
import sys
from pathlib import Path

# Add parent to path so tools can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_tools.adb_tools import (
    adb_device_info, adb_shell, adb_push_pull, adb_app_mgmt,
    adb_list_apps, adb_install_cert
)
from mcp_tools.apk_tools import (
    apk_unpack, apk_detect_packer, apk_decompile,
    apk_extract_manifest, apk_string_search
)
from mcp_tools.proxy_tools import (
    proxy_start, proxy_stop, proxy_list_flows, proxy_get_flow
)
from mcp_tools.hook_tools import (
    hook_gen_frida, hook_gen_lsposed, hook_run
)
from mcp_tools.crypto_tools import (
    crypto_aes, crypto_hash, crypto_rc4, crypto_rsa, crypto_sign_verify
)
from mcp_tools.data_tools import (
    db_explore, file_parse_java_serial, web_fetch_js
)
from mcp_tools.toolkit_bridge import (
    toolkit_analyze, toolkit_scaffold
)

# Tool registry — maps tool names to functions
TOOLS = {
    # ADB (6)
    "adb_device_info": adb_device_info,
    "adb_shell": adb_shell,
    "adb_push_pull": adb_push_pull,
    "adb_app_mgmt": adb_app_mgmt,
    "adb_list_apps": adb_list_apps,
    "adb_install_cert": adb_install_cert,
    # APK (5)
    "apk_unpack": apk_unpack,
    "apk_detect_packer": apk_detect_packer,
    "apk_decompile": apk_decompile,
    "apk_extract_manifest": apk_extract_manifest,
    "apk_string_search": apk_string_search,
    # Proxy (4)
    "proxy_start": proxy_start,
    "proxy_stop": proxy_stop,
    "proxy_list_flows": proxy_list_flows,
    "proxy_get_flow": proxy_get_flow,
    # Hook (3)
    "hook_gen_frida": hook_gen_frida,
    "hook_gen_lsposed": hook_gen_lsposed,
    "hook_run": hook_run,
    # Crypto (5)
    "crypto_aes": crypto_aes,
    "crypto_hash": crypto_hash,
    "crypto_rc4": crypto_rc4,
    "crypto_rsa": crypto_rsa,
    "crypto_sign_verify": crypto_sign_verify,
    # Data (3)
    "db_explore": db_explore,
    "file_parse_java_serial": file_parse_java_serial,
    "web_fetch_js": web_fetch_js,
    # Toolkit (2)
    "toolkit_analyze": toolkit_analyze,
    "toolkit_scaffold": toolkit_scaffold,
}


def list_tools() -> list[str]:
    """Return list of all registered tool names."""
    return sorted(TOOLS.keys())


def call_tool(name: str, **kwargs) -> dict:
    """Call a registered tool by name with keyword arguments."""
    if name not in TOOLS:
        return {"status": "ERROR", "error": f"Unknown tool: {name}. Available: {list_tools()}"}
    try:
        return TOOLS[name](**kwargs)
    except TypeError as e:
        return {"status": "ERROR", "error": f"Argument error for {name}: {e}"}
    except Exception as e:
        return {"status": "ERROR", "error": f"Tool {name} failed: {e}"}


if __name__ == "__main__":
    # When run directly, print tool list
    tools = list_tools()
    print(f"Reverse Agent MCP Server — {len(tools)} tools registered")
    for t in tools:
        doc = TOOLS[t].__doc__ or "(no docstring)"
        print(f"  {t}: {doc.split(chr(10))[0]}")
