"""Dynamic Model Tier & Reasoning Effort Router using Laya System 1 classification.

Classifies software tasks into an 8-class taxonomy (<35ms on MPS/GPU) and maps them
to the optimal Model Tier (flash, standard, frontier), Reasoning Effort scale:
- AGY (Gemini): low, medium, high
- Claude Code: low, medium, high, xhigh, max
thinking token budgets, and harness-specific model identifiers.
"""

from __future__ import annotations
import os
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

# Provider-specific model matrix
# AGY: Gemini 3.8 Flash, Gemini 3.1 Pro (and flash_lite for tiny subagents)
# Claude Code: Claude 3.5 Haiku, Claude 3.7 Sonnet, Claude 3 Opus
PROVIDER_MODELS = {
    "agy": {
        "flash": {
            "model_name": "Gemini 3.8 Flash",
            "model_id": "gemini-3.8-flash",
            "subagent_model": "flash_lite",
        },
        "standard": {
            "model_name": "Gemini 3.8 Flash",
            "model_id": "gemini-3.8-flash",
            "subagent_model": "flash",
        },
        "frontier": {
            "model_name": "Gemini 3.1 Pro",
            "model_id": "gemini-3.1-pro",
            "subagent_model": "pro",
        },
    },
    "claude": {
        "flash": {
            "model_name": "Claude 3.5 Haiku",
            "model_id": "claude-3-5-haiku-20241022",
            "subagent_model": "haiku",
        },
        "standard": {
            "model_name": "Claude 3.7 Sonnet",
            "model_id": "claude-3-7-sonnet-20250219",
            "subagent_model": "sonnet",
        },
        "frontier": {
            "model_name": "Claude 3.7 Sonnet (Extended Thinking)",
            "model_id": "claude-3-7-sonnet-20250219",
            "subagent_model": "opus",
        },
    },
}

# Harness-specific effort scales
# AGY: low, medium, high
# Claude: low, medium, high, xhigh, max
HARNESS_EFFORT_SCALES = {
    "agy": {
        "doc_typo": "low",
        "ops_script": "low",
        "simple_inspect": "low",
        "routine_crud": "low",
        "review_audit": "medium",
        "complex_refactor": "medium",
        "hard_debug": "high",
        "arch_design": "high",
    },
    "claude": {
        "doc_typo": "low",
        "ops_script": "low",
        "simple_inspect": "low",
        "routine_crud": "medium",
        "review_audit": "high",
        "complex_refactor": "high",
        "hard_debug": "xhigh",
        "arch_design": "max",
    },
}

# Policy mapping table: Task Class -> Model Tier, Thinking Token Budgets, and Descriptions
ROUTING_POLICIES: Dict[str, Dict[str, Any]] = {
    "doc_typo": {
        "model_tier": "flash",
        "max_thinking_tokens": 0,
        "description": "Localized text/comment fix requiring zero reasoning overhead.",
    },
    "ops_script": {
        "model_tier": "flash",
        "max_thinking_tokens": 0,
        "description": "Routine CLI execution or environment command without logic changes.",
    },
    "simple_inspect": {
        "model_tier": "flash",
        "max_thinking_tokens": 1024,
        "description": "Read-only exploration, symbol lookup, or codebase question.",
    },
    "routine_crud": {
        "model_tier": "standard",
        "max_thinking_tokens": 2048,
        "description": "Standard feature implementation, endpoint logic, or unit tests.",
    },
    "review_audit": {
        "model_tier": "standard",
        "max_thinking_tokens": 4096,
        "description": "Risk assessment, regression audit, or code review across modified files.",
    },
    "complex_refactor": {
        "model_tier": "standard",
        "max_thinking_tokens": 8192,
        "description": "Multi-component refactor, schema evolution, or contract adjustments.",
    },
    "hard_debug": {
        "model_tier": "frontier",
        "max_thinking_tokens": 16384,
        "description": "Subtle concurrency defect, memory anomaly, or complex diagnosis.",
    },
    "arch_design": {
        "model_tier": "frontier",
        "max_thinking_tokens": 32768,
        "description": "Net-new subsystem design, cryptographic flow, or architectural contract.",
    },
}

DEFAULT_POLICY = ROUTING_POLICIES["routine_crud"]


def detect_agent_harness(explicit_harness: Optional[str] = None) -> str:
    """Detect if caller is AGY (Antigravity/Gemini) or Claude Code.

    Checks:
    1. Explicit caller argument ('agy' or 'claude').
    2. Environment variables (ANTIGRAVITY_SESSION, CLAUDE_CODE, ANTHROPIC_API_KEY).
    3. Caller process/executable ancestry.
    """
    if explicit_harness:
        h = explicit_harness.lower().strip()
        if "agy" in h or "gemini" in h or "antigravity" in h:
            return "agy"
        if "claude" in h or "anthropic" in h:
            return "claude"

    if os.environ.get("ANTIGRAVITY_APP_DATA_DIR") or os.environ.get("AGY_PROJECT_ROOT"):
        return "agy"
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") or os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude"

    return "agy"


TASK_SKILL_MAP = {
    "review_audit": {
        "skill": "review_gate",
        "tools": ["reflex_review_gate"],
    },
    "simple_inspect": {
        "skill": "fast_explore",
        "tools": ["reflex_fast_explore", "reflex_grep"],
    },
}


def derive_skill(task_class: str, prompt: str) -> tuple[Optional[str], list[str]]:
    """Derive specialized skill recommendation directly from task_class and prompt."""
    p_lower = prompt.lower()
    if any(k in p_lower for k in ("compact", "prune memory", "compress memory", "prune context")):
        return "compact", ["reflex_compact"]
    if any(k in p_lower for k in ("find all", "rank files", "explore files", "locate files", "search files")):
        return "fast_explore", ["reflex_fast_explore", "reflex_grep"]
    mapping = TASK_SKILL_MAP.get(task_class)
    if mapping:
        return mapping["skill"], mapping["tools"]
    return None, []


def route_model(prompt: str, harness: Optional[str] = None) -> dict:
    """Classify prompt into task class and return harness-specific model tier + reasoning effort.

    harness: 'agy' (Gemini: low/medium/high) or 'claude' (Claude: low/medium/high/xhigh/max).
    Auto-detects harness if None.
    """
    active_harness = detect_agent_harness(harness)
    harness_catalog = PROVIDER_MODELS.get(active_harness, PROVIDER_MODELS["agy"])
    effort_scale = HARNESS_EFFORT_SCALES.get(active_harness, HARNESS_EFFORT_SCALES["agy"])

    if not prompt or not prompt.strip():
        base_policy = ROUTING_POLICIES["simple_inspect"]
        tier = base_policy["model_tier"]
        tier_info = harness_catalog.get(tier, harness_catalog["flash"])
        effort = effort_scale.get("simple_inspect", "low")
        return {
            "task_class": "simple_inspect",
            "confidence": 1.0,
            "harness": active_harness,
            "reasoning_effort": effort,
            **base_policy,
            "recommended_model": tier_info["model_name"],
            "model_id": tier_info["model_id"],
            "subagent_model": tier_info["subagent_model"],
            "recommended_skill": None,
            "skill_tools": [],
            "summary_tag": (
                f"[AgentReflex Router ({active_harness.upper()}): class=simple_inspect | "
                f"tier={tier} ({tier_info['model_name']}) | effort={effort}]"
            ),
        }

    questions = {
        "task_class": {
            "type": "choice",
            "instructions": "Classify the software task into one category.",
            "criteria": TASK_CLASS_CRITERIA,
        }
    }

    try:
        res = query_laya(prompt[:1200], questions, timeout=10.0)
        tc_res = res.get("task_class", {})
        task_class = tc_res.get("choice", "routine_crud")
        probs = tc_res.get("probabilities", {})
        conf = round(probs.get(task_class, tc_res.get("answer_confidence", 0.5)), 3)

        base_policy = ROUTING_POLICIES.get(task_class, DEFAULT_POLICY)
        tier = base_policy["model_tier"]
        tier_info = harness_catalog.get(tier, harness_catalog["standard"])
        effort = effort_scale.get(task_class, "medium")

        rec_skill, skill_tools = derive_skill(task_class, prompt)

        summary_tag = (
            f"[AgentReflex Router ({active_harness.upper()}): class={task_class} | "
            f"tier={tier} ({tier_info['model_name']}) | effort={effort} | "
            f"thinking={base_policy['max_thinking_tokens']}]"
        )

        return {
            "task_class": task_class,
            "confidence": conf,
            "harness": active_harness,
            "reasoning_effort": effort,
            **base_policy,
            "recommended_model": tier_info["model_name"],
            "model_id": tier_info["model_id"],
            "subagent_model": tier_info["subagent_model"],
            "recommended_skill": rec_skill,
            "skill_tools": skill_tools,
            "summary_tag": summary_tag,
        }
    except Exception:
        tier_info = harness_catalog["standard"]
        effort = effort_scale.get("routine_crud", "low")
        return {
            "task_class": "routine_crud",
            "confidence": 0.5,
            "harness": active_harness,
            "reasoning_effort": effort,
            **DEFAULT_POLICY,
            "recommended_model": tier_info["model_name"],
            "model_id": tier_info["model_id"],
            "subagent_model": tier_info["subagent_model"],
            "recommended_skill": None,
            "skill_tools": [],
            "summary_tag": (
                f"[AgentReflex Router ({active_harness.upper()}): class=routine_crud | "
                f"tier=standard ({tier_info['model_name']}) | effort={effort}]"
            ),
        }
