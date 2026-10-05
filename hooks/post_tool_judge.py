#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.judge import judge_test_coverage


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({}))
            return

        data = json.loads(raw_input)
        tool_call = data.get("toolCall", {})
        args = tool_call.get("args", {})

        content = (
            args.get("content")
            or args.get("patch")
            or args.get("CodeContent")
            or args.get("ReplacementContent")
            or ""
        )

        if content:
            eval_result = judge_test_coverage(content)
            if eval_result.get("requires_verification", False):
                sys.stderr.write(
                    f"[Laya Test Judge] Notice: Significant uncovered logic detected "
                    f"(risk score: {eval_result['uncovered_risk']:.2f}). Consider writing unit tests.\n"
                )

        # Standard PostToolUse output is an empty JSON object
        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
