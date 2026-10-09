#!/usr/bin/env python3
"""End-to-end simulation test runner for sys1-helper."""

import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PYTHON = sys.executable

GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_status(name: str, passed: bool, detail: str = ""):
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"[{status}] {BOLD}{name}{RESET}")
    if detail:
        print(f"       -> {detail}")


def run_cmd(cmd_list, stdin_payload=None):
    proc = subprocess.run(
        cmd_list,
        input=stdin_payload,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    print(f"{BOLD}=== AgentReflex End-to-End Simulation ==={RESET}\n")

    # 1. Daemon Health Check
    _, stdout, _ = run_cmd(["curl", "-s", "http://127.0.0.1:8765/health"])
    try:
        health = json.loads(stdout)
        is_healthy = health.get("status") == "ok"
        dev = health.get("device", "unknown")
        print_status("1. Daemon Connectivity", is_healthy, f"device: {dev}")
    except Exception:
        print_status("1. Daemon Connectivity", False, "Daemon not running on :8765")
        return

    # 2. PreToolUse Guardrail - Simulate Dangerous Action (Should BLOCK)
    payload_bad = json.dumps({
        "toolCall": {
            "name": "write_file",
            "args": {"content": "OPENAI_API_KEY = 'sk-proj-1234567890abcdef1234567890'"}
        }
    })
    _, out_bad, _ = run_cmd([PYTHON, "hooks/pre_tool_enforcer.py"], stdin_payload=payload_bad)
    try:
        res_bad = json.loads(out_bad)
        blocked = res_bad.get("decision") == "deny" and not res_bad.get("allow_tool")
        reason = res_bad.get("reason", "")[:70]
        print_status("2. Guardrail Block Dangerous Edit", blocked, f"reason: {reason}")
    except Exception as e:
        print_status("2. Guardrail Block Dangerous Edit", False, str(e))

    # 3. PreToolUse Guardrail - Simulate Safe Action (Should ALLOW)
    payload_good = json.dumps({
        "toolCall": {
            "name": "write_file",
            "args": {"content": "def calculate_total(items): return sum(items)"}
        }
    })
    _, out_good, _ = run_cmd([PYTHON, "hooks/pre_tool_enforcer.py"], stdin_payload=payload_good)
    try:
        res_good = json.loads(out_good)
        allowed = res_good.get("decision") == "allow" and res_good.get("allow_tool")
        print_status("3. Guardrail Allow Safe Edit", allowed, "passed cleanly")
    except Exception as e:
        print_status("3. Guardrail Allow Safe Edit", False, str(e))

    # 4. PreInvocation Hook - Simulate Skill Routing
    payload_inv = json.dumps({"prompt": "Can you review git diff changes and check for security bugs?"})
    _, out_inv, _ = run_cmd([PYTHON, "hooks/pre_invocation.py"], stdin_payload=payload_inv)
    try:
        res_inv = json.loads(out_inv)
        context = res_inv.get("additionalContext", "")
        routed = "/review_gate" in context or "review" in context.lower()
        print_status("4. Intent / Skill Router", routed, f"routed: {context}")
    except Exception as e:
        print_status("4. Intent / Skill Router", False, str(e))

    # 5. Surgical Context Retrieval (jevgrep)
    code, out_grep, _ = run_cmd([PYTHON, "skills/reflex-grep/run.py", "predict lock", "daemon/server.py"])
    try:
        res_grep = json.loads(out_grep)
        matches = res_grep.get("matches_count", 0)
        top_snippet = res_grep["snippets"][0] if matches > 0 else {}
        print_status(
            "5. Surgical Retrieval (jevgrep)",
            matches > 0,
            f"found {matches} snippets (lines {top_snippet.get('start_line')}-{top_snippet.get('end_line')})",
        )
    except Exception as e:
        print_status("5. Surgical Retrieval (jevgrep)", False, str(e))

    # 6. Memory Promotion Gate
    from lib.memory_gate import judge_memory_promotion
    mem_res = judge_memory_promotion("Always use parameterized SQL queries; never interpolate raw strings.")
    print_status(
        "6. Memory Promotion Gate",
        mem_res["should_promote"],
        f"category: {mem_res['category']} ({mem_res['recommendation']})",
    )

    # 7. Loop Detector
    from lib.loop_detector import check_agent_loop
    stuck_actions = [
        {"tool": "run_command", "args": {"cmd": "npm test"}},
        {"tool": "run_command", "args": {"cmd": "npm test"}},
        {"tool": "run_command", "args": {"cmd": "npm test"}},
    ]
    loop_res = check_agent_loop(stuck_actions)
    print_status("7. Infinite Loop Detector", loop_res["is_looping"], loop_res["reason"][:70])

    # 8. Trajectory & Tool Budget Governor (Warden Governor)
    from lib.warden_governor import evaluate_trajectory_governor
    gov_res = evaluate_trajectory_governor(
        task_goal="Fix database connection timeout error",
        recent_actions=[
            {"tool": "run_command", "args": {"command": "ls -la /tmp"}},
            {"tool": "run_command", "args": {"command": "ps aux"}},
            {"tool": "run_command", "args": {"command": "cat /etc/hosts"}},
        ],
        proposed_tool="run_command",
        proposed_args={"command": "uname -a"},
        total_tool_calls=18,
        max_tool_calls=25,
    )
    gov_pass = (not gov_res["allow_action"]) and gov_res["is_stalled"]
    print_status("8. Trajectory Budget Governor", gov_pass, f"status: {gov_res['governor_status']} ({gov_res['reason'][:60]})")

    # 9. Stop / Done Task Completion Validator
    from lib.done_validator import validate_task_completion
    done_res = validate_task_completion(
        task_goal="Fix database connection timeout error",
        git_diff="diff --git a/db.py b/db.py\n- timeout = 5\n+ timeout = 30",
        test_output="12 passed in 0.3s",
        final_output="Increased pool timeout to 30 seconds. Tests passing.",
    )
    print_status(
        "9. Task Completion Validator",
        done_res["is_complete"],
        f"status: {done_res['status']} ({done_res['reason']})",
    )

    # 10. Speculative Decision Fan-Out & Prompt Triage
    from lib.speculative_triage import triage_task, format_triage_tags
    triage_res = triage_task("Migrate auth schema table to support OAuth tokens")
    triage_pass = bool(triage_res.get("task_type") and triage_res.get("tags"))
    tags_preview = format_triage_tags(triage_res)[:70]
    print_status(
        "10. Speculative Decision Fan-Out",
        triage_pass,
        f"{tags_preview}...",
    )

    # 11. Hallucinated Tool Call & Parameter Gate
    from lib.param_validator import validate_tool_call
    bad_call = validate_tool_call(
        "run_command",
        {"CommandLine": "git checkout -b --remote-track origin/main"},
    )
    good_call = validate_tool_call(
        "run_command",
        {"CommandLine": "git checkout -b feature/login origin/main"},
    )
    param_pass = (not bad_call["is_valid"]) and good_call["is_valid"]
    print_status(
        "11. Hallucinated Parameter Gate",
        param_pass,
        f"caught '{bad_call['error_type']}': {bad_call['suggestion']}",
    )

    # 12. Semantic Action Cache ("Learn to Skip")
    from lib.action_cache import cache_action_sequence, lookup_action_cache
    test_intent = "Run test suite check"
    cache_action_sequence(
        test_intent,
        [{"tool": "run_command", "args": {"CommandLine": "pytest -q"}}],
    )
    cache_hit = lookup_action_cache(test_intent)
    cache_pass = bool(cache_hit and cache_hit.get("cache_hit"))
    print_status(
        "12. Semantic Action Cache",
        cache_pass,
        f"hit '{cache_hit.get('matched_intent')}' with {cache_hit.get('action_count')} cached action(s)",
    )

    print(f"\n{BOLD}=== Simulation Complete ==={RESET}\n")


if __name__ == "__main__":
    main()



