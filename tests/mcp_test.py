import unittest
import subprocess
import json
from pathlib import Path

MCP_SERVER_PATH = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
PYTHON_BIN = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
if not PYTHON_BIN.exists():
    import sys
    PYTHON_BIN = Path(sys.executable)


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.proc = subprocess.Popen(
            [str(PYTHON_BIN), str(MCP_SERVER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait()

    def rpc(self, method: str, params: dict = None, msg_id: int = 1) -> dict:
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            req["params"] = params
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def test_initialize(self):
        res = self.rpc("initialize")
        self.assertEqual(res["result"]["serverInfo"]["name"], "agentreflex")

    def test_list_tools(self):
        res = self.rpc("tools/list")
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertEqual(len(tool_names), 7)
        self.assertIn("sys1_check_violations", tool_names)
        self.assertIn("sys1_grep", tool_names)
        self.assertIn("sys1_review_gate", tool_names)
        self.assertIn("sys1_compact", tool_names)
        self.assertIn("sys1_rank_files", tool_names)
        self.assertIn("sys1_judge_coverage", tool_names)
        self.assertIn("sys1_memory_gate", tool_names)

    def test_call_check_violations(self):
        res = self.rpc(
            "tools/call",
            {"name": "sys1_check_violations", "arguments": {"content": "const x = 1;"}},
        )
        data = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("violates", data)
        self.assertFalse(data["violates"])


if __name__ == "__main__":
    unittest.main()
