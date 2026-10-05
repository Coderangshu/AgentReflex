"""Memory promotion gate using Laya System 1 decision engine.

Judges completed agent execution traces, corrections, or lessons learned to decide
whether a finding contains a reusable, durable lesson worth promoting to permanent
memory or if it is just task-specific ephemeral noise.
"""

from lib.client import query_laya


def judge_memory_promotion(lesson_text: str, context: str = "") -> dict:
    """Evaluate whether a lesson or correction should be promoted to permanent memory.

    Returns dict with promotion decision, score, confidence, and target category.
    """
    state = f"Context: {context}\nLesson/Finding: {lesson_text}"[:1200]

    questions = {
        "should_promote": {
            "type": "noul",
            "instructions": (
                "Is this finding/lesson a reusable architectural pattern, durable coding convention, "
                "or recurring bug fix that should be saved to permanent memory (NOT one-off disposable task noise)?"
            ),
        },
        "category": {
            "type": "choice",
            "instructions": "What category of permanent memory does this finding belong to?",
            "criteria": {
                "rule": "Coding style, forbidden pattern, or strict project policy",
                "architecture": "System architecture, component dependency, or data flow knowledge",
                "gotcha": "Subtle bug, environment quirk, or library gotcha with resolution",
                "ephemeral": "One-off task progress, disposable debug log, or transient scratchpad detail",
            },
        },
    }

    res = query_laya(state, questions)

    promote_score = res.get("should_promote", {}).get("noul", 0.0)
    category = res.get("category", {}).get("choice", "ephemeral")
    cat_conf = res.get("category", {}).get("answer_confidence", 0.0)

    # Must have high promote score and not classified as ephemeral
    should_promote = (promote_score >= 0.70) and (category != "ephemeral")

    return {
        "should_promote": should_promote,
        "promotion_score": promote_score,
        "category": category,
        "category_confidence": cat_conf,
        "recommendation": "PROMOTE_TO_MEMORY" if should_promote else "DISCARD_EPHEMERAL",
    }
