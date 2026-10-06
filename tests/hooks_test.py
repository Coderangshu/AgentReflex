import unittest
import subprocess
import json
import sys
import tempfile
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

    def test_pre_invocation_auto_compaction(self):
        hook_path = ROOT / "hooks" / "pre_invocation.py"
        with tempfile.NamedTemporaryFile("w+", suffix=".jsonl", delete=False) as tf:
            # Generate >50KB transcript of noisy steps
            for i in range(300):
                line = json.dumps({
                    "step_index": i,
                    "type": "TOOL_RESULT",
                    "content": f"Downloading assets chunk {i}/300 [=====>     ] 50% 1200kB/s complete\n" * 5,
                })
                tf.write(line + "\n")
            tf_path = Path(tf.name)

        try:
            payload = json.dumps({
                "prompt": "continue task",
                "transcriptPath": str(tf_path),
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
            self.assertIn("additionalContext", data)
            # Verify compaction notice was injected
            self.assertIn("Auto-Compaction", data["additionalContext"])
        finally:
            tf_path.unlink()

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
