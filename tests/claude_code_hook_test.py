import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.client import is_daemon_alive

HOOK = ROOT / "hooks" / "claude_code_hook.py"
PYTHON = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def run_hook(payload) -> str:
    proc = subprocess.run(
        [PYTHON, str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def pre(tool_name, tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}


@unittest.skipUnless(is_daemon_alive(), "AgentReflex daemon not running (make start)")
class TestClaudeCodeHook(unittest.TestCase):
    def assertAsks(self, out):
        data = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(data["hookEventName"], "PreToolUse")
        self.assertEqual(data["permissionDecision"], "ask")
        self.assertTrue(data["permissionDecisionReason"])

    def test_destructive_bash_asks(self):
        self.assertAsks(run_hook(pre("Bash", {"command": "rm -rf / --no-preserve-root"})))

    def test_benign_bash_silent(self):
        self.assertEqual(run_hook(pre("Bash", {"command": "git status"})), "")

    def test_hardcoded_secret_in_write_asks(self):
        content = 'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
        self.assertAsks(run_hook(pre("Write", {"file_path": "a.py", "content": content})))

    def test_secret_in_edit_and_multiedit_asks(self):
        self.assertAsks(run_hook(pre("Edit", {"new_string": 'password = "hunter2hunter2"'})))
        edits = [{"new_string": "x = 1"}, {"new_string": 'token = "ghp_' + "a" * 36 + '"'}]
        self.assertAsks(run_hook(pre("MultiEdit", {"edits": edits})))

    def test_short_benign_edit_silent(self):
        out = run_hook(pre("Edit", {"new_string": "def greet(name):\n    return f'Hello {name}'\n"}))
        self.assertEqual(out, "")

    def test_prompt_router_recommends_review_tool(self):
        out = run_hook({
            "hook_event_name": "UserPromptSubmit",
            "prompt": "review my git diff for security risks before I open the PR",
        })
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("reflex_review_gate", ctx)


class TestFailOpen(unittest.TestCase):
    def test_garbage_and_empty_input_silent(self):
        self.assertEqual(run_hook("not json"), "")
        self.assertEqual(run_hook(""), "")

    def test_unknown_event_silent(self):
        self.assertEqual(run_hook({"hook_event_name": "Stop"}), "")


if __name__ == "__main__":
    unittest.main()
