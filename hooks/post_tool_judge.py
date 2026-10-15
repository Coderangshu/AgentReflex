#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.judge import judge_test_coverage
try:
    from lib.server_logger import (
        log_activity,
        resolve_project_name,
        resolve_agent_name,
        resolve_project_dir,
        extract_post_tool_details,
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

    def extract_post_tool_details(data):
        return "unknown_tool", {}, "", "success"



def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({}))
            return

        data = json.loads(raw_input)
        tool_call = data.get("toolCall", {}) or {}
        args = tool_call.get("args", {}) or {}

        cwd_val = data.get("cwd") or args.get("Cwd")
        project_dir = resolve_project_dir(
            data.get("workspacePaths"),
            cwd_val,
            data.get("transcriptPath"),
        )
        project = resolve_project_name(
            data.get("workspacePaths"),
            cwd_val,
            data.get("transcriptPath"),
        )
        agent = resolve_agent_name(data.get("modelName"), data.get("conversationId"))

        tool_name, final_args, response, status = extract_post_tool_details(data)
        if not final_args:
            final_args = args

        log_activity(
            project=project,
            agent=agent,
            tool=tool_name,
            args=final_args,
            response=response,
            status=status,
            project_dir=project_dir,
        )

        content = (
            final_args.get("content")
            or final_args.get("patch")
            or final_args.get("CodeContent")
            or final_args.get("ReplacementContent")
            or ""
        )

        if content:
            eval_result = judge_test_coverage(content)
            if eval_result.get("requires_verification", False):
                sys.stderr.write(
                    f"[AgentReflex Test Judge] Notice: Significant uncovered logic detected "
                    f"(risk score: {eval_result['uncovered_risk']:.2f}). Consider writing unit tests.\n"
                )

        # Speculative prefetch for culprit files on command failure or crash tracebacks
        t_lower = tool_name.lower()
        if ("command" in t_lower or "bash" in t_lower or "exec" in t_lower) and response:
            is_failure = status == "error" or any(k in response.lower() for k in ("traceback", "error[", "panic:", "fatal error:", "exception:", "syntaxerror"))
            if is_failure:
                try:
                    from lib.traceback_extractor import extract_culprit_frame
                    from lib.client import trigger_prefetch

                    frame = extract_culprit_frame(response, cwd=project_dir or cwd_val)
                    if frame and frame.get("file"):
                        trigger_prefetch(
                            tool="view_file",
                            args={"AbsolutePath": frame["file"]},
                            cwd=project_dir or cwd_val or "",
                        )
                except Exception:
                    pass

        # Standard PostToolUse output is an empty JSON object
        print(json.dumps({}))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
