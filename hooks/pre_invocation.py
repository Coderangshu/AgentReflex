#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.skill_picker import pick_skill


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({}))
            return

        data = json.loads(raw_input)
        user_prompt = (
            data.get("prompt")
            or data.get("userMessage")
            or data.get("content")
            or ""
        )

        if not user_prompt:
            print(json.dumps({}))
            return

        result = pick_skill(user_prompt)
        choice = result.get("skill", "none")
        conf = result.get("confidence", 0.0)

        context = ""
        inject_steps = []
        if choice != "none" and conf > 0.65:
            context = f"[Laya Context Router]: Recommended skill for this request: /{choice}"
            inject_steps = [{"ephemeralMessage": context}]

        response = {
            "additionalContext": context,
            "injectSteps": inject_steps,
        }
        print(json.dumps(response))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
