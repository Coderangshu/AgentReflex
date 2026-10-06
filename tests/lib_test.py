import unittest
from unittest.mock import patch
from lib.compaction import score_message_retention, should_prune
from lib.judge import judge_test_coverage
from lib.skill_picker import pick_skill
from lib.file_ranker import rank_files
from lib.review_gate import review_diff
from lib.browser_nav import select_element
from lib.rule_enforcer import check_violations


class TestSys1HelperLib(unittest.TestCase):

    @patch("lib.compaction.query_laya")
    def test_compaction(self, mock_query):
        mock_query.return_value = {
            "keep": {"noul": 0.1},
            "is_noise": {"noul": 0.9},
        }
        res = score_message_retention("Step 1/1000 Downloading 1%...")
        self.assertTrue(res["should_prune"])
        self.assertTrue(should_prune("Step 1/1000 Downloading 1%..."))

    @patch("lib.judge.query_laya")
    def test_judge(self, mock_query):
        mock_query.return_value = {
            "needs_tests": {"noul": 0.85},
            "is_test_file": {"noul": 0.05},
        }
        res = judge_test_coverage("def critical_payment_charge(): pass")
        self.assertTrue(res["requires_verification"])
        self.assertGreaterEqual(res["uncovered_risk"], 0.7)

    @patch("lib.skill_picker.query_laya")
    def test_skill_picker(self, mock_query):
        mock_query.return_value = {
            "route": {"choice": "fast_explore", "answer_confidence": 0.82}
        }
        res = pick_skill("find all payment controller files")
        self.assertEqual(res["skill"], "fast_explore")
        self.assertTrue(res["is_recommended"])

    @patch("lib.file_ranker.query_laya")
    def test_file_ranker(self, mock_query):
        mock_query.side_effect = [
            {"relevant": {"noul": 0.9}},
            {"relevant": {"noul": 0.2}},
        ]
        paths = ["controllers/payment.py", "README.md"]
        ranked = rank_files("process stripe credit card payment", paths, top_k=2)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0][0], "controllers/payment.py")
        self.assertGreater(ranked[0][1], ranked[1][1])

    @patch("lib.review_gate.query_laya")
    def test_review_gate_rejection(self, mock_query):
        mock_query.return_value = {
            "breaking_api": {"noul": 0.1},
            "security_injection": {"noul": 0.85},
            "secrets_leak": {"noul": 0.0},
            "perf_regression": {"noul": 0.0},
            "test_gap": {"noul": 0.1},
            "unhandled_exceptions": {"noul": 0.0},
            "contract_violation": {"noul": 0.0},
        }
        res = review_diff("cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')")
        self.assertFalse(res["passed"])
        self.assertEqual(res["recommendation"], "REJECT / REQUIRE CHANGES")
        self.assertIn(("security_injection", 0.85), res["flagged_risks"])

    @patch("lib.browser_nav.query_laya")
    def test_browser_nav(self, mock_query):
        mock_query.return_value = {
            "best_element": {"choice": "opt_0", "answer_confidence": 0.88}
        }
        candidates = [
            {"id": "submit-btn", "tag": "button", "text": "Submit Payment", "role": "button"},
            {"id": "cancel-btn", "tag": "button", "text": "Cancel", "role": "button"},
        ]
        res = select_element("Submit user payment details", candidates)
        self.assertEqual(res["choice_key"], "opt_0")
        self.assertEqual(res["winner"]["id"], "submit-btn")

    @patch("lib.rule_enforcer.query_laya")
    def test_rule_enforcer(self, mock_query):
        mock_query.return_value = {
            "violates": {"noul": 0.95}
        }
        res = check_violations("api_key = 'sk_live_1234567890'")
        self.assertTrue(res["violates"])
        self.assertIn("AgentReflex rule guardrail triggered", res["reason"])


if __name__ == "__main__":
    unittest.main()
