import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

from lib.memory_gate import judge_memory_promotion
from lib.loop_detector import check_agent_loop, evaluate_task_output
from lib.surgical_retrieval import chunk_file, score_snippet, surgical_search


class TestAdvancedFeatures(unittest.TestCase):

    @patch("lib.memory_gate.query_laya")
    def test_memory_promotion_gate_accept(self, mock_query):
        mock_query.return_value = {
            "should_promote": {"noul": 0.88},
            "category": {"choice": "rule", "answer_confidence": 0.90},
        }
        res = judge_memory_promotion("Always use UUIDv4 for public entities in Postgres schemas.")
        self.assertTrue(res["should_promote"])
        self.assertEqual(res["category"], "rule")
        self.assertEqual(res["recommendation"], "PROMOTE_TO_MEMORY")

    @patch("lib.memory_gate.query_laya")
    def test_memory_promotion_gate_reject_ephemeral(self, mock_query):
        mock_query.return_value = {
            "should_promote": {"noul": 0.20},
            "category": {"choice": "ephemeral", "answer_confidence": 0.85},
        }
        res = judge_memory_promotion("Debugged line 42 by printing temp variable x.")
        self.assertFalse(res["should_promote"])
        self.assertEqual(res["recommendation"], "DISCARD_EPHEMERAL")

    def test_loop_detector_identical_actions(self):
        # 3 identical actions should trigger loop detection immediately
        actions = [
            {"tool": "view_file", "args": {"file": "app.py", "lines": [1, 20]}},
            {"tool": "view_file", "args": {"file": "app.py", "lines": [1, 20]}},
            {"tool": "view_file", "args": {"file": "app.py", "lines": [1, 20]}},
        ]
        res = check_agent_loop(actions)
        self.assertTrue(res["is_looping"])
        self.assertEqual(res["loop_score"], 1.0)
        self.assertIn("repeated identical tool call", res["reason"])

    @patch("lib.loop_detector.query_laya")
    def test_evaluate_task_output(self, mock_query):
        mock_query.return_value = {
            "meets_criteria": {"noul": 0.92},
            "has_unhandled_failure": {"noul": 0.05},
        }
        res = evaluate_task_output("Sort the list in place", "def sort_list(l): l.sort()")
        self.assertTrue(res["satisfied"])
        self.assertEqual(res["recommendation"], "ACCEPT_OUTPUT")

    def test_surgical_chunking(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as tf:
            tf.write("\n".join([f"line_{i} = {i}" for i in range(50)]))
            tf_path = Path(tf.name)

        try:
            chunks = chunk_file(tf_path, window_lines=20, overlap=5)
            self.assertGreaterEqual(len(chunks), 2)
            self.assertEqual(chunks[0]["start_line"], 1)
            self.assertEqual(chunks[0]["end_line"], 20)
        finally:
            tf_path.unlink()

    @patch("lib.surgical_retrieval.score_snippet")
    def test_surgical_search(self, mock_score):
        mock_score.return_value = 0.85
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as tf:
            tf.write("def auth_login(user, pwd):\n    return verify(user, pwd)\n")
            tf_path = Path(tf.name)

        try:
            results = surgical_search("user login authentication", [tf_path], max_snippets=1)
            self.assertEqual(len(results), 1)
            self.assertIn("auth_login", results[0]["snippet"])
            self.assertEqual(results[0]["score"], 0.85)
        finally:
            tf_path.unlink()


if __name__ == "__main__":
    unittest.main()
