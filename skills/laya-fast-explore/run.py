#!/usr/bin/env python3
"""Runner script for laya-fast-explore skill."""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.file_ranker import rank_files


def main():
    if len(sys.argv) < 2:
        print("Usage: run.py <search_intent> [file_paths...]")
        print("Or pipe file paths via stdin: find . | run.py <search_intent>")
        sys.exit(1)

    intent = sys.argv[1]
    paths = sys.argv[2:]

    # If no paths passed as args, try reading from stdin
    if not paths and not sys.stdin.isatty():
        paths = [line.strip() for line in sys.stdin if line.strip()]

    if not paths:
        print(json.dumps({"error": "No candidate file paths provided", "ranked": []}))
        sys.exit(0)

    ranked = rank_files(intent, paths, top_k=5)

    output = {
        "intent": intent,
        "ranked": [{"path": path, "score": round(score, 4)} for path, score in ranked],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
