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

    def test_derived_skills(self):
        # 1. Review diff -> review_gate
        rev_res = route_model("review my git diff for security risks before opening PR")
        self.assertEqual(rev_res["recommended_skill"], "review_gate")
        self.assertIn("reflex_review_gate", rev_res["skill_tools"])

        # 2. Inspect codebase -> fast_explore
        insp_res = route_model("find all payment gateway controller files")
        self.assertEqual(insp_res["recommended_skill"], "fast_explore")
        self.assertIn("reflex_fast_explore", insp_res["skill_tools"])

        # 3. Explicit compaction -> compact
        comp_res = route_model("please compact conversation memory and prune logs")
        self.assertEqual(comp_res["recommended_skill"], "compact")
        self.assertIn("reflex_compact", comp_res["skill_tools"])

        # 4. Routine doc typo -> no skill needed
        typo_res = route_model("Fix typo in README header")
        self.assertIsNone(typo_res["recommended_skill"])
        self.assertEqual(typo_res["skill_tools"], [])

    def test_harness_detection(self):
        self.assertEqual(detect_agent_harness("agy"), "agy")
        self.assertEqual(detect_agent_harness("gemini"), "agy")
        self.assertEqual(detect_agent_harness("claude"), "claude")
        self.assertEqual(detect_agent_harness("anthropic"), "claude")


if __name__ == "__main__":
    unittest.main()
