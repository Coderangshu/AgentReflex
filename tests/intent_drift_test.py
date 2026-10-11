import unittest
from unittest.mock import patch
from lib.intent_drift import check_intent_drift


class TestIntentDrift(unittest.TestCase):

    def test_empty_goal(self):
        res = check_intent_drift("", [])
        self.assertFalse(res["has_drifted"])
        self.assertEqual(res["alignment_score"], 1.0)

    def test_too_few_actions_no_drift(self):
        res = check_intent_drift(
            "Fix database connection timeout",
            [{"tool": "view_file", "args": {"path": "db/pool.py"}}],
        )
        self.assertFalse(res["has_drifted"])

    @patch("lib.intent_drift.query_laya")
    def test_aligned_actions(self, mock_query):
        mock_query.return_value = {
            "drift": {
                "choice": "aligned",
                "probabilities": {"aligned": 0.88, "drifting": 0.12},
                "confidence": 0.88,
            },
            "alignment_score": {"noul": 0.85},
        }
        res = check_intent_drift(
            "Fix database connection timeout",
            [
                {"tool": "view_file", "args": {"path": "db/pool.py"}},
                {"tool": "view_file", "args": {"path": "db/config.py"}},
            ],
            proposed_tool="replace_file_content",
            proposed_args={"TargetFile": "db/pool.py"},
        )
        self.assertFalse(res["has_drifted"])
        self.assertEqual(res["drift_status"], "aligned")
        self.assertEqual(res["alignment_score"], 0.85)

    @patch("lib.intent_drift.query_laya")
    def test_drifted_actions_alarm(self, mock_query):
        mock_query.return_value = {
            "drift": {
                "choice": "drifting",
                "probabilities": {"aligned": 0.20, "drifting": 0.80},
                "confidence": 0.80,
            },
            "alignment_score": {"noul": 0.12},
        }
        res = check_intent_drift(
            "Fix database connection timeout",
            [
                {"tool": "view_file", "args": {"path": "frontend/navbar.css"}},
                {"tool": "replace_file_content", "args": {"TargetFile": "frontend/button.jsx"}},
            ],
            proposed_tool="replace_file_content",
            proposed_args={"TargetFile": "frontend/style.css"},
        )
        self.assertTrue(res["has_drifted"])
        self.assertEqual(res["drift_status"], "drifting")
        self.assertIn("Intent Drift Alarm", res["warning"])
        self.assertIn("Course correction required", res["warning"])


if __name__ == "__main__":
    unittest.main()
