#!/usr/bin/env python3
"""Runner script for laya-review-gate skill."""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.review_gate import review_diff


def main():
    diff_text = ""
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            diff_text = path.read_text(encoding="utf-8")
        else:
            diff_text = sys.argv[1]
    elif not sys.stdin.isatty():
        diff_text = sys.stdin.read()

    if not diff_text.strip():
        print("Usage: run.py <diff_file_or_patch>")
        print("Or pipe diff via stdin: git diff | run.py")
        sys.exit(1)

    result = review_diff(diff_text)
    print(json.dumps(result, indent=2))

    if not result.get("passed", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
