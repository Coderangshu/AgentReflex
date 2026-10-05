"""DOM interactive click selector for web/browser navigation using Laya."""

from lib.client import query_laya


def select_element(goal: str, candidates: list[dict]) -> dict:
    """Select the best interactive DOM element to interact with to satisfy the goal.

    candidates: list of dicts with keys like 'id', 'text', 'tag', 'role', 'selector'
    Returns the winning element and confidence.
    """
    if not candidates:
        return {"winner": None, "confidence": 0.0, "reason": "No candidate elements provided"}

    # Build criteria map for choice question
    criteria = {}
    candidate_map = {}
    for idx, cand in enumerate(candidates):
        key = f"opt_{idx}"
        desc = (
            f"Tag: <{cand.get('tag', 'element')}> "
            f"Text: '{cand.get('text', '')}' "
            f"Role: '{cand.get('role', '')}' "
            f"Selector: '{cand.get('selector', cand.get('id', ''))}'"
        )
        criteria[key] = desc
        candidate_map[key] = cand

    criteria["none"] = "None of these elements advance the user's stated goal"

    state = f"Goal: {goal}\nInteractive Elements Count: {len(candidates)}"
    questions = {
        "best_element": {
            "type": "choice",
            "instructions": f"Which interactive DOM element should be clicked or interacted with to achieve: '{goal}'?",
            "criteria": criteria,
        }
    }

    res = query_laya(state, questions)
    choice = res.get("best_element", {}).get("choice", "none")
    conf = res.get("best_element", {}).get("answer_confidence", 0.0)

    winner = candidate_map.get(choice) if choice != "none" else None
    return {
        "winner": winner,
        "choice_key": choice,
        "confidence": conf,
    }
