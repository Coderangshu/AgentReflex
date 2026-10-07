import unittest
from unittest.mock import patch
from lib.warden_governor import (
    score_forward_progress,
    evaluate_trajectory_governor,
    DEFAULT_MAX_TOOL_CALLS,
)


class TestWardenGovernor(unittest.TestCase):

    def test_governor_allow_normal_flow(self):
        actions = [
            {"tool": "view_file", "args": {"file": "auth.py"}},
            {"tool": "replace_file_content", "args": {"file": "auth.py"}},
        ]
        res = evaluate_trajectory_governor(
            task_goal="Fix typo in auth token validator",
            recent_actions=actions,
            proposed_tool="run_command",
            proposed_args={"command": "pytest tests/auth_test.py"},
            total_tool_calls=2,
            max_tool_calls=25,
        )
        self.assertTrue(res["allow_action"])
        self.assertEqual(res["governor_status"], "ALLOW")
        self.assertFalse(res["is_stalled"])

    def test_governor_hard_tool_budget_limit(self):
        actions = [{"tool": f"view_file_{i}", "args": {"file": f"file_{i}.py"}} for i in range(25)]
        res = evaluate_trajectory_governor(
            task_goal="Find obscure bug",
            recent_actions=actions,
            proposed_tool="view_file_25",
            total_tool_calls=25,
            max_tool_calls=25,
        )
        self.assertFalse(res["allow_action"])
        self.assertEqual(res["governor_status"], "TOOL_BUDGET_EXCEEDED")
        self.assertIn("Tool budget exhausted", res["reason"])

    def test_governor_hard_token_budget_limit(self):
        res = evaluate_trajectory_governor(
            task_goal="Analyze repo",
            recent_actions=[{"tool": "view_file", "args": {}}],
            proposed_tool="view_file",
            total_tool_calls=5,
            max_tool_calls=25,
            estimated_tokens=130_000,
            max_tokens=120_000,
        )
        self.assertFalse(res["allow_action"])
        self.assertEqual(res["governor_status"], "TOKEN_BUDGET_EXCEEDED")
        self.assertIn("Estimated token budget exhausted", res["reason"])

    def test_governor_catches_repeated_identical_loops(self):
        actions = [
            {"tool": "run_command", "args": {"command": "npm test"}},
            {"tool": "run_command", "args": {"command": "npm test"}},
        ]
        res = evaluate_trajectory_governor(
            task_goal="Run build",
            recent_actions=actions,
            proposed_tool="run_command",
            proposed_args={"command": "npm test"},
            total_tool_calls=2,
        )
        self.assertFalse(res["allow_action"])
        self.assertEqual(res["governor_status"], "LOOP_HALT")
        self.assertIn("repeated identical tool call", res["reason"])

    @patch("lib.warden_governor.query_laya")
    def test_governor_neural_velocity_stall_intervene(self, mock_query):
        mock_query.return_value = {
            "velocity": {"choice": "spinning_wheels", "answer_confidence": 0.88},
            "is_productive": {"noul": 0.15},
        }
        actions = [
            {"tool": "run_command", "args": {"command": "ls -la dir1"}},
            {"tool": "run_command", "args": {"command": "ls -la dir2"}},
            {"tool": "run_command", "args": {"command": "ls -la dir3"}},
            {"tool": "run_command", "args": {"command": "ls -la dir4"}},
        ]
        # Total tool calls = 16 out of 25 (64% budget, >60% threshold)
        res = evaluate_trajectory_governor(
            task_goal="Fix failing unit test in billing service",
            recent_actions=actions,
            proposed_tool="run_command",
            proposed_args={"command": "ls -la dir5"},
            total_tool_calls=16,
            max_tool_calls=25,
        )
        self.assertFalse(res["allow_action"])
        self.assertEqual(res["governor_status"], "PROGRESS_STALLED")
        self.assertTrue(res["is_stalled"])
        self.assertIn("spinning_wheels", res["reason"])


if __name__ == "__main__":
    unittest.main()
