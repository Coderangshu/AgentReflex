#!/usr/bin/env bash
set -e

TARGET_DIR="${1:-.}"
TOOLKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing Laya hooks and skills into: $TARGET_DIR"

mkdir -p "$TARGET_DIR/.agents/skills"

# 1. Symlink Skills
ln -sfn "$TOOLKIT_ROOT/skills/reflex-fast-explore" "$TARGET_DIR/.agents/skills/reflex-fast-explore"
ln -sfn "$TOOLKIT_ROOT/skills/reflex-review-gate" "$TARGET_DIR/.agents/skills/reflex-review-gate"
ln -sfn "$TOOLKIT_ROOT/skills/reflex-compact" "$TARGET_DIR/.agents/skills/reflex-compact"
ln -sfn "$TOOLKIT_ROOT/skills/reflex-grep" "$TARGET_DIR/.agents/skills/reflex-grep"

PYTHON_BIN="python3"
if [ -f "$TOOLKIT_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$TOOLKIT_ROOT/.venv/bin/python"
fi

# 2. Generate or update .agents/hooks.json
cat <<EOF > "$TARGET_DIR/.agents/hooks.json"
{
  "reflex-guardrails": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "$PYTHON_BIN $TOOLKIT_ROOT/hooks/pre_invocation.py",
        "timeout": 15
      }
    ],
    "PreToolUse": [
      {
        "matcher": "write_file|edit_file|replace_file_content|write_to_file|run_command|command",
        "hooks": [
          {
            "type": "command",
            "command": "$PYTHON_BIN $TOOLKIT_ROOT/hooks/pre_tool_enforcer.py",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "write_file|edit_file|replace_file_content|write_to_file",
        "hooks": [
          {
            "type": "command",
            "command": "$PYTHON_BIN $TOOLKIT_ROOT/hooks/post_tool_judge.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
EOF

# Ensure hooks and scripts are executable
chmod +x "$TOOLKIT_ROOT"/hooks/*.py
chmod +x "$TOOLKIT_ROOT"/skills/*/run.py

echo "✅ Successfully configured .agents/ in $TARGET_DIR"
