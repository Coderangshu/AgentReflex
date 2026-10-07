"""Multi-turn conversation trajectory and history pruner (AgentDiet).

Uses System 1 decision engine to perform semantic dependency analysis across
multi-turn agent history:
1. Identifies error traces that were subsequently resolved by later steps (obsolete errors).
2. Identifies exploratory searches/listings superseded by actual file edits or reads.
3. Distills large multi-step traces into lean, high-signal active memory.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from lib.client import query_laya
from lib.compaction import score_message_retention


def classify_trajectory_step(step_content: str, future_context: str = "") -> dict:
    """Classify an individual conversation step in the context of subsequent events.

    Returns dict with classification ('obsolete_error', 'transient_listing', 'durable_state'),
    retention recommendation, and confidence score.
    """
    if not step_content or not step_content.strip():
        return {
            "category": "transient_listing",
            "should_prune": True,
            "confidence": 1.0,
            "reason": "Empty step",
        }

    # First check deterministic heuristic noise (progress bars, downloads)
    heuristic = score_message_retention(step_content)
    if heuristic.get("should_prune", False):
        return {
            "category": "transient_listing",
            "should_prune": True,
            "confidence": heuristic.get("noise_score", 0.9),
            "reason": "Terminal progress noise",
        }

    # Evaluate whether step is an obsolete error resolved by later steps
    if future_context:
        state_err = f"Past Action / Output:\n{step_content[:700]}\n\nSubsequent Resolution / Actions:\n{future_context[:500]}"
        q_err = {
            "status": {
                "type": "choice",
                "instructions": "Determine the state of this past trace given that subsequent steps succeeded.",
                "criteria": {
                    "resolved_past_error": "An error, traceback, or failed test that was subsequently resolved",
                    "active_unresolved_issue": "An ongoing error that is not yet fixed",
                    "permanent_requirement": "A project rule or user prompt requirement",
                },
            }
        }
        res_err = query_laya(state_err, q_err)
        choice_err = res_err.get("status", {}).get("choice", "")
        conf_err = res_err.get("status", {}).get("answer_confidence", 0.0)
        if choice_err == "resolved_past_error" and conf_err >= 0.65:
            return {
                "category": "obsolete_error",
                "should_prune": True,
                "confidence": conf_err,
                "reason": f"Classified as resolved_past_error with {conf_err:.0%} confidence",
            }

    # Evaluate whether step is a disposable directory listing or search dump
    state_list = f"Diagnostic Output:\n{step_content[:700]}"
    q_list = {
        "is_transient_search": {
            "type": "noul",
            "instructions": "Is this a temporary directory listing, search output, or disposable diagnostic log?",
        }
    }
    res_list = query_laya(state_list, q_list)
    search_score = res_list.get("is_transient_search", {}).get("noul", 0.0)
    if search_score >= 0.70:
        return {
            "category": "transient_listing",
            "should_prune": True,
            "confidence": search_score,
            "reason": f"Classified as transient directory listing with {search_score:.0%} confidence",
        }

    return {
        "category": "durable_state",
        "should_prune": False,
        "confidence": 1.0 - search_score,
        "reason": "Retained as active context",
    }


def prune_trajectory(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze a multi-step execution trajectory and return pruned, lean history.

    steps: list of dicts with keys:
      - 'step_index': int
      - 'type': str (e.g. 'USER_INPUT', 'PLANNER_RESPONSE', 'TOOL_RESULT')
      - 'tool_name': optional str
      - 'content': str
    """
    if not steps:
        return {"total_steps": 0, "pruned_steps": 0, "active_steps": [], "pruned_indices": []}

    total_steps = len(steps)
    pruned_indices = []
    active_steps = []

    # Compile future summaries for lookahead context
    for i, step in enumerate(steps):
        step_type = step.get("type", "")
        content = step.get("content", "")

        # Always preserve explicit user inputs
        if step_type in ("USER_INPUT", "USER_EXPLICIT"):
            active_steps.append(step)
            continue

        # Lookahead: collect next 3 steps to see if this step was resolved/superseded
        future_snippets = []
        for next_step in steps[i + 1 : i + 4]:
            tname = next_step.get("tool_name", "")
            snippet = next_step.get("content", "")[:120].replace("\n", " ")
            future_snippets.append(f"{tname}: {snippet}".strip())
        future_context = " -> ".join(future_snippets)

        classification = classify_trajectory_step(content, future_context=future_context)

        if classification.get("should_prune", False):
            pruned_indices.append(step.get("step_index", i))
        else:
            active_steps.append(step)

    return {
        "total_steps": total_steps,
        "pruned_steps": len(pruned_indices),
        "kept_steps": len(active_steps),
        "pruned_indices": pruned_indices,
        "active_steps": active_steps,
        "reduction_pct": round((len(pruned_indices) / max(1, total_steps)) * 100, 1),
    }


def prune_transcript_file(transcript_path: Path | str) -> Dict[str, Any]:
    """Read a transcript.jsonl file, prune obsolete steps, and return summary."""
    tpath = Path(transcript_path)
    if not tpath.exists():
        return {"error": f"File not found: {transcript_path}"}

    steps = []
    with open(tpath, "r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                steps.append({
                    "step_index": data.get("step_index", idx + 1),
                    "type": data.get("type", "UNKNOWN"),
                    "tool_name": data.get("tool_name", ""),
                    "content": data.get("content", ""),
                })
            except Exception:
                continue

    return prune_trajectory(steps)
