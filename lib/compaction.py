"""Faster context compaction and pruning decision engine using Laya."""

import re
from lib.client import query_laya

# Deterministic fast patterns for obvious progress bars and transfer logs
FAST_NOISE_PATTERNS = [
    re.compile(r"\[\s*=+>\s*\]"),                          # [=====>   ]
    re.compile(r"\b\d+%\b.*(?:kB/s|MB/s|it/s)"),            # 50% 1200kB/s
    re.compile(r"Fetching \d+ files:\s*\d+%", re.IGNORECASE),
    re.compile(r"Downloading bytes:\s*\|", re.IGNORECASE),
    re.compile(r"Reconstruction complete:\s*\|", re.IGNORECASE),
]


def score_message_retention(message_content: str) -> dict:
    """Evaluate whether a message or tool output should be retained in working memory.

    Combines deterministic heuristic filters for fast progress bars with
    Laya's neural decision model for nuanced log classification.
    """
    if not message_content or not message_content.strip():
        return {"keep_score": 0.0, "noise_score": 1.0, "should_prune": True}

    # Fast heuristic check for terminal transfer / progress bar spew
    for pat in FAST_NOISE_PATTERNS:
        if pat.search(message_content):
            return {"keep_score": 0.05, "noise_score": 0.95, "should_prune": True}

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
        "should_prune": (noise_prob > 0.65 and keep_prob < 0.35) or (noise_prob >= 0.80),
    }


def should_prune(text: str, noise_threshold: float = 0.65) -> bool:
    """Convenience boolean helper for compaction pipelines."""
    scored = score_message_retention(text)
    return scored["should_prune"] or (scored["noise_score"] >= noise_threshold)
