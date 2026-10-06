#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.skill_picker import pick_skill
from lib.compaction import score_message_retention

AUTO_COMPACT_SIZE_THRESHOLD_BYTES = 50 * 1024  # 50 KB


def compact_recent_transcript(transcript_path_str: str) -> dict:
    """Read transcript, score noisy blocks using Laya, and return compacted context if bloated."""
    if not transcript_path_str:
        return {}

    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return {}

    try:
        file_size = tpath.stat().st_size
        if file_size < AUTO_COMPACT_SIZE_THRESHOLD_BYTES:
            return {}

        total_steps = 0
        pruned_steps = 0
        kept_summaries = []

        with open(tpath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_steps += 1
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                step_type = data.get("type", "")
                content = data.get("content", "")

                # Always keep user prompts
                if step_type in ("USER_INPUT", "USER_EXPLICIT"):
                    continue

                if not content:
                    continue

                score_res = score_message_retention(content)
                if score_res.get("should_prune", False):
                    pruned_steps += 1
                else:
                    # Keep concise snippet of essential step
                    snippet = content[:150].replace("\n", " ").strip()
                    if snippet:
                        kept_summaries.append(f"Step {data.get('step_index', total_steps)}: {snippet}")

        if pruned_steps > 0:
            sample_kept = kept_summaries[-5:]  # Keep last 5 essential points
            summary_text = (
                f"[AgentReflex Auto-Compaction]: Pruned {pruned_steps}/{total_steps} noise steps "
                f"from active transcript ({file_size // 1024}KB -> lean memory). "
                f"Essential context: {' | '.join(sample_kept) if sample_kept else 'Clean state preserved'}."
            )
            return {
                "active": True,
                "summary": summary_text,
                "pruned_steps": pruned_steps,
            }
        return {}
    except Exception:
        return {}


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

        transcript_path = data.get("transcriptPath", "")

        context_parts = []
        inject_steps = []

        # 1. Automatic transcript compaction if context window is bloated
        compaction_res = compact_recent_transcript(transcript_path)
        if compaction_res.get("active"):
            summary_msg = compaction_res["summary"]
            context_parts.append(summary_msg)
            inject_steps.append({"ephemeralMessage": summary_msg})

        # 2. Skill routing
        if user_prompt:
            result = pick_skill(user_prompt)
            choice = result.get("skill", "none")
            conf = result.get("confidence", 0.0)

            if choice != "none" and conf > 0.65:
                route_msg = f"[AgentReflex Context Router]: Recommended skill for this request: /{choice}"
                context_parts.append(route_msg)
                inject_steps.append({"ephemeralMessage": route_msg})

        full_context = "\n".join(context_parts)
        response = {
            "additionalContext": full_context,
            "injectSteps": inject_steps,
        }
        print(json.dumps(response))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
