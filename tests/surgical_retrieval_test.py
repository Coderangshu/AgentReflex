import unittest
from pathlib import Path
import tempfile
from lib.surgical_retrieval import chunk_file, detect_language


class TestSurgicalRetrievalAST(unittest.TestCase):

    def test_detect_language(self):
        self.assertEqual(detect_language(Path("test.py")), "python")
        self.assertEqual(detect_language(Path("kernel.rs")), "rust")
        self.assertEqual(detect_language(Path("app.tsx")), "tsx")
        self.assertEqual(detect_language(Path("server.go")), "go")
        self.assertEqual(detect_language(Path("main.c")), "c")
        self.assertEqual(detect_language(Path("notes.txt")), "unknown")

    def test_rust_ast_chunking(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".rs", delete=False) as tf:
            tf.write("""pub struct Scheduler {
    quantum: u64,
}

impl Scheduler {
    pub fn schedule(&self) {
        // Round robin
    }
}

fn switch_context() {
    // Assembly swap
}
""")
            tf.flush()
            chunks = chunk_file(Path(tf.name))
            self.assertEqual(len(chunks), 3)
            self.assertEqual(chunks[0]["chunk_type"], "ast_struct_item")
            self.assertEqual(chunks[1]["chunk_type"], "ast_impl_item")
            self.assertEqual(chunks[2]["chunk_type"], "ast_function_item")
            self.assertEqual(chunks[0]["start_line"], 1)
            self.assertEqual(chunks[0]["end_line"], 3)

    def test_python_ast_chunking(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as tf:
            tf.write("""class User:
    def __init__(self, name):
        self.name = name

def authenticate():
    return True
""")
            tf.flush()
            chunks = chunk_file(Path(tf.name))
            self.assertGreaterEqual(len(chunks), 2)
            types = [c["chunk_type"] for c in chunks]
            self.assertIn("ast_class_definition", types)
            self.assertIn("ast_function_definition", types)

    def test_markdown_fallback_sliding_window(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tf:
            lines = [f"Documentation line {i}" for i in range(1, 80)]
            tf.write("\n".join(lines))
            tf.flush()
            chunks = chunk_file(Path(tf.name), window_lines=30, overlap=5)
            self.assertGreater(len(chunks), 1)
            for c in chunks:
                self.assertEqual(c["chunk_type"], "sliding_window")


if __name__ == "__main__":
    unittest.main()
