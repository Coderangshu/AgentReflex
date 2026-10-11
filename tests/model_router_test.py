import unittest
from lib.model_router import route_model, ROUTING_POLICIES


class TestModelRouter(unittest.TestCase):
    def test_empty_prompt_fallback(self):
        res = route_model("")
        self.assertEqual(res["task_class"], "simple_inspect")
        self.assertEqual(res["model_tier"], "flash")
        self.assertEqual(res["reasoning_effort"], "low")

    def test_doc_typo_routes_to_flash_none(self):
        res = route_model("Fix typo in the README markdown header documentation")
        self.assertEqual(res["task_class"], "doc_typo")
        self.assertEqual(res["model_tier"], "flash")
        self.assertEqual(res["reasoning_effort"], "none")
        self.assertEqual(res["max_thinking_tokens"], 0)
        self.assertEqual(res["subagent_model"], "flash_lite")

    def test_hard_debug_routes_to_frontier_high(self):
        res = route_model("Debug intermittent deadlock and race condition in worker pool")
        self.assertEqual(res["task_class"], "hard_debug")
        self.assertEqual(res["model_tier"], "frontier")
        self.assertEqual(res["reasoning_effort"], "high")
        self.assertEqual(res["max_thinking_tokens"], 8192)
        self.assertEqual(res["subagent_model"], "pro")

    def test_review_audit_routes_to_standard_medium(self):
        res = route_model("Review git diff for security vulnerabilities before merge")
        self.assertEqual(res["task_class"], "review_audit")
        self.assertEqual(res["model_tier"], "standard")
        self.assertEqual(res["reasoning_effort"], "medium")
        self.assertEqual(res["subagent_model"], "pro")


if __name__ == "__main__":
    unittest.main()
