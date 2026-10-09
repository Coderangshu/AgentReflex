#!/usr/bin/env python3
"""Claude Code hook adapter for AgentReflex.

One entry point for three Claude Code hook events (dispatched on `hook_event_name`):
- PreToolUse:       policy guardrail on Bash commands and file edits (asks for confirmation on violation)
- PostToolUse:      test-coverage nudge after file edits (fed back to Claude as additional context)
- UserPromptSubmit: routes the prompt to the matching reflex_* MCP tool

Fails open: if the daemon is down or anything errors, the hook stays silent and Claude proceeds.
"""

import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.client import is_daemon_alive
from lib.rule_enforcer import check_violations
from lib.judge import judge_test_coverage
from lib.skill_picker import pick_skill
from lib.secret_scan import (
    has_hardcoded_secret,
    has_destructive_command,
    MIN_EDIT_CHARS_FOR_MODEL,
    SECRET_REASON,
    DESTRUCTIVE_CMD_REASON,
)
from lib.param_validator import validate_tool_call

# Skill-router labels -> the MCP tools that implement them in Claude Code
SKILL_TO_TOOLS = {
    "fast_explore": "reflex_rank_files / reflex_grep",
    "review_gate": "reflex_review_gate",
    "compact": "reflex_compact / reflex_prune_trajectory",
}


def edited_content(tool_name: str, tool_input: dict) -> str:
    """Pull the text being written out of Write / Edit / MultiEdit / NotebookEdit inputs."""
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        return tool_input.get("new_string", "")
    if tool_name == "MultiEdit":
        return "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))
    if tool_name == "NotebookEdit":
        return tool_input.get("new_source", "")
    return ""


def ask(reason: str) -> dict:
    # "ask" rather than "deny": the user stays in control of false positives
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def pre_tool_use(data: dict) -> dict:
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # For Bash or command executions, check for hallucinated CLI flags
    if tool_name in ("Bash", "run_command"):
        param_res = validate_tool_call(tool_name, tool_input)
        if not param_res.get("is_valid", True):
            msg = f"AgentReflex: {param_res.get('reason')} ({param_res.get('suggestion')})"
            return ask(msg)

    if tool_name == "Bash":
        content = tool_input.get("command", "")
        if has_destructive_command(content):
            return ask(DESTRUCTIVE_CMD_REASON)
    else:
        content = edited_content(tool_name, tool_input)
        if has_hardcoded_secret(content):
            return ask(SECRET_REASON)
        # The model over-scores short snippets (benign 3-line edits hit 90%+), so only trust it on longer edits
        if len(content) < MIN_EDIT_CHARS_FOR_MODEL:
            return {}
    if not content:
        return {}

    result = check_violations(content)
    return ask(result["reason"]) if result.get("violates") else {}


NON_CODE_EXTS = {
    ".md", ".markdown", ".txt", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".tsv", ".lock", ".env",
    ".svg", ".png", ".jpg", ".html", ".css", ".scss",
}


def target_file_path(tool_name: str, tool_input: dict) -> str:
    """Extract target file path from tool arguments."""
    return (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("file")
        or ""
    )


def post_tool_use(data: dict) -> dict:
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    file_path = target_file_path(tool_name, tool_input)

    # Skip documentation, configs, and non-source files to avoid nagging
    if file_path:
        suffix = Path(file_path).suffix.lower()
        if suffix in NON_CODE_EXTS:
            return {}

    content = edited_content(tool_name, tool_input)
    # Only nudge for substantive edits to prevent noise on small 2-line tweaks
    if not content or len(content) < MIN_EDIT_CHARS_FOR_MODEL:
        return {}

    res = judge_test_coverage(content)
    if not res.get("requires_verification"):
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "[AgentReflex Test Judge] Significant uncovered logic detected "
                f"(risk score: {res['uncovered_risk']:.2f}). Consider adding or updating unit tests."
            ),
        }
    }


def user_prompt_submit(data: dict) -> dict:
    prompt = data.get("prompt", "")
    if not prompt:
        return {}
    res = pick_skill(prompt)
    tools = SKILL_TO_TOOLS.get(res.get("skill", "none"))
    if not tools or not res.get("is_recommended"):
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"[AgentReflex Router] This request fits the AgentReflex tool(s): {tools}.",
        }
    }


HANDLERS = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "UserPromptSubmit": user_prompt_submit,
}


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
        handler = HANDLERS.get(data.get("hook_event_name", ""))
        if handler is None or not is_daemon_alive():
            return
        out = handler(data)
        if out:
            print(json.dumps(out))
    except Exception:
        pass  # fail open


if __name__ == "__main__":
    main()
