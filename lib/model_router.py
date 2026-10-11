"""Dynamic Model Tier & Reasoning Effort Router using Laya System 1 classification.

Classifies software tasks into an 8-class taxonomy (<35ms on MPS/GPU) and maps them
to the optimal Model Tier (flash, standard, frontier), Reasoning Effort (none, low, medium, high),
thinking token budgets, and target subagent tiers.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from lib.client import query_laya

TASK_CLASS_CRITERIA = {
    "doc_typo": "Documentation, comments, typos, markdown, or formatting",
    "ops_script": "Shell commands, builds, installs, deployments, package configs, or git operations",
    "simple_inspect": "Explaining existing code, reading files, answering codebase questions, or diagnostics",
    "routine_crud": "Standard feature logic, API endpoints, UI components, or standard unit tests",
    "review_audit": "Reviewing diffs, PR risk analysis, security audits, or regression checks",
    "complex_refactor": "Multi-file structural changes, DB migrations, or broad API contract renames",
    "hard_debug": "Subtle concurrency bugs, race conditions, memory leaks, or tricky crashes",
    "arch_design": "New architectural subsystems, cryptographic protocols, or complete system design",
}

# Policy mapping table: Task Class -> Model Tier, Thinking Effort, Subagent, and Limits
ROUTING_POLICIES: Dict[str, Dict[str, Any]] = {
    "doc_typo": {
        "model_tier": "flash",
        "reasoning_effort": "none",
        "max_thinking_tokens": 0,
        "recommended_model": "claude-3-5-haiku-20241022",
        "subagent_model": "flash_lite",
        "description": "Localized text/comment fix requiring zero reasoning overhead.",
    },
    "ops_script": {
        "model_tier": "flash",
        "reasoning_effort": "none",
        "max_thinking_tokens": 0,
        "recommended_model": "claude-3-5-haiku-20241022",
        "subagent_model": "flash",
        "description": "Routine CLI execution or environment command without logic changes.",
    },
    "simple_inspect": {
        "model_tier": "flash",
        "reasoning_effort": "low",
        "max_thinking_tokens": 1024,
        "recommended_model": "claude-3-5-haiku-20241022",
        "subagent_model": "flash",
        "description": "Read-only exploration, symbol lookup, or codebase question.",
    },
    "routine_crud": {
        "model_tier": "standard",
        "reasoning_effort": "low",
        "max_thinking_tokens": 2048,
        "recommended_model": "claude-3-7-sonnet-20250219",
        "subagent_model": "flash",
        "description": "Standard feature implementation, endpoint logic, or unit tests.",
    },
    "review_audit": {
        "model_tier": "standard",
        "reasoning_effort": "medium",
        "max_thinking_tokens": 4096,
        "recommended_model": "claude-3-7-sonnet-20250219",
        "subagent_model": "pro",
        "description": "Risk assessment, regression audit, or code review across modified files.",
    },
    "complex_refactor": {
        "model_tier": "standard",
        "reasoning_effort": "medium",
        "max_thinking_tokens": 4096,
        "recommended_model": "claude-3-7-sonnet-20250219",
        "subagent_model": "pro",
        "description": "Multi-component refactor, schema evolution, or contract adjustments.",
    },
    "hard_debug": {
        "model_tier": "frontier",
        "reasoning_effort": "high",
        "max_thinking_tokens": 8192,
        "recommended_model": "claude-3-7-sonnet-20250219",
        "subagent_model": "pro",
        "description": "Subtle concurrency defect, memory anomaly, or complex diagnosis.",
    },
    "arch_design": {
        "model_tier": "frontier",
        "reasoning_effort": "high",
        "max_thinking_tokens": 16384,
        "recommended_model": "claude-3-7-sonnet-20250219",
        "subagent_model": "pro",
        "description": "Net-new subsystem design, cryptographic flow, or architectural contract.",
    },
}

DEFAULT_POLICY = ROUTING_POLICIES["routine_crud"]


def route_model(prompt: str) -> dict:
    """Classify prompt into task class and return model tier + reasoning effort policy.

    Evaluates prompt locally using Laya in ~30ms. Fails open to 'routine_crud' on error.
    """
    if not prompt or not prompt.strip():
        return {
            "task_class": "simple_inspect",
            "confidence": 1.0,
            **ROUTING_POLICIES["simple_inspect"],
            "summary_tag": "[AgentReflex Router: class=simple_inspect | tier=flash | effort=low]",
        }

    questions = {
        "task_class": {
            "type": "choice",
            "instructions": "Classify the software task into one category.",
            "criteria": TASK_CLASS_CRITERIA,
        }
    }

    try:
        res = query_laya(prompt[:1200], questions, timeout=5.0)
        tc_res = res.get("task_class", {})
        task_class = tc_res.get("choice", "routine_crud")
        conf = round(tc_res.get("answer_confidence", 0.5), 3)

        policy = ROUTING_POLICIES.get(task_class, DEFAULT_POLICY)

        summary_tag = (
            f"[AgentReflex Router: class={task_class} | tier={policy['model_tier']} | "
            f"effort={policy['reasoning_effort']} | thinking={policy['max_thinking_tokens']}]"
        )

        return {
            "task_class": task_class,
            "confidence": conf,
            **policy,
            "summary_tag": summary_tag,
        }
    except Exception:
        return {
            "task_class": "routine_crud",
            "confidence": 0.5,
            **DEFAULT_POLICY,
            "summary_tag": "[AgentReflex Router: class=routine_crud | tier=standard | effort=low]",
        }
