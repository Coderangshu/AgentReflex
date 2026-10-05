"""Intent and skill selector using Laya."""

from lib.client import query_laya


def pick_skill(prompt: str) -> dict:
    """Determine which specialized agent skill best fits the user's prompt."""
    questions = {
        "route": {
            "type": "choice",
            "instructions": "Determine what specialized agent skill is best suited for this prompt.",
            "criteria": {
                "fast_explore": "Finding, exploring, indexing, or ranking files across the codebase",
                "review_gate": "Reviewing PR, git diffs, evaluating code risk, safety checks",
                "compact": "Compacting conversation memory, pruning noisy logs, summarizing context",
                "none": "General conversation, routine edits, simple questions, or unrelated requests",
            },
        }
    }
    res = query_laya(prompt, questions)
    choice = res.get("route", {}).get("choice", "none")
    conf = res.get("route", {}).get("answer_confidence", 0.0)

    return {
        "skill": choice,
        "confidence": conf,
        "is_recommended": choice != "none" and conf > 0.65,
    }
