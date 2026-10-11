import unittest
import tempfile
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

from lib.server_logger import (
    resolve_project_name,
    resolve_agent_name,
    summarize_args,
    summarize_response,
    log_activity,
    is_logging_enabled,
    get_project_log_paths,
    extract_post_tool_details,
)


class TestServerLogger(unittest.TestCase):

    def test_resolve_project_name(self):
        self.assertEqual(resolve_project_name(["/Users/foo/git/vmtest"]), "vmtest")
        self.assertEqual(
            resolve_project_name(
                [],
                transcript_path="/Users/foo/git/myproject/.gemini/antigravity-cli/brain/123/transcript.jsonl",
            ),
            "myproject",
        )
        self.assertEqual(resolve_project_name([], cwd="/Users/foo/git/laya"), "laya")

    def test_resolve_agent_name(self):
        self.assertEqual(
            resolve_agent_name("gemini-3.8-flash", "9e2b39b6-8396-4da8"),
            "gemini-3.8-flash (9e2b39b6)",
        )
        self.assertEqual(resolve_agent_name("gemini-pro", ""), "gemini-pro")
        self.assertEqual(resolve_agent_name("", "9e2b39b6-8396"), "agent-9e2b39b6")
        self.assertEqual(resolve_agent_name("", ""), "agent")

    def test_summarize_args_and_response(self):
        cmd_args = {"CommandLine": "ls -la\npwd"}
        self.assertIn("ls -la pwd", summarize_args("run_command", cmd_args))

        file_args = {"TargetFile": "/path/to/main.py"}
        self.assertEqual(summarize_args("replace_file_content", file_args), "file='main.py'")

        resp = "hello world\nfrom test"
        self.assertEqual(summarize_response(resp), "hello world from test")

        long_resp = "a" * 500
        truncated = summarize_response(long_resp, max_len=100)
        self.assertTrue(truncated.endswith("... (500 chars)"))

    def test_is_logging_enabled_controls(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            # Default is False (OFF by default)
            self.assertFalse(is_logging_enabled(p))

            # 1. Opt-in flag file: .reflex-log enables
            flag_file = p / ".reflex-log"
            flag_file.touch()
            self.assertTrue(is_logging_enabled(p))
            flag_file.unlink()
            self.assertFalse(is_logging_enabled(p))

            # 2. Config file: .agentreflex.json enables
            cfg_file = p / ".agentreflex.json"
            cfg_file.write_text(json.dumps({"logging": True}), encoding="utf-8")
            self.assertTrue(is_logging_enabled(p))
            cfg_file.write_text(json.dumps({"logging": False}), encoding="utf-8")
            self.assertFalse(is_logging_enabled(p))
            cfg_file.unlink()

            # 3. Env var enables
            os.environ["AGENTREFLEX_LOGGING"] = "1"
            try:
                self.assertTrue(is_logging_enabled(p))
            finally:
                os.environ.pop("AGENTREFLEX_LOGGING", None)

    def test_log_activity_writes_isolated_project_files(self):
        with tempfile.TemporaryDirectory() as td:
            old_log_dir = os.environ.get("AGENTREFLEX_LOGS_DIR")
            old_env_logging = os.environ.get("AGENTREFLEX_LOGGING")
            os.environ["AGENTREFLEX_LOGS_DIR"] = td
            os.environ["AGENTREFLEX_LOGGING"] = "1"
            try:
                import importlib
                import lib.server_logger as sl
                importlib.reload(sl)

                sl.log_activity(
                    project="vmtest",
                    agent="test_agent",
                    tool="run_command",
                    args={"CommandLine": "pytest"},
                    response="all tests passed",
                    status="completed",
                )

                log_path = Path(td) / "vmtest.log"
                jsonl_path = Path(td) / "vmtest.jsonl"

                self.assertTrue(log_path.exists())
                self.assertTrue(jsonl_path.exists())

                log_content = log_path.read_text(encoding="utf-8")
                # Inside vmtest.log, [PROJECT: vmtest] is omitted per user requirement
                self.assertNotIn("[PROJECT:", log_content)
                self.assertIn("[TOOL: run_command]", log_content)
                self.assertIn("[AGENT: test_agent]", log_content)
                self.assertTrue(log_content.startswith("[TOOL: run_command] cmd='pytest' -> response=all tests passed [AGENT: test_agent]"))
                self.assertIn("response=all tests passed", log_content)

                jsonl_lines = jsonl_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(jsonl_lines), 1)
                data = json.loads(jsonl_lines[0])
                self.assertNotIn("project", data)
                self.assertEqual(data["tool"], "run_command")
                self.assertEqual(data["agent"], "test_agent")
                self.assertIn("timestamp", data)
                self.assertEqual(data["response"], "all tests passed")
            finally:
                if old_log_dir:
                    os.environ["AGENTREFLEX_LOGS_DIR"] = old_log_dir
                else:
                    os.environ.pop("AGENTREFLEX_LOGS_DIR", None)
                if old_env_logging:
                    os.environ["AGENTREFLEX_LOGGING"] = old_env_logging
                else:
                    os.environ.pop("AGENTREFLEX_LOGGING", None)
                importlib.reload(sl)

    def test_extract_post_tool_details_from_transcript(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl", delete=False) as tf:
            tf.write(json.dumps({
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "run_command", "args": {"CommandLine": "git status"}}]
            }) + "\n")
            tf.write(json.dumps({
                "step_index": 2,
                "type": "GENERIC",
                "content": "On branch main, working tree clean\n"
            }) + "\n")
            tf_path = Path(tf.name)

        try:
            payload = {"transcriptPath": str(tf_path)}
            tool_name, args, response, status = extract_post_tool_details(payload)
            self.assertEqual(tool_name, "run_command")
            self.assertEqual(args.get("CommandLine"), "git status")
            self.assertIn("working tree clean", response)
            self.assertEqual(status, "success")
        finally:
            tf_path.unlink()

    def test_post_tool_judge_hook_logs_activity_per_project(self):
        hook_path = ROOT / "hooks" / "post_tool_judge.py"
        with tempfile.TemporaryDirectory() as td:
            old_log_dir = os.environ.get("AGENTREFLEX_LOGS_DIR")
            os.environ["AGENTREFLEX_LOGS_DIR"] = td
            try:
                payload = json.dumps({
                    "workspacePaths": ["/Users/angshuman/git/sample_proj"],
                    "modelName": "gemini-3.8-flash",
                    "conversationId": "abc12345-6789",
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "npm test"}
                    },
                    "toolResult": "pass: 10 tests"
                })

                proc = subprocess.run(
                    [PYTHON, str(hook_path)],
                    input=payload,
                    capture_output=True,
                    text=True,
                    cwd=str(ROOT),
                    env=dict(os.environ, AGENTREFLEX_LOGS_DIR=td, AGENTREFLEX_LOGGING="1"),
                )
                self.assertEqual(proc.returncode, 0)

                log_path = Path(td) / "sample_proj.log"
                self.assertTrue(log_path.exists())
                log_content = log_path.read_text(encoding="utf-8")
                self.assertNotIn("[PROJECT:", log_content)
                self.assertIn("[TOOL: run_command]", log_content)
                self.assertIn("npm test", log_content)
                self.assertIn("pass: 10 tests", log_content)
            finally:
                if old_log_dir:
                    os.environ["AGENTREFLEX_LOGS_DIR"] = old_log_dir
                else:
                    os.environ.pop("AGENTREFLEX_LOGS_DIR", None)


if __name__ == "__main__":
    unittest.main()
