"""Cross-Turn Intent Drift Alarm.

Monitors multi-turn agent execution trajectory against the user's primary goal.
Detects semantic derailment when the agent wanders into off-topic rabbit holes
after multiple tool steps or recovered errors.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from lib.client import query_laya


# Thresholds for triggering course correction alarm
DRIFT_ALIGNMENT_THRESHOLD = 0.35  # Below 35% alignment triggers alarm
MIN_ACTIONS_BEFORE_ALARM = 2      # Allow initial exploratory steps


def check_intent_drift(
    primary_goal: str,
    recent_actions: list[dict],
    proposed_tool: str = "",
    proposed_args: dict = None,
) -> dict:
    """Evaluate whether the agent's current trajectory has drifted from the user's goal.

    Uses System 1 neural decision scoring to compare the user's original objective
    against the actual files, tools, and arguments currently being touched.
    """
    if not primary_goal:
        return {
            "has_drifted": False,
            "alignment_score": 1.0,
            "drift_status": "aligned",
            "confidence": 1.0,
            "warning": "",
        }

    # Format action trace for neural scoring
    action_trace = []
    for idx, act in enumerate(recent_actions[-4:]):
        tool = act.get("tool", "tool")
        args = act.get("args", {})
        # Extract meaningful path or command target
        target = (
            args.get("TargetFile")
            or args.get("AbsolutePath")
            or args.get("CommandLine")
            or args.get("commandLine")
            or str(args)[:60]
        )
        action_trace.append(f"Step {idx+1}: {tool}({target})")

    if proposed_tool:
        prop_args = proposed_args or {}
        prop_target = (
            prop_args.get("TargetFile")
            or prop_args.get("AbsolutePath")
            or prop_args.get("CommandLine")
            or prop_args.get("commandLine")
            or str(prop_args)[:60]
        )
        action_trace.append(f"Next: {proposed_tool}({prop_target})")

    # If very few actions taken, do not prematurely alarm
    if len(action_trace) < MIN_ACTIONS_BEFORE_ALARM:
        return {
            "has_drifted": False,
            "alignment_score": 1.0,
            "drift_status": "aligned",
            "confidence": 1.0,
            "warning": "",
        }

    state = (
        f"User Objective: {primary_goal}\n\n"
        f"Recent Agent Actions:\n" + "\n".join(f"{i+1}. {a}" for i, a in enumerate(action_trace))
    )[:1200]

    questions = {
        "drift": {
            "type": "choice",
            "instructions": "Are the agent actions aligned with the user objective or drifting to an unrelated topic?",
            "criteria": {
                "aligned": "Actions are relevant and working on, editing, or testing the objective",
                "drifting": "Actions are completely unrelated to the objective",
            },
        },
        "alignment": {
            "type": "noul",
            "instructions": "Rate how relevant these actions are to the user objective.",
        },
    }

    try:
        res = query_laya(state, questions)
        drift_data = res.get("drift", {})
        drift_choice = drift_data.get("choice", "aligned")
        probs = drift_data.get("probabilities", {})
        drift_conf = probs.get(drift_choice, drift_data.get("confidence", 0.5))
        alignment_score = (
            res.get("alignment", {}).get("noul")
            or res.get("alignment_score", {}).get("noul")
            or 0.5
        )

        # Trigger alarm only when drifting with low alignment
        has_drifted = (drift_choice == "drifting" and alignment_score < 0.30) or (alignment_score < 0.15)

        warning_msg = ""
        if has_drifted:
            warning_msg = (
                f"[AgentReflex Intent Drift Alarm]: Agent activity has drifted from original user objective "
                f"('{primary_goal[:100]}...') to off-topic actions (alignment: {alignment_score:.2f}). "
                f"Course correction required: return focus to primary objective."
            )

        return {
            "has_drifted": has_drifted,
            "alignment_score": round(alignment_score, 4),
            "drift_status": drift_choice,
            "confidence": round(drift_conf, 4),
            "warning": warning_msg,
        }
    except Exception:
        return {
            "has_drifted": False,
            "alignment_score": 1.0,
            "drift_status": "aligned",
            "confidence": 1.0,
            "warning": "",
        }
