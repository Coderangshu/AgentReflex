import unittest
import subprocess
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


class TestHooks(unittest.TestCase):

    def test_pre_invocation_hook(self):
        hook_path = ROOT / "hooks" / "pre_invocation.py"
        payload = json.dumps({"prompt": "please explore and find controllers in this repo"})
        proc = subprocess.run(
            [PYTHON, str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIn("additionalContext", data)
        self.assertIn("injectSteps", data)

    def test_pre_tool_enforcer_hook_allow(self):
        hook_path = ROOT / "hooks" / "pre_tool_enforcer.py"
        payload = json.dumps({
            "toolCall": {
                "name": "edit_file",
                "args": {"content": "def greet(name):\n    return f'Hello {name}'\n"}
            }
        })
        proc = subprocess.run(
            [PYTHON, str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("allow_tool", False))
        self.assertEqual(data.get("decision"), "allow")

    def test_post_tool_judge_hook(self):
        hook_path = ROOT / "hooks" / "post_tool_judge.py"
        payload = json.dumps({
            "toolCall": {
                "name": "edit_file",
                "args": {"content": "def add(a, b): return a + b"}
            }
        })
        proc = subprocess.run(
            [PYTHON, str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data, {})


if __name__ == "__main__":
    unittest.main()
