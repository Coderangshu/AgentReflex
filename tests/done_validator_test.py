import unittest
from unittest.mock import patch
from lib.done_validator import validate_task_completion


class TestDoneValidator(unittest.TestCase):

    def test_empty_goal_passes(self):
        res = validate_task_completion("")
        self.assertTrue(res["is_complete"])
        self.assertEqual(res["status"], "TASK_COMPLETE")

    @patch("lib.done_validator.query_laya")
    def test_complete_task_with_passing_tests(self, mock_query):
        mock_query.return_value = {
            "status": {"choice": "task_complete", "answer_confidence": 0.90},
            "has_failing_tests": {"noul": 0.05},
            "satisfies_goal": {"noul": 0.92},
        }
        res = validate_task_completion(
            task_goal="Fix bug in auth token parser",
            git_diff="diff --git a/auth.py b/auth.py\n+ token = token.strip()",
            test_output="4 passed in 0.12s",
            final_output="Fixed token parser by stripping whitespace. All unit tests pass.",
        )
        self.assertTrue(res["is_complete"])
        self.assertEqual(res["status"], "TASK_COMPLETE")
        self.assertEqual(len(res["missing_criteria"]), 0)

    @patch("lib.done_validator.query_laya")
    def test_incomplete_task_with_failing_tests(self, mock_query):
        mock_query.return_value = {
            "status": {"choice": "needs_more_work", "answer_confidence": 0.85},
            "has_failing_tests": {"noul": 0.95},
            "satisfies_goal": {"noul": 0.30},
        }
        res = validate_task_completion(
            task_goal="Fix bug in auth token parser",
            git_diff="diff --git a/auth.py b/auth.py\n+ syntax error here",
            test_output="FAILED tests/auth_test.py::test_parse_token - AssertionError",
            final_output="Done with the changes.",
        )
        self.assertFalse(res["is_complete"])
        self.assertEqual(res["status"], "NEEDS_MORE_WORK")
        self.assertIn("Failing tests or unresolved errors detected", res["missing_criteria"])


if __name__ == "__main__":
    unittest.main()
