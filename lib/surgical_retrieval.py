"""Surgical context retrieval engine (jevgrep) using Laya.

Chunks code files into windows or symbol blocks, scores each locally in ~30ms,
and extracts only the strictly necessary lines to minimize LLM token consumption.
"""

from __future__ import annotations
from typing import Union, List, Dict
from pathlib import Path
from lib.client import query_laya


def chunk_file(file_path: Path, window_lines: int = 30, overlap: int = 5) -> list[dict]:
    """Split a file into overlapping line windows with metadata."""
    if not file_path.exists() or file_path.is_dir():
        return []

    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    if not lines:
        return []

    chunks = []
    total = len(lines)
    step = max(1, window_lines - overlap)

    for start in range(0, total, step):
        end = min(total, start + window_lines)
        chunk_text = "\n".join(lines[start:end])
        chunks.append({
            "file": str(file_path),
            "start_line": start + 1,
            "end_line": end,
            "content": chunk_text,
        })
        if end >= total:
            break

    return chunks


def score_snippet(query: str, snippet: dict) -> float:
    """Score how relevant a specific snippet is to the target query."""
    state = f"Query: {query}\nFile: {snippet['file']}:{snippet['start_line']}-{snippet['end_line']}\n\n{snippet['content']}"[:1200]
    questions = {
        "relevant": {
            "type": "noul",
            "instructions": f"Does this code snippet directly answer, define, or implement logic for: '{query}'?",
        }
    }
    res = query_laya(state, questions)
    return res.get("relevant", {}).get("noul", 0.0)


def surgical_search(
    query: str,
    target_paths: list[str | Path],
    max_snippets: int = 3,
    window_lines: int = 30,
) -> list[dict]:
    """Perform surgical search across target files, returning top scored code snippets."""
    all_chunks = []
    for p in target_paths:
        path_obj = Path(p)
        if path_obj.is_file():
            all_chunks.extend(chunk_file(path_obj, window_lines=window_lines))
        elif path_obj.is_dir():
            valid_exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".sql", ".rs", ".go"}
            for sub_file in path_obj.rglob("*"):
                if (
                    sub_file.is_file()
                    and sub_file.suffix in valid_exts
                    and "node_modules" not in sub_file.parts
                    and ".git" not in sub_file.parts
                    and ".venv" not in sub_file.parts
                ):
                    all_chunks.extend(chunk_file(sub_file, window_lines=window_lines))

    scored = []
    for chunk in all_chunks:
        score = score_snippet(query, chunk)
        if score > 0.30:  # Base filter
            scored.append({
                "file": chunk["file"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "score": round(score, 4),
                "snippet": chunk["content"],
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:max_snippets]
