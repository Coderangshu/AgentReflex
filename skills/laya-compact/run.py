#!/usr/bin/env python3
"""Runner script for laya-compact skill."""

import sys
import json
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.compaction import score_message_retention


def compact_transcript(transcript_path: Path) -> dict:
    if not transcript_path.exists():
        return {"error": f"Transcript file not found: {transcript_path}"}

    total_steps = 0
    kept_steps = []
    pruned_count = 0

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_steps += 1
            try:
                data = json.loads(line)
            except Exception:
                continue

            content = data.get("content", "")
            step_type = data.get("type", "")

            # Always keep user input or model plans
            if step_type in ("USER_INPUT", "USER_EXPLICIT"):
                kept_steps.append({
                    "step_index": data.get("step_index", total_steps),
                    "type": step_type,
                    "content": content,
                    "retained": "always_user",
                })
                continue

            if not content:
                continue

            score_res = score_message_retention(content)
            if score_res.get("should_prune", False):
                pruned_count += 1
            else:
                kept_steps.append({
                    "step_index": data.get("step_index", total_steps),
                    "type": step_type,
                    "content": content[:500] + ("..." if len(content) > 500 else ""),
                    "keep_score": round(score_res.get("keep_score", 0.0), 3),
                })

    return {
        "status": "success",
        "total_steps": total_steps,
        "pruned_steps": pruned_count,
        "retained_steps": len(kept_steps),
        "reduction_rate": f"{(pruned_count / max(1, total_steps)):.1%}",
        "compacted_context": kept_steps,
    }


def compact_text(text: str) -> dict:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    retained = []
    pruned = 0

    for p in paragraphs:
        score_res = score_message_retention(p)
        if score_res.get("should_prune", False):
            pruned += 1
        else:
            retained.append(p)

    return {
        "status": "success",
        "total_blocks": len(paragraphs),
        "pruned_blocks": pruned,
        "retained_blocks": len(retained),
        "compacted_text": "\n\n".join(retained),
    }


def main():
    parser = argparse.ArgumentParser(description="Laya Fast Context Compactor")
    parser.add_argument("--transcript", type=str, help="Path to transcript.jsonl")
    parser.add_argument("--text", type=str, help="Raw text string to compact")
    args = parser.parse_args()

    if args.transcript:
        res = compact_transcript(Path(args.transcript))
        print(json.dumps(res, indent=2))
        return

    if args.text:
        res = compact_text(args.text)
        print(json.dumps(res, indent=2))
        return

    if not sys.stdin.isatty():
        raw_input = sys.stdin.read()
        res = compact_text(raw_input)
        print(json.dumps(res, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
