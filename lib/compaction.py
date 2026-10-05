"""Faster context compaction and pruning decision engine using Laya."""

from lib.client import query_laya


def score_message_retention(message_content: str) -> dict:
    """Evaluate whether a message or tool output should be retained in working memory.

    Returns dict with decision and confidence.
    """
    questions = {
        "keep": {
            "type": "noul",
            "instructions": "Does this message contain critical user instructions, active code, unhandled errors, or key state that MUST be retained in memory?",
        },
        "is_noise": {
            "type": "noul",
            "instructions": "Is this text purely verbose logging, progress noise, repeated listings, or disposable output?",
        },
    }
    res = query_laya(message_content, questions)
    keep_prob = res.get("keep", {}).get("noul", 0.5)
    noise_prob = res.get("is_noise", {}).get("noul", 0.5)

    return {
        "keep_score": keep_prob,
        "noise_score": noise_prob,
        "should_prune": noise_prob > 0.65 and keep_prob < 0.35,
    }


def should_prune(text: str, noise_threshold: float = 0.65) -> bool:
    """Convenience boolean helper for compaction pipelines."""
    scored = score_message_retention(text)
    return scored["should_prune"] or (scored["noise_score"] >= noise_threshold)
