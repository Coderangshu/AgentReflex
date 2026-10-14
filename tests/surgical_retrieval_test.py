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

    def test_ruby_ast_chunking(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".rb", delete=False) as tf:
            tf.write("""class PaymentGateway
  def process_charge(amount)
    true
  end
end

def refund(id)
  false
end
""")
            tf.flush()
            chunks = chunk_file(Path(tf.name))
            self.assertGreaterEqual(len(chunks), 2)
            types = [c["chunk_type"] for c in chunks]
            self.assertIn("ast_class", types)
            self.assertTrue(any("method" in t for t in types))

    def test_php_ast_chunking(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".php", delete=False) as tf:
            tf.write("""<?php
class OrderService {
    public function createOrder($cart) {
        return 1;
    }
}

function sendNotification($email) {
    return true;
}
""")
            tf.flush()
            chunks = chunk_file(Path(tf.name))
            self.assertGreaterEqual(len(chunks), 2)
            types = [c["chunk_type"] for c in chunks]
            self.assertIn("ast_class_declaration", types)
            self.assertTrue(any("function" in t or "method" in t for t in types))

    def test_markdown_fallback_sliding_window(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tf:
            lines = [f"Documentation line {i}" for i in range(1, 80)]
            tf.write("\n".join(lines))
            tf.flush()
            chunks = chunk_file(Path(tf.name), window_lines=30, overlap=5)
            self.assertGreater(len(chunks), 1)
            for c in chunks:
                self.assertEqual(c["chunk_type"], "sliding_window")

    def test_content_hash_manifest_caching(self):
        from lib.surgical_retrieval import clear_ast_cache, _AST_CHUNK_CACHE, compute_content_hash
        clear_ast_cache()
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as tf:
            code1 = "def fn_one():\n    return 1\n"
            tf.write(code1)
            tf.flush()
            path = Path(tf.name)

            # First run: parses AST and populates cache
            chunks1 = chunk_file(path)
            h1 = compute_content_hash(code1.encode("utf-8"))
            cache_key1 = (str(path.resolve()), h1)
            self.assertIn(cache_key1, _AST_CHUNK_CACHE)
            self.assertEqual(len(chunks1), 1)

            # Second run with same file content: serves directly from manifest cache (identical object)
            chunks2 = chunk_file(path)
            self.assertIs(chunks1, chunks2)

            # Edit file: modifies SHA-1 hash and triggers new parse
            code2 = "def fn_one():\n    return 1\n\ndef fn_two():\n    return 2\n"
            tf.seek(0)
            tf.write(code2)
            tf.truncate()
            tf.flush()

            chunks3 = chunk_file(path)
            h2 = compute_content_hash(code2.encode("utf-8"))
            cache_key2 = (str(path.resolve()), h2)
            self.assertIn(cache_key2, _AST_CHUNK_CACHE)
            self.assertNotEqual(h1, h2)
            self.assertEqual(len(chunks3), 2)


if __name__ == "__main__":
    unittest.main()
