"""Automated Stop / Done Validator using Laya System 1 decision engine.

Validates whether an agent's task is genuinely complete before allowing it to stop:
1. Prevents premature victory (declaring complete while broken tests, unhandled errors,
   or missing requirements remain).
2. Prevents over-iteration (continuing speculative edits after objectives are already met).
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from lib.client import query_laya


def validate_task_completion(
    task_goal: str,
    final_output: str = "",
    git_diff: str = "",
    test_output: str = "",
) -> dict:
    """Validate whether an agent has fully completed its assigned task.

    Evaluates:
    - task_goal: Stated user prompt or objective.
    - final_output: Concluding message or explanation proposed by the agent.
    - git_diff: Code modifications made during the task.
    - test_output: Test suite, build, or linter output.

    Returns dict with:
    - is_complete: bool
    - confidence: float
    - status: 'TASK_COMPLETE' | 'NEEDS_MORE_WORK'
    - missing_criteria: list of identified gaps
    - reason: explanation of decision
    """
    if not task_goal:
        return {
            "is_complete": True,
            "confidence": 1.0,
            "status": "TASK_COMPLETE",
            "missing_criteria": [],
            "reason": "No explicit goal provided",
        }

    # Build evaluation payload
    evidence_parts = [f"User Goal: {task_goal}"]
    if git_diff:
        evidence_parts.append(f"Code Changes (diff):\n{git_diff[:800]}")
    if test_output:
        evidence_parts.append(f"Test / Verification Output:\n{test_output[:400]}")
    if final_output:
        evidence_parts.append(f"Agent Summary:\n{final_output[:400]}")

    state = "\n\n".join(evidence_parts)[:1200]

    questions = {
        "status": {
            "type": "choice",
            "instructions": "Determine if the user's goal has been completely satisfied based on the code changes and test output.",
            "criteria": {
                "task_complete": "All user requirements are implemented, code changes address the goal, and no tests or errors are failing",
                "needs_more_work": "Core requirements are still missing, broken syntax remains, or tests are failing",
                "unrelated_or_blocked": "The task was blocked or changes do not match what the user requested",
            },
        },
        "has_failing_tests": {
            "type": "noul",
            "instructions": "Are there any failing tests, build errors, or unhandled exceptions in the output?",
        },
        "satisfies_goal": {
            "type": "noul",
            "instructions": "Do the provided code changes and output directly fulfill the user's stated goal?",
        },
    }

    res = query_laya(state, questions)

    status_choice = res.get("status", {}).get("choice", "task_complete")
    status_conf = res.get("status", {}).get("answer_confidence", 0.0)
    has_failures = res.get("has_failing_tests", {}).get("noul", 0.0)
    satisfies_goal = res.get("satisfies_goal", {}).get("noul", 0.8)

    missing = []
    if has_failures >= 0.60:
        missing.append("Failing tests or unresolved errors detected")
    if satisfies_goal < 0.40:
        missing.append("Changes do not adequately fulfill the stated user goal")
    if status_choice in ("needs_more_work", "unrelated_or_blocked") and status_conf >= 0.55:
        missing.append(f"Classified as '{status_choice}' ({status_conf:.0%} certainty)")

    is_complete = len(missing) == 0 and (satisfies_goal >= 0.50 or status_choice == "task_complete")

    status_str = "TASK_COMPLETE" if is_complete else "NEEDS_MORE_WORK"
    reason = (
        "Task objectives satisfied and verified."
        if is_complete
        else f"Task incomplete: {'; '.join(missing)}."
    )

    return {
        "is_complete": is_complete,
        "confidence": round(status_conf, 2),
        "status": status_str,
        "satisfaction_score": round(satisfies_goal, 2),
        "failure_risk": round(has_failures, 2),
        "missing_criteria": missing,
        "reason": reason,
    }
