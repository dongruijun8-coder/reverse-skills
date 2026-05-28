"""State management tools — checkpoint, resume, and session tracking.

Auto-saves .agent_state.json at every phase boundary so interrupted sessions
can resume from the last completed phase instead of restarting from scratch.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


# Default project root — configurable via environment
DEFAULT_PROJECTS_DIR = Path(os.environ.get("REVERSE_PROJECTS_DIR",
                           Path.home() / ".claude" / "reverse-skills" / "projects"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / ".agent_state.json"


# ── Core state operations ───────────────────────────────────────────

def state_init(project_dir: str, app_name: str, package: str = "",
               apk_path: str = "") -> dict:
    """Initialize a new agent state file for an app.

    Args:
        project_dir: Project directory (e.g. projects/shuangyu)
        app_name: App display name
        package: Android package name
        apk_path: Original APK file path
    """
    proj = Path(project_dir)
    proj.mkdir(parents=True, exist_ok=True)

    state = {
        "app_name": app_name,
        "package": package,
        "apk_path": apk_path,
        "current_phase": "0",
        "phase_status": "STARTING",
        "phases": {},
        "scratch": {},
        "strategy_stack": {},
        "artifacts": {},
        "resume_point": {"phase": "0", "description": "Phase 0: APK static analysis"},
        "created_at": _now(),
        "updated_at": _now(),
        "total_rounds": 0,
    }

    _state_path(project_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "OK", "project_dir": str(proj), "app_name": app_name, "state": state}


def state_load(project_dir: str) -> dict:
    """Load existing agent state. Returns error if no state file exists."""
    sp = _state_path(project_dir)
    if not sp.exists():
        return {"status": "ERROR", "error": f"No state file at {sp}. Use state_init() first."}
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
        return {"status": "OK", "state": state, "project_dir": project_dir}
    except json.JSONDecodeError as e:
        return {"status": "ERROR", "error": f"Corrupted state file: {e}"}


def state_save(project_dir: str, **kwargs) -> dict:
    """Update and save agent state. Merges kwargs into existing state.

    Example:
        state_save("projects/shuangyu", current_phase="1", phase_status="DONE")
        state_save("projects/shuangyu", scratch={"packer": "NIS"})
    """
    sp = _state_path(project_dir)
    if sp.exists():
        state = json.loads(sp.read_text(encoding="utf-8"))
    else:
        return {"status": "ERROR", "error": f"No state file at {sp}. Use state_init() first."}

    # Deep merge scratch dict
    if "scratch" in kwargs and isinstance(kwargs["scratch"], dict):
        state.setdefault("scratch", {})
        state["scratch"].update(kwargs["scratch"])
        del kwargs["scratch"]

    # Update top-level fields
    for k, v in kwargs.items():
        if k == "scratch":
            continue
        state[k] = v

    state["updated_at"] = _now()
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "OK", "state": state, "project_dir": project_dir}


def state_phase_start(project_dir: str, phase: str, description: str = "") -> dict:
    """Mark a phase as IN_PROGRESS. Call BEFORE starting phase execution."""
    sp = _state_path(project_dir)
    if not sp.exists():
        return {"status": "ERROR", "error": f"No state file at {sp}"}

    state = json.loads(sp.read_text(encoding="utf-8"))
    state["current_phase"] = phase
    state["phase_status"] = "IN_PROGRESS"
    state.setdefault("phases", {})
    state["phases"][str(phase)] = {
        "status": "IN_PROGRESS",
        "started_at": _now(),
        "description": description,
        "attempts": state["phases"].get(str(phase), {}).get("attempts", 0) + 1,
    }
    state["resume_point"] = {"phase": phase, "description": description or f"Phase {phase}"}
    state["updated_at"] = _now()
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "OK", "phase": phase, "resume_point": state["resume_point"]}


def state_phase_done(project_dir: str, phase: str, summary: str = "",
                     artifacts: dict | None = None) -> dict:
    """Mark a phase as DONE. Call AFTER phase completes successfully."""
    sp = _state_path(project_dir)
    if not sp.exists():
        return {"status": "ERROR", "error": f"No state file at {sp}"}

    state = json.loads(sp.read_text(encoding="utf-8"))
    state["phases"][str(phase)] = {
        "status": "DONE",
        "completed_at": _now(),
        "summary": summary,
        "attempts": state["phases"].get(str(phase), {}).get("attempts", 0),
    }

    if artifacts:
        state.setdefault("artifacts", {})
        state["artifacts"].update(artifacts)

    # Compute next phase
    phase_order = ["0", "0.5", "1", "2", "3", "4", "5"]
    try:
        idx = phase_order.index(str(phase))
        next_phase = phase_order[idx + 1] if idx + 1 < len(phase_order) else "done"
    except ValueError:
        next_phase = "unknown"

    state["current_phase"] = next_phase
    state["phase_status"] = "DONE" if next_phase == "done" else "AWAITING_NEXT"
    state["resume_point"] = {"phase": next_phase, "description": f"Next: Phase {next_phase}"}
    state["updated_at"] = _now()
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "OK", "phase": phase, "next_phase": next_phase, "summary": summary}


def state_phase_fail(project_dir: str, phase: str, error: str, retry: bool = True) -> dict:
    """Record a phase failure. Tracks retry count for exit condition decisions."""
    sp = _state_path(project_dir)
    if not sp.exists():
        return {"status": "ERROR", "error": f"No state file at {sp}"}

    state = json.loads(sp.read_text(encoding="utf-8"))
    phase_key = str(phase)
    state.setdefault("phases", {})
    ph = state["phases"].setdefault(phase_key, {"attempts": 0, "errors": []})
    ph.setdefault("errors", [])
    ph["errors"].append({"time": _now(), "error": error})
    ph["attempts"] = ph.get("attempts", 0)
    ph.setdefault("status", "FAILED")
    state["updated_at"] = _now()
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    attempts = ph["attempts"]
    if attempts >= 3 and retry:
        return {
            "status": "EXIT",
            "phase": phase,
            "attempts": attempts,
            "action": "DEGRADE — max retries reached. Degrade strategy per exit_conditions.md.",
            "recent_errors": ph["errors"][-3:],
        }
    return {
        "status": "RETRY",
        "phase": phase,
        "attempts": attempts,
        "action": f"Retry {attempts}/3",
        "error": error,
    }


def state_list_sessions(projects_dir: str | None = None) -> dict:
    """List all saved agent sessions with their current status."""
    base = Path(projects_dir) if projects_dir else DEFAULT_PROJECTS_DIR
    if not base.exists():
        return {"status": "OK", "sessions": [], "count": 0}

    sessions = []
    for sf in sorted(base.rglob(".agent_state.json")):
        try:
            state = json.loads(sf.read_text(encoding="utf-8"))
            sessions.append({
                "app": state.get("app_name", sf.parent.name),
                "package": state.get("package", ""),
                "phase": state.get("current_phase", "?"),
                "status": state.get("phase_status", "?"),
                "updated": state.get("updated_at", ""),
                "project_dir": str(sf.parent),
            })
        except Exception:
            pass

    return {"status": "OK", "sessions": sessions, "count": len(sessions)}


def state_get_resume_plan(project_dir: str) -> dict:
    """Get a human-readable resume plan for the user."""
    sp = _state_path(project_dir)
    if not sp.exists():
        return {"status": "ERROR", "error": f"No session found at {project_dir}"}

    state = json.loads(sp.read_text(encoding="utf-8"))
    resume = state.get("resume_point", {})
    phases = state.get("phases", {})

    completed = [p for p, v in phases.items() if v.get("status") == "DONE"]
    in_progress = [p for p, v in phases.items() if v.get("status") == "IN_PROGRESS"]
    failed = [p for p, v in phases.items() if v.get("status") == "FAILED"]

    return {
        "status": "OK",
        "app": state.get("app_name", "unknown"),
        "current_phase": state.get("current_phase", "?"),
        "phase_status": state.get("phase_status", "?"),
        "phases_done": completed,
        "phases_in_progress": in_progress,
        "phases_failed": failed,
        "resume_phase": resume.get("phase", "?"),
        "resume_description": resume.get("description", ""),
        "scratch_keys": list(state.get("scratch", {}).keys()),
        "artifacts": state.get("artifacts", {}),
        "last_updated": state.get("updated_at", ""),
    }
