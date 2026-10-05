"""Explore and search file scorer using Laya."""

from lib.client import query_laya


def score_file_path(intent: str, file_path: str) -> float:
    """Score how relevant a single file path is to the target search intent."""
    state = f"Target Intent: {intent}\nCandidate File: {file_path}"
    questions = {
        "relevant": {
            "type": "noul",
            "instructions": f"Is candidate file '{file_path}' highly relevant to accomplishing: '{intent}'?",
        }
    }
    res = query_laya(state, questions)
    return res.get("relevant", {}).get("noul", 0.0)


def rank_files(
    intent: str, file_paths: list[str], top_k: int = 5
) -> list[tuple[str, float]]:
    """Rank a list of file paths by relevance to the given intent.

    Returns a sorted list of (file_path, score) tuples in descending order.
    """
    scored = []
    for fp in file_paths:
        cleaned = fp.strip()
        if not cleaned:
            continue
        score = score_file_path(intent, cleaned)
        scored.append((cleaned, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
