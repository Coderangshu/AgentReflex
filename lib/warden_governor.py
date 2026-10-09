"""Trajectory and Tool Budget Governor (Warden Governor).

Monitors agent trajectory execution, tracking tool call counts, token/cost budgets,
and neural velocity scoring to prevent unproductive exploration spirals and
runaway API spend.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from lib.client import query_laya
from lib.loop_detector import check_agent_loop


# Baseline default budget thresholds per user turn
DEFAULT_MAX_TOOL_CALLS = 60
DEFAULT_MAX_ESTIMATED_TOKENS = 250_000


def score_forward_progress(
    task_goal: str,
    recent_actions: list[dict],
    proposed_tool: str = "",
    proposed_args: dict = None,
) -> dict:
    """Evaluate whether recent actions and the proposed tool advance the goal.

    Uses System 1 neural decision model to classify whether the agent is making
    active forward progress or thrashing/spinning wheels without tangible movement.
    """
    if not task_goal:
        return {
            "progress_score": 1.0,
            "is_stalled": False,
            "status": "normal",
            "reason": "No goal specified",
        }

    # Format recent history for classification
    history_snippets = []
    for idx, act in enumerate(recent_actions[-4:]):
        tool = act.get("tool", "unknown")
        args_str = str(act.get("args", ""))[:80]
        err = act.get("error", "")
        err_str = f" [Error: {err[:50]}]" if err else ""
        history_snippets.append(f"Step {idx+1}: {tool}({args_str}){err_str}")

    if proposed_tool:
        prop_str = str(proposed_args or {})[:80]
        history_snippets.append(f"Next: {proposed_tool}({prop_str})")

    if not history_snippets:
        return {
            "progress_score": 1.0,
            "is_stalled": False,
            "status": "normal",
            "reason": "Starting execution",
        }

    state = (
        f"Goal: {task_goal}\n"
        f"Recent Trajectory & Proposed Action:\n"
        + "\n".join(history_snippets)
    )[:1200]

    questions = {
        "velocity": {
            "type": "choice",
            "instructions": "Evaluate the velocity of the agent toward completing the goal.",
            "criteria": {
                "advancing": "Action sequence directly explores relevant files, executes required edits, or verifies progress toward the goal",
                "spinning_wheels": "Agent is stuck repeating searches, reading unrelated files, or thrashing without getting closer to the solution",
                "deviating": "Agent has drifted away from the original goal into unrelated refactoring or tangents",
            },
        },
        "is_productive": {
            "type": "noul",
            "instructions": "Is this action sequence making meaningful, productive progress toward satisfying the goal?",
        },
    }

    res = query_laya(state, questions)
    velocity_choice = res.get("velocity", {}).get("choice", "advancing")
    velocity_conf = res.get("velocity", {}).get("answer_confidence", 0.0)
    productive_score = res.get("is_productive", {}).get("noul", 0.8)

    is_stalled = (
        velocity_choice in ("spinning_wheels", "deviating") and velocity_conf >= 0.50
    ) or (productive_score < 0.40)

    return {
        "progress_score": productive_score,
        "velocity_status": velocity_choice,
        "confidence": velocity_conf,
        "is_stalled": is_stalled,
        "reason": (
            f"Agent trajectory classified as '{velocity_choice}' ({velocity_conf:.0%} certainty, productive score: {productive_score:.2f})"
            if is_stalled
            else "Trajectory advancing toward goal"
        ),
    }


def evaluate_trajectory_governor(
    task_goal: str,
    recent_actions: list[dict],
    proposed_tool: str = "",
    proposed_args: dict = None,
    total_tool_calls: int = 0,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    estimated_tokens: int = 0,
    max_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> dict:
    """Master governor decision function.

    Combines:
    1. Deterministic and neural loop thrashing detection (`check_agent_loop`).
    2. Tool count and token budget threshold enforcement.
    3. Neural forward progress velocity scoring (`score_forward_progress`).

    Returns dict with `allow_action: bool`, `governor_status`, `budget_usage`, and reason.
    """
    total_calls = total_tool_calls or len(recent_actions)
    if proposed_tool:
        total_calls += 1

    tool_budget_pct = total_calls / max_tool_calls if max_tool_calls > 0 else 0.0
    token_budget_pct = estimated_tokens / max_tokens if max_tokens > 0 else 0.0

    # 1. Check for immediate infinite/stuck loop
    all_actions = list(recent_actions)
    if proposed_tool:
        all_actions.append({"tool": proposed_tool, "args": proposed_args or {}})

    loop_res = check_agent_loop(all_actions)
    if loop_res.get("is_looping", False):
        return {
            "allow_action": False,
            "governor_status": "LOOP_HALT",
            "is_stalled": True,
            "budget_risk": 1.0,
            "tool_budget_pct": round(tool_budget_pct, 2),
            "token_budget_pct": round(token_budget_pct, 2),
            "reason": loop_res.get("reason", "Agent loop detected"),
        }

    # 2. Hard budget overrun checks
    if max_tool_calls > 0 and total_calls >= max_tool_calls:
        return {
            "allow_action": False,
            "governor_status": "TOOL_BUDGET_EXCEEDED",
            "is_stalled": True,
            "budget_risk": 1.0,
            "tool_budget_pct": round(tool_budget_pct, 2),
            "token_budget_pct": round(token_budget_pct, 2),
            "reason": f"Tool budget exhausted ({total_calls}/{max_tool_calls} tool calls in current turn). Request user checkpoint.",
        }

    if max_tokens > 0 and estimated_tokens >= max_tokens:
        return {
            "allow_action": False,
            "governor_status": "TOKEN_BUDGET_EXCEEDED",
            "is_stalled": True,
            "budget_risk": 1.0,
            "tool_budget_pct": round(tool_budget_pct, 2),
            "token_budget_pct": round(token_budget_pct, 2),
            "reason": f"Estimated token budget exhausted ({estimated_tokens:,}/{max_tokens:,} tokens in current turn). Request user checkpoint.",
        }

    # 3. Neural forward progress velocity scoring (only if sufficient actions taken)
    if len(recent_actions) >= 3 and task_goal:
        prog = score_forward_progress(
            task_goal=task_goal,
            recent_actions=recent_actions,
            proposed_tool=proposed_tool,
            proposed_args=proposed_args,
        )
        if prog.get("is_stalled", False):
            # If also approaching budget limit (>60%), intervene firmly
            if tool_budget_pct >= 0.60 or token_budget_pct >= 0.60:
                return {
                    "allow_action": False,
                    "governor_status": "PROGRESS_STALLED",
                    "is_stalled": True,
                    "budget_risk": max(tool_budget_pct, token_budget_pct),
                    "tool_budget_pct": round(tool_budget_pct, 2),
                    "token_budget_pct": round(token_budget_pct, 2),
                    "reason": f"Trajectory stalled without forward progress ({prog.get('reason')}). Intervention required.",
                }
            else:
                return {
                    "allow_action": True,
                    "governor_status": "WARNING_STALL_RISK",
                    "is_stalled": True,
                    "budget_risk": max(tool_budget_pct, token_budget_pct),
                    "tool_budget_pct": round(tool_budget_pct, 2),
                    "token_budget_pct": round(token_budget_pct, 2),
                    "warning": prog.get("reason"),
                    "reason": "Warning: Trajectory velocity low, but within allowable budget.",
                }

    # 4. Normal smooth execution
    return {
        "allow_action": True,
        "governor_status": "ALLOW",
        "is_stalled": False,
        "budget_risk": max(tool_budget_pct, token_budget_pct),
        "tool_budget_pct": round(tool_budget_pct, 2),
        "token_budget_pct": round(token_budget_pct, 2),
        "reason": "Execution within budget and progressing normally.",
    }
