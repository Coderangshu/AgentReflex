"""Speculative Decision Fan-Out and Prompt Triage using Laya System 1 engine.

Evaluates user prompt or code diff across multiple tactical dimensions simultaneously
in a single forward pass (<45ms on GPU):
1. Task type (bug, feature, refactor, investigation)
2. Database / schema migration need
3. Unit or integration test requirement
4. Authentication / security sensitivity
5. Breaking change / API contract risk
6. Overall risk tier (low, medium, high)
"""

from __future__ import annotations
from typing import Dict, Any, List
from lib.client import query_laya

TRIAGE_QUESTIONS = {
    "task_type": {
        "type": "choice",
        "instructions": "Classify the primary intent of this user task.",
        "criteria": {
            "bug_fix": "Fixing a bug, error, broken logic, crash, or unexpected behavior",
            "feature": "Implementing a new feature, endpoint, UI element, or capability",
            "refactor": "Refactoring existing code structure without changing business behavior",
            "exploration": "Exploring codebase, reading files, answering questions, or diagnostics",
        },
    },
    "needs_migration": {
        "type": "noul",
        "instructions": "Does this task or diff involve database schemas, SQL migrations, or database tables?",
    },
    "needs_tests": {
        "type": "noul",
        "instructions": "Does this task or change introduce new business logic that requires unit/integration tests?",
    },
    "touches_auth": {
        "type": "noul",
        "instructions": "Does this task involve authentication, authorization, passwords, tokens, or security credentials?",
    },
    "is_breaking": {
        "type": "noul",
        "instructions": "Is this a breaking API change, schema change, or backwards-incompatible modification?",
    },
    "risk_level": {
        "type": "choice",
        "instructions": "What is the overall architectural and operational risk level of this request?",
        "criteria": {
            "low": "Routine documentation, typo fix, styling, logging, or non-destructive read",
            "medium": "Standard single-component logic change, unit test, or isolated feature",
            "high": "Core architecture, authentication, database migrations, or payments/security",
        },
    },
}


def triage_task(prompt_or_diff: str, threshold: float = 0.65) -> dict:
    """Triage a prompt or code diff across 6 speculative tactical dimensions in one pass.

    Returns dict with extracted boolean flags, classified categories, and prompt tags.
    """
    if not prompt_or_diff or not prompt_or_diff.strip():
        return {
            "task_type": "exploration",
            "needs_migration": False,
            "needs_tests": False,
            "touches_auth": False,
            "is_breaking": False,
            "risk_level": "low",
            "tags": [],
            "summary_tag": "[AgentReflex Triage: exploration | risk: low]",
        }

    res = query_laya(prompt_or_diff[:1200], TRIAGE_QUESTIONS)

    task_type = res.get("task_type", {}).get("choice", "feature")
    needs_migration = res.get("needs_migration", {}).get("noul", 0.0) >= threshold
    needs_tests = res.get("needs_tests", {}).get("noul", 0.0) >= threshold
    touches_auth = res.get("touches_auth", {}).get("noul", 0.0) >= threshold
    is_breaking = res.get("is_breaking", {}).get("noul", 0.0) >= threshold
    risk_level = res.get("risk_level", {}).get("choice", "medium")

    tags = [f"type:{task_type}", f"risk:{risk_level}"]
    if needs_migration:
        tags.append("db:migration")
    if touches_auth:
        tags.append("security:auth")
    if is_breaking:
        tags.append("api:breaking")
    if needs_tests:
        tags.append("action:tests_required")

    summary_tag = f"[AgentReflex Triage: {' | '.join(tags)}]"

    return {
        "task_type": task_type,
        "needs_migration": needs_migration,
        "needs_tests": needs_tests,
        "touches_auth": touches_auth,
        "is_breaking": is_breaking,
        "risk_level": risk_level,
        "tags": tags,
        "summary_tag": summary_tag,
        "scores": {
            "migration_score": round(res.get("needs_migration", {}).get("noul", 0.0), 3),
            "tests_score": round(res.get("needs_tests", {}).get("noul", 0.0), 3),
            "auth_score": round(res.get("touches_auth", {}).get("noul", 0.0), 3),
            "breaking_score": round(res.get("is_breaking", {}).get("noul", 0.0), 3),
        },
    }


def format_triage_tags(triage_result: dict) -> str:
    """Format triage dict into an injectable prompt tag string."""
    if not triage_result:
        return ""
    return triage_result.get("summary_tag", "")

