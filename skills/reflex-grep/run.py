#!/usr/bin/env python3
"""Runner script for laya-grep (surgical context retrieval / jevgrep)."""

import sys
import json
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.surgical_retrieval import surgical_search


def main():
    parser = argparse.ArgumentParser(description="Laya Surgical Code Search (jevgrep)")
    parser.add_argument("query", type=str, help="Search query or semantic intent")
    parser.add_argument("paths", nargs="+", help="Files or directories to search")
    parser.add_argument("--top-k", type=int, default=3, help="Max snippets to return")
    parser.add_argument("--window", type=int, default=30, help="Lines per snippet window")
    args = parser.parse_args()

    results = surgical_search(
        query=args.query,
        target_paths=args.paths,
        max_snippets=args.top_k,
        window_lines=args.window,
    )

    output = {
        "query": args.query,
        "matches_count": len(results),
        "snippets": results,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
