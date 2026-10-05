"""7-point PR and diff risk gate using Laya."""

from lib.client import query_laya

GATE_CRITERIA = {
    "breaking_api": "Does this diff introduce breaking changes or backwards-incompatible API changes?",
    "security_injection": "Does this diff introduce security vulnerabilities (e.g. injection, unsafe shell, bypasses)?",
    "secrets_leak": "Does this diff introduce hardcoded API keys, secrets, tokens, or credentials?",
    "perf_regression": "Does this diff introduce performance regressions, heavy unindexed loops, or memory leaks?",
    "test_gap": "Does this diff add significant business logic without accompanying test assertions?",
    "unhandled_exceptions": "Does this diff leave failure paths, network errors, or exceptions unhandled?",
    "contract_violation": "Does this diff violate data contracts, schemas, or serialization formats?",
}


def review_diff(diff_text: str, risk_threshold: float = 0.70) -> dict:
    """Evaluate a git diff or code patch against 7 critical risk dimensions.

    Returns dict with scores per dimension, overall risk score, and pass/fail gate.
    """
    questions = {
        key: {
            "type": "noul",
            "instructions": instruction,
        }
        for key, instruction in GATE_CRITERIA.items()
    }

    # Query Laya daemon
    res = query_laya(diff_text, questions)

    scores = {}
    flagged = []
    max_score = 0.0

    for key in GATE_CRITERIA:
        score = res.get(key, {}).get("noul", 0.0)
        scores[key] = score
        if score >= risk_threshold:
            flagged.append((key, score))
        if score > max_score:
            max_score = score

    passed = len(flagged) == 0

    return {
        "passed": passed,
        "max_risk_score": max_score,
        "flagged_risks": flagged,
        "dimension_scores": scores,
        "recommendation": "APPROVE" if passed else "REJECT / REQUIRE CHANGES",
    }
