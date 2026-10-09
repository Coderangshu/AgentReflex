#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.skill_picker import pick_skill
from lib.compaction import score_message_retention
from lib.trajectory_pruner import prune_trajectory
from lib.speculative_triage import triage_task
from lib.action_cache import lookup_action_cache

AUTO_COMPACT_SIZE_THRESHOLD_BYTES = 50 * 1024  # 50 KB


def compact_recent_transcript(transcript_path_str: str) -> dict:
    """Read transcript, run semantic trajectory pruning, and return compacted context if bloated."""
    if not transcript_path_str:
        return {}

    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return {}

    try:
        file_size = tpath.stat().st_size
        if file_size < AUTO_COMPACT_SIZE_THRESHOLD_BYTES:
            return {}

        raw_steps = []
        with open(tpath, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    raw_steps.append({
                        "step_index": data.get("step_index", idx + 1),
                        "type": data.get("type", "UNKNOWN"),
                        "tool_name": data.get("tool_name", ""),
                        "content": data.get("content", ""),
                    })
                except Exception:
                    continue

        if not raw_steps:
            return {}

        # Run semantic trajectory pruner (AgentDiet)
        res = prune_trajectory(raw_steps)
        pruned_count = res.get("pruned_steps", 0)
        total_steps = res.get("total_steps", len(raw_steps))

        if pruned_count > 0:
            kept = res.get("active_steps", [])
            sample_kept = [
                f"Step {s.get('step_index')}: {s.get('content', '')[:120].replace(chr(10), ' ').strip()}"
                for s in kept[-5:]
                if s.get("content")
            ]
            summary_text = (
                f"[AgentReflex Trajectory Pruner]: Pruned {pruned_count}/{total_steps} obsolete/noise steps "
                f"({res.get('reduction_pct', 0)}% reduction, {file_size // 1024}KB file). "
                f"Active state: {' | '.join(sample_kept) if sample_kept else 'Clean context preserved'}."
            )
            return {
                "active": True,
                "summary": summary_text,
                "pruned_steps": pruned_count,
            }
        return {}
    except Exception:
        return {}
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

            # 3. Speculative Prompt Triage (Fan-Out)
            triage_res = triage_task(user_prompt)
            if triage_res.get("tags"):
                triage_msg = triage_res["summary_tag"]
                context_parts.append(triage_msg)
                inject_steps.append({"ephemeralMessage": triage_msg})

            # 4. Semantic Action Cache ("Learn to Skip")
            cache_hit = lookup_action_cache(user_prompt)
            if cache_hit and cache_hit.get("cache_hit"):
                acts = cache_hit.get("actions", [])
                acts_summary = ", ".join(
                    f"{a.get('tool', 'tool')}({list((a.get('args') or {}).values())[:1]})"
                    for a in acts[:3]
                )
                cache_msg = (
                    f"[AgentReflex Action Cache: HIT (conf {cache_hit.get('confidence', 1.0):.2f}) - "
                    f"Suggested verified actions: {acts_summary}]"
                )
                context_parts.append(cache_msg)
                inject_steps.append({"ephemeralMessage": cache_msg})

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
