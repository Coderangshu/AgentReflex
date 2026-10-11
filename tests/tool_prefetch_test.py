import unittest
from unittest.mock import patch, MagicMock
from lib.tool_prefetch import (
    hash_tool_call,
    is_safe_prefetch_action,
    predict_speculative_action,
    execute_speculative_action,
)


class TestToolPrefetch(unittest.TestCase):

    def test_hash_tool_call_deterministic(self):
        h1 = hash_tool_call("view_file", {"AbsolutePath": "/a/b/c.py"})
        h2 = hash_tool_call("view_file", {"AbsolutePath": "/a/b/c.py"})
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

    def test_safe_prefetch_filter(self):
        # Read-only whitelisted commands
        self.assertTrue(is_safe_prefetch_action("run_command", {"CommandLine": "git status"}))
        self.assertTrue(is_safe_prefetch_action("run_command", {"CommandLine": "git diff"}))
        self.assertTrue(is_safe_prefetch_action("find_by_name", {}))

        # Mutating or destructive commands blocked
        self.assertFalse(is_safe_prefetch_action("run_command", {"CommandLine": "rm -rf ."}))
        self.assertFalse(is_safe_prefetch_action("run_command", {"CommandLine": "git commit -m 'test'"}))
        self.assertFalse(is_safe_prefetch_action("write_to_file", {"TargetFile": "a.txt"}))
        self.assertFalse(is_safe_prefetch_action("replace_file_content", {}))

    @patch("lib.tool_prefetch.query_laya")
    def test_predict_speculative_action_git(self, mock_query):
        mock_query.return_value = {
            "action": {"choice": "git_status"},
            "confidence": {"noul": 0.88},
        }
        res = predict_speculative_action("Check git status and pending commits in the repo")
        self.assertIsNotNone(res)
        self.assertEqual(res["tool"], "run_command")
        self.assertEqual(res["args"]["CommandLine"], "git status")

    @patch("lib.tool_prefetch.query_laya")
    def test_predict_speculative_low_confidence_ignored(self, mock_query):
        mock_query.return_value = {
            "action": {"choice": "other"},
            "confidence": {"noul": 0.30},
        }
        res = predict_speculative_action("Random conversational chatter")
        self.assertIsNone(res)

    def test_execute_speculative_action(self):
        res = execute_speculative_action("run_command", {"CommandLine": "git status"})
        self.assertEqual(res.get("status"), "success")
        self.assertIn("branch", res.get("output", "").lower())


if __name__ == "__main__":
    unittest.main()
