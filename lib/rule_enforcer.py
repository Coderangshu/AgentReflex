"""Code and command policy guardrail using Laya."""

from lib.client import query_laya

DEFAULT_RULE = (
    "Never hardcode plaintext authentication secrets or private API credentials, "
    "and never execute destructive filesystem deletion like rm -rf / or dropping production database servers."
)


def check_violations(
    content: str, rule: str = DEFAULT_RULE, threshold: float = 0.80
) -> dict:

    """Evaluate whether code, patch, or shell command violates safety rules.

    Returns dict with violation status, confidence/score, and rule.
    """
    if not content or not content.strip():
        return {
            "violates": False,
            "score": 0.0,
            "rule": rule,
        }

    questions = {
        "violates": {
            "type": "noul",
            "instructions": f"Does this code edit or command violate: '{rule}'?",
        }
    }

    res = query_laya(content, questions)
    score = res.get("violates", {}).get("noul", 0.0)

    return {
        "violates": score >= threshold,
        "score": score,
        "rule": rule,
        "reason": f"Laya rule guardrail triggered ({score:.0%} certainty): {rule}"
        if score >= threshold
        else "",
    }
