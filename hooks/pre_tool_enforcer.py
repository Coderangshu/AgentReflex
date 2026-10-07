#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.rule_enforcer import check_violations
from lib.secret_scan import has_hardcoded_secret, MIN_EDIT_CHARS_FOR_MODEL, SECRET_REASON
from lib.loop_detector import check_agent_loop
from lib.warden_governor import evaluate_trajectory_governor


def parse_transcript_history(transcript_path_str: str) -> tuple[list[dict], int, str]:
    """Read transcript steps to extract action history, tool call counts, and user goal."""
    if not transcript_path_str:
        return [], 0, ""
    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return [], 0, ""

    try:
        lines = tpath.read_text(encoding="utf-8", errors="replace").splitlines()
        recent_actions = []
        total_tool_calls = 0
        user_goal = ""

        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                # Find the user's initial prompt/request
                if not user_goal and item.get("type") in ("USER_INPUT", "user"):
                    user_goal = str(item.get("content", ""))[:300]

                tcs = item.get("tool_calls", [])
                if tcs:
                    total_tool_calls += len(tcs)
                    for tc in tcs:
                        recent_actions.append({
                            "tool": tc.get("name"),
                            "args": tc.get("args", {}),
                            "error": item.get("error", ""),
                        })
            except Exception:
                continue

        return recent_actions[-6:], total_tool_calls, user_goal
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
        recent_actions, total_tool_calls, user_goal = parse_transcript_history(transcript_path)
        
        gov_res = evaluate_trajectory_governor(
            task_goal=user_goal,
            recent_actions=recent_actions,
            proposed_tool=tool_name,
            proposed_args=args,
            total_tool_calls=total_tool_calls,
        )

        if not gov_res.get("allow_action", True):
            reason = gov_res.get("reason", "Trajectory budget governor intervention")
            print(
                json.dumps(
                    {
                        "decision": "deny",
                        "reason": reason,
                        "allow_tool": False,
                        "deny_reason": reason,
                        "governor_status": gov_res.get("governor_status"),
                    }
                )
            )
            return

        # 2. Extract modified code or command across standard parameter names
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

        if not command:
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
