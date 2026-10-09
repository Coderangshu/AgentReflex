import unittest
from pathlib import Path
from lib.param_validator import validate_tool_call


class TestParamValidator(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_valid_commands_and_tools(self):
        res = validate_tool_call(
            "run_command",
            {"CommandLine": "git checkout -b feature/login origin/main"},
        )
        self.assertTrue(res["is_valid"])

        res2 = validate_tool_call(
            "view_file",
            {"AbsolutePath": str(self.root / "README.md")},
        )
        self.assertTrue(res2["is_valid"])

    def test_hallucinated_cli_flags(self):
        res = validate_tool_call(
            "run_command",
            {"CommandLine": "git checkout -b --remote-track origin/main"},
        )
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_type"], "hallucinated_cli_flag")
        self.assertIn("use 'git checkout --track", res["suggestion"])

        res_npm = validate_tool_call(
            "run_command",
            {"CommandLine": "npm install --save-dev-only lodash"},
        )
        self.assertFalse(res_npm["is_valid"])
        self.assertEqual(res_npm["error_type"], "hallucinated_cli_flag")

    def test_missing_required_params(self):
        res = validate_tool_call(
            "replace_file_content",
            {"TargetFile": "some_file.py"},  # Missing TargetContent and ReplacementContent
        )
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_type"], "missing_required_param")

    def test_nonexistent_read_path(self):
        res = validate_tool_call(
            "view_file",
            {"AbsolutePath": str(self.root / "nonexistent_file_xyz_123.py")},
        )
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_type"], "nonexistent_read_path")

    def test_nonexistent_edit_target(self):
        res = validate_tool_call(
            "replace_file_content",
            {
                "TargetFile": str(self.root / "imaginary_code_path.py"),
                "TargetContent": "a",
                "ReplacementContent": "b",
            },
        )
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_type"], "nonexistent_edit_target")


if __name__ == "__main__":
    unittest.main()
