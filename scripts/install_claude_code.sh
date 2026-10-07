#!/usr/bin/env bash
# Wire AgentReflex into Claude Code: MCP server + hooks + CLAUDE.md rules.
#
# Usage:
#   scripts/install_claude_code.sh --user            # every project (~/.claude)
#   scripts/install_claude_code.sh [TARGET_DIR]      # one project (TARGET_DIR/.claude), default: .
set -e

TOOLKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$TOOLKIT_ROOT/.venv/bin/python"
MARKER="# AgentReflex Rules for Claude Code"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing $PYTHON_BIN. Run: python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

if [ "$1" = "--user" ]; then
  SCOPE="user"
  SETTINGS="$HOME/.claude/settings.json"
  CLAUDE_MD="$HOME/.claude/CLAUDE.md"
else
  SCOPE="project"
  TARGET_DIR="$(cd "${1:-.}" && pwd)"
  SETTINGS="$TARGET_DIR/.claude/settings.json"
  CLAUDE_MD="$TARGET_DIR/CLAUDE.md"
fi

mkdir -p "$(dirname "$SETTINGS")"

# 1. MCP server (idempotent: replace any existing registration in this scope)
if command -v claude >/dev/null 2>&1; then
  (cd "${TARGET_DIR:-$HOME}" && claude mcp remove agentreflex -s "$SCOPE" >/dev/null 2>&1 || true)
  (cd "${TARGET_DIR:-$HOME}" && claude mcp add -s "$SCOPE" agentreflex -- "$PYTHON_BIN" "$TOOLKIT_ROOT/mcp/server.py")
else
  echo "claude CLI not found; skipping MCP registration" >&2
fi

# 2. Hooks: merge into settings.json, replacing only our own entries
"$PYTHON_BIN" - "$SETTINGS" "$PYTHON_BIN" "$TOOLKIT_ROOT/hooks/claude_code_hook.py" <<'EOF'
import json, sys
from pathlib import Path

settings_path, python_bin, hook = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
command = f'"{python_bin}" "{hook}"'

wanted = {
    "PreToolUse": "Bash|Write|Edit|MultiEdit",
    "PostToolUse": "Write|Edit|MultiEdit",
    "UserPromptSubmit": None,
}
hooks = settings.setdefault("hooks", {})
for event, matcher in wanted.items():
    groups = [
        g for g in hooks.get(event, [])
        if not any("claude_code_hook.py" in h.get("command", "") for h in g.get("hooks", []))
    ]
    group = {"hooks": [{"type": "command", "command": command, "timeout": 15}]}
    if matcher:
        group["matcher"] = matcher
    hooks[event] = groups + [group]

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
EOF
echo "Hooks written to $SETTINGS"

# 3. CLAUDE.md rules (append once)
if [ -f "$CLAUDE_MD" ] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  echo "Rules already present in $CLAUDE_MD"
else
  { [ -s "$CLAUDE_MD" ] && echo; cat "$TOOLKIT_ROOT/CLAUDE.md"; } >> "$CLAUDE_MD"
  echo "Rules appended to $CLAUDE_MD"
fi

echo "Done. Restart Claude Code and make sure the daemon is up (make start)."
