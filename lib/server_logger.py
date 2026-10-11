import os
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = Path(os.environ.get("AGENTREFLEX_LOGS_DIR", ROOT_DIR / "logs"))
SERVER_LOG_FILE = LOGS_DIR / "server.log"
SERVER_JSONL_FILE = LOGS_DIR / "server.jsonl"


def _ensure_log_dir():
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def resolve_project_dir(
    workspace_paths: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    transcript_path: Optional[str] = None,
) -> Optional[Path]:
    """Find the root directory path of the project being worked on."""
    if workspace_paths and len(workspace_paths) > 0 and workspace_paths[0]:
        p = Path(workspace_paths[0])
        if p.exists():
            return p

    if transcript_path:
        tpath = Path(transcript_path)
        parts = tpath.parts
        for i, part in enumerate(parts):
            if part in (".gemini", ".agents") and i > 0:
                p = Path(*parts[:i])
                if p.exists():
                    return p

    if cwd:
        p = Path(cwd)
        if p.exists():
            return p

    return Path.cwd()


def resolve_project_name(
    workspace_paths: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    transcript_path: Optional[str] = None,
) -> str:
    """Extract a clean human-readable project name from available metadata."""
    if workspace_paths and len(workspace_paths) > 0 and workspace_paths[0]:
        return Path(workspace_paths[0]).name or str(workspace_paths[0])

    if transcript_path:
        tpath = Path(transcript_path)
        parts = tpath.parts
        for i, part in enumerate(parts):
            if part in (".gemini", ".agents") and i > 0:
                return parts[i - 1]

    if cwd:
        return Path(cwd).name or str(cwd)

    return Path.cwd().name or "default"


def is_logging_enabled(project_path: Optional[Any] = None) -> bool:
    """Check if logging is enabled for the target project.

    Logging is OFF by default.
    Enable via any of:
    1. Environment variable: AGENTREFLEX_LOGGING=1 / true / on
    2. Project flag file: .reflex-log
    3. Project config file: .agentreflex.json or .agents/config.json -> {"logging": true}
    4. Project hooks config: .agents/hooks.json -> {"reflex-guardrails": {"logging": true}}

    Default: False (logging disabled).
    """
    env_val = os.environ.get("AGENTREFLEX_LOGGING", "").strip().lower()
    if env_val in ("1", "true", "yes", "on", "enable", "enabled"):
        return True
    if env_val in ("0", "false", "no", "off", "disable", "disabled"):
        return False

    p = Path(project_path) if project_path else Path.cwd()
    if not p.is_absolute():
        if (Path.cwd() / p).exists():
            p = Path.cwd() / p
        elif Path.cwd().name == str(project_path):
            p = Path.cwd()
        elif (Path.home() / "git" / p).exists():
            p = Path.home() / "git" / p

    if not p.exists():
        # Check current working directory as fallback
        if (Path.cwd() / ".reflex-log").exists():
            return True
        return False

    # 1. Project-level opt-in flag file
    if (p / ".reflex-log").exists():
        return True

    # 2. Project config file (.agentreflex.json or .agents/config.json)
    for cfg_candidate in (
        p / ".agentreflex.json",
        p / ".agents" / "config.json",
        p / ".agents" / "agentreflex.json",
    ):
        if cfg_candidate.exists():
            try:
                data = json.loads(cfg_candidate.read_text(encoding="utf-8"))
                if "logging" in data:
                    return bool(data["logging"])
            except Exception:
                pass

    # 3. .agents/hooks.json reflex-guardrails setting
    hooks_file = p / ".agents" / "hooks.json"
    if hooks_file.exists():
        try:
            data = json.loads(hooks_file.read_text(encoding="utf-8"))
            guardrails = data.get("reflex-guardrails", {})
            if isinstance(guardrails, dict) and "logging" in guardrails:
                return bool(guardrails["logging"])
        except Exception:
            pass

    return False


def get_project_log_paths(project: str) -> Tuple[Path, Path]:
    """Return isolated per-project log file paths: logs/<project>.log and .jsonl."""
    clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", project.strip()) or "default"
    log_file = LOGS_DIR / f"{clean_name}.log"
    jsonl_file = LOGS_DIR / f"{clean_name}.jsonl"
    return log_file, jsonl_file


def resolve_agent_name(
    model_name: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """Format agent identity as 'model (conv_id)'."""
    short_cid = conversation_id[:8] if conversation_id else ""
    clean_model = model_name or ""

    if clean_model and short_cid:
        return f"{clean_model} ({short_cid})"
    if clean_model:
        return clean_model
    if short_cid:
        return f"agent-{short_cid}"
    return "agent"


def summarize_args(tool_name: str, args: Any) -> str:
    """Format tool arguments concisely for human-readable logging."""
    if not isinstance(args, dict):
        return str(args)[:150].replace("\n", " ")

    t_lower = tool_name.lower()
    if "command" in t_lower or "bash" in t_lower:
        cmd = (
            args.get("CommandLine")
            or args.get("commandLine")
            or args.get("command")
            or ""
        )
        if cmd:
            cmd_clean = str(cmd).replace("\n", " ").strip()
            return f"cmd='{cmd_clean[:180]}'"

    if any(k in t_lower for k in ("file", "edit", "view", "write")):
        target = (
            args.get("TargetFile")
            or args.get("AbsolutePath")
            or args.get("path")
            or args.get("file_path")
            or ""
        )
        if target:
            return f"file='{Path(str(target)).name}'"

    try:
        raw = json.dumps(args, ensure_ascii=False)
        return raw[:150]
    except Exception:
        return str(args)[:150]


def summarize_response(response: Any, max_len: int = 240) -> str:
    """Format and truncate response snippet for single-line logging."""
    if response is None:
        return ""
    text = str(response).strip()
    if not text:
        return "(empty)"

    single_line = " ".join(text.split())
    if len(single_line) > max_len:
        return f"{single_line[:max_len]}... ({len(text)} chars)"
    return single_line


def log_activity(
    project: str,
    agent: str,
    tool: str,
    args: Any,
    response: Any = "",
    status: str = "success",
    duration_ms: Optional[float] = None,
    project_dir: Optional[Any] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a structured event into an isolated per-project log file."""
    # Check project-level logging toggle
    if not is_logging_enabled(project_dir or project):
        return

    _ensure_log_dir()

    now_iso = datetime.now().astimezone().isoformat()
    now_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    clean_proj = project or "default"
    clean_agent = agent or "agent"
    clean_tool = tool or "unknown_tool"
    args_summary = summarize_args(clean_tool, args)
    resp_summary = summarize_response(response)

    dur_str = f" in {duration_ms:.1f}ms" if duration_ms is not None else ""

    log_file, jsonl_file = get_project_log_paths(clean_proj)

    # 1. Isolated per-project human-readable log (omits project tag inside file)
    # Order: [TOOL] first, req (args) & res (response) before [AGENT], [timestamp] last
    log_line = (
        f"[TOOL: {clean_tool}] {args_summary}{dur_str} -> response={resp_summary} "
        f"[AGENT: {clean_agent}] [STATUS: {status}] [{now_fmt}]\n"
    )

    try:
        with open(log_file, "a", encoding="utf-8", errors="replace") as f:
            f.write(log_line)
    except Exception:
        pass

    # 2. Isolated per-project JSONL log (tool first, args/response before agent, timestamp last)
    json_record = {
        "tool": clean_tool,
        "args": args if isinstance(args, (dict, list, str, int, bool)) else str(args),
        "response": str(response) if response is not None else "",
        "agent": clean_agent,
        "status": status,
        "duration_ms": duration_ms,
        "timestamp": now_iso,
    }
    if extra:
        json_record.update(extra)

    try:
        with open(jsonl_file, "a", encoding="utf-8", errors="replace") as f:
            f.write(json.dumps(json_record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_server_event(event_type: str, details: Any, status: str = "ok") -> None:
    """Record internal daemon server lifecycle events into server.log."""
    _ensure_log_dir()
    now_fmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_iso = datetime.now().astimezone().isoformat()

    msg = str(details).replace("\n", " ")
    line = f"[{now_fmt}] [SERVER: {event_type}] {msg} [STATUS: {status}]\n"

    try:
        with open(SERVER_LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
        with open(SERVER_JSONL_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": now_iso,
                        "type": "server_event",
                        "event": event_type,
                        "details": details,
                        "status": status,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def extract_post_tool_details(data: dict) -> tuple[str, dict, str, str]:
    """Extract tool name, args, response content, and status from a hook payload."""
    tool_call = data.get("toolCall", {}) or {}
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {}) or {}

    error = data.get("error", "")
    response = data.get("toolResult") or data.get("result") or data.get("content") or ""
    status = "error" if error else "success"

    if error:
        response = f"ERROR: {error}"

    transcript_path_str = data.get("transcriptPath", "")
    if transcript_path_str and (not tool_name or not response):
        tpath = Path(transcript_path_str)
        if tpath.exists():
            try:
                with open(tpath, "rb") as f:
                    try:
                        f.seek(-8192, os.SEEK_END)
                    except OSError:
                        f.seek(0)
                    tail_bytes = f.read()
                tail_lines = tail_bytes.decode("utf-8", errors="replace").splitlines()
                steps = []
                for line in tail_lines:
                    if line.strip():
                        try:
                            steps.append(json.loads(line))
                        except Exception:
                            continue

                for s in reversed(steps):
                    if not response and s.get("content") and not s.get("tool_calls"):
                        response = s.get("content", "")
                    if not tool_name and s.get("tool_calls"):
                        tc = s["tool_calls"][0]
                        tool_name = tc.get("name", "")
                        if not args:
                            args = tc.get("args", {})
                    if tool_name and response:
                        break
            except Exception:
                pass

    return tool_name or "unknown_tool", args, response, status
