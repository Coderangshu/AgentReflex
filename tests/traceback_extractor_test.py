import unittest
import tempfile
import os
from pathlib import Path
from lib.traceback_extractor import (
    extract_traceback_frames,
    extract_culprit_frame,
    is_external_frame,
)


class TestTracebackExtractor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_is_external_frame(self):
        self.assertTrue(is_external_frame("/Users/user/project/.venv/lib/python3.11/site-packages/pkg/foo.py"))
        self.assertTrue(is_external_frame("/app/node_modules/lodash/index.js"))
        self.assertTrue(is_external_frame("/root/.cargo/registry/src/index.crates.io/tokio/src/lib.rs"))
        self.assertTrue(is_external_frame("<string>"))
        self.assertFalse(is_external_frame("/Users/user/project/src/auth.py"))
        self.assertFalse(is_external_frame("src/components/button.tsx"))

    def test_python_traceback_extraction(self):
        # Create dummy repo file
        py_file = self.root / "services" / "auth.py"
        py_file.parent.mkdir(parents=True, exist_ok=True)
        py_file.write_text("def login(): pass\n")

        traceback_text = f"""
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/pytest/__init__.py", line 120, in pytest_runtest
    res = hook()
  File "{py_file}", line 42, in login
    raise ValueError("Invalid token")
ValueError: Invalid token
"""
        frames = extract_traceback_frames(traceback_text, cwd=str(self.root))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["file"], str(py_file.resolve()))
        self.assertEqual(frames[0]["line"], 42)
        self.assertEqual(frames[0]["language"], "python")

        culprit = extract_culprit_frame(traceback_text, cwd=str(self.root))
        self.assertIsNotNone(culprit)
        self.assertEqual(culprit["file"], str(py_file.resolve()))
        self.assertEqual(culprit["line"], 42)

    def test_rust_error_extraction(self):
        rs_file = self.root / "src" / "parser.rs"
        rs_file.parent.mkdir(parents=True, exist_ok=True)
        rs_file.write_text("fn parse() {}\n")

        rust_output = f"""
error[E0308]: mismatched types
  --> src/parser.rs:24:9
   |
24 |         expected_tokens
   |         ^^^^^^^^^^^^^^^ expected `bool`, found `usize`
"""
        culprit = extract_culprit_frame(rust_output, cwd=str(self.root))
        self.assertIsNotNone(culprit)
        self.assertEqual(culprit["file"], str(rs_file.resolve()))
        self.assertEqual(culprit["line"], 24)
        self.assertEqual(culprit["language"], "rust")

    def test_typescript_jest_extraction(self):
        ts_file = self.root / "src" / "routes" / "api.ts"
        ts_file.parent.mkdir(parents=True, exist_ok=True)
        ts_file.write_text("export function route() {}\n")

        node_output = f"""
FAIL src/routes/api.test.ts
  ● API Tests › should authenticate user

    TypeError: Cannot read properties of undefined (reading 'headers')

      at Object.<anonymous> (/app/node_modules/express/lib/router/index.js:12:5)
      at handleRequest ({ts_file}:55:18)
"""
        culprit = extract_culprit_frame(node_output, cwd=str(self.root))
        self.assertIsNotNone(culprit)
        self.assertEqual(culprit["file"], str(ts_file.resolve()))
        self.assertEqual(culprit["line"], 55)
        self.assertEqual(culprit["language"], "javascript")

    def test_go_panic_extraction(self):
        go_file = self.root / "worker" / "task.go"
        go_file.parent.mkdir(parents=True, exist_ok=True)
        go_file.write_text("package worker\n")

        go_output = f"""
panic: runtime error: slice bounds out of range [:10] with capacity 0

goroutine 1 [running]:
main.runTask(...)
	worker/task.go:88 +0x3a
"""
        culprit = extract_culprit_frame(go_output, cwd=str(self.root))
        self.assertIsNotNone(culprit)
        self.assertEqual(culprit["file"], str(go_file.resolve()))
        self.assertEqual(culprit["line"], 88)
        self.assertEqual(culprit["language"], "go")

    def test_cpp_error_extraction(self):
        cpp_file = self.root / "src" / "engine.cpp"
        cpp_file.parent.mkdir(parents=True, exist_ok=True)
        cpp_file.write_text("int main() { return 0; }\n")

        cpp_output = f"""
src/engine.cpp:112:5: error: use of undeclared identifier 'compute_buffer'
    compute_buffer->sync();
    ^
"""
        culprit = extract_culprit_frame(cpp_output, cwd=str(self.root))
        self.assertIsNotNone(culprit)
        self.assertEqual(culprit["file"], str(cpp_file.resolve()))
        self.assertEqual(culprit["line"], 112)
        self.assertEqual(culprit["language"], "cpp")

    def test_no_error_output(self):
        clean_output = "Ran 84 tests in 4.120s\nOK\n"
        culprit = extract_culprit_frame(clean_output, cwd=str(self.root))
        self.assertIsNone(culprit)


if __name__ == "__main__":
    unittest.main()
