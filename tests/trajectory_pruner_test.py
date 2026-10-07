import unittest
from unittest.mock import patch
from lib.trajectory_pruner import classify_trajectory_step, prune_trajectory


class TestTrajectoryPruner(unittest.TestCase):
    def test_empty_step(self):
        res = classify_trajectory_step("")
        self.assertTrue(res["should_prune"])
        self.assertEqual(res["category"], "transient_listing")

    def test_progress_bar_heuristic(self):
        progress_text = "Downloading [=====>     ] 50% 1200kB/s"
        res = classify_trajectory_step(progress_text)
        self.assertTrue(res["should_prune"])
        self.assertEqual(res["reason"], "Terminal progress noise")

    @patch("lib.trajectory_pruner.query_laya")
    def test_obsolete_error_resolved_by_later_step(self, mock_query):
        # Step 1 failed, but subsequent actions resolved it
        mock_query.return_value = {
            "status": {
                "type": "choice",
                "choice": "resolved_past_error",
                "answer_confidence": 0.92,
            }
        }

        step = "Error: ModuleNotFoundError: No module named 'requests' in app.py:10"
        future = "pip install requests -> write_to_file app.py -> tests passed cleanly"
        res = classify_trajectory_step(step, future_context=future)

        self.assertTrue(res["should_prune"])
        self.assertEqual(res["category"], "obsolete_error")
        self.assertGreaterEqual(res["confidence"], 0.65)

    @patch("lib.trajectory_pruner.query_laya")
    def test_durable_state_preserved(self, mock_query):
        # Critical user constraint / rule must be preserved
        mock_query.side_effect = [
            {"status": {"type": "choice", "choice": "active_unresolved_issue", "answer_confidence": 0.88}},
            {"is_transient_search": {"type": "noul", "noul": 0.10}},
        ]

        step = "User constraint: Database migrations must never drop existing user columns."
        res = classify_trajectory_step(step, future_context="edit migration.sql")

        self.assertFalse(res["should_prune"])
        self.assertEqual(res["category"], "durable_state")

    @patch("lib.trajectory_pruner.query_laya")
    def test_prune_trajectory_workflow(self, mock_query):
        # Mock step 2: obsolete error (resolved_past_error -> pruned)
        # Mock step 3: durable code edit (active -> kept)
        mock_query.side_effect = [
            {"status": {"type": "choice", "choice": "resolved_past_error", "answer_confidence": 0.95}},
            {"status": {"type": "choice", "choice": "permanent_requirement", "answer_confidence": 0.85}},
            {"is_transient_search": {"type": "noul", "noul": 0.05}},
        ]

        steps = [
            {"step_index": 1, "type": "USER_INPUT", "content": "Please fix the failing build"},
            {"step_index": 2, "type": "TOOL_RESULT", "tool_name": "run_command", "content": "Compilation error at line 42"},
            {"step_index": 3, "type": "TOOL_RESULT", "tool_name": "write_file", "content": "Fix applied: updated variable typing"},
        ]

        res = prune_trajectory(steps)
        self.assertEqual(res["total_steps"], 3)
        self.assertEqual(res["pruned_steps"], 1)
        self.assertEqual(res["kept_steps"], 2)
        self.assertIn(2, res["pruned_indices"])
        # User input (step 1) and fix (step 3) must be in active_steps
        self.assertEqual(res["active_steps"][0]["step_index"], 1)
        self.assertEqual(res["active_steps"][1]["step_index"], 3)


if __name__ == "__main__":
    unittest.main()
