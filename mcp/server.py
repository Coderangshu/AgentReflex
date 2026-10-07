#!/usr/bin/env python3
"""Standard-library JSON-RPC 2.0 stdio Model Context Protocol (MCP) server.

Exposes AgentReflex System 1 decision modules as tools for Claude Code and any MCP client:
- reflex_check_violations: Pre-tool guardrail checking forbidden commands / secret leaks
- reflex_grep: Surgical context retrieval (jevgrep) returning strictly relevant lines
- reflex_review_gate: 7-point PR / diff risk audit
- reflex_compact: Scans logs/outputs and flags noise for compaction
- reflex_rank_files: Semantic path relevance reranking
- reflex_judge_coverage: Evaluates code changes for missing test coverage
- reflex_memory_gate: Evaluates whether lessons should be promoted to permanent memory
- reflex_prune_trajectory: Multi-turn history pruner (AgentDiet)
"""

import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.rule_enforcer import check_violations
from lib.surgical_retrieval import surgical_search
from lib.review_gate import review_diff
from lib.compaction import score_message_retention
from lib.file_ranker import rank_files
from lib.judge import judge_test_coverage
from lib.memory_gate import judge_memory_promotion
from lib.trajectory_pruner import prune_trajectory
from lib.warden_governor import evaluate_trajectory_governor
from lib.client import is_daemon_alive

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

TOOLS = [
    {
        "name": "reflex_check_violations",
        "description": "Sub-50ms local safety guardrail. Checks code edits or shell commands against safety rules (secrets, destructive rm -rf, SQL injections) before execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Code patch or shell command to evaluate",
                },
                "rule": {
                    "type": "string",
                    "description": "Optional custom safety rule text. Defaults to standard secrets and destructive actions policy.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "reflex_grep",
        "description": "Surgical code retrieval (jevgrep). Chunks files into 20-30 line windows, scores each locally in ~30ms, and returns only strictly relevant snippets instead of entire files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search intent, question, or symbol to find",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target file or directory paths to inspect",
                },
                "max_snippets": {
                    "type": "integer",
                    "description": "Max snippets to return (default 3)",
                    "default": 3,
                },
            },
            "required": ["query", "paths"],
        },
    },
    {
        "name": "reflex_review_gate",
        "description": "7-point git diff and PR risk gate. Audits code changes across breaking API changes, security injections, secrets leaks, perf regressions, test gaps, unhandled errors, and schema breaks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Git diff or code patch text to audit",
                },
            },
            "required": ["diff"],
        },
    },
    {
        "name": "reflex_compact",
        "description": "Scores terminal output, tool logs, or conversation blocks to identify disposable noise vs critical state for context compaction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Terminal output, log, or conversation text to score",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "reflex_rank_files",
        "description": "Semantically scores and ranks candidate file paths for a given task intent so the agent only reads top matches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Target goal, feature, or bug description",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Candidate file paths to rank",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["intent", "file_paths"],
        },
    },
    {
        "name": "reflex_judge_coverage",
        "description": "Evaluates code changes immediately to determine whether newly introduced logic requires test coverage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Newly written or modified code",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "reflex_memory_gate",
        "description": "Judges post-task findings and lessons to decide whether they should be promoted to permanent project memory or discarded as ephemeral task noise.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lesson": {
                    "type": "string",
                    "description": "Lesson, insight, or bug resolution to evaluate",
                },
                "context": {
                    "type": "string",
                    "description": "Optional task context where the lesson was discovered",
                    "default": "",
                },
            },
            "required": ["lesson"],
        },
    },
    {
        "name": "reflex_prune_trajectory",
        "description": "Multi-turn conversation history pruner (AgentDiet). Analyzes execution steps to identify obsolete error traces resolved by later steps, stripping stale noise while preserving critical active state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "List of conversation step objects with content and type",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_index": {"type": "integer"},
                            "type": {"type": "string"},
                            "tool_name": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "reflex_trajectory_governor",
        "description": "Trajectory velocity and tool budget governor (Warden Governor). Tracks action count, token budget, and neural forward progress velocity to prevent unproductive exploration spirals and runaway spending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_goal": {
                    "type": "string",
                    "description": "User's stated goal or prompt",
                },
                "recent_actions": {
                    "type": "array",
                    "description": "List of recent tool actions with 'tool' and 'args'",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string"},
                            "args": {"type": "object"},
                            "error": {"type": "string"},
                        },
                    },
                },
                "proposed_tool": {
                    "type": "string",
                    "description": "Optional next proposed tool name",
                    "default": "",
                },
                "total_tool_calls": {
                    "type": "integer",
                    "description": "Cumulative tool calls executed so far in session",
                    "default": 0,
                },
                "max_tool_calls": {
                    "type": "integer",
                    "description": "Maximum allowed tool budget (default 25)",
                    "default": 25,
                },
            },
            "required": ["task_goal"],
        },
    },
]


def handle_call_tool(name: str, arguments: dict) -> dict:
    if name in ("reflex_check_violations", "sys1_check_violations"):
        content = arguments.get("content", "")
        rule = arguments.get("rule")
        if rule:
            res = check_violations(content, rule=rule)
        else:
            res = check_violations(content)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_grep", "sys1_grep"):
        query = arguments.get("query", "")
        paths = arguments.get("paths", [])
        max_snippets = arguments.get("max_snippets", 3)
        res = surgical_search(query, paths, max_snippets=max_snippets)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_review_gate", "sys1_review_gate"):
        diff = arguments.get("diff", "")
        res = review_diff(diff)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_compact", "sys1_compact"):
        text = arguments.get("text", "")
        res = score_message_retention(text)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_rank_files", "sys1_rank_files"):
        intent = arguments.get("intent", "")
        fps = arguments.get("file_paths", [])
        top_k = arguments.get("top_k", 5)
        res = rank_files(intent, fps, top_k=top_k)
        formatted = [{"file": f, "score": s} for f, s in res]
        return {"content": [{"type": "text", "text": json.dumps(formatted, indent=2)}]}

    elif name in ("reflex_judge_coverage", "sys1_judge_coverage"):
        content = arguments.get("content", "")
        res = judge_test_coverage(content)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_memory_gate", "sys1_memory_gate"):
        lesson = arguments.get("lesson", "")
        context = arguments.get("context", "")
        res = judge_memory_promotion(lesson, context=context)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_prune_trajectory", "sys1_prune_trajectory"):
        steps = arguments.get("steps", [])
        res = prune_trajectory(steps)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    elif name in ("reflex_trajectory_governor", "sys1_trajectory_governor"):
        task_goal = arguments.get("task_goal", "")
        recent_actions = arguments.get("recent_actions", [])
        proposed_tool = arguments.get("proposed_tool", "")
        total_tool_calls = arguments.get("total_tool_calls", 0)
        max_tool_calls = arguments.get("max_tool_calls", 25)
        res = evaluate_trajectory_governor(
            task_goal=task_goal,
            recent_actions=recent_actions,
            proposed_tool=proposed_tool,
            total_tool_calls=total_tool_calls,
            max_tool_calls=max_tool_calls,
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    else:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
        }


def run_server():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "agentreflex",
                        "version": "0.1.0",
                    },
                },
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            try:
                result = handle_call_tool(tool_name, args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result,
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(e)},
                }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        else:
            if msg_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method {method} not found"},
                }
            else:
                continue

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_server()
