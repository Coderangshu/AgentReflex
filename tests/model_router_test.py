import unittest
from lib.model_router import route_model, detect_agent_harness


class TestModelRouter(unittest.TestCase):
    def test_empty_prompt_fallback(self):
        res = route_model("")
        self.assertEqual(res["task_class"], "simple_inspect")
        self.assertEqual(res["model_tier"], "flash")
        self.assertEqual(res["reasoning_effort"], "low")

    def test_doc_typo_routes_to_flash_low_agy(self):
        res = route_model("Fix typo in the README markdown header documentation", harness="agy")
        self.assertEqual(res["task_class"], "doc_typo")
        self.assertEqual(res["model_tier"], "flash")
        self.assertEqual(res["recommended_model"], "Gemini 3.8 Flash")
        self.assertEqual(res["subagent_model"], "flash_lite")
        self.assertEqual(res["reasoning_effort"], "low")
        self.assertEqual(res["max_thinking_tokens"], 0)

    def test_doc_typo_routes_to_flash_low_claude(self):
        res = route_model("Fix typo in the README markdown header documentation", harness="claude")
        self.assertEqual(res["task_class"], "doc_typo")
        self.assertEqual(res["model_tier"], "flash")
        self.assertEqual(res["recommended_model"], "Claude 3.5 Haiku")
        self.assertEqual(res["subagent_model"], "haiku")
        self.assertEqual(res["reasoning_effort"], "low")

    def test_hard_debug_routes_to_frontier_high_agy(self):
        res = route_model("Debug intermittent deadlock and race condition in worker pool", harness="agy")
        self.assertEqual(res["task_class"], "hard_debug")
        self.assertEqual(res["model_tier"], "frontier")
        self.assertEqual(res["recommended_model"], "Gemini 3.1 Pro")
        self.assertEqual(res["subagent_model"], "pro")
        self.assertEqual(res["reasoning_effort"], "high")
        self.assertEqual(res["max_thinking_tokens"], 16384)

    def test_hard_debug_routes_to_frontier_xhigh_claude(self):
        res = route_model("Debug intermittent deadlock and race condition in worker pool", harness="claude")
        self.assertEqual(res["task_class"], "hard_debug")
        self.assertEqual(res["model_tier"], "frontier")
        self.assertIn("Claude", res["recommended_model"])
        self.assertEqual(res["subagent_model"], "opus")
        self.assertEqual(res["reasoning_effort"], "xhigh")

    def test_arch_design_effort_scales(self):
        prompt = "Design distributed fault-tolerant Raft consensus subsystem and state machine replication protocol"
        agy_res = route_model(prompt, harness="agy")
        claude_res = route_model(prompt, harness="claude")

        self.assertEqual(agy_res["task_class"], "arch_design")
        self.assertEqual(agy_res["reasoning_effort"], "high")
        self.assertEqual(agy_res["recommended_model"], "Gemini 3.1 Pro")

        self.assertEqual(claude_res["task_class"], "arch_design")
        self.assertEqual(claude_res["reasoning_effort"], "max")
        self.assertIn("Claude", claude_res["recommended_model"])

    def test_harness_detection(self):
        self.assertEqual(detect_agent_harness("agy"), "agy")
        self.assertEqual(detect_agent_harness("gemini"), "agy")
        self.assertEqual(detect_agent_harness("claude"), "claude")
        self.assertEqual(detect_agent_harness("anthropic"), "claude")


if __name__ == "__main__":
    unittest.main()
