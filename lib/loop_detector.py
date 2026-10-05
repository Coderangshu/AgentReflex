"""Lightweight judge for detecting agent loops and evaluating task outputs using Laya."""

from lib.client import query_laya


def check_agent_loop(recent_actions: list[dict], threshold: float = 0.70) -> dict:
    """Analyze recent agent actions to detect repetitive loops or lack of progress.

    recent_actions: list of dicts with 'tool', 'args', 'error' (up to last 5 actions)
    """
    if not recent_actions or len(recent_actions) < 2:
        return {"is_looping": False, "loop_score": 0.0, "reason": "Insufficient history"}

    # Heuristic quick check for identical consecutive actions
    identical_count = 1
    last_act = recent_actions[-1]
    for prev in reversed(recent_actions[:-1]):
        if (
            prev.get("tool") == last_act.get("tool")
            and str(prev.get("args")) == str(last_act.get("args"))
        ):
            identical_count += 1
        else:
            break

    if identical_count >= 3:
        return {
            "is_looping": True,
            "loop_score": 1.0,
            "reason": f"Agent repeated identical tool call '{last_act.get('tool')}' {identical_count} times in a row.",
        }

    # Semantic evaluation using Laya
    history_summary = []
    for idx, act in enumerate(recent_actions[-4:]):
        tool = act.get("tool", "unknown")
        args_summary = str(act.get("args", ""))[:80]
        err = act.get("error", "")
        err_str = f" [Error: {err[:50]}]" if err else ""
        history_summary.append(f"Step {idx+1}: {tool}({args_summary}){err_str}")

    state = "Recent Actions:\n" + "\n".join(history_summary)
    questions = {
        "is_stuck": {
            "type": "noul",
            "instructions": (
                "Is the agent stuck in an unproductive loop, thrashing on errors, "
                "or repeating equivalent failed actions without progress?"
            ),
        }
    }

    res = query_laya(state, questions)
    score = res.get("is_stuck", {}).get("noul", 0.0)

    is_looping = score >= threshold
    return {
        "is_looping": is_looping,
        "loop_score": score,
        "reason": f"Laya loop detector triggered ({score:.0%} certainty): Agent appears stuck without forward progress."
        if is_looping
        else "Normal execution flow",
    }


def evaluate_task_output(task_goal: str, output_text: str, rubric: str = None) -> dict:
    """Evaluate whether an agent/tool output meets task criteria and satisfies the goal."""
    if not rubric:
        rubric = "Output directly answers the request, contains no unhandled errors, and completes the stated goal."

    state = f"Goal: {task_goal}\nRubric: {rubric}\nOutput: {output_text}"[:1200]
    questions = {
        "meets_criteria": {
            "type": "noul",
            "instructions": f"Does this output satisfy the stated goal according to the rubric: '{rubric}'?",
        },
        "has_unhandled_failure": {
            "type": "noul",
            "instructions": "Does this output contain unhandled failures, stack traces, or unfinished work?",
        },
    }

    res = query_laya(state, questions)
    meets_score = res.get("meets_criteria", {}).get("noul", 0.5)
    failure_score = res.get("has_unhandled_failure", {}).get("noul", 0.0)

    satisfied = (meets_score >= 0.70) and (failure_score < 0.40)

    return {
        "satisfied": satisfied,
        "quality_score": meets_score,
        "failure_score": failure_score,
        "recommendation": "ACCEPT_OUTPUT" if satisfied else "REQUIRE_REVISION",
    }
