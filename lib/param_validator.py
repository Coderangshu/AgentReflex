"""Hallucinated Tool Call and Parameter Gate using System 1 validation.

Validates proposed tool names, arguments, commands, and target paths before execution:
1. Deterministic syntax validation for common CLI commands (git, npm, pip, pytest, docker)
   and file operation parameter schemas.
2. Workspace path plausibility check (verifies read/edit targets exist or have valid parent dirs).
3. Neural validation via Laya (<25ms) for ambiguous or complex command flags and tool invocations.
"""

from __future__ import annotations
import os
import re
import shlex
from pathlib import Path
from typing import Dict, Any, Optional
from lib.client import query_laya

# Known CLI commands and illegal / hallucinated flags commonly produced by LLMs
KNOWN_CLI_HALLUCINATIONS = {
    "git": {
        "--remote-track": "use 'git checkout --track <remote>/<branch>' instead",
        "--auto-merge": "git checkout / merge does not take --auto-merge; use standard git merge",
        "--stage-all": "use 'git add -A' or 'git add .'",
        "--force-push": "use 'git push --force' or 'git push --force-with-lease'",
        "--delete-branch": "use 'git branch -d <branch>' or 'git push origin --delete <branch>'",
        "--create-branch": "use 'git checkout -b <branch>' or 'git switch -c <branch>'",
    },
    "npm": {
        "--save-dev-only": "use 'npm install --save-dev'",
        "--global-install": "use 'npm install -g <pkg>'",
        "--install-deps": "use 'npm install'",
        "--clean-cache": "use 'npm cache clean --force'",
    },
    "pip": {
        "--requirements-file": "use '-r' or '--requirement'",
        "--upgrade-all": "pip does not have --upgrade-all; use 'pip list --outdated' or loop",
        "--install-dir": "use '--target <dir>'",
        "--virtualenv": "use python -m venv <dir> first",
    },
    "pytest": {
        "--run-failed": "use '--last-failed' or '--lf'",
        "--rerun": "use '--reruns <count>' with pytest-rerunfailures",
        "--all-tests": "run pytest without arguments to run all discovered tests",
    },
    "curl": {
        "--json-data": "use '-d' or '--json'",
        "--header-token": "use '-H \"Authorization: Bearer <token>\"'",
    },
    "find": {
        "--name": "find takes single dash '-name'",
        "--type": "find takes single dash '-type'",
        "--maxdepth": "find takes single dash '-maxdepth'",
    },
    "grep": {
        "--recursive-dir": "use '-r' or '--recursive'",
        "--line-numbers": "use '-n'",
    },
}

# Required parameter schemas for common tool types across AGY, Claude Code, and standard MCP
STANDARD_TOOL_PARAM_SCHEMAS = {
    "view_file": {"required": [["AbsolutePath", "target_file", "path", "file_path"]]},
    "replace_file_content": {
        "required": [
            ["TargetFile", "file_path", "path"],
            ["TargetContent", "old_string", "target_string"],
            ["ReplacementContent", "new_string", "replacement"],
        ]
    },
    "write_to_file": {
        "required": [
            ["TargetFile", "file_path", "path"],
            ["CodeContent", "content"],
        ]
    },
    "run_command": {"required": [["CommandLine", "command", "cmd"]]},
    "read_file": {"required": [["path", "file_path", "AbsolutePath"]]},
    "Edit": {"required": [["file_path"], ["old_string"], ["new_string"]]},
    "Write": {"required": [["file_path"], ["content"]]},
    "Bash": {"required": [["command"]]},
}


def _check_command_hallucinations(command_str: str) -> Optional[dict]:
    """Check command line string for known hallucinated CLI flags and malformed tokens."""
    if not command_str or not command_str.strip():
        return {
            "is_valid": False,
            "error_type": "empty_command",
            "reason": "Proposed command is empty.",
            "suggestion": "Specify a valid executable command.",
        }

    try:
        tokens = shlex.split(command_str)
    except ValueError as e:
        # Unbalanced quotes or syntax error
        return {
            "is_valid": False,
            "error_type": "syntax_error",
            "reason": f"Command syntax error in shell tokenization: {str(e)}",
            "suggestion": "Fix unmatched quotes or unescaped shell special characters.",
        }

    if not tokens:
        return None

    cmd_binary = Path(tokens[0]).name

    # Check known tool hallucinations
    if cmd_binary in KNOWN_CLI_HALLUCINATIONS:
        bad_flags = KNOWN_CLI_HALLUCINATIONS[cmd_binary]
        for token in tokens[1:]:
            flag_name = token.split("=")[0]
            if flag_name in bad_flags:
                fix = bad_flags[flag_name]
                return {
                    "is_valid": False,
                    "error_type": "hallucinated_cli_flag",
                    "reason": f"Hallucinated or invalid flag '{flag_name}' for command '{cmd_binary}'.",
                    "suggestion": fix,
                }

    return None


def _check_missing_parameters(tool_name: str, args: dict) -> Optional[dict]:
    """Check if required tool arguments are missing based on standard schema conventions."""
    if not isinstance(args, dict):
        return {
            "is_valid": False,
            "error_type": "invalid_argument_type",
            "reason": f"Tool arguments for '{tool_name}' must be a JSON object, got {type(args).__name__}.",
            "suggestion": "Pass arguments as key-value JSON dictionary.",
        }

    schema = STANDARD_TOOL_PARAM_SCHEMAS.get(tool_name)
    if not schema:
        return None

    req_groups = schema.get("required", [])
    for group in req_groups:
        has_any = any(k in args and args[k] is not None for k in group)
        if not has_any:
            expected_names = " or ".join(f"'{k}'" for k in group)
            return {
                "is_valid": False,
                "error_type": "missing_required_param",
                "reason": f"Missing required parameter for tool '{tool_name}': expected {expected_names}.",
                "suggestion": f"Provide {group[0]} in tool call arguments.",
            }

    return None


def _check_path_plausibility(
    tool_name: str,
    args: dict,
    cwd: Optional[str] = None,
) -> Optional[dict]:
    """Check if target file path is plausible (not referencing imaginary non-existent parent dirs)."""
    # Extract path from common parameter keys
    path_val = (
        args.get("AbsolutePath")
        or args.get("TargetFile")
        or args.get("file_path")
        or args.get("path")
        or args.get("Target")
    )
    if not path_val or not isinstance(path_val, str):
        return None

    base_dir = Path(cwd) if cwd else Path.cwd()
    target_path = Path(path_val)
    if not target_path.is_absolute():
        target_path = base_dir / target_path

    # Read/view operations: file MUST exist
    is_read_tool = any(read_key in tool_name.lower() for read_key in ("read", "view", "grep", "cat"))
    if is_read_tool:
        if not target_path.exists():
            return {
                "is_valid": False,
                "error_type": "nonexistent_read_path",
                "reason": f"Target file '{path_val}' does not exist on disk.",
                "suggestion": f"Check path spelling or use file search/list to locate '{target_path.name}'.",
            }

    # Edit/replace operations: file MUST exist
    is_edit_tool = any(edit_key in tool_name.lower() for edit_key in ("edit", "replace", "patch"))
    if is_edit_tool:
        if not target_path.exists():
            return {
                "is_valid": False,
                "error_type": "nonexistent_edit_target",
                "reason": f"Cannot edit '{path_val}' because the file does not exist.",
                "suggestion": f"To create a new file use write_to_file or verify target path.",
            }

    # Write operations: parent directory should exist or be within plausible workspace
    is_write_tool = any(write_key in tool_name.lower() for write_key in ("write", "create"))
    if is_write_tool:
        parent = target_path.parent
        # Disallow ridiculous nonexistent deep nesting (more than 3 levels non-existent)
        nonexistent_parents = 0
        curr = parent
        while curr and not curr.exists() and curr != curr.parent:
            nonexistent_parents += 1
            curr = curr.parent
            if nonexistent_parents > 3:
                return {
                    "is_valid": False,
                    "error_type": "implausible_directory_tree",
                    "reason": f"Target path '{path_val}' points to deeply nested nonexistent directories.",
                    "suggestion": "Verify directory path or create required directories explicitly.",
                }

    return None


def validate_tool_call(
    tool_name: str,
    args: dict,
    cwd: Optional[str] = None,
    use_neural: bool = True,
) -> dict:
    """Master parameter and tool call validation gate.

    Combines:
    1. Schema validation (missing required params).
    2. CLI hallucination checks (invalid flags for git, npm, pip, pytest).
    3. Workspace path plausibility checks (nonexistent read/edit files).
    4. Optional neural Laya validation (<25ms) for ambiguous commands.
    """
    if not tool_name:
        return {
            "is_valid": False,
            "error_type": "missing_tool_name",
            "reason": "Tool name is empty or unspecified.",
            "suggestion": "Specify a valid tool name.",
        }

    args = args or {}

    # 1. Missing parameter schema check
    param_err = _check_missing_parameters(tool_name, args)
    if param_err:
        return param_err

    # 2. Extract command string for CLI validation
    cmd_val = (
        args.get("CommandLine")
        or args.get("commandLine")
        or args.get("command")
        or args.get("cmd")
    )
    if cmd_val and isinstance(cmd_val, str):
        cmd_err = _check_command_hallucinations(cmd_val)
        if cmd_err:
            return cmd_err

    # 3. Path plausibility check
    path_err = _check_path_plausibility(tool_name, args, cwd=cwd)
    if path_err:
        return path_err

    # 4. Neural verification via Laya for non-trivial commands
    neural_score = 0.0
    if use_neural and cmd_val and isinstance(cmd_val, str) and len(cmd_val) > 10:
        state = f"Command execution request:\ncommand: {cmd_val[:400]}"
        questions = {
            "is_malformed": {
                "type": "noul",
                "instructions": (
                    "Is this command completely malformed, broken, or containing garbage syntax?"
                ),
            }
        }
        res = query_laya(state, questions)
        is_malformed = res.get("is_malformed", {}).get("noul", 0.0)
        neural_score = round(is_malformed, 3)
        if is_malformed >= 0.85:
            return {
                "is_valid": False,
                "error_type": "hallucinated_syntax",
                "reason": f"Command appears to contain malformed syntax or invalid flags (malformed score: {neural_score:.2f}).",
                "suggestion": f"Check command options for: {cmd_val[:60]}",
                "neural_score": neural_score,
            }

    return {
        "is_valid": True,
        "error_type": None,
        "reason": "Tool call parameters and syntax validated successfully.",
        "suggestion": None,
        "neural_score": neural_score,
    }
