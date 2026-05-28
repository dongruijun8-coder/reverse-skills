"""MCP Server entry point — registers all tools for the Reverse Engineering Agent.

Two modes:
  1. CLI:  python server.py <tool_name> '<json_args>'   (existing)
  2. MCP:  python server.py --mcp                        (stdio JSON-RPC for Claude Code)

To register in Claude Code, add to ~/.claude/settings.json:
  "mcpServers": {
    "reverse-skills": {
      "command": "python",
      "args": ["<install_dir>/mcp_tools/server.py", "--mcp"]
    }
  }
"""
import json
import sys
import os
from pathlib import Path

# Ensure parent dir is importable
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

# ── Tool registry ──────────────────────────────────────────────────

TOOLS = {
    "adb_device_info": adb_device_info,
    "adb_shell": adb_shell,
    "adb_push_pull": adb_push_pull,
    "adb_app_mgmt": adb_app_mgmt,
    "adb_list_apps": adb_list_apps,
    "adb_install_cert": adb_install_cert,
    "apk_unpack": apk_unpack,
    "apk_detect_packer": apk_detect_packer,
    "apk_decompile": apk_decompile,
    "apk_extract_manifest": apk_extract_manifest,
    "apk_string_search": apk_string_search,
    "proxy_start": proxy_start,
    "proxy_stop": proxy_stop,
    "proxy_list_flows": proxy_list_flows,
    "proxy_get_flow": proxy_get_flow,
    "hook_gen_frida": hook_gen_frida,
    "hook_gen_lsposed": hook_gen_lsposed,
    "hook_run": hook_run,
    "crypto_aes": crypto_aes,
    "crypto_hash": crypto_hash,
    "crypto_rc4": crypto_rc4,
    "crypto_rsa": crypto_rsa,
    "crypto_sign_verify": crypto_sign_verify,
    "db_explore": db_explore,
    "file_parse_java_serial": file_parse_java_serial,
    "web_fetch_js": web_fetch_js,
    "toolkit_analyze": toolkit_analyze,
    "toolkit_scaffold": toolkit_scaffold,
}

# ── MCP Tool Schemas (JSON Schema for each tool's parameters) ───────

TOOL_SCHEMAS = {
    "adb_device_info": {
        "description": "Get connected Android device information (model, OS, root status, Magisk)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "adb_shell": {
        "description": "Execute a shell command on the connected Android device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute on device"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30}
            },
            "required": ["cmd"]
        }
    },
    "adb_push_pull": {
        "description": "Push files to or pull files from the Android device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["push", "pull"], "description": "push to device or pull from device"},
                "src": {"type": "string", "description": "Source path (local for push, device for pull)"},
                "dst": {"type": "string", "description": "Destination path (device for push, local for pull)"}
            },
            "required": ["direction", "src", "dst"]
        }
    },
    "adb_app_mgmt": {
        "description": "Install, uninstall, start, or stop an Android app",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["install", "uninstall", "start", "stop"]},
                "package": {"type": "string", "description": "Package name (e.g. com.example.app)"},
                "apk_path": {"type": "string", "description": "Path to APK file (required for install action)"}
            },
            "required": ["action", "package"]
        }
    },
    "adb_list_apps": {
        "description": "List installed third-party apps on the device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter_str": {"type": "string", "description": "Optional filter string to narrow results"}
            },
            "required": []
        }
    },
    "adb_install_cert": {
        "description": "Install a CA certificate as a system trusted credential (requires root + userdebug/eng build)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cert_path": {"type": "string", "description": "Path to the CA certificate file"},
                "cert_name": {"type": "string", "description": "Name for the certificate (default: mitmproxy)", "default": "mitmproxy"}
            },
            "required": ["cert_path"]
        }
    },
    "apk_unpack": {
        "description": "Unpack an APK (ZIP format) and return a file tree summary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apk_path": {"type": "string", "description": "Path to the APK file"},
                "output_dir": {"type": "string", "description": "Directory to extract APK contents to"}
            },
            "required": ["apk_path", "output_dir"]
        }
    },
    "apk_detect_packer": {
        "description": "Detect APK packer/protector by checking for known .so files in lib/ directory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unpacked_dir": {"type": "string", "description": "Path to the unpacked APK directory"}
            },
            "required": ["unpacked_dir"]
        }
    },
    "apk_decompile": {
        "description": "Decompile APK to Java source using jadx (skip if packer detected)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "apk_path": {"type": "string", "description": "Path to the APK file"},
                "output_dir": {"type": "string", "description": "Directory for decompiled Java output"},
                "threads": {"type": "integer", "description": "Number of threads (default 4)", "default": 4}
            },
            "required": ["apk_path", "output_dir"]
        }
    },
    "apk_extract_manifest": {
        "description": "Parse AndroidManifest.xml — extract package name, version, permissions, network security config",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unpacked_dir": {"type": "string", "description": "Path to the unpacked APK directory"}
            },
            "required": ["unpacked_dir"]
        }
    },
    "apk_string_search": {
        "description": "Scan APK files for URLs, API keys, IP addresses, and other patterns",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unpacked_dir": {"type": "string", "description": "Path to the unpacked APK directory"},
                "patterns": {"type": "array", "items": {"type": "string"}, "description": "Optional custom regex patterns"}
            },
            "required": ["unpacked_dir"]
        }
    },
    "proxy_start": {
        "description": "Start mitmproxy in recording mode. Returns immediately; proxy runs in background.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "Port to listen on (default 8080)", "default": 8080},
                "filter_domain": {"type": "string", "description": "Optional domain filter to record"},
                "output_dir": {"type": "string", "description": "Directory for the .mitm dump file (default: .)", "default": "."}
            },
            "required": []
        }
    },
    "proxy_stop": {
        "description": "Kill all running mitmdump processes (cross-platform)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "proxy_list_flows": {
        "description": "List captured HTTP flows from a .mitm dump file with URL, method, status, host",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dump_file": {"type": "string", "description": "Path to .mitm dump file. Uses last proxy_start dump if omitted."},
                "filter_host": {"type": "string", "description": "Optional hostname filter"},
                "limit": {"type": "integer", "description": "Max flows to return (default 50)", "default": 50}
            },
            "required": []
        }
    },
    "proxy_get_flow": {
        "description": "Get full request/response body and headers for a specific flow by index",
        "inputSchema": {
            "type": "object",
            "properties": {
                "flow_index": {"type": "integer", "description": "The flow index from proxy_list_flows output"},
                "dump_file": {"type": "string", "description": "Path to .mitm dump file. Uses last proxy_start dump if omitted."}
            },
            "required": ["flow_index"]
        }
    },
    "hook_gen_frida": {
        "description": "Generate a Frida JavaScript hook script with version tracking. Presets: crypto, ssl, app_layer, gson, full.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_classes": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Custom target class.method strings. If None, uses preset defaults."
                },
                "script_type": {
                    "type": "string",
                    "enum": ["crypto", "ssl", "app_layer", "gson", "full"],
                    "description": "Hook preset (default: crypto)",
                    "default": "crypto"
                },
                "package": {"type": "string", "description": "Target app package name (for version tracking directory)"},
                "output_dir": {"type": "string", "description": "Directory to save the hook script"}
            },
            "required": []
        }
    },
    "hook_gen_lsposed": {
        "description": "Generate an LSPosed/Xposed module skeleton for persistent hooks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hook_targets": {"type": "object", "description": "Hook target configuration"},
                "output_dir": {"type": "string", "description": "Output directory for the module"}
            },
            "required": []
        }
    },
    "hook_run": {
        "description": "Run a Frida/hluda hook script. hluda mode for NIS apps (attach, not spawn).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["frida", "hluda", "frida-attach", "gadget", "lsposed"],
                    "description": "frida=spawn, hluda/frida-attach=attach, gadget/lsposed=TODO"
                },
                "script_path": {"type": "string", "description": "Path to the hook JavaScript file"},
                "package": {"type": "string", "description": "Target app package name"},
                "server_path": {"type": "string", "description": "Path to hluda-server binary (for hluda method)"},
                "timeout": {"type": "integer", "description": "Max seconds to run (default 60)", "default": 60}
            },
            "required": ["method", "script_path", "package"]
        }
    },
    "crypto_aes": {
        "description": "AES encrypt/decrypt. Supports ECB, CBC, GCM modes. AES-128 and AES-256.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["ECB", "CBC", "GCM"], "description": "AES mode"},
                "key": {"type": "string", "description": "Key string (16 or 32 chars)"},
                "data": {"type": "string", "description": "Base64-encoded input for decrypt, plain text for encrypt"},
                "iv": {"type": "string", "description": "IV/nonce string. 16 bytes for CBC, 12 bytes recommended for GCM."},
                "operation": {"type": "string", "enum": ["encrypt", "decrypt"], "description": "Operation direction", "default": "decrypt"},
                "key_size": {"type": "integer", "description": "Key size in bits: 128 or 256", "default": 128}
            },
            "required": ["mode", "key", "data"]
        }
    },
    "crypto_hash": {
        "description": "Compute MD5/SHA1/SHA256 hash of a string",
        "inputSchema": {
            "type": "object",
            "properties": {
                "algo": {"type": "string", "enum": ["md5", "sha1", "sha256"], "description": "Hash algorithm"},
                "data": {"type": "string", "description": "String to hash"},
                "uppercase": {"type": "boolean", "description": "Return uppercase hex if true", "default": False}
            },
            "required": ["algo", "data"]
        }
    },
    "crypto_rc4": {
        "description": "RC4 encrypt/decrypt",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Hex-encoded key string"},
                "data": {"type": "string", "description": "Data to encrypt/decrypt (hex or base64)"},
                "input_format": {"type": "string", "enum": ["hex", "base64"], "description": "Data input format", "default": "hex"}
            },
            "required": ["key", "data"]
        }
    },
    "crypto_rsa": {
        "description": "RSA encrypt/decrypt with PEM key",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key_pem": {"type": "string", "description": "PEM-format RSA key"},
                "data": {"type": "string", "description": "Base64-encoded data"},
                "direction": {"type": "string", "enum": ["encrypt", "decrypt"], "description": "Operation direction", "default": "encrypt"}
            },
            "required": ["key_pem", "data"]
        }
    },
    "crypto_sign_verify": {
        "description": "Verify a generated sign() function against captured request. The critical feedback loop tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sign_code": {"type": "string", "description": "Python code defining def compute_sign(params, key):"},
                "params": {"type": "object", "description": "The exact parameters from the captured request"},
                "expected_sign": {"type": "string", "description": "The signature value from the captured request"},
                "key": {"type": "string", "description": "The sign key to use (default empty string)", "default": ""}
            },
            "required": ["sign_code", "params", "expected_sign"]
        }
    },
    "db_explore": {
        "description": "Open and scan SQLite/MMKV/text files for URLs, keys, and credentials",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Path to .db, .sqlite, or MMKV file"},
                "scan_patterns": {"type": "array", "items": {"type": "string"}, "description": "Optional custom regex patterns"}
            },
            "required": ["db_path"]
        }
    },
    "file_parse_java_serial": {
        "description": "Parse Java serialized files and XML-wrapped data (share_data.xml) to extract credentials",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the serialized or XML-wrapped file"}
            },
            "required": ["file_path"]
        }
    },
    "web_fetch_js": {
        "description": "Fetch JavaScript/HTML files from a URL, optionally extracting embedded script links",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch (.js or .html)"},
                "output_dir": {"type": "string", "description": "Directory to save downloaded files"},
                "extract_links": {"type": "boolean", "description": "If true, find and return embedded script URLs", "default": False}
            },
            "required": ["url", "output_dir"]
        }
    },
    "toolkit_analyze": {
        "description": "Analyze a .mitm flow dump to extract API spec. Falls back to FlowReader when reverse-toolkit unavailable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mitm_file": {"type": "string", "description": "Path to the .mitm flow dump file"},
                "app_name": {"type": "string", "description": "App name for the output spec"},
                "output_dir": {"type": "string", "description": "Directory to write api_spec.json (default: projects/{app_name}/)"}
            },
            "required": ["mitm_file", "app_name"]
        }
    },
    "toolkit_scaffold": {
        "description": "Generate plugin.py and models.py from an api_spec.json file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_path": {"type": "string", "description": "Path to api_spec.json"},
                "output_dir": {"type": "string", "description": "Directory to write plugin.py and models.py"}
            },
            "required": ["spec_path", "output_dir"]
        }
    },
}


# ── Tool call dispatch ─────────────────────────────────────────────

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


# ── MCP stdio JSON-RPC handler ──────────────────────────────────────

def _mcp_send(response: dict) -> None:
    """Send a JSON-RPC response to stdout."""
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _mcp_handle_request(req: dict) -> dict | None:
    """Handle a single JSON-RPC request. Returns response or None for notifications."""
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "reverse-skills",
                    "version": "1.2.0"
                }
            }
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    elif method == "tools/list":
        tools = []
        for name in sorted(TOOLS.keys()):
            schema = TOOL_SCHEMAS.get(name, {
                "description": TOOLS[name].__doc__ or f"Call {name}",
                "inputSchema": {"type": "object", "properties": {}}
            })
            tools.append({
                "name": name,
                "description": schema.get("description", ""),
                "inputSchema": schema.get("inputSchema", {"type": "object", "properties": {}})
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        }

    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        result = call_tool(tool_name, **arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                ]
            }
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


def mcp_serve() -> None:
    """Run the MCP stdio JSON-RPC server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _mcp_handle_request(req)
        if resp is not None:
            _mcp_send(resp)


# ── CLI entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--mcp":
        mcp_serve()
    elif len(sys.argv) < 2:
        tools = list_tools()
        print(f"Reverse Skills — {len(tools)} tools registered")
        for t in tools:
            doc = TOOLS[t].__doc__ or "(no docstring)"
            print(f"  {t}: {doc.split(chr(10))[0]}")
    else:
        tool_name = sys.argv[1]
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        result = call_tool(tool_name, **args)
        print(json.dumps(result, ensure_ascii=False))
