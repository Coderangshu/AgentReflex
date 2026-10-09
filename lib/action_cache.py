"""Semantic Action Cache ("Learn to Skip") using System 1 similarity matching.

Caches verified idempotent diagnostic tool execution sequences across sessions:
1. Computes workspace state fingerprint (git HEAD commit hash + untracked/dirty status).
2. Matches incoming prompt intent against stored successful trajectories using keyword + Laya semantic score.
3. If intent matches with confidence >= 0.75 and workspace fingerprint matches, returns cached tool sequence.
4. Only caches read-only / diagnostic actions (run test, lint, status check, view file, grep).
   Rejects mutating actions (edits, writes, git commits, destructive commands).
"""

from __future__ import annotations
import os
import json
import sqlite3
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from lib.client import query_laya

CACHE_DIR = Path.home() / ".agentreflex"
CACHE_DB_PATH = CACHE_DIR / "action_cache.db"

# Blacklisted mutations that must never be cached or replayed automatically
MUTATING_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "edit_file",
    "Edit",
    "Write",
    "MultiEdit",
}

MUTATING_COMMAND_PATTERNS = [
    "git commit",
    "git push",
    "git merge",
    "git rebase",
    "git reset",
    "rm ",
    "mv ",
    "cp ",
    "chmod ",
    "chown ",
    "npm install",
    "pip install",
    "yarn add",
    "pnpm add",
]


def _get_db() -> sqlite3.Connection:
    """Initialize SQLite database for action cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_root TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            intent TEXT NOT NULL,
            actions_json TEXT NOT NULL,
            action_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            use_count INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_workspace ON action_cache(workspace_root, state_hash)"
    )
    conn.commit()
    return conn


def get_workspace_state_hash(workspace_root: Optional[str] = None) -> str:
    """Compute lightweight hash of workspace git HEAD and uncommitted changes status."""
    root = Path(workspace_root) if workspace_root else Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        head_commit = proc.stdout.strip() if proc.returncode == 0 else "no-git"

        # Check git status summary for dirty modifications
        proc_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        status_text = proc_status.stdout.strip() if proc_status.returncode == 0 else ""

        combined = f"{head_commit}:{status_text}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "unversioned_state"


def is_idempotent_action(tool_name: str, args: dict) -> bool:
    """Verify an action is safe and idempotent (read-only diagnostic, not mutating)."""
    if tool_name in MUTATING_TOOLS:
        return False

    cmd = (
        args.get("CommandLine")
        or args.get("commandLine")
        or args.get("command")
        or args.get("cmd")
        or ""
    )
    if cmd:
        cmd_lower = cmd.lower()
        for bad in MUTATING_COMMAND_PATTERNS:
            if bad in cmd_lower:
                return False

    return True


def cache_action_sequence(
    intent: str,
    actions: List[Dict[str, Any]],
    workspace_root: Optional[str] = None,
) -> bool:
    """Cache a successful sequence of diagnostic tool actions for a given intent.

    Returns True if successfully cached, False if rejected (e.g. mutating actions).
    """
    if not intent or not actions:
        return False

    # Ensure every single action is idempotent
    for act in actions:
        tool = act.get("tool") or act.get("name") or ""
        args = act.get("args") or {}
        if not is_idempotent_action(tool, args):
            return False

    root_str = str(Path(workspace_root).resolve()) if workspace_root else str(Path.cwd().resolve())
    state_hash = get_workspace_state_hash(root_str)

    try:
        conn = _get_db()
        actions_json = json.dumps(actions)
        conn.execute(
            """
            INSERT INTO action_cache (workspace_root, state_hash, intent, actions_json, action_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (root_str, state_hash, intent.strip(), actions_json, len(actions)),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def lookup_action_cache(
    intent: str,
    workspace_root: Optional[str] = None,
    threshold: float = 0.75,
) -> Optional[dict]:
    """Look up cached action sequence for intent if workspace state matches.

    Returns dict with cached actions and confidence if hit, or None if miss.
    """
    if not intent or not intent.strip():
        return None

    root_str = str(Path(workspace_root).resolve()) if workspace_root else str(Path.cwd().resolve())
    state_hash = get_workspace_state_hash(root_str)

    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, intent, actions_json, action_count, use_count
            FROM action_cache
            WHERE workspace_root = ? AND state_hash = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (root_str, state_hash),
        )
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return None

        clean_intent = intent.strip().lower()

        # 1. Fast exact or substring match check (0ms)
        for row in rows:
            cached_intent = row["intent"].strip().lower()
            if clean_intent == cached_intent:
                # Update use counter
                conn.execute(
                    "UPDATE action_cache SET use_count = use_count + 1 WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                conn.close()
                return {
                    "cache_hit": True,
                    "matched_intent": row["intent"],
                    "match_type": "exact",
                    "confidence": 1.0,
                    "actions": json.loads(row["actions_json"]),
                    "action_count": row["action_count"],
                    "state_hash": state_hash,
                }

        # 2. Semantic matching via Laya System 1 model (<30ms)
        for row in rows:
            cached_intent = row["intent"]
            state = (
                f"Task Intent Comparison:\n"
                f"Candidate Intent A: {cached_intent}\n"
                f"Candidate Intent B: {intent}"
            )
            questions = {
                "is_same_intent": {
                    "type": "noul",
                    "instructions": (
                        "Do Candidate Intent A and Candidate Intent B represent the exact same task action or intention?"
                    ),
                }
            }
            res = query_laya(state, questions)
            score = res.get("is_same_intent", {}).get("noul", 0.0)
            if score >= threshold:
                conn.execute(
                    "UPDATE action_cache SET use_count = use_count + 1 WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                conn.close()
                return {
                    "cache_hit": True,
                    "matched_intent": cached_intent,
                    "match_type": "semantic",
                    "confidence": round(score, 3),
                    "actions": json.loads(row["actions_json"]),
                    "action_count": row["action_count"],
                    "state_hash": state_hash,
                }

        conn.close()
        return None
    except Exception:
        return None


def clear_cache(workspace_root: Optional[str] = None) -> int:
    """Clear action cache for workspace or completely."""
    try:
        conn = _get_db()
        if workspace_root:
            root_str = str(Path(workspace_root).resolve())
            cur = conn.execute(
                "DELETE FROM action_cache WHERE workspace_root = ?", (root_str,)
            )
        else:
            cur = conn.execute("DELETE FROM action_cache")
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception:
        return 0
