#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.compaction import score_message_retention
from lib.trajectory_pruner import prune_trajectory
from lib.speculative_triage import triage_task
from lib.action_cache import lookup_action_cache
from lib.model_router import route_model

AUTO_COMPACT_SIZE_THRESHOLD_BYTES = 50 * 1024  # 50 KB


def compact_recent_transcript(transcript_path_str: str) -> dict:
    """Fast non-blocking check for large transcripts to avoid freezing interactive turns."""
    if not transcript_path_str:
        return {}

    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return {}

    try:
        file_size = tpath.stat().st_size
        if file_size < AUTO_COMPACT_SIZE_THRESHOLD_BYTES:
            return {}

        # Alert the model to prune context via /reflex-compact rather than blocking interactive turn
        summary_text = (
            f"[AgentReflex Trajectory Pruner Alert]: Active transcript is {file_size // 1024}KB. "
            f"Run /reflex-compact if memory pruning is needed."
        )
        return {
            "active": True,
            "summary": summary_text,
            "pruned_steps": 0,
        }
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

        # 2. Dynamic Model Tier, Effort & Skill Router (Single Unified Pass)
        if user_prompt:
            router_res = route_model(user_prompt, harness="agy")
            task_class = router_res.get("task_class", "routine_crud")

            # 2a. Recommended Skill (derived directly from task_class with 0 extra calls)
            rec_skill = router_res.get("recommended_skill")
            if rec_skill:
                route_msg = f"[AgentReflex Context Router]: Recommended skill for this request: /{rec_skill}"
                context_parts.append(route_msg)
                inject_steps.append({"ephemeralMessage": route_msg})

            # 2b. Speculative Prompt Triage (Bypassed for simple/inspect tasks to protect TTFT)
            if task_class not in ("doc_typo", "ops_script", "simple_inspect"):
                triage_res = triage_task(user_prompt)
                if triage_res.get("tags"):
                    triage_msg = triage_res["summary_tag"]
                    context_parts.append(triage_msg)
                    inject_steps.append({"ephemeralMessage": triage_msg})

            # 2c. Semantic Action Cache ("Learn to Skip")
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

            # 2d. Injected Model Tier & Reasoning Tag
            if router_res.get("summary_tag"):
                router_msg = router_res["summary_tag"]
                context_parts.append(router_msg)
                inject_steps.append({"ephemeralMessage": router_msg})

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
