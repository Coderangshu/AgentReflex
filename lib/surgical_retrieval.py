"""Surgical context retrieval engine (jevgrep) using Laya.

Chunks code files into windows or symbol blocks, scores each locally in ~30ms,
and extracts only the strictly necessary lines to minimize LLM token consumption.
"""

from __future__ import annotations
import hashlib
from typing import Union, List, Dict, Optional, Tuple
from pathlib import Path
from lib.client import query_laya

# In-memory manifest cache: (file_path_str, sha1_hex) -> list of chunks
_AST_CHUNK_CACHE: dict[tuple[str, str], list[dict]] = {}


def compute_content_hash(raw_bytes: bytes) -> str:
    """Compute SHA-1 hash for file content."""
    return hashlib.sha1(raw_bytes).hexdigest()


def clear_ast_cache():
    """Clear memory manifest cache for test isolation."""
    _AST_CHUNK_CACHE.clear()


# Language mapping from extension or shebang
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}

# Top-level AST node types representing cohesive functional blocks
AST_BOUNDARY_NODES = {
    "python": {
        "function_definition",
        "async_function_definition",
        "class_definition",
        "decorated_definition",
    },
    "rust": {
        "function_item",
        "impl_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "mod_item",
        "macro_definition",
    },
    "typescript": {
        "function_declaration",
        "method_definition",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
    },
    "tsx": {
        "function_declaration",
        "method_definition",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
    },
    "javascript": {
        "function_declaration",
        "method_definition",
        "class_declaration",
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "c": {
        "function_definition",
        "struct_specifier",
        "enum_specifier",
        "type_definition",
    },
    "cpp": {
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
        "template_declaration",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "method_declaration",
        "constructor_declaration",
    },
    "ruby": {
        "method",
        "singleton_method",
        "class",
        "module",
    },
    "php": {
        "function_definition",
        "class_declaration",
        "method_declaration",
        "interface_declaration",
        "trait_declaration",
    },
    "swift": {
        "function_declaration",
        "class_declaration",
        "struct_declaration",
        "protocol_declaration",
        "extension_declaration",
    },
    "kotlin": {
        "function_declaration",
        "class_declaration",
        "object_declaration",
    },
}


def detect_language(file_path: Path) -> str:
    """Automatically detect programming language from extension or shebang."""
    ext = file_path.suffix.lower()
    if ext in LANGUAGE_EXTENSIONS:
        return LANGUAGE_EXTENSIONS[ext]

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline().strip()
            if first_line.startswith("#!"):
                lower = first_line.lower()
                if "python" in lower:
                    return "python"
                if "node" in lower or "bun" in lower:
                    return "javascript"
                if "bash" in lower or "sh" in lower:
                    return "bash"
    except Exception:
        pass

    return "unknown"


def _chunk_sliding_window(
    lines: list[str],
    file_path: Path,
    window_lines: int = 30,
    overlap: int = 5,
) -> list[dict]:
    """Fallback sliding window chunking for non-code or unsupported syntax."""
    chunks = []
    total = len(lines)
    step = max(1, window_lines - overlap)

    for start in range(0, total, step):
        end = min(total, start + window_lines)
        chunk_text = "\n".join(lines[start:end])
        chunks.append({
            "file": str(file_path),
            "start_line": start + 1,
            "end_line": end,
            "content": chunk_text,
            "chunk_type": "sliding_window",
        })
        if end >= total:
            break

    return chunks


def _get_ast_parser(language: str):
    """Retrieve tree-sitter parser using modern tree_sitter_language_pack with fallback."""
    try:
        from tree_sitter_language_pack import get_parser
        return get_parser(language)
    except Exception:
        pass

    try:
        from tree_sitter_languages import get_parser
        return get_parser(language)
    except Exception:
        return None


def _chunk_ast(
    raw_bytes: bytes,
    lines: list[str],
    file_path: Path,
    language: str,
    max_chunk_lines: int = 70,
) -> list[dict]:
    """Extract complete syntactic blocks (functions, classes, impls) via AST."""
    try:
        parser = _get_ast_parser(language)
        if parser is None:
            return []
        tree = parser.parse(raw_bytes)
    except Exception:
        return []

    target_types = AST_BOUNDARY_NODES.get(language, set())
    if not target_types:
        return []

    ast_chunks = []
    covered_ranges = []

    def visit(node):
        if node.type in target_types:
            s_line = node.start_point[0] + 1
            e_line = node.end_point[0] + 1

            # Avoid tiny 1-line noise or comments
            if e_line >= s_line:
                node_lines_count = e_line - s_line + 1

                # If block is reasonably sized, keep intact
                if node_lines_count <= max_chunk_lines:
                    chunk_text = "\n".join(lines[s_line - 1:e_line])
                    ast_chunks.append({
                        "file": str(file_path),
                        "start_line": s_line,
                        "end_line": e_line,
                        "content": chunk_text,
                        "chunk_type": f"ast_{node.type}",
                    })
                    covered_ranges.append((s_line, e_line))
                    return  # Do not recurse into already captured sub-methods

        # Recurse children to find nested functions/classes
        for child in node.children:
            visit(child)

    visit(tree.root_node)

    # Sort chunks by starting line
    ast_chunks.sort(key=lambda x: x["start_line"])
    return ast_chunks


def chunk_file(
    file_path: Path,
    window_lines: int = 30,
    overlap: int = 5,
    use_cache: bool = True,
) -> list[dict]:
    """Chunk a file into semantic units with SHA-1 content hash manifest memoization.

    1. Checks (file_path, content_hash) in cache to skip redundant AST parsing.
    2. Detects file language automatically.
    3. Uses tree-sitter AST to extract complete function/class/impl boundaries.
    4. Falls back to sliding windows for non-code files, syntax errors, or unhandled gaps.
    """
    if not file_path.exists() or file_path.is_dir():
        return []

    try:
        raw_bytes = file_path.read_bytes()
    except Exception:
        return []

    if not raw_bytes.strip():
        return []

    file_str = str(file_path.resolve())
    c_hash = compute_content_hash(raw_bytes)
    cache_key = (file_str, c_hash)

    if use_cache and cache_key in _AST_CHUNK_CACHE:
        return _AST_CHUNK_CACHE[cache_key]

    lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
    if not lines:
        return []

    lang = detect_language(file_path)
    if lang in AST_BOUNDARY_NODES:
        ast_chunks = _chunk_ast(raw_bytes, lines, file_path, lang)
        if ast_chunks:
            if use_cache:
                _AST_CHUNK_CACHE[cache_key] = ast_chunks
            return ast_chunks

    # Fallback: Sliding window for plain text, markdown, config, or unparsed code
    sliding_chunks = _chunk_sliding_window(lines, file_path, window_lines=window_lines, overlap=overlap)
    if use_cache:
        _AST_CHUNK_CACHE[cache_key] = sliding_chunks
    return sliding_chunks


def score_snippet(query: str, snippet: dict) -> float:
    """Score how relevant a specific snippet is to the target query."""
    state = f"Query: {query}\nFile: {snippet['file']}:{snippet['start_line']}-{snippet['end_line']}\n\n{snippet['content']}"[:1200]
    questions = {
        "relevant": {
            "type": "noul",
            "instructions": f"Does this code snippet directly answer, define, or implement logic for: '{query}'?",
        }
    }
    res = query_laya(state, questions)
    return res.get("relevant", {}).get("noul", 0.0)


def surgical_search(
    query: str,
    target_paths: list[str | Path],
    max_snippets: int = 3,
    window_lines: int = 30,
) -> list[dict]:
    """Perform surgical search across target files, returning top scored code snippets."""
    all_chunks = []
    for p in target_paths:
        path_obj = Path(p)
        if path_obj.is_file():
            all_chunks.extend(chunk_file(path_obj, window_lines=window_lines))
        elif path_obj.is_dir():
            valid_exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".sql", ".rs", ".go"}
            for sub_file in path_obj.rglob("*"):
                if (
                    sub_file.is_file()
                    and sub_file.suffix in valid_exts
                    and "node_modules" not in sub_file.parts
                    and ".git" not in sub_file.parts
                    and ".venv" not in sub_file.parts
                ):
                    all_chunks.extend(chunk_file(sub_file, window_lines=window_lines))

    scored = []
    for chunk in all_chunks:
        score = score_snippet(query, chunk)
        if score > 0.30:  # Base filter
            scored.append({
                "file": chunk["file"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "score": round(score, 4),
                "snippet": chunk["content"],
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:max_snippets]
