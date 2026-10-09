import unittest
import tempfile
import shutil
from pathlib import Path
from lib.action_cache import (
    cache_action_sequence,
    lookup_action_cache,
    is_idempotent_action,
    get_workspace_state_hash,
    clear_cache,
)


class TestActionCache(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        clear_cache(self.tmp_dir)

    def tearDown(self):
        clear_cache(self.tmp_dir)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_idempotent_checks(self):
        self.assertTrue(is_idempotent_action("view_file", {"AbsolutePath": "README.md"}))
        self.assertTrue(is_idempotent_action("run_command", {"CommandLine": "pytest tests/auth_test.py"}))
        self.assertTrue(is_idempotent_action("run_command", {"CommandLine": "git status"}))

        # Mutating actions rejected
        self.assertFalse(is_idempotent_action("replace_file_content", {}))
        self.assertFalse(is_idempotent_action("write_to_file", {}))
        self.assertFalse(is_idempotent_action("run_command", {"CommandLine": "git commit -m 'feat'"}))
        self.assertFalse(is_idempotent_action("run_command", {"CommandLine": "rm -rf /tmp/foo"}))

    def test_cache_and_lookup_exact(self):
        actions = [
            {"tool": "run_command", "args": {"CommandLine": "pytest -q"}},
        ]
        intent = "Run all unit tests"
        ok = cache_action_sequence(intent, actions, workspace_root=self.tmp_dir)
        self.assertTrue(ok)

        hit = lookup_action_cache("Run all unit tests", workspace_root=self.tmp_dir)
        self.assertIsNotNone(hit)
        self.assertTrue(hit["cache_hit"])
        self.assertEqual(hit["match_type"], "exact")
        self.assertEqual(len(hit["actions"]), 1)

    def test_cache_rejects_mutating_actions(self):
        bad_actions = [
            {"tool": "write_to_file", "args": {"TargetFile": "a.txt", "CodeContent": "hello"}},
        ]
        ok = cache_action_sequence("Create file", bad_actions, workspace_root=self.tmp_dir)
        self.assertFalse(ok)

        hit = lookup_action_cache("Create file", workspace_root=self.tmp_dir)
        self.assertIsNone(hit)


if __name__ == "__main__":
    unittest.main()
