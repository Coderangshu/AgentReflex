#!/usr/bin/env python3
import sys
import json
import re
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.rule_enforcer import check_violations
from lib.secret_scan import (
    has_hardcoded_secret,
    has_destructive_command,
    MIN_EDIT_CHARS_FOR_MODEL,
    SECRET_REASON,
    DESTRUCTIVE_CMD_REASON,
)
from lib.loop_detector import check_agent_loop
from lib.warden_governor import evaluate_trajectory_governor
from lib.param_validator import validate_tool_call
from lib.intent_drift import check_intent_drift
from lib.client import claim_prefetch, invalidate_prefetch
try:
    from lib.server_logger import (
        log_activity,
        resolve_project_name,
        resolve_agent_name,
        resolve_project_dir,
    )
except Exception:
    def log_activity(*args, **kwargs):
        pass

    def resolve_project_name(*args, **kwargs):
        return "default"

    def resolve_agent_name(*args, **kwargs):
        return "agent"

    def resolve_project_dir(*args, **kwargs):
        return None



def parse_transcript_history(transcript_path_str: str) -> tuple[list[dict], int, str]:
    """Read transcript steps to extract action history, tool call counts, and user goal.

    Counts tool calls scoped to the CURRENT turn (since the most recent USER_INPUT)
    to prevent lifetime session tool calls from tripping turn limits.
    """
    if not transcript_path_str:
        return [], 0, ""
    tpath = Path(transcript_path_str)
    if not tpath.exists():
        return [], 0, ""

    try:
        lines = tpath.read_text(encoding="utf-8", errors="replace").splitlines()
        recent_actions = []
        turn_tool_calls = 0
        current_turn_goal = ""

        # Scan transcript and reset counter on each new user input turn
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                item_type = item.get("type", "")

                # Reset turn counter and update active goal whenever user inputs new prompt
                if item_type in ("USER_INPUT", "user", "USER_PROMPT", "USER") or item.get("source") in ("USER_EXPLICIT", "USER"):
                    turn_tool_calls = 0
                    raw_c = str(item.get("content", ""))
                    # Strip XML wrapping like <USER_REQUEST>
                    for tag in ("<USER_REQUEST>", "</USER_REQUEST>", "<ADDITIONAL_METADATA>", "</ADDITIONAL_METADATA>"):
                        raw_c = raw_c.replace(tag, "")
                    current_turn_goal = raw_c.strip()[:300]
                    continue

                tcs = item.get("tool_calls", [])
                if tcs:
                    turn_tool_calls += len(tcs)
                    for tc in tcs:
                        # Only record actions that were not blocked/denied by guardrails
                        recent_actions.append({
                            "tool": tc.get("name"),
                            "args": tc.get("args", {}),
                            "error": item.get("error", ""),
                        })
            except Exception:
                continue

        return recent_actions[-6:], turn_tool_calls, current_turn_goal
    except Exception:
        return [], 0, ""


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"decision": "allow", "allow_tool": True}))
            return

        data = json.loads(raw_input)
        tool_call = data.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        args = tool_call.get("args", {})

        # Extract project and agent identities for centralized server logging
        transcript_path = data.get("transcriptPath")
        cwd_dir = args.get("Cwd") or args.get("cwd") or data.get("cwd") or args.get("working_directory")
        project_dir = resolve_project_dir(data.get("workspacePaths"), cwd_dir, transcript_path)
        project = resolve_project_name(data.get("workspacePaths"), cwd_dir, transcript_path)
        agent = resolve_agent_name(data.get("modelName"), data.get("conversationId"))

        def emit_decision(decision: str, reason: str = "", overwrite: dict = None):
            allow = (decision == "allow")
            payload = {"decision": decision, "allow_tool": allow}
            if reason:
                payload["reason"] = reason
                payload["deny_reason"] = reason
            if overwrite:
                payload["overwrite"] = overwrite

            status = "allowed" if allow else "denied"
            resp = f"BLOCKED: {reason}" if not allow else "CALL_ALLOWED"
            log_activity(
                project=project,
                agent=agent,
                tool=tool_name,
                args=args,
                response=resp,
                status=status,
                project_dir=project_dir,
            )
            print(json.dumps(payload))

        # 1. Trajectory & Tool Budget Governor Check
        recent_actions, turn_tool_calls, user_goal = parse_transcript_history(transcript_path)

        gov_res = evaluate_trajectory_governor(
            task_goal=user_goal,
            recent_actions=recent_actions,
            proposed_tool=tool_name,
            proposed_args=args,
            total_tool_calls=turn_tool_calls,
        )

        if not gov_res.get("allow_action", True):
            reason = gov_res.get("reason", "Trajectory budget governor intervention")
            emit_decision("deny", reason)
            return

        # 2. Cross-Turn Intent Drift Alarm (exempt read-only tools and verification commands)
        READ_ONLY_TOOLS = {
            "view_file",
            "find_by_name",
            "grep_search",
            "read_url_content",
            "read_resource",
            "list_resources",
            "view_image",
        }
        cmd_str = (args.get("CommandLine") or args.get("commandLine") or "").lower()
        is_dev_verification = any(k in cmd_str for k in ("unittest", "pytest", "git", "make test", "npm test", "python"))

        # Strip time metadata strings from user_goal for accurate prompt length check
        clean_goal = re.sub(r"The current local time is:.*", "", user_goal, flags=re.DOTALL).strip() if user_goal else ""
        is_short_prompt = len(clean_goal) <= 35

        if clean_goal and not is_short_prompt and len(recent_actions) >= 3 and tool_name not in READ_ONLY_TOOLS and not is_dev_verification:
            drift_res = check_intent_drift(
                primary_goal=clean_goal,
                recent_actions=recent_actions,
                proposed_tool=tool_name,
                proposed_args=args,
            )
            if drift_res.get("has_drifted", False):
                emit_decision("deny", drift_res.get("warning"))
                return

        # 3. Hallucinated Tool Call & Parameter Gate
        param_res = validate_tool_call(tool_name, args, cwd=cwd_dir)
        if not param_res.get("is_valid", True):
            reason = f"AgentReflex Param Gate: {param_res.get('reason')} Suggestion: {param_res.get('suggestion')}"
            emit_decision("deny", reason)
            return

        # 3. Dynamic Subagent Model Tier Overwrite (invoke_subagent)
        if tool_name == "invoke_subagent":
            subagents = args.get("Subagents", [])
            has_mod = False
            for sa in subagents:
                sa_prompt = sa.get("Prompt", "")
                current_model = sa.get("Model", "inherit")
                # If model is unspecified or set to default/inherit/pro, dynamically route
                if current_model in ("inherit", "pro", ""):
                    route_decision = route_model(sa_prompt, harness="agy")
                    target_model = route_decision.get("subagent_model", "flash")
                    if target_model != current_model:
                        sa["Model"] = target_model
                        has_mod = True
            if has_mod:
                emit_decision("allow", overwrite={"Subagents": subagents})
                return

        # 4. Extract modified code or command across standard parameter names
        command = args.get("commandLine") or args.get("CommandLine") or ""
        edit = (
            args.get("content")
            or args.get("patch")
            or args.get("CodeContent")
            or args.get("ReplacementContent")
            or ""
        )
        content = command or edit

        # 5. Speculative Prefetch Claim / Invalidation
        if edit or (command and not any(command.strip().startswith(p) for p in ("git status", "git diff", "git log", "git branch", "pytest --collect-only"))):
            # Mutating action: instantly invalidate any cached speculative prefetch
            invalidate_prefetch()
        elif tool_name in READ_ONLY_TOOLS or (command and any(command.strip().startswith(p) for p in ("git status", "git diff", "git log", "git branch"))):
            claim_res = claim_prefetch(tool_name, args)
            if claim_res.get("hit"):
                # Pre-computed output verified and available in RAM
                emit_decision("allow")
                return

        if not content:
            emit_decision("allow")
            return

        if command:
            if has_destructive_command(command):
                emit_decision("deny", DESTRUCTIVE_CMD_REASON)
                return
        else:
            # File edit: deterministic secret check, and skip the model on short snippets it over-scores
            if has_hardcoded_secret(edit):
                emit_decision("deny", SECRET_REASON)
                return
            if len(edit) < MIN_EDIT_CHARS_FOR_MODEL:
                emit_decision("allow")
                return

        result = check_violations(content)

        if result.get("violates", False):
            reason = result.get("reason", "AgentReflex rule guardrail triggered")
            emit_decision("deny", reason)
        else:
            emit_decision("allow")
    except Exception:
        print(json.dumps({"decision": "allow", "allow_tool": True}))


if __name__ == "__main__":
    main()
