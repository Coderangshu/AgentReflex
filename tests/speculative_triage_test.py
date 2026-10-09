import unittest
from lib.speculative_triage import triage_task, format_triage_tags


class TestSpeculativeTriage(unittest.TestCase):
    def test_empty_prompt(self):
        res = triage_task("")
        self.assertEqual(res["task_type"], "exploration")
        self.assertEqual(res["tags"], [])
        self.assertIn("AgentReflex Triage:", format_triage_tags(res))

    def test_migration_and_auth_triage(self):
        prompt = (
            "Write a database migration for the user password authentication "
            "schema table to rename credentials."
        )
        res = triage_task(prompt)
        self.assertIn("task_type", res)
        self.assertTrue(res["needs_migration"])
        self.assertTrue(res["touches_auth"])
        self.assertIn("risk_level", res)
        self.assertTrue(len(res["tags"]) > 0)

        tag_str = format_triage_tags(res)
        self.assertTrue(tag_str.startswith("[AgentReflex Triage:"))
        self.assertIn("type:", tag_str)
        self.assertIn("db:migration", tag_str)
        self.assertIn("security:auth", tag_str)

    def test_doc_safe_task(self):
        prompt = "Fix a typo in the README markdown documentation."
        res = triage_task(prompt)
        self.assertIn("task_type", res)
        self.assertEqual(res.get("needs_migration"), False)


if __name__ == "__main__":
    unittest.main()
