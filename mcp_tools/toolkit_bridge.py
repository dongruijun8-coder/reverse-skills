"""Bridge to existing reverse-toolkit — wrap analyzer and generator pipelines."""
import json
import subprocess
import sys
from pathlib import Path


# Path to the reverse-toolkit src directory
_TOOLKIT_SRC = Path(__file__).resolve().parent.parent.parent / "reverse-toolkit" / "src"


def toolkit_analyze(mitm_file: str, app_name: str, output_dir: str | None = None) -> dict:
    """Run the reverse-toolkit analyzer pipeline on a .mitm flow file.

    Calls: parse_flows → extract_endpoints → classify → build_spec → generate_doc

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

    try:
        sys.path.insert(0, str(_TOOLKIT_SRC))
        from toolkit.analyzer.flow_parser import parse_flows
        from toolkit.analyzer.endpoint_extractor import extract_endpoints
        from toolkit.analyzer.classifier import classify_endpoints
        from toolkit.analyzer.spec_builder import build_spec
    except ImportError as e:
        return {"status": "ERROR", "error": f"Failed to import toolkit: {e}. "
                                              f"Ensure reverse-toolkit is installed."}

    try:
        # Step 1: Parse flows
        flows = parse_flows(str(mitm_path))

        # Step 2: Extract unique endpoints
        endpoints = extract_endpoints(flows)

        # Step 3: Classify
        classified = classify_endpoints(endpoints)

        # Step 4: Build spec
        spec = build_spec(app_name, classified, flows)

        # Step 5: Save
        spec_path = output / "api_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

        return {
            "status": "OK",
            "spec_path": str(spec_path),
            "total_flows": len(flows),
            "unique_endpoints": len(endpoints),
            "categories": {cat: len(eps) for cat, eps in classified.items()},
            "base_url": spec.get("base_url", "unknown"),
            "has_auth": bool(spec.get("auth", {}).get("login_flow"))
        }
    except Exception as e:
        return {"status": "ERROR", "error": f"Analysis failed: {e}"}
    finally:
        sys.path.remove(str(_TOOLKIT_SRC))


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
