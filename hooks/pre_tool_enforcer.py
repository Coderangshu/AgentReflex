#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.rule_enforcer import check_violations
from lib.secret_scan import (
    has_hardcoded_secret,
    has_destructive_command,
    MIN_EDIT_CHARS_FOR_MODEL,
    SECRET_REASON,
    DESTRUCTIVE_CMD_REASON,
)
from lib.loop_detector import check_agent_loop
from lib.warden_governor import evaluate_trajectory_governor
from lib.param_validator import validate_tool_call


def parse_transcript_history(transcript_path_str: str) -> tuple[list[dict], int, str]:
    """Read transcript steps to extract action history, tool call counts, and user goal.

    Counts tool calls scoped to the CURRENT turn (since the most recent USER_INPUT)
    to prevent lifetime session tool calls from tripping turn limits.
    """
    if not transcript_path_str:
        return [], 0, ""
    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return [], 0, ""

    try:
        lines = tpath.read_text(encoding="utf-8", errors="replace").splitlines()
        recent_actions = []
        turn_tool_calls = 0
        current_turn_goal = ""

        # Scan transcript and reset counter on each new user input turn
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                item_type = item.get("type", "")

                # Reset turn counter and update active goal whenever user inputs new prompt
                if item_type in ("USER_INPUT", "user"):
                    turn_tool_calls = 0
                    current_turn_goal = str(item.get("content", ""))[:300]
                    continue

                tcs = item.get("tool_calls", [])
                if tcs:
                    turn_tool_calls += len(tcs)
                    for tc in tcs:
                        # Only record actions that were not blocked/denied by guardrails
                        recent_actions.append({
                            "tool": tc.get("name"),
                            "args": tc.get("args", {}),
                            "error": item.get("error", ""),
                        })
            except Exception:
                continue

        return recent_actions[-6:], turn_tool_calls, current_turn_goal
    except Exception:
        return [], 0, ""


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"decision": "allow", "allow_tool": True}))
            return

        data = json.loads(raw_input)
        tool_call = data.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        args = tool_call.get("args", {})

        # 1. Trajectory & Tool Budget Governor Check
        transcript_path = data.get("transcriptPath")
        recent_actions, turn_tool_calls, user_goal = parse_transcript_history(transcript_path)
        
        gov_res = evaluate_trajectory_governor(
            task_goal=user_goal,
            recent_actions=recent_actions,
            proposed_tool=tool_name,
            proposed_args=args,
            total_tool_calls=turn_tool_calls,
        )

        if not gov_res.get("allow_action", True):
            reason = gov_res.get("reason", "Trajectory budget governor intervention")
            # Only emit valid protobuf fields expected by protojson unmarshaler
            print(
                json.dumps(
                    {
                        "decision": "deny",
                        "reason": reason,
                        "allow_tool": False,
                        "deny_reason": reason,
                    }
                )
            )
            return

        # 2. Hallucinated Tool Call & Parameter Gate
        cwd_dir = args.get("Cwd") or args.get("cwd") or args.get("working_directory")
        param_res = validate_tool_call(tool_name, args, cwd=cwd_dir)
        if not param_res.get("is_valid", True):
            reason = f"AgentReflex Param Gate: {param_res.get('reason')} Suggestion: {param_res.get('suggestion')}"
            print(
                json.dumps(
                    {
                        "decision": "deny",
                        "reason": reason,
                        "allow_tool": False,
                        "deny_reason": reason,
                    }
                )
            )
            return

        # 3. Extract modified code or command across standard parameter names
        command = args.get("commandLine") or args.get("CommandLine") or ""
        edit = (
            args.get("content")
            or args.get("patch")
            or args.get("CodeContent")
            or args.get("ReplacementContent")
            or ""
        )
        content = command or edit

        if not content:
            print(json.dumps({"decision": "allow", "allow_tool": True}))
            return

        if command:
            if has_destructive_command(command):
                print(
                    json.dumps(
                        {
                            "decision": "deny",
                            "reason": DESTRUCTIVE_CMD_REASON,
                            "allow_tool": False,
                            "deny_reason": DESTRUCTIVE_CMD_REASON,
                        }
                    )
                )
                return
        else:
            # File edit: deterministic secret check, and skip the model on short snippets it over-scores
            if has_hardcoded_secret(edit):
                print(
                    json.dumps(
                        {
                            "decision": "deny",
                            "reason": SECRET_REASON,
                            "allow_tool": False,
                            "deny_reason": SECRET_REASON,
                        }
                    )
                )
                return
            if len(edit) < MIN_EDIT_CHARS_FOR_MODEL:
                print(json.dumps({"decision": "allow", "allow_tool": True}))
                return

        result = check_violations(content)

        if result.get("violates", False):
            reason = result.get("reason", "AgentReflex rule guardrail triggered")
            print(
                json.dumps(
                    {
                        "decision": "deny",
                        "reason": reason,
                        "allow_tool": False,
                        "deny_reason": reason,
                    }
                )
            )
        else:
            print(json.dumps({"decision": "allow", "allow_tool": True}))
    except Exception:
        print(json.dumps({"decision": "allow", "allow_tool": True}))


if __name__ == "__main__":
    main()
