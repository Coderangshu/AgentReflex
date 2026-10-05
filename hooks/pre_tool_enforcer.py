#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.rule_enforcer import check_violations
from lib.loop_detector import check_agent_loop


def check_transcript_loop(transcript_path_str: str, current_tool: str, current_args: dict) -> dict:
    """Read recent transcript steps to verify agent is not looping."""
    if not transcript_path_str:
        return {"is_looping": False}
    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return {"is_looping": False}

    try:
        lines = tpath.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]
        recent_actions = []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                for tc in item.get("tool_calls", []):
                    recent_actions.append({
                        "tool": tc.get("name"),
                        "args": tc.get("args", {}),
                        "error": item.get("error", ""),
                    })
            except Exception:
                continue

        recent_actions.append({"tool": current_tool, "args": current_args})
        return check_agent_loop(recent_actions)
    except Exception:
        return {"is_looping": False}


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

        # 1. Check for infinite/stuck agent loop
        transcript_path = data.get("transcriptPath")
        loop_res = check_transcript_loop(transcript_path, tool_name, args)
        if loop_res.get("is_looping", False):
            reason = loop_res.get("reason", "Agent loop detected")
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

        # 2. Extract modified code or command across standard parameter names
        content = (
            args.get("content")
            or args.get("patch")
            or args.get("commandLine")
            or args.get("CommandLine")
            or args.get("CodeContent")
            or args.get("ReplacementContent")
            or ""
        )

        if not content:
            print(json.dumps({"decision": "allow", "allow_tool": True}))
            return

        result = check_violations(content)

        if result.get("violates", False):
            reason = result.get("reason", "Laya rule guardrail triggered")
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
